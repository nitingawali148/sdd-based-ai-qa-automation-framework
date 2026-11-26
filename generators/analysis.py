"""Execution planning, failure analysis, change-impact narrative and report narrative (offline rules).

Analysis is always labelled probable; it never alters execution results.
"""

from __future__ import annotations

import re
from typing import Any

from core.llm_factory import OFFLINE_LABEL
from core.models import (
    ChangeRecord,
    ExecutionPlan,
    ExecutionRun,
    FailureAnalysisItem,
    FailureAnalysisReport,
    ReportNarrative,
)

_ACTUAL = re.compile(r"actual (?:visible messages|body|URL): (.*)$", re.S)
_EXPECTED = re.compile(r"SDD-EXPECTED (.*?)(?:;|$)")


def plan_execution(payload: dict[str, Any], blackboard: dict[str, Any] | None = None) -> ExecutionPlan:
    tcs = payload.get("test_case_ids") or []
    suites = payload.get("suites") or []
    if tcs:
        why = f"Targeted run of {len(tcs)} test case(s) selected by change impact or user request."
    elif suites:
        why = f"Suite run: {', '.join(suites)}."
    else:
        why = "Full regression of all approved automation for the selected specifications."
    return ExecutionPlan(suites=suites, test_case_ids=tcs, channels=payload.get("channels") or ["ui", "api"],
                         rationale=why)


def classify(result: dict[str, Any], changed_acs: dict[str, str]) -> FailureAnalysisItem:
    msg = f"{result.get('error_type', '')}: {result.get('message', '')}\n{result.get('traceback', '')}"
    expected = (m.group(1).strip() if (m := _EXPECTED.search(msg)) else "")
    actual = (m.group(1).strip()[:300] if (m := _ACTUAL.search(result.get("message", ""))) else "")
    base = dict(automation_id=result.get("automation_id", ""), test_case_id=result.get("test_case_id", ""),
                nodeid=result.get("nodeid", ""), expected=expected, actual=actual,
                evidence=[e for e in (result.get("screenshot"), result.get("trace")) if e])
    low = msg.lower()
    if re.search(r"connection refused|connecterror|err_connection|name or service not known|timed out connecting|"
                 r"demo app did not start", low):
        return FailureAnalysisItem(**base, category="ENVIRONMENT_ISSUE", confidence=0.9,
                                   root_cause="The application under test was not reachable.",
                                   recommendation="Check the environment URL, that the app is running and network "
                                                  "access; re-run once the environment is healthy.")
    if "test-data" in low or "testdataerror" in low:
        return FailureAnalysisItem(**base, category="TEST_DATA_ISSUE", confidence=0.9,
                                   root_cause="Required test data or environment variable is missing.",
                                   recommendation="Provide the missing value in .env / test_data and re-run.")
    if re.search(r"syntaxerror|importerror|modulenotfounderror|fixture '.*' not found|nameerror|attributeerror", low):
        return FailureAnalysisItem(**base, category="AUTOMATION_ISSUE", confidence=0.85,
                                   root_cause="The automation code itself is broken (import/fixture/attribute).",
                                   recommendation="Regenerate the script from the approved automation spec, or fix "
                                                  "the shared framework code, then re-validate.")
    if "sdd-expected" in low:
        changed = [a for a in result.get("ac_ids", []) if a in changed_acs]
        if changed:
            return FailureAnalysisItem(
                **base, category="SPEC_IMPLEMENTATION_DRIFT", confidence=0.8,
                root_cause=f"{', '.join(changed)} changed in {changed_acs[changed[0]]}; the application still "
                           "shows the previous behaviour. The test checks the new, approved specification.",
                recommendation="Implement the approved specification change in the application (or revert the "
                               "spec change); keep the test as the acceptance check.")
        return FailureAnalysisItem(**base, category="APPLICATION_DEFECT", confidence=0.7,
                                   root_cause="The application's behaviour differs from the approved acceptance "
                                              "criterion (expected vs actual shown).",
                                   recommendation="Raise a defect with the evidence after a human confirms it.")
    if re.search(r"timeout|waiting for|strict mode violation|locator", low):
        return FailureAnalysisItem(**base, category="AUTOMATION_ISSUE", confidence=0.6,
                                   root_cause="An element could not be located/interacted with in time; the page "
                                              "structure may differ from the specification's UI section.",
                                   recommendation="Compare the page with the spec's UI elements; update the spec "
                                                  "(labels/roles) if the UI changed intentionally.")
    return FailureAnalysisItem(**base, category="UNKNOWN", confidence=0.3,
                               root_cause="No rule matched; needs human triage.",
                               recommendation="Inspect the traceback, screenshot and trace.")


def analyse_failures(payload: dict[str, Any], blackboard: dict[str, Any] | None = None) -> FailureAnalysisReport:
    run = ExecutionRun.model_validate(payload["execution"])
    changed: dict[str, str] = {}
    for c in payload.get("changes", []):
        rec = ChangeRecord.model_validate(c)
        for ch in rec.ac_changes:
            changed[ch.ac_id] = f"{rec.id} ({rec.spec_id} v{rec.from_version} -> v{rec.to_version})"
    items = [classify(r.model_dump(), changed) for r in run.results if r.outcome in ("failed", "error")]
    counts: dict[str, int] = {}
    for i in items:
        counts[i.category] = counts.get(i.category, 0) + 1
    summary = ("No failures to analyse." if not items else
               f"{len(items)} failure(s): " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return FailureAnalysisReport(execution_id=run.id, items=items, summary=summary, generated_by=OFFLINE_LABEL)


def change_narrative(payload: dict[str, Any], blackboard: dict[str, Any] | None = None) -> ReportNarrative:
    rec = ChangeRecord.model_validate(payload["change"])
    hl = [f"{c.ac_id} {c.change}" + (f" ({', '.join(c.fields_changed)})" if c.fields_changed else "")
          for c in rec.ac_changes]
    risks = []
    if any(c.change == "removed" for c in rec.ac_changes):
        risks.append("Removed acceptance criteria: their tests are marked obsolete, not deleted.")
    if rec.impact.test_cases:
        risks.append(f"{len(rec.impact.test_cases)} test case(s) and {len(rec.impact.scripts)} script(s) must be "
                     "regenerated and re-approved before they run again.")
    return ReportNarrative(
        headline=f"{rec.spec_id} v{rec.from_version} -> v{rec.to_version}: {len(rec.ac_changes)} AC change(s), "
                 f"{len(rec.impact.test_cases)} impacted / {len(rec.impact.unaffected_test_cases)} unaffected test "
                 "case(s)",
        highlights=hl + rec.other_changes, risks=risks,
        recommendations=["Review the diff, approve the new spec version, then regenerate only impacted artifacts."],
        generated_by=OFFLINE_LABEL)


def report_narrative(payload: dict[str, Any], blackboard: dict[str, Any] | None = None) -> ReportNarrative:
    cov = payload.get("coverage", {})
    last = payload.get("last_execution") or {}
    fa = payload.get("failure_summary", "")
    hl = [f"Requirement coverage {cov.get('requirements', {}).get('pct', 0)}%, AC coverage "
          f"{cov.get('acceptance_criteria', {}).get('pct', 0)}%, automation coverage "
          f"{cov.get('automation', {}).get('pct', 0)}%."]
    if last:
        hl.append(f"Last execution {last.get('id')}: {last.get('passed', 0)} passed, {last.get('failed', 0)} failed, "
                  f"{last.get('skipped', 0)} skipped, {last.get('error', 0)} errors.")
    risks = []
    if payload.get("uncovered_requirements"):
        risks.append(f"Uncovered requirements: {', '.join(payload['uncovered_requirements'])} (spec not approved).")
    if payload.get("outdated_scripts"):
        risks.append(f"{len(payload['outdated_scripts'])} outdated script(s) need regeneration.")
    if fa:
        risks.append(f"Failure analysis: {fa}")
    recs = ["Resolve open clarification items before approving pending specifications."] if \
        payload.get("uncovered_requirements") else []
    if last and last.get("failed"):
        recs.append("Triage failures with the evidence in the Failure Analysis section; confirm defects by a human.")
    return ReportNarrative(headline="QA status from the specification-driven lifecycle", highlights=hl, risks=risks,
                           recommendations=recs or ["No action required."], generated_by=OFFLINE_LABEL)
