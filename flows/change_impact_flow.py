"""Flow 5 - Specification Change Flow (re-entrant; advances as far as the human gates allow).

Specification Update -> Version Comparison -> Change Detection -> Impact Analysis -> [spec approval]
-> Impacted Test Identification -> Selective Regeneration (test design) -> [test case approval]
-> Selective Regeneration (scripts) -> [script approval] -> Re-Execution (impacted only) -> Updated Reports
"""

from __future__ import annotations

from crewai.flow.flow import Flow, listen, or_, router, start

from core.artifact_manager import ArtifactManager
from core.config import settings
from core.logger import audit, log
from core.models import ChangeRecord, SpecStatus
from core.state import ChangeImpactFlowState
from crews.analysis_crew import run_change_impact
from flows import stages
from reporting.dashboard import build_reports
from traceability.engine import impact_of
from versioning.spec_diff import diff_specs
from versioning.version_manager import VersionManager, bump

_NONE = "__none__"  # sentinel scope: regenerate nothing new, only retire obsolete artifacts
AUTOMATION_DONE = "AUTOMATION_REGENERATED"


class ChangeImpactFlow(Flow[ChangeImpactFlowState]):
    @start()
    def detect_change(self) -> str:
        am, vm = ArtifactManager(), VersionManager()
        sid = self.state.spec_id
        approved = vm.load_approved(sid)
        if approved is None:
            self.state.message = f"{sid} has no approved version yet - nothing to compare"
            return "none"
        open_rec = am.open_change(sid)
        if open_rec:
            self.state.change_id = open_rec.id
            self.state.message = f"Resuming {open_rec.id}"
            return open_rec.id
        working = am.load_spec(sid)
        changes, notes, indirect = diff_specs(approved, working)
        if not changes and not indirect and not notes:
            self.state.message = f"{sid}: working specification equals approved v{approved.version}"
            return "none"
        if working.version == approved.version:
            working.version = bump(approved.version, settings().section("versioning").get("bump_on_change", "minor"))
        working.status = SpecStatus.DRAFT
        am.save_spec(working)
        touched = {c.ac_id for c in changes} | indirect
        rec = ChangeRecord(id=am.next_change_id(), spec_id=sid, from_version=approved.version,
                           to_version=working.version, ac_changes=changes, other_changes=notes,
                           impact=impact_of(sid, touched))
        narrative = run_change_impact(rec)
        rec.analysis = "\n".join([narrative.headline, *narrative.highlights, *narrative.risks])
        rec.history.append(f"DETECTED: {len(changes)} AC change(s); version {rec.from_version} -> {rec.to_version}")
        am.save_change(rec)
        audit.write("change_detected", change_id=rec.id, spec_id=sid, acs=[c.ac_id for c in changes],
                    impacted_test_cases=rec.impact.test_cases, unaffected=rec.impact.unaffected_test_cases)
        self.state.change_id = rec.id
        return rec.id

    @router(detect_change)
    def route(self) -> str:
        return "progress" if self.state.change_id else "no_change"

    def _save(self, rec: ChangeRecord, note: str) -> None:
        rec.history.append(note)
        ArtifactManager().save_change(rec)
        log.info("%s: %s", rec.id, note)

    @listen("progress")
    def advance(self) -> None:
        am, vm = ArtifactManager(), VersionManager()
        sid = self.state.spec_id
        rec = next(c for c in am.load_changes(sid) if c.id == self.state.change_id)
        regen_acs = sorted({c.ac_id for c in rec.ac_changes if c.change != "removed"} |
                           set(rec.impact.acceptance_criteria) - {c.ac_id for c in rec.ac_changes
                                                                   if c.change == "removed"})
        self.state.impacted_ac_ids = regen_acs

        # ---- gate 1: the new spec version must be validated and approved by a human
        if rec.status == "PENDING_SPEC_APPROVAL":
            if not vm.spec_is_approved(sid):
                report = stages.validate_specification(sid)
                if not report.passed:
                    self.state.status = "NEEDS_CLARIFICATION"
                    self.state.next_action = "Resolve clarification_request.md and run `change` again"
                    return
                self.state.status = "AWAITING_SPEC_APPROVAL"
                self.state.next_action = (f"Review the diff in specifications/changes/{rec.id}.yaml, then: python main.py "
                                          f"approve {sid} --stage spec --by \"<your name>\"")
                return
            # ---- selective regeneration of test design (only impacted ACs)
            stages.design_tests(sid, regen_acs or [_NONE])
            cases = am.load(sid, "test_cases")
            rec.impact.test_cases = sorted(t.id for t in cases.test_cases
                                           if t.status == "active" and set(t.ac_ids) & set(regen_acs))
            rec.impact.unaffected_test_cases = sorted(t.id for t in cases.test_cases
                                                      if t.status == "active" and t.id not in rec.impact.test_cases)
            rec.status = "REGENERATED"
            self._save(rec, f"TEST_DESIGN_REGENERATED for {regen_acs}: {rec.impact.test_cases} "
                            f"(preserved: {len(rec.impact.unaffected_test_cases)})")

        self.state.impacted_test_cases = rec.impact.test_cases
        if rec.status == "REGENERATED":
            # ---- gate 2: regenerated test cases approved
            if not vm.is_approved(sid, "test_cases"):
                self.state.status = "AWAITING_TEST_CASE_APPROVAL"
                self.state.next_action = (f"Review the regenerated test cases {rec.impact.test_cases}, then: python main.py "
                                          f"approve {sid} --stage test_cases --by \"<your name>\"")
                return
            # ---- selective script regeneration
            if not vm.is_approved(sid, "scripts"):
                if AUTOMATION_DONE not in " ".join(rec.history):
                    report, staged = stages.generate_automation(sid, rec.impact.test_cases or [_NONE])
                    self._save(rec, f"{AUTOMATION_DONE}: {len(staged)} file(s) staged; validation "
                                    f"{'passed' if report.passed else 'FAILED'}")
                    if not report.passed:
                        self.state.status = "CODE_VALIDATION_FAILED"
                        self.state.next_action = "See code_validation_report.yaml"
                        return
                self.state.status = "AWAITING_SCRIPT_APPROVAL"
                self.state.next_action = (f"Review output/staging/{sid}/ then: python main.py approve {sid} --stage scripts "
                                          "--by \"<your name>\"")
                return
            # ---- re-execute impacted tests only
            runnable, problems = stages.runnable_specs([sid])
            if not runnable:
                self.state.status = "BLOCKED"
                self.state.next_action = "; ".join(problems)
                return
            if rec.impact.test_cases:
                run = stages.execute_tests([sid], test_case_ids=rec.impact.test_cases)
                stages.analyse_failures(run)
                self.state.execution_id = run.id
                note = f"RE-EXECUTED impacted test cases in {run.id}: {run.summary}"
            else:
                note = "NO_RE-EXECUTION: no active test case impacted (obsolete artifacts retired only)"
            rec.status = "EXECUTED"
            self._save(rec, note)
            self.state.artifacts.update(build_reports())
            self.state.status = "CHANGE_COMPLETE"

    @listen("no_change")
    def nothing(self) -> None:
        self.state.status = "NO_CHANGE"

    @listen(or_(advance, nothing))
    def finish(self) -> ChangeImpactFlowState:
        audit.write("flow", flow="change_impact", spec_id=self.state.spec_id, change_id=self.state.change_id,
                    status=self.state.status)
        return self.state
