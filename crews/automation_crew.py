"""Automation design crew: UI Automation Design Agent and/or API Automation Design Agent."""

from __future__ import annotations

from typing import Any

from core.models import APIAutomationDesign, FeatureSpec, TestCaseSet, UIAutomationDesign
from crews.base import run_crew


def run_automation_crew(spec: FeatureSpec, cases: TestCaseSet, openapi_path: str, need_ui: bool, need_api: bool,
                        only_test_case_ids: list[str] | None = None) -> tuple[UIAutomationDesign | None,
                                                                               APIAutomationDesign | None]:
    payload: dict[str, Any] = {"spec": spec.model_dump(mode="json"), "test_cases": cases.model_dump(mode="json"),
                               "openapi_path": openapi_path, "only_test_case_ids": only_test_case_ids or []}
    steps = []
    if need_ui:
        steps.append(("ui_automation_design", payload))
    if need_api:
        steps.append(("api_automation_design", payload))
    if not steps:
        return None, None
    out = run_crew("automation-design", steps, spec_id=spec.id)
    return out.get("ui_automation_design"), out.get("api_automation_design")  # type: ignore[return-value]
