"""Traceability engine: Requirement -> Spec -> AC -> Scenario -> Test case -> Script -> Execution.

Builds the full matrix, coverage metrics, uncovered requirements, outdated scripts and change impact sets
from the artifacts on disk (never from AI output alone).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.artifact_manager import ArtifactManager
from core.config import settings
from core.models import ExecutionRun, FeatureSpec, ImpactSet, TestResult
from versioning.version_manager import VersionManager


def load_executions() -> list[ExecutionRun]:
    d = settings().path("executions")
    runs = []
    for p in sorted(d.glob("EXEC-*.json")):
        try:
            runs.append(ExecutionRun.model_validate(json.loads(p.read_text(encoding="utf-8"))))
        except (ValueError, json.JSONDecodeError):
            continue
    return runs


def latest_results(runs: list[ExecutionRun]) -> dict[str, tuple[TestResult, str]]:
    """automation_id -> (latest result, execution id)."""
    out: dict[str, tuple[TestResult, str]] = {}
    for run in runs:
        for r in run.results:
            if r.automation_id:
                out[r.automation_id] = (r, run.id)
    return out


def impact_of(spec_id: str, ac_ids: set[str]) -> ImpactSet:
    am = ArtifactManager()
    scenarios = am.load(spec_id, "scenarios")
    cases = am.load(spec_id, "test_cases")
    automation = am.load(spec_id, "automation")
    imp = ImpactSet(acceptance_criteria=sorted(ac_ids))
    if scenarios:
        imp.scenarios = sorted(s.id for s in scenarios.scenarios if set(s.ac_ids) & ac_ids and s.status == "active")
    if cases:
        active = [t for t in cases.test_cases if t.status == "active"]
        imp.test_cases = sorted(t.id for t in active if set(t.ac_ids) & ac_ids)
        imp.unaffected_test_cases = sorted(t.id for t in active if not set(t.ac_ids) & ac_ids)
    if automation:
        imp.scripts = sorted(f"{r.automation_id} ({r.file}::{r.function})" for r in automation.scripts
                             if set(r.ac_ids) & ac_ids)
    return imp


class TraceabilityEngine:
    def __init__(self) -> None:
        self.am = ArtifactManager()
        self.vm = VersionManager()

    def requirement_ids(self) -> list[str]:
        return sorted({p.stem.upper() for p in self.am.requirement_files()})

    def build(self) -> dict[str, Any]:
        runs = load_executions()
        latest = latest_results(runs)
        rows: list[dict[str, Any]] = []
        specs: list[dict[str, Any]] = []
        outdated: list[dict[str, Any]] = []
        reg = self.am.registry()["specs"]
        covered_reqs: set[str] = set()
        totals = {"ac": 0, "ac_with_tc": 0, "tc": 0, "tc_automated": 0, "scripts": 0, "scripts_executed": 0,
                  "scripts_passed": 0}

        for spec_id, entry in sorted(reg.items()):
            try:
                spec: FeatureSpec = self.am.load_spec(spec_id)
            except FileNotFoundError:
                continue
            scenarios = self.am.load(spec_id, "scenarios")
            cases = self.am.load(spec_id, "test_cases")
            automation = self.am.load(spec_id, "automation")
            validation = self.am.load(spec_id, "validation")
            approved = self.vm.latest_approved_version(spec_id)
            approvals = {s: self.vm.is_approved(spec_id, s) for s in ("spec", "test_cases", "scripts")}
            specs.append({
                "spec_id": spec_id, "title": spec.title, "feature": spec.feature,
                "requirements": spec.requirement_ids, "version": spec.version, "status": spec.status.value,
                "approved_version": approved, "approved_versions": self.vm.approved_versions(spec_id),
                "superseded_versions": entry.get("superseded_versions", []), "approvals": approvals,
                "ac_count": len(spec.acceptance_criteria),
                "validation": {"passed": validation.passed if validation else None,
                               "errors": len(validation.errors) if validation else 0,
                               "warnings": len(validation.warnings) if validation else 0,
                               "findings": [f.model_dump() for f in validation.findings] if validation else []},
            })
            if spec.status.value == "APPROVED" or approved:
                covered_reqs |= set(spec.requirement_ids)
            ac_now = {a.id: a.content_hash() for a in spec.acceptance_criteria}
            scripts = {r.test_case_id: r for r in (automation.scripts if automation else [])}
            for r in (automation.scripts if automation else []):
                stale = [a for a in r.ac_ids if ac_now.get(a) != r.ac_hash]
                if stale or any(a not in ac_now for a in r.ac_ids):
                    outdated.append({"spec_id": spec_id, "automation_id": r.automation_id,
                                     "test_case_id": r.test_case_id, "file": r.file, "ac_ids": r.ac_ids,
                                     "script_spec_version": r.spec_version, "current_spec_version": spec.version,
                                     "reason": "acceptance criterion changed after the script was generated"})
            for ac in spec.acceptance_criteria:
                totals["ac"] += 1
                tcs = [t for t in (cases.test_cases if cases else []) if ac.id in t.ac_ids and t.status == "active"]
                if tcs:
                    totals["ac_with_tc"] += 1
                if not tcs:
                    rows.append(self._row(spec, ac.id, ac.title, None, None, None, None))
                for t in tcs:
                    sc = next((s for s in (scenarios.scenarios if scenarios else []) if s.id == t.scenario_id), None)
                    rec = scripts.get(t.id)
                    res = latest.get(rec.automation_id) if rec else None
                    rows.append(self._row(spec, ac.id, ac.title, sc.id if sc else t.scenario_id, t, rec, res,
                                          outdated=bool(rec and rec.ac_hash != ac.content_hash())))
            for t in (cases.test_cases if cases else []):
                if t.status != "active":
                    continue
                totals["tc"] += 1
                if t.id in scripts:
                    totals["tc_automated"] += 1
            for r in (automation.scripts if automation else []):
                totals["scripts"] += 1
                if r.automation_id in latest:
                    totals["scripts_executed"] += 1
                    if latest[r.automation_id][0].outcome == "passed":
                        totals["scripts_passed"] += 1

        req_ids = self.requirement_ids()
        uncovered = [r for r in req_ids if r not in covered_reqs]
        pct = lambda a, b: round(100.0 * a / b, 1) if b else 0.0  # noqa: E731
        coverage = {
            "requirements": {"total": len(req_ids), "covered": len(req_ids) - len(uncovered),
                             "pct": pct(len(req_ids) - len(uncovered), len(req_ids))},
            "acceptance_criteria": {"total": totals["ac"], "covered": totals["ac_with_tc"],
                                    "pct": pct(totals["ac_with_tc"], totals["ac"])},
            "automation": {"total": totals["tc"], "covered": totals["tc_automated"],
                           "pct": pct(totals["tc_automated"], totals["tc"])},
            "execution": {"total": totals["scripts"], "covered": totals["scripts_executed"],
                          "pct": pct(totals["scripts_executed"], totals["scripts"])},
            "pass_rate": {"total": totals["scripts_executed"], "covered": totals["scripts_passed"],
                          "pct": pct(totals["scripts_passed"], totals["scripts_executed"])},
        }
        return {"rows": rows, "specs": specs, "coverage": coverage, "uncovered_requirements": uncovered,
                "outdated_scripts": outdated, "executions": [self._run_summary(r) for r in runs]}

    @staticmethod
    def _row(spec: FeatureSpec, ac_id: str, ac_title: str, sc_id: str | None, tc: Any, rec: Any,
             res: tuple[TestResult, str] | None, outdated: bool = False) -> dict[str, Any]:
        return {
            "requirement": ", ".join(spec.requirement_ids), "spec_id": spec.id, "spec_version": spec.version,
            "ac_id": ac_id, "ac_title": ac_title, "scenario_id": sc_id or "",
            "test_case_id": tc.id if tc else "", "test_case_title": tc.title if tc else "",
            "channel": tc.channel if tc else "", "priority": tc.priority if tc else "",
            "automation_id": rec.automation_id if rec else "",
            "script": f"{rec.file}::{rec.function}" if rec else "",
            "execution_id": res[1] if res else "", "outcome": res[0].outcome if res else "not run",
            "outdated": outdated,
        }

    @staticmethod
    def _run_summary(run: ExecutionRun) -> dict[str, Any]:
        return {"id": run.id, "started_at": run.started_at, "finished_at": run.finished_at,
                "environment": run.environment, "exit_code": run.exit_code, **run.summary,
                "selection": run.selection}


def write_traceability_markdown(data: dict[str, Any], path: Path) -> Path:
    lines = ["# Requirement Traceability Matrix", "",
             "| Requirement | Spec | AC | Scenario | Test case | Channel | Automation | Last result | Outdated |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in data["rows"]:
        lines.append(f"| {r['requirement']} | {r['spec_id']} v{r['spec_version']} | {r['ac_id']} | {r['scenario_id']} "
                     f"| {r['test_case_id']} | {r['channel'].upper()} | {r['automation_id']} | {r['outcome']} "
                     f"| {'yes' if r['outdated'] else ''} |")
    lines += ["", f"Uncovered requirements: {', '.join(data['uncovered_requirements']) or 'none'}",
              f"Outdated scripts: {len(data['outdated_scripts'])}"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
