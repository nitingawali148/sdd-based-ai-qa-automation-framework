"""Test design crew: Test Design Agent -> Test Case Agent, plus the Test Data Agent."""

from __future__ import annotations

from core.models import FeatureSpec, TestCaseSet, TestDataSet, TestScenarioSet
from crews.base import run_crew


def run_test_design_crew(spec: FeatureSpec, only_ac_ids: list[str] | None = None) -> tuple[TestScenarioSet,
                                                                                         TestCaseSet, TestDataSet]:
    spec_json = spec.model_dump(mode="json")
    out = run_crew("test-design", [
        ("test_scenarios", {"spec": spec_json, "only_ac_ids": only_ac_ids or []}),
        ("test_cases", {"spec": spec_json}),
        ("test_data", {"spec": spec_json}),
    ], spec_id=spec.id)
    return out["test_scenarios"], out["test_cases"], out["test_data"]  # type: ignore[return-value]
