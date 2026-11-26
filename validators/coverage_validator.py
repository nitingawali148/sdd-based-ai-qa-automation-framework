"""Coverage validation for the Test Design flow: every approved AC (and channel) must have a test case,
and every test case must map to an existing AC."""

from __future__ import annotations

from collections import Counter

from core.models import CoverageReport, FeatureSpec, Finding, TestCaseSet, TestScenarioSet


def validate_coverage(spec: FeatureSpec, scenarios: TestScenarioSet, cases: TestCaseSet) -> CoverageReport:
    findings: list[Finding] = list(scenarios.coverage_notes)
    ac_ids = {a.id for a in spec.acceptance_criteria}
    active = [t for t in cases.test_cases if t.status == "active"]
    covered: set[str] = set()
    for ac in spec.acceptance_criteria:
        for ch in ac.channels:
            if any(ac.id in t.ac_ids and t.channel == ch for t in active):
                covered.add(f"{ac.id}:{ch}")
            else:
                findings.append(Finding(code="AC_NOT_COVERED", severity="error", artifact_id=ac.id,
                                        message=f"{ac.id} has no active {ch.upper()} test case"))
    for t in active:
        unknown = set(t.ac_ids) - ac_ids
        if unknown:
            findings.append(Finding(code="TC_UNKNOWN_AC", severity="error", artifact_id=t.id,
                                    message=f"{t.id} references unknown AC(s) {sorted(unknown)}"))
        if not t.ac_ids:
            findings.append(Finding(code="TC_NO_AC", severity="error", artifact_id=t.id,
                                    message=f"{t.id} is not mapped to any acceptance criterion"))
        if not t.steps or t.expected.kind == "unknown":
            findings.append(Finding(code="TC_INCOMPLETE", severity="error", artifact_id=t.id,
                                    message=f"{t.id} has no steps or no measurable expected result"))
    ids = Counter(t.id for t in cases.test_cases)
    for tc_id, n in ids.items():
        if n > 1:
            findings.append(Finding(code="TC_DUPLICATE_ID", severity="error", artifact_id=tc_id,
                                    message=f"Test case ID {tc_id} is used {n} times"))
    covered_acs = {k.split(":")[0] for k in covered}
    uncovered = sorted(ac_ids - covered_acs)
    by_type = Counter(s.type for s in scenarios.scenarios if s.status == "active")
    return CoverageReport(spec_id=spec.id, spec_version=spec.version,
                          passed=not any(f.severity == "error" for f in findings),
                          ac_total=len(ac_ids), ac_covered=len(covered_acs), uncovered_acs=uncovered,
                          scenarios_by_type=dict(by_type), findings=findings)
