"""Deterministic code rendering: automation designs -> Playwright POM / HTTPX pytest code.

Agents *design* (locators, flows, assertions); this module *writes* the code from Jinja templates, so the
generated code is reproducible and reviewable. Each test lives in a marked region:

    # >>> sdd:begin UI-TEST-LOGIN-002
    ...
    # <<< sdd:end UI-TEST-LOGIN-002

Selective regeneration replaces only the regions of impacted tests; all others are preserved verbatim.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from core.artifact_manager import templates
from core.models import (
    APIAutomationDesign,
    FeatureSpec,
    PageObjectDesign,
    TestCaseSet,
    UIAutomationDesign,
)
from generators.text_rules import snake

REGION = re.compile(r"^# >>> sdd:begin (?P<id>[A-Z0-9-]+)\n(?P<body>.*?)^# <<< sdd:end (?P=id)\n", re.S | re.M)


def code_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def parse_regions(text: str) -> dict[str, str]:
    return {m.group("id"): m.group(0) for m in REGION.finditer(text)}


def merge_regions(header: str, existing_text: str | None, new_regions: dict[str, str],
                  regenerate: set[str] | None, order: list[str], drop: set[str]) -> str:
    """Rebuild a test module: regenerate selected regions, keep the rest verbatim, drop obsolete ones."""
    old = parse_regions(existing_text or "")
    parts = [header.rstrip() + "\n"]
    for aid in order:
        if aid in drop:
            continue
        if aid in old and regenerate is not None and aid not in regenerate:
            parts.append(old[aid])
        elif aid in new_regions:
            parts.append(new_regions[aid])
        elif aid in old:
            parts.append(old[aid])
    return "\n\n".join(p.rstrip() + "\n" for p in parts)


# ----------------------------------------------------------------------------- page objects
def render_page_object(page: PageObjectDesign, spec: FeatureSpec) -> str:
    return templates().get_template("page_object.py.j2").render(page=page, spec=spec)


# ----------------------------------------------------------------------------- UI tests
def render_ui_regions(design: UIAutomationDesign, spec: FeatureSpec, cases: TestCaseSet) -> dict[str, str]:
    tpl = templates().get_template("ui_test.py.j2")
    pages = {p.page: p for p in design.pages}
    by_tc = {t.id: t for t in cases.test_cases}
    out = {}
    for t in design.tests:
        tc = by_tc[t.test_case_id]
        page = pages[t.start_page]
        target = pages.get(t.assertion.value) if t.assertion.kind == "navigate" else None
        fill = {f: cls for f, cls in t.fill.items() if f in page.form_fields}
        out[t.automation_id] = tpl.render(t=t, tc=tc, spec=spec, page=page, target=target, fill=fill,
                                          var=snake(page.page) + "_page", feature=spec.feature)
    return out


def ui_header(spec: FeatureSpec, design: UIAutomationDesign) -> str:
    return templates().get_template("ui_module_header.py.j2").render(spec=spec, pages=design.pages)


# ----------------------------------------------------------------------------- API tests
def render_api_regions(design: APIAutomationDesign, spec: FeatureSpec, cases: TestCaseSet) -> dict[str, str]:
    tpl = templates().get_template("api_test.py.j2")
    by_tc = {t.id: t for t in cases.test_cases}
    out = {}
    for t in design.tests:
        tc = by_tc[t.test_case_id]
        collection = re.sub(r"/\{[^}]+\}$", "", t.path)
        out[t.automation_id] = tpl.render(t=t, tc=tc, spec=spec, collection=collection)
    return out


def api_header(spec: FeatureSpec) -> str:
    return templates().get_template("api_module_header.py.j2").render(spec=spec)


def ui_test_file(root: Path, spec: FeatureSpec) -> Path:
    return root / f"test_{snake(spec.feature)}.py"


def api_test_file(root: Path, spec: FeatureSpec) -> Path:
    return root / f"test_{snake(spec.feature)}_api.py"
