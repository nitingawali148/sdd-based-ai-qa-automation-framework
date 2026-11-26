"""Offline rule engine: deterministic implementations of every agent task.

Used (1) as the CrewAI `BaseLLM` backend when LLM_PROVIDER=offline and (2) as guardrails/validators when a
real LLM is used. Keys match the `[[sdd-task:<key>]]` markers in config/tasks.yaml.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from generators import analysis, automation_design, requirement_analyzer, spec_builder, spec_reviewer, test_design

HANDLERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], Any]] = {
    "requirement_analysis": requirement_analyzer.analyze,
    "specification_design": spec_builder.build_spec,
    "specification_validation": spec_reviewer.review,
    "test_scenarios": test_design.design_scenarios,
    "test_cases": test_design.build_test_cases,
    "test_data": test_design.build_test_data,
    "ui_automation_design": automation_design.design_ui,
    "api_automation_design": automation_design.design_api,
    "execution_planning": analysis.plan_execution,
    "failure_analysis": analysis.analyse_failures,
    "change_impact_analysis": analysis.change_narrative,
    "qa_reporting": analysis.report_narrative,
}
