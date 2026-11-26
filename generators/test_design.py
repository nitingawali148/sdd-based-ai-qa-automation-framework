"""Test Design, Test Case and Test Data rules (offline rule engine).

Scenarios are derived only from approved acceptance criteria. Each scenario/test case has a stable `key`
(AC + channel + variant) so IDs survive regeneration; the flow assigns IDs (see traceability.id_allocator).
"""

from __future__ import annotations

from typing import Any

from core.llm_factory import OFFLINE_LABEL
from core.models import (
    AcceptanceCriterion,
    Expectation,
    FeatureSpec,
    Finding,
    InputField,
    TestCase,
    TestCaseSet,
    TestDataSet,
    TestScenario,
    TestScenarioSet,
    TestStep,
)

_TYPE_PRIORITY = {"positive": "P1", "negative": "P2", "boundary": "P2"}


def _spec(payload: dict[str, Any]) -> FeatureSpec:
    return FeatureSpec.model_validate(payload["spec"])


def _selected(spec: FeatureSpec, only: list[str] | None) -> list[AcceptanceCriterion]:
    return [a for a in spec.acceptance_criteria if not only or a.id in only]


# ----------------------------------------------------------------------------- scenarios
def design_scenarios(payload: dict[str, Any], blackboard: dict[str, Any] | None = None) -> TestScenarioSet:
    spec = _spec(payload)
    fields = {f.name: f for f in spec.inputs}
    out: list[TestScenario] = []
    notes: list[Finding] = []
    for ac in _selected(spec, payload.get("only_ac_ids")):
        for ch in ac.channels:
            exp = ac.expected_ui if ch == "ui" else ac.expected_api
            if exp is None or exp.kind == "unknown":
                continue
            prio = "P1" if ac.type == "positive" and spec.priority == "P1" else _TYPE_PRIORITY[ac.type]
            tags = ["functional", "regression"] + (["smoke"] if ac.type == "positive" else [])
            base = TestScenario(id="", key=f"{ac.id}:{ch}:base", title=f"{ac.title} [{ch.upper()}]",
                                type=ac.type, channel=ch, ac_ids=[ac.id], inputs=dict(ac.inputs), expected=exp,
                                priority=prio, tags=tags, spec_id=spec.id, spec_version=spec.version,  # type: ignore[arg-type]
                                ac_hash=ac.content_hash())
            out.append(base)
            # Boundary companion: the value exactly on the limit must NOT trigger the limit message.
            for fname, cls in ac.inputs.items():
                f = fields.get(fname)
                if cls not in ("too_short", "too_long") or f is None or exp.kind != "message":
                    continue
                on_limit = "at_min" if cls == "too_short" else "at_max"
                limit = f.min_length if cls == "too_short" else f.max_length
                out.append(TestScenario(
                    id="", key=f"{ac.id}:{ch}:{on_limit}:{fname}",
                    title=f"{fname} with exactly {limit} characters does not show \"{exp.value}\" [{ch.upper()}]",
                    type="boundary", channel=ch, ac_ids=[ac.id], inputs={**ac.inputs, fname: on_limit},  # type: ignore[arg-type]
                    expected=Expectation(kind="message", value=exp.value, negate=True), priority="P2",
                    tags=["functional", "regression"], spec_id=spec.id, spec_version=spec.version,
                    ac_hash=ac.content_hash()))
    covered_fields = {n for s in out for n, c in s.inputs.items() if c in ("too_short", "too_long")}
    for f in spec.inputs:
        if (f.min_length or f.max_length) and f.name not in covered_fields:
            notes.append(Finding(code="BOUNDARY_NOT_SPECIFIED", severity="info", artifact_id=f.name,
                                 message=f"'{f.name}' has length rules but no boundary AC; no boundary scenario was "
                                         "generated (agents must not invent acceptance criteria)."))
    return TestScenarioSet(spec_id=spec.id, spec_version=spec.version, scenarios=out, coverage_notes=notes,
                           generated_by=OFFLINE_LABEL)


# ----------------------------------------------------------------------------- test cases
def _describe_data(field: str, cls: str) -> str:
    return f"{field}: <{cls}>"


def _ui_steps(spec: FeatureSpec, sc: TestScenario, ac: AcceptanceCriterion) -> list[TestStep]:
    page = next((p for p in spec.ui_pages if p.name == ac.start_page), spec.ui_pages[0])
    steps = [TestStep(n=1, action="navigate", target=f"{page.name} page ({page.path})",
                      expected=f"{page.name} page is displayed")]
    labels = {f.name: (f.label or f.name) for f in spec.inputs}
    for name, cls in sc.inputs.items():
        steps.append(TestStep(n=len(steps) + 1, action="fill", target=labels.get(name, name), data=cls))
    button = next((e.label for e in page.elements if e.role == "button"), "Submit")
    steps.append(TestStep(n=len(steps) + 1, action="click", target=f"{button} button"))
    steps.append(TestStep(n=len(steps) + 1, action="verify", expected=sc.expected.describe()))
    return steps


def _api_steps(sc: TestScenario, ac: AcceptanceCriterion) -> tuple[list[str], list[TestStep]]:
    assert ac.api is not None
    pre, steps = [], []
    if ac.api.auth:
        pre.append("A valid access token is obtained for an authenticated admin")
    else:
        pre.append("No Authorization header is sent" if "unauth" in f"{ac.given} {ac.when}".lower()
                   else "Endpoint is public (no authentication required)")
    if ac.api.precondition == "existing_resource":
        pre.append("A resource exists (created through the API in test setup)")
    if ac.api.precondition == "duplicate":
        pre.append("A resource with the same unique values already exists (created in test setup)")
    body = ", ".join(_describe_data(k, v) for k, v in sc.inputs.items())
    steps.append(TestStep(n=1, action="request", target=f"{ac.api.method} {ac.api.path}", data=body))
    steps.append(TestStep(n=2, action="verify", expected=sc.expected.describe()))
    return pre, steps


def build_test_cases(payload: dict[str, Any], blackboard: dict[str, Any] | None = None) -> TestCaseSet:
    blackboard = blackboard or {}
    spec = _spec(payload)
    sc_set = blackboard.get("test_scenarios") or payload.get("scenarios")
    scenarios = sc_set if isinstance(sc_set, TestScenarioSet) else TestScenarioSet.model_validate(sc_set)
    acs = {a.id: a for a in spec.acceptance_criteria}
    out: list[TestCase] = []
    for sc in scenarios.scenarios:
        if sc.status != "active":
            continue
        ac = acs[sc.ac_ids[0]]
        pre = [f"Application is reachable at the configured base URL ({sc.channel.upper()})"]
        if ac.given:
            pre.append(f"Given {ac.given}")
        if sc.channel == "ui":
            steps = _ui_steps(spec, sc, ac)
        else:
            extra, steps = _api_steps(sc, ac)
            pre += extra
        if any(c == "valid" for c in sc.inputs.values()) and "registered" in ac.given.lower():
            pre.append("Registered user credentials are provided through environment variables")
        out.append(TestCase(
            id="", key=sc.key, scenario_id=sc.id, title=sc.title, channel=sc.channel, ac_ids=sc.ac_ids,
            spec_id=spec.id, spec_version=spec.version, ac_hash=sc.ac_hash, priority=sc.priority,
            preconditions=pre, steps=steps, test_data=dict(sc.inputs), expected=sc.expected,
            expected_result=sc.expected.describe(), start_page=ac.start_page if sc.channel == "ui" else "",
            api=ac.api if sc.channel == "api" else None, tags=sc.tags))
    return TestCaseSet(spec_id=spec.id, spec_version=spec.version, test_cases=out, generated_by=OFFLINE_LABEL)


# ----------------------------------------------------------------------------- test data
def _values(f: InputField, uses_registered_identity: bool) -> dict[str, str]:
    v: dict[str, str] = {"empty": "", "missing": "${omit}"}
    if f.type == "email":
        v["valid"] = "${env:SDD_DEMO_USER_EMAIL}" if uses_registered_identity else "${faker:unique_email}"
        v["unregistered"] = "${faker:unique_email}"
        v["duplicate"] = "${faker:unique_email}"
        v["malformed"] = "not-an-email"
        v["invalid"] = "not-an-email"
    elif f.type == "password":
        v["valid"] = "${env:SDD_DEMO_USER_PASSWORD}" if uses_registered_identity else "${faker:password:12}"
        v["invalid"] = "${faker:password:12}"
    elif f.type == "enum":
        v["valid"] = f.enum[0] if f.enum else "value"
        v["invalid"] = "not-a-valid-option"
    elif f.type == "integer":
        v["valid"], v["invalid"] = "1", "not-a-number"
    else:
        v["valid"] = "${faker:name}" if f.name in ("name", "full_name") else "${faker:word}"
        v["invalid"] = "${repeat:x:" + str((f.max_length or 255) + 1) + "}"
    if f.min_length:
        v["too_short"] = "${repeat:x:" + str(f.min_length - 1) + "}"
        v["at_min"] = "${repeat:x:" + str(f.min_length) + "}"
    if f.max_length:
        v["too_long"] = "${repeat:x:" + str(f.max_length + 1) + "}"
        v["at_max"] = "${repeat:x:" + str(f.max_length) + "}"
    return v


def build_test_data(payload: dict[str, Any], blackboard: dict[str, Any] | None = None) -> TestDataSet:
    spec = _spec(payload)
    registered = any("registered user" in a.given.lower() for a in spec.acceptance_criteria)
    data = {f.name: _values(f, registered) for f in spec.inputs}
    notes = ["Credentials are referenced as ${env:VAR}; values live in .env (never in this file).",
             "${faker:...} values are generated at runtime, unique per call; ${omit} removes the field."]
    return TestDataSet(feature=spec.feature, spec_id=spec.id, spec_version=spec.version, fields=data, notes=notes,
                       generated_by=OFFLINE_LABEL)
