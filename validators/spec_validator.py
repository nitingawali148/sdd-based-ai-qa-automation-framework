"""Deterministic specification validation: the hard gate before human approval.

Errors block the lifecycle. An agent's review can add findings but can never remove a rule finding.
"""

from __future__ import annotations

import re
from collections import defaultdict

from core.config import ROOT, settings
from core.models import FeatureSpec, Finding, StructuredRequirement, ValidationReport
from generators.text_rules import has_number, similarity, vague_terms
from parsers.openapi_parser import OpenAPISpec


def validate_spec(spec: FeatureSpec, requirement: StructuredRequirement | None = None,
                  openapi: OpenAPISpec | None = None) -> ValidationReport:
    cfg = settings().section("validation")
    findings: list[Finding] = []

    def add(code: str, severity: str, message: str, artifact_id: str = "") -> None:
        findings.append(Finding(code=code, severity=severity, message=message, artifact_id=artifact_id))  # type: ignore[arg-type]

    # --- identity & traceability -------------------------------------------------------------
    if not re.fullmatch(r"SPEC-[A-Z0-9]+-\d{3}", spec.id):
        add("SPEC_ID_FORMAT", "error", f"Specification ID '{spec.id}' must match SPEC-<CODE>-nnn", spec.id)
    if not re.fullmatch(r"\d+\.\d+", spec.version):
        add("SPEC_VERSION_FORMAT", "error", f"Version '{spec.version}' must be <major>.<minor>", spec.id)
    if not spec.requirement_ids:
        add("SPEC_NO_REQUIREMENT", "error", "Specification does not reference a requirement", spec.id)
    if not spec.acceptance_criteria:
        add("SPEC_NO_AC", "error", "Specification has no acceptance criteria", spec.id)
    for q in spec.open_questions:
        add("OPEN_QUESTION", "error", f"Open question must be resolved before approval: {q}", spec.id)

    # --- completeness: no acceptance criterion of the requirement may be dropped ---------------------
    if requirement is not None:
        expected_ids = {a.id for a in requirement.acceptance_criteria}
        source = ROOT / requirement.source_file if requirement.source_file else None
        if source is not None and source.exists() and source.suffix.lower() in (".md", ".yaml", ".yml", ".json"):
            # independent check against the raw document, so a lossy analysis step cannot hide a dropped AC
            raw_ids = set(re.findall(r"\b(AC-\d{3})\b", source.read_text(encoding="utf-8")))
            for missing in sorted(raw_ids - expected_ids):
                add("AC_LOST_IN_ANALYSIS", "error", f"{missing} is in {requirement.source_file} but missing from the "
                    "structured requirement", missing)
            expected_ids |= raw_ids
        for missing in sorted(expected_ids - {a.id for a in spec.acceptance_criteria}):
            add("AC_MISSING_FROM_SPEC", "error", f"{missing} from requirement {requirement.id} is missing from the "
                "specification (acceptance criteria must not be dropped)", missing)

    seen: set[str] = set()
    field_names = {f.name for f in spec.inputs}
    page_names = {p.name for p in spec.ui_pages}
    raw_by_id = {a.id: a for a in requirement.acceptance_criteria} if requirement else {}

    for ac in spec.acceptance_criteria:
        if ac.id in seen:
            add("AC_DUPLICATE_ID", "error", f"Duplicate acceptance criterion ID {ac.id}", ac.id)
        seen.add(ac.id)
        if not re.fullmatch(r"AC-\d{3}", ac.id):
            add("AC_ID_FORMAT", "error", f"AC ID '{ac.id}' must match AC-nnn", ac.id)
        # AI must not invent acceptance criteria
        if requirement is not None:
            raw = raw_by_id.get(ac.id)
            if raw is None:
                add("AC_NOT_IN_REQUIREMENT", "error", f"{ac.id} does not exist in requirement {requirement.id} "
                    "(acceptance criteria must not be invented)", ac.id)
            elif similarity(raw.text, ac.source_text or f"{ac.given} {ac.when} {ac.then}") < cfg.get(
                    "ac_trace_similarity", 0.55):
                add("AC_DIVERGES_FROM_REQUIREMENT", "error",
                    f"{ac.id} no longer matches the requirement text; re-run analysis or update the requirement", ac.id)
        if not ac.when or not ac.then:
            add("AC_NOT_TESTABLE", "error", f"{ac.id} is not in Given/When/Then form: '{ac.source_text[:90]}'", ac.id)
        for term in vague_terms(f"{ac.when} {ac.then}"):
            add("AC_VAGUE", "error", f"{ac.id} uses the vague term '{term}'. State the exact expected outcome.",
                ac.id)
        if not ac.channels:
            add("AC_NO_CHANNEL", "error", f"{ac.id} does not say whether it is verified via UI or API", ac.id)
        if "ui" in ac.channels:
            if not spec.ui_pages:
                add("AC_UI_NO_PAGES", "error", f"{ac.id} is a UI criterion but the spec defines no UI pages", ac.id)
            if not ac.expected_ui or ac.expected_ui.kind == "unknown":
                add("AC_UI_EXPECTATION_UNMEASURABLE", "error",
                    f"{ac.id}: expected UI result is not measurable ('{ac.then}'). Quote the exact message or name "
                    "the target page.", ac.id)
            if ac.start_page and ac.start_page not in page_names:
                add("AC_UNKNOWN_PAGE", "error", f"{ac.id} starts on unknown page '{ac.start_page}'", ac.id)
            if ac.expected_ui and ac.expected_ui.kind == "navigate" and ac.expected_ui.value not in page_names:
                add("AC_UNKNOWN_PAGE", "error", f"{ac.id} navigates to unknown page '{ac.expected_ui.value}'", ac.id)
        if "api" in ac.channels:
            if not ac.api:
                add("AC_API_UNBOUND", "error", f"{ac.id} is an API criterion but no endpoint could be bound", ac.id)
            elif openapi is not None and openapi.operation(ac.api.method, ac.api.path) is None:
                add("AC_API_NOT_IN_OPENAPI", "error",
                    f"{ac.id}: {ac.api.method} {ac.api.path} is not defined in the OpenAPI contract", ac.id)
            if not ac.expected_api or ac.expected_api.kind != "status":
                add("AC_API_EXPECTATION_UNMEASURABLE", "error",
                    f"{ac.id}: expected API result has no status code. Add e.g. '- API: returns 401'.", ac.id)
            elif ac.api and openapi is not None:
                op = openapi.operation(ac.api.method, ac.api.path)
                if op and str(ac.expected_api.status_code) not in op["responses"]:
                    add("AC_STATUS_NOT_IN_OPENAPI", "warning",
                        f"{ac.id}: status {ac.expected_api.status_code} is not documented for "
                        f"{ac.api.method} {ac.api.path}", ac.id)
        for name in ac.inputs:
            if name not in field_names:
                add("AC_UNKNOWN_FIELD", "error", f"{ac.id} refers to unknown input field '{name}'", ac.id)

    # --- conflicts: same channel + same stimulus but different expectation -----------------------
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    expectations: dict[tuple[str, str], set[str]] = defaultdict(set)
    for ac in spec.acceptance_criteria:
        for ch in ac.channels:
            api_key = f"{ac.api.method} {ac.api.path} {ac.api.auth} {ac.api.precondition}" if ac.api else ""
            key = (ch, f"{sorted(ac.inputs.items())}|{api_key}|{ac.start_page}")
            exp = ac.expected_ui if ch == "ui" else ac.expected_api
            if exp and exp.kind != "unknown":
                groups[key].append(ac.id)
                expectations[key].add(exp.model_dump_json())
    for key, ids in groups.items():
        if len(expectations[key]) > 1:
            add("AC_CONFLICT", "error", f"{', '.join(ids)} describe the same {key[0].upper()} action with different "
                "expected results", ",".join(ids))

    # --- missing scenarios (coverage of the inputs) ---------------------------------------------
    negative_fields = {name for ac in spec.acceptance_criteria for name, cls in ac.inputs.items() if cls != "valid"}
    for f in spec.inputs:
        if f.required and f.name not in negative_fields:
            add("MISSING_NEGATIVE_SCENARIO", "warning",
                f"No acceptance criterion covers an invalid/empty value for required field '{f.name}'", f.name)
        if (f.min_length or f.max_length) and not any(
                ac.inputs.get(f.name) in ("too_short", "too_long") for ac in spec.acceptance_criteria):
            add("MISSING_BOUNDARY_SCENARIO", "warning",
                f"Field '{f.name}' has length rules ({f.description}) but no boundary acceptance criterion", f.name)
        if f.type == "email" and not any(ac.inputs.get(f.name) in ("malformed", "invalid")
                                         for ac in spec.acceptance_criteria):
            add("MISSING_FORMAT_SCENARIO", "info", f"No acceptance criterion covers a malformed '{f.name}'", f.name)

    # --- business rules & NFRs --------------------------------------------------------------------
    for br in spec.business_rules:
        for term in vague_terms(br.text):
            add("BR_VAGUE", "warning", f"{br.id} uses the vague term '{term}': '{br.text}'", br.id)
    for nfr in spec.non_functional:
        if not has_number(nfr.text) and not re.search(r"never|must not|asvs|owasp", nfr.text, re.I):
            add("NFR_NOT_MEASURABLE", "warning", f"{nfr.id} has no measurable threshold: '{nfr.text}'", nfr.id)

    block_warn = bool(cfg.get("block_on_warnings", False))
    passed = not any(f.severity == "error" or (block_warn and f.severity == "warning") for f in findings)
    return ValidationReport(spec_id=spec.id, spec_version=spec.version, passed=passed, findings=findings)
