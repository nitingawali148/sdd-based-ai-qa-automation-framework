"""Flow 3 - Automation Flow.

Approved Test Cases (gate) -> UI/API Classification -> Automation Design (UI + API agents)
-> Script Generation (staging) -> Code Validation -> Human Script Approval (gate, promotes scripts)
"""

from __future__ import annotations

from crewai.flow.flow import Flow, listen, or_, router, start

from core.artifact_manager import ArtifactManager
from core.logger import audit
from core.state import AutomationFlowState
from flows import stages
from versioning.version_manager import VersionManager


class AutomationFlow(Flow[AutomationFlowState]):
    @start()
    def check_test_cases_approved(self) -> bool:
        return VersionManager().is_approved(self.state.spec_id, "test_cases")

    @router(check_test_cases_approved)
    def test_case_gate(self) -> str:
        vm = VersionManager()
        if not vm.is_approved(self.state.spec_id, "test_cases"):
            self.state.gate("approved_test_cases", "BLOCKED", "test cases are not approved (or changed since)")
            return "blocked"
        self.state.gate("approved_test_cases", "PASSED")
        if vm.is_approved(self.state.spec_id, "scripts") and not self.state.only_test_case_ids:
            return "already_approved"
        return "automate"

    @listen("automate")
    def classify(self) -> None:
        cases = ArtifactManager().load(self.state.spec_id, "test_cases")
        scope = set(self.state.only_test_case_ids)
        active = [t for t in cases.test_cases if t.status == "active" and (not scope or t.id in scope)]
        self.state.ui_test_cases = [t.id for t in active if t.channel == "ui"]
        self.state.api_test_cases = [t.id for t in active if t.channel == "api"]

    @listen(classify)
    def design_generate_validate(self) -> None:
        report, staged = stages.generate_automation(self.state.spec_id, self.state.only_test_case_ids or None)
        self.state.staged_files = staged
        self.state.findings = [f.model_dump() for f in report.findings]
        self.state.artifacts["automation_spec"] = str(ArtifactManager().path_of(self.state.spec_id, "automation"))
        self.state.artifacts["code_validation"] = str(ArtifactManager().path_of(self.state.spec_id, "code_validation"))

    @router(design_generate_validate)
    def code_gate(self) -> str:
        report = ArtifactManager().load(self.state.spec_id, "code_validation")
        if not report.passed:
            self.state.gate("code_validation", "BLOCKED", f"{len(report.findings)} finding(s)")
            return "invalid_code"
        self.state.gate("code_validation", "PASSED")
        self.state.gate("human_script_approval", "AWAITING_APPROVAL")
        return "awaiting_script_approval"

    @listen("blocked")
    def on_blocked(self) -> None:
        self.state.status = "BLOCKED"
        self.state.next_action = f"Approve test cases first: python main.py approve {self.state.spec_id} --stage test_cases"

    @listen("invalid_code")
    def invalid(self) -> None:
        self.state.status = "CODE_VALIDATION_FAILED"
        self.state.next_action = "See code_validation_report.yaml; fix the automation design/templates and re-run"

    @listen("awaiting_script_approval")
    def request_approval(self) -> None:
        self.state.status = "AWAITING_SCRIPT_APPROVAL"
        self.state.next_action = (f"Review the staged files in output/staging/{self.state.spec_id}/ then run: "
                                  f"python main.py approve {self.state.spec_id} --stage scripts --by \"<your name>\"")

    @listen(or_("already_approved", on_blocked, invalid, request_approval))
    def finish(self) -> AutomationFlowState:
        if self.state.status == "STARTED":
            self.state.status = "SCRIPTS_APPROVED"
        audit.write("flow", flow="automation", spec_id=self.state.spec_id, status=self.state.status,
                    staged=self.state.staged_files)
        return self.state
