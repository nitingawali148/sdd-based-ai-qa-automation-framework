"""UI and API Automation Design rules (offline rule engine).

Locators come from the approved specification's UI section (accessible label / role / text), which is the
most stable Playwright strategy. API tests come from the AC's OpenAPI binding.
"""

from __future__ import annotations

from typing import Any

from core.llm_factory import OFFLINE_LABEL
from core.models import (
    APIAutomationDesign,
    APITestDesign,
    FeatureSpec,
    Locator,
    PageObjectDesign,
    TestCaseSet,
    UIAutomationDesign,
    UITestDesign,
)
from generators.text_rules import pascal, snake
from parsers.openapi_parser import OpenAPISpec

_ROLE_STRATEGY = {"textbox": "label", "button": "role", "heading": "role", "link": "role", "alert": "role",
                  "checkbox": "label", "combobox": "label"}


def _function_name(tc_id: str, title: str) -> str:
    words = snake(title.split("->")[0].split("[")[0]).split("_")[:7]
    return f"test_{snake(tc_id)}_{'_'.join(w for w in words if w)}"


def design_ui(payload: dict[str, Any], blackboard: dict[str, Any] | None = None) -> UIAutomationDesign:
    spec = FeatureSpec.model_validate(payload["spec"])
    cases = TestCaseSet.model_validate(payload["test_cases"])
    only = set(payload.get("only_test_case_ids") or [])
    pages: list[PageObjectDesign] = []
    for p in spec.ui_pages:
        locators = []
        for e in p.elements:
            strategy = _ROLE_STRATEGY.get(e.role, "text")
            locators.append(Locator(key=snake(e.label), strategy=strategy, value=e.label,  # type: ignore[arg-type]
                                    role=e.role if strategy == "role" else ""))
        form_fields = {}
        for f in spec.inputs:
            label = (f.label or f.name).lower()
            loc = next((loc for loc in locators if loc.strategy == "label" and loc.value.lower() == label), None)
            if loc:
                form_fields[f.name] = loc.key
        submit = next((loc.key for loc in locators if loc.role == "button"), "")
        pages.append(PageObjectDesign(page=p.name, class_name=f"{pascal(p.name)}Page", module=f"{snake(p.name)}_page",
                                      path=p.path, locators=locators, form_fields=form_fields, submit_key=submit))
    tests = []
    for tc in cases.test_cases:
        if tc.channel != "ui" or tc.status != "active" or (only and tc.id not in only):
            continue
        tests.append(UITestDesign(automation_id=tc.automation_id, test_case_id=tc.id,
                                  function_name=_function_name(tc.id, tc.title), start_page=tc.start_page,
                                  fill=dict(tc.test_data), submit=True, assertion=tc.expected))
    return UIAutomationDesign(spec_id=spec.id, spec_version=spec.version, pages=pages, tests=tests,
                              generated_by=OFFLINE_LABEL)


def design_api(payload: dict[str, Any], blackboard: dict[str, Any] | None = None) -> APIAutomationDesign:
    spec = FeatureSpec.model_validate(payload["spec"])
    cases = TestCaseSet.model_validate(payload["test_cases"])
    only = set(payload.get("only_test_case_ids") or [])
    openapi = None
    if payload.get("openapi_path"):
        from pathlib import Path
        openapi = OpenAPISpec.load(Path(payload["openapi_path"]))
    tests = []
    for tc in cases.test_cases:
        if tc.channel != "api" or tc.status != "active" or tc.api is None or (only and tc.id not in only):
            continue
        op = openapi.operation(tc.api.method, tc.api.path) if openapi else None
        status = tc.expected.status_code or 200
        has_schema = bool(openapi and openapi.response_schema(tc.api.method, tc.api.path, status))
        tests.append(APITestDesign(
            automation_id=tc.automation_id, test_case_id=tc.id, function_name=_function_name(tc.id, tc.title),
            method=tc.api.method, path=tc.api.path, operation_id=tc.api.operation_id, auth=tc.api.auth,
            precondition=tc.api.precondition, payload=dict(tc.test_data), expected_status=status,
            body_contains=tc.expected.body_contains, validate_schema=tc.expected.validate_schema and has_schema,
            destructive=bool(op and op["destructive"])))
    return APIAutomationDesign(spec_id=spec.id, spec_version=spec.version, tests=tests, generated_by=OFFLINE_LABEL)
