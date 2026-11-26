"""Requirement Analysis rules: ParsedDocument payload -> StructuredRequirement.

It extracts only what the requirement states. Missing or vague information becomes an ambiguity or an
open question; nothing is invented.
"""

from __future__ import annotations

import re
from typing import Any

from core.llm_factory import OFFLINE_LABEL
from core.models import (
    APIEndpointRef,
    Finding,
    InputField,
    RawAcceptanceCriterion,
    StructuredRequirement,
    UIElement,
    UIPage,
)
from generators.text_rules import has_number, vague_terms
from parsers.requirement_parser import parse_bullets, parse_table

_AC_LINE = re.compile(r"^(AC-\d+)\s*(?:\[([^\]]+)\])?\s*[:\-–]\s*(.+)$", re.I)
_ENDPOINT = re.compile(r"^(GET|POST|PUT|PATCH|DELETE)\s+(\S+)\s*(?:[-–:]\s*(.*))?$", re.I)


def _bullets(doc: dict[str, Any], *names: str) -> list[tuple[str, list[str]]]:
    for name in names:
        for key, body in doc["sections"].items():
            if key.startswith(name):
                return parse_bullets(body)
    return []


def _section(doc: dict[str, Any], *names: str) -> str:
    for name in names:
        for key, body in doc["sections"].items():
            if key.startswith(name):
                return body.strip()
    return ""


def _parse_rules(field: InputField, rules: str) -> None:
    r = rules.lower()
    if m := re.search(r"(\d+)\s*(?:-|–|to)\s*(\d+)\s*char", r):
        field.min_length, field.max_length = int(m.group(1)), int(m.group(2))
    if m := re.search(r"(?:max(?:imum)?|at most|up to)\s*(\d+)", r):
        field.max_length = int(m.group(1))
    if m := re.search(r"(?:min(?:imum)?|at least)\s*(\d+)", r):
        field.min_length = int(m.group(1))
    if field.type == "enum":
        field.enum = [v.strip() for v in re.split(r"[,/|]", rules) if v.strip() and " " not in v.strip()]
    field.description = rules.strip()


def _fields(doc: dict[str, Any]) -> list[InputField]:
    out = []
    for row in parse_table(_section(doc, "input fields", "inputs", "fields")):
        name = row.get("field") or row.get("name") or ""
        if not name:
            continue
        f = InputField(name=name.strip().lower(), type=(row.get("type") or "string").strip().lower(),
                       required=(row.get("required", "yes").strip().lower() in ("yes", "y", "true", "required")),
                       label=(row.get("ui_label") or row.get("label") or "").strip() or None)
        _parse_rules(f, row.get("rules", "") or row.get("validation", ""))
        out.append(f)
    return out


def _ui_pages(doc: dict[str, Any]) -> list[UIPage]:
    pages = []
    for row in parse_table(_section(doc, "ui", "user interface", "screens")):
        elements = []
        for part in re.split(r",\s*(?![^()]*\))", row.get("elements", "")):
            m = re.match(r"\s*(.+?)\s*\((\w+)\)\s*$", part)
            if m:
                elements.append(UIElement(label=m.group(1), role=m.group(2).lower()))
            elif part.strip():
                elements.append(UIElement(label=part.strip(), role="text"))
        pages.append(UIPage(name=row.get("page", "").strip(), path=row.get("path", "/").strip(), elements=elements))
    return pages


def _endpoints(doc: dict[str, Any]) -> list[APIEndpointRef]:
    out = []
    for text, _ in _bullets(doc, "api"):
        if m := _ENDPOINT.match(text.strip()):
            out.append(APIEndpointRef(method=m.group(1).upper(), path=m.group(2), summary=(m.group(3) or "").strip()))
    return out


def analyze(payload: dict[str, Any], blackboard: dict[str, Any] | None = None) -> StructuredRequirement:
    doc = payload["document"]
    meta = doc.get("meta", {})
    req_id = str(meta.get("id") or payload.get("requirement_id"))
    feature = str(meta.get("feature") or re.sub(r"[^a-z0-9]+", "-", doc["title"].lower()).strip("-"))
    code = str(meta.get("feature_code") or feature.split("-")[-1]).upper()

    ui_pages = _ui_pages(doc)
    endpoints = _endpoints(doc)
    default_channels = ["ui"] if ui_pages else ["api"]
    acs: list[RawAcceptanceCriterion] = []
    ambiguities: list[Finding] = []
    for text, subs in _bullets(doc, "acceptance criteria"):
        m = _AC_LINE.match(text)
        if not m:
            ambiguities.append(Finding(code="AC_NO_ID", severity="error", message=f"Acceptance criterion without "
                                       f"a stable ID (AC-nnn): '{text[:80]}'"))
            continue
        channels = [c.strip().lower() for c in (m.group(2) or "").split(",") if c.strip()] or default_channels
        api_text = next((s.split(":", 1)[1].strip() for s in subs if s.lower().startswith("api:")), "")
        acs.append(RawAcceptanceCriterion(id=m.group(1).upper(), text=m.group(3).strip(),
                                          channels=[c for c in channels if c in ("ui", "api")], api_text=api_text))

    business_rules = [t for t, _ in _bullets(doc, "business rules")]
    nfr = [t for t, _ in _bullets(doc, "non-functional", "nfr")]
    open_q = [t for t, _ in _bullets(doc, "open questions") if t.strip().lower() not in ("none", "(none)", "n/a")]

    fields = _fields(doc)
    # label inference from UI textboxes when the table has no UI label column
    textboxes = [e.label for p in ui_pages for e in p.elements if e.role == "textbox"]
    for f in fields:
        if not f.label:
            f.label = next((lbl for lbl in textboxes if lbl.lower() == f.name.lower()), None)

    for ac in acs:
        for term in vague_terms(ac.text):
            ambiguities.append(Finding(code="VAGUE_TERM", severity="error", artifact_id=ac.id,
                                       message=f"{ac.id} uses the vague term '{term}'; state a measurable outcome"))
    for i, br in enumerate(business_rules, 1):
        for term in vague_terms(br):
            ambiguities.append(Finding(code="VAGUE_TERM", severity="warning", artifact_id=f"BR-{i:03d}",
                                       message=f"Business rule '{br}' uses the vague term '{term}'"))
    for i, n in enumerate(nfr, 1):
        if not has_number(n) and not re.search(r"never|must not|asvs|owasp", n, re.I):
            ambiguities.append(Finding(code="NFR_NOT_MEASURABLE", severity="warning", artifact_id=f"NFR-{i:03d}",
                                       message=f"Non-functional requirement has no measurable threshold: '{n}'"))
    if not acs:
        open_q.append("No acceptance criteria were provided. Please add testable acceptance criteria.")
    if not fields and ui_pages:
        ambiguities.append(Finding(code="NO_INPUT_FIELDS", severity="warning",
                                   message="UI pages are described but no input fields/validation rules are given"))

    return StructuredRequirement(
        id=req_id, title=str(meta.get("title") or doc["title"]), feature=feature, feature_code=code,
        priority=str(meta.get("priority", "P2")) if str(meta.get("priority", "P2")) in ("P1", "P2", "P3") else "P2",
        user_story=_section(doc, "user story"), objective=_section(doc, "objective"),
        business_rules=business_rules, input_fields=fields, acceptance_criteria=acs, ui_pages=ui_pages,
        api_endpoints=endpoints, non_functional=nfr,
        dependencies=[t for t, _ in _bullets(doc, "dependencies")], open_questions=open_q,
        ambiguities=ambiguities, source_file=doc.get("source_file", ""), source_hash=doc.get("source_hash", ""),
        analysed_by=OFFLINE_LABEL,
    )
