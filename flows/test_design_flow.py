"""Flow 2 - Test Design Flow.

Approved Specification (gate) -> Test Scenario Generation -> Test Case Generation (+ Test Data)
-> Coverage Validation -> Human Approval (gate) -> Approved Test Cases
"""

from __future__ import annotations

from crewai.flow.flow import Flow, listen, or_, router, start

from core.artifact_manager import ArtifactManager
from core.logger import audit
from core.state import TestDesignFlowState
from flows import stages
from versioning.version_manager import VersionManager


class TestDesignFlow(Flow[TestDesignFlowState]):
    __test__ = False

    @start()
    def check_spec_approved(self) -> bool:
        return VersionManager().spec_is_approved(self.state.spec_id)

    @router(check_spec_approved)
    def spec_gate(self) -> str:
        if not VersionManager().spec_is_approved(self.state.spec_id):
            self.state.gate("approved_spec", "BLOCKED", "specification is not approved (or changed since approval)")
            return "blocked"
        self.state.gate("approved_spec", "PASSED")
        vm = VersionManager()
        if vm.is_approved(self.state.spec_id, "test_cases") and not self.state.only_ac_ids:
            return "already_approved"
        return "design"

    @listen("design")
    def generate(self) -> None:
        scenarios, cases, coverage = stages.design_tests(self.state.spec_id, self.state.only_ac_ids or None)
        self.state.scenario_count = len([s for s in scenarios.scenarios if s.status == "active"])
        self.state.test_case_count = len([t for t in cases.test_cases if t.status == "active"])
        self.state.coverage = {"ac_total": coverage.ac_total, "ac_covered": coverage.ac_covered,
                               "uncovered": coverage.uncovered_acs, "by_type": coverage.scenarios_by_type}
        am = ArtifactManager()
        self.state.artifacts.update({"test_scenarios": str(am.path_of(self.state.spec_id, "scenarios")),
                                     "test_cases": str(am.path_of(self.state.spec_id, "test_cases")),
                                     "test_cases_md": str(am.spec_dir(self.state.spec_id) / "test_cases.md")})

    @router(generate)
    def coverage_gate(self) -> str:
        coverage = ArtifactManager().load(self.state.spec_id, "coverage")
        if not coverage.passed:
            self.state.gate("coverage", "BLOCKED", f"uncovered: {coverage.uncovered_acs}")
            return "coverage_failed"
        self.state.gate("coverage", "PASSED")
        self.state.gate("human_test_case_approval", "AWAITING_APPROVAL")
        return "awaiting_test_case_approval"

    @listen("blocked")
    def on_blocked(self) -> None:
        self.state.status = "BLOCKED"
        self.state.next_action = f"Approve the specification first: python main.py spec ... / approve {self.state.spec_id}"

    @listen("coverage_failed")
    def on_coverage_failed(self) -> None:
        self.state.status = "COVERAGE_FAILED"
        self.state.next_action = "Inspect coverage_report.yaml; fix the specification or the test design and re-run"

    @listen("awaiting_test_case_approval")
    def request_approval(self) -> None:
        self.state.status = "AWAITING_TEST_CASE_APPROVAL"
        self.state.next_action = (f"Review {self.state.artifacts['test_cases_md']} then run: python main.py approve "
                                  f"{self.state.spec_id} --stage test_cases --by \"<your name>\"")

    @listen(or_("already_approved", on_blocked, on_coverage_failed, request_approval))
    def finish(self) -> TestDesignFlowState:
        if self.state.status == "STARTED":
            self.state.status = "TEST_CASES_APPROVED"
        audit.write("flow", flow="test_design", spec_id=self.state.spec_id, status=self.state.status)
        return self.state
