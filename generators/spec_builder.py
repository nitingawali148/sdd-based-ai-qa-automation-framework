"""Specification Architect rules: StructuredRequirement -> versioned FeatureSpec.

Each acceptance criterion in the spec comes from exactly one requirement AC (same ID, source text kept).
The rules only *structure* it (Given/When/Then, inputs, measurable expectations, API binding). When an
outcome cannot be made measurable, the expectation stays `unknown` and the validator blocks the spec.
"""

from __future__ import annotations

import re
from typing import Any

from core.llm_factory import OFFLINE_LABEL
from core.models import (
    AcceptanceCriterion,
    APIBinding,
    APIEndpointRef,
    Expectation,
    FeatureSpec,
    InputField,
    RawAcceptanceCriterion,
    StructuredRequirement,
    TextItem,
    UIPage,
)
from generators.text_rules import QUOTED, STATUS, classify_ac, field_data_class, split_gwt
from parsers.openapi_parser import OpenAPISpec

_SCHEMA_HINT = re.compile(r"\b(the (?:created|updated) user|the user\b|list of users|the users|the created|"
                          r"the updated|the list)\b", re.I)


def ui_expectation(then: str, pages: list[UIPage]) -> Expectation:
    if q := QUOTED.search(then):
        negate = bool(re.search(r"\bnot\b.*\b(displayed|shown)\b", then, re.I))
        return Expectation(kind="message", value=q.group(1), negate=negate)
    m = re.search(r"\b(?:navigated|redirected|taken)\s+to\s+(?:the\s+)?(.+?)(?:\s+page)?\s*$", then, re.I)
    if m:
        target = m.group(1).strip().lower()
        page = next((p for p in pages if p.name.lower() == target or p.name.lower() in target), None)
        if page:
            return Expectation(kind="navigate", value=page.name)
    return Expectation(kind="unknown", value=then)


def api_expectation(text: str) -> Expectation:
    m = STATUS.search(text)
    if not m:
        return Expectation(kind="unknown", value=text)
    q = QUOTED.search(text)
    return Expectation(kind="status", status_code=int(m.group(1)), value=m.group(1),
                       body_contains=q.group(1) if q else "", validate_schema=bool(_SCHEMA_HINT.search(text)))


def _pick_endpoint(clause: str, endpoints: list[APIEndpointRef]) -> APIEndpointRef | None:
    c = clause.lower()
    item = [e for e in endpoints if "{" in e.path]
    coll = [e for e in endpoints if "{" not in e.path]

    def find(method: str, pool: list[APIEndpointRef]) -> APIEndpointRef | None:
        return next((e for e in pool if e.method == method), None)

    if re.search(r"partially update|patch", c):
        return find("PATCH", item)
    if re.search(r"\b(update|replace|modify)\b", c):
        return find("PUT", item) or find("PATCH", item)
    if re.search(r"\b(delete|remove)\b", c):
        return find("DELETE", item)
    if re.search(r"\blist\b|\ball users\b", c):
        return find("GET", coll)
    if re.search(r"\b(retrieve|get|view|fetch|read)\b", c):
        return find("GET", item)
    if re.search(r"\b(create|add|register)\b", c):
        return find("POST", coll)
    if len(endpoints) == 1:
        return endpoints[0]
    return find("POST", coll)


def _api_binding(ac: RawAcceptanceCriterion, given: str, when: str, endpoints: list[APIEndpointRef],
                 openapi: OpenAPISpec | None) -> APIBinding | None:
    ep = _pick_endpoint(when, endpoints)
    if ep is None:
        return None
    op = openapi.operation(ep.method, ep.path) if openapi else None
    secured = bool(op["secured"]) if op else True
    unauth = bool(re.search(r"unauthenticated|without (?:a |an )?(?:token|authentication)|anonymous", f"{given} {when}",
                            re.I))
    pre = "none"
    if re.search(r"\bsame\b|\bduplicate\b", when, re.I):
        pre = "duplicate"
    elif "{" in ep.path and re.search(r"\bexisting\b", given, re.I):
        pre = "existing_resource"
    elif "{" in ep.path:
        pre = "existing_resource"
    return APIBinding(method=ep.method, path=ep.path, operation_id=op["operation_id"] if op else "",
                      auth=secured and not unauth, precondition=pre)  # type: ignore[arg-type]


def _inputs(fields: list[InputField], given: str, when: str, channel_needs_body: bool, partial: bool) -> dict[str, str]:
    clause = f"{given} {when}"
    out: dict[str, str] = {}
    for f in fields:
        names = [f.name] + ([f.label] if f.label and f.label.lower() != f.name else [])
        cls = field_data_class(names, clause, f.type)
        if cls is not None:
            out[f.name] = cls
        elif channel_needs_body and not partial:
            out[f.name] = "valid"
    return out


def _title(when: str, then: str, text: str) -> str:
    if not when:
        return text[:100]
    q = QUOTED.search(then)
    short_then = f"\"{q.group(1)}\" shown" if q else then
    t = f"{when[0].upper()}{when[1:]} -> {short_then}"
    t = re.sub(r"^(They|The user|User)\s+", "", t, flags=re.I)
    return t[0].upper() + t[1:]


def build_ac(raw: RawAcceptanceCriterion, req: StructuredRequirement, openapi: OpenAPISpec | None) -> AcceptanceCriterion:
    given, when, then = split_gwt(raw.text)
    channels = list(raw.channels)
    binding = _api_binding(raw, given, when, req.api_endpoints, openapi) if "api" in channels else None
    needs_body = True
    partial = False
    if binding is not None:
        needs_body = binding.method in ("POST", "PUT", "PATCH")
        partial = binding.method == "PATCH"
    ui_page = ""
    if "ui" in channels and req.ui_pages:
        named = next((p.name for p in req.ui_pages if re.search(rf"\b{re.escape(p.name)}\b", given or "", re.I)), "")
        form = next((p.name for p in req.ui_pages if any(e.role == "textbox" for e in p.elements)), "")
        ui_page = named or form or req.ui_pages[0].name
    inputs = _inputs(req.input_fields, given, when, needs_body, partial) if when else {}
    exp_ui = ui_expectation(then, req.ui_pages) if "ui" in channels and then else None
    exp_api = None
    if "api" in channels:
        exp_api = api_expectation(raw.api_text or then)
        if exp_api.kind == "status" and not exp_api.body_contains and raw.api_text == "" and exp_ui and \
                exp_ui.kind == "message":
            exp_api.body_contains = exp_ui.value
    return AcceptanceCriterion(
        id=raw.id, title=_title(when, then, raw.text), type=classify_ac(raw.text),  # type: ignore[arg-type]
        given=given, when=when, then=then, channels=channels, inputs=inputs, expected_ui=exp_ui,
        expected_api=exp_api, api=binding, start_page=ui_page, requirement_id=req.id, source_text=raw.text,
    )


def build_spec(payload: dict[str, Any], blackboard: dict[str, Any] | None = None) -> FeatureSpec:
    blackboard = blackboard or {}
    req_data = blackboard.get("requirement_analysis") or payload.get("requirement")
    req = req_data if isinstance(req_data, StructuredRequirement) else StructuredRequirement.model_validate(req_data)
    openapi = None
    if payload.get("openapi_path"):
        try:
            openapi = OpenAPISpec.load(__import__("pathlib").Path(payload["openapi_path"]))
        except FileNotFoundError:
            openapi = None

    frs: list[TextItem] = []
    for f in req.input_fields:
        rule = f", {f.description}" if f.description else ""
        frs.append(TextItem(id="", text=f"The user must provide {f.label or f.name} ({f.type}"
                                        f"{', required' if f.required else ', optional'}{rule})."))
    for e in req.api_endpoints:
        frs.append(TextItem(id="", text=f"The system must provide {e.method} {e.path}: {e.summary}."))
    for p in req.ui_pages:
        frs.append(TextItem(id="", text=f"The system must provide the {p.name} page at {p.path}."))
    for i, fr in enumerate(frs, 1):
        fr.id = f"FR-{i:03d}"

    return FeatureSpec(
        id=payload.get("spec_id") or f"SPEC-{req.feature_code}-001",
        version=payload.get("version", "1.0"),
        title=req.title, feature=req.feature, feature_code=req.feature_code, requirement_ids=[req.id],
        priority=req.priority, objective=req.objective or req.user_story, user_story=req.user_story,
        functional_requirements=frs,
        business_rules=[TextItem(id=f"BR-{i:03d}", text=t) for i, t in enumerate(req.business_rules, 1)],
        inputs=req.input_fields,
        acceptance_criteria=[build_ac(a, req, openapi) for a in req.acceptance_criteria],
        ui_pages=req.ui_pages, api_endpoints=req.api_endpoints,
        non_functional=[TextItem(id=f"NFR-{i:03d}", text=t) for i, t in enumerate(req.non_functional, 1)],
        dependencies=req.dependencies, open_questions=req.open_questions,
        generated_by=OFFLINE_LABEL, source_requirement_hash=req.source_hash,
    )
