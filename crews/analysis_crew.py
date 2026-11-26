"""Execution planning, failure analysis, change impact and reporting crews."""

from __future__ import annotations

from typing import Any

from core.models import ChangeRecord, ExecutionPlan, ExecutionRun, FailureAnalysisReport, ReportNarrative
from crews.base import run_crew


def run_execution_planning(request: dict[str, Any]) -> ExecutionPlan:
    return run_crew("execution-planning", [("execution_planning", request)])["execution_planning"]  # type: ignore[return-value]


def run_failure_analysis(run: ExecutionRun, changes: list[ChangeRecord]) -> FailureAnalysisReport:
    out = run_crew("failure-analysis", [("failure_analysis", {
        "execution": run.model_dump(mode="json"), "changes": [c.model_dump(mode="json") for c in changes]})])
    return out["failure_analysis"]  # type: ignore[return-value]


def run_change_impact(change: ChangeRecord) -> ReportNarrative:
    out = run_crew("change-impact", [("change_impact_analysis", {"change": change.model_dump(mode="json")})],
                   spec_id=change.spec_id)
    return out["change_impact_analysis"]  # type: ignore[return-value]


def run_reporting(summary: dict[str, Any]) -> ReportNarrative:
    return run_crew("reporting", [("qa_reporting", summary)])["qa_reporting"]  # type: ignore[return-value]
