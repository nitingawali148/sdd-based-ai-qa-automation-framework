"""Specification crews: Requirement Analysis -> Specification Architect, and the Specification Validator."""

from __future__ import annotations

from typing import Any

from core.models import FeatureSpec, SpecReview, StructuredRequirement
from crews.base import run_crew


def run_specification_crew(document: dict[str, Any], spec_meta: dict[str, Any]) -> tuple[StructuredRequirement,
                                                                                          FeatureSpec]:
    """Collaborative crew: the architect receives the analyst's structured requirement as task context."""
    out = run_crew("specification", [
        ("requirement_analysis", {"document": document}),
        ("specification_design", spec_meta),
    ], spec_id=spec_meta.get("spec_id", ""))
    req: StructuredRequirement = out["requirement_analysis"]  # type: ignore[assignment]
    spec: FeatureSpec = out["specification_design"]  # type: ignore[assignment]
    return req, carry_over_facts(req, spec, spec_meta)


def carry_over_facts(req: StructuredRequirement, spec: FeatureSpec, meta: dict[str, Any]) -> FeatureSpec:
    """Deterministic guardrail: facts already stated in the requirement (inputs, UI pages, endpoints, IDs) are
    copied into the spec when an LLM drops them, and page paths are normalised to page names. Nothing new is
    invented; acceptance criteria are still checked by the validator against the requirement."""
    spec.id = meta.get("spec_id") or spec.id or f"SPEC-{req.feature_code}-001"
    spec.version = meta.get("version", spec.version)
    spec.feature, spec.feature_code = req.feature, req.feature_code
    spec.requirement_ids = spec.requirement_ids or [req.id]
    spec.inputs = req.input_fields or spec.inputs
    spec.ui_pages = req.ui_pages or spec.ui_pages
    spec.api_endpoints = req.api_endpoints or spec.api_endpoints
    spec.source_requirement_hash = req.source_hash
    by_path = {p.path.rstrip("/").lower(): p.name for p in spec.ui_pages}
    by_name = {p.name.lower(): p.name for p in spec.ui_pages}

    def page_name(value: str) -> str:
        key = value.strip().rstrip("/").lower()
        return by_path.get(key) or by_name.get(key.removesuffix(" page")) or value

    for ac in spec.acceptance_criteria:
        if ac.start_page:
            ac.start_page = page_name(ac.start_page)
        elif "ui" in ac.channels and spec.ui_pages:
            ac.start_page = next((p.name for p in spec.ui_pages if any(e.role == "textbox" for e in p.elements)),
                                 spec.ui_pages[0].name)
        if ac.expected_ui and ac.expected_ui.kind == "navigate":
            ac.expected_ui.value = page_name(ac.expected_ui.value)
        ac.requirement_id = ac.requirement_id or req.id
    return spec


def run_spec_review_crew(spec: FeatureSpec, requirement: StructuredRequirement | None,
                         openapi_path: str) -> SpecReview:
    out = run_crew("specification-review", [
        ("specification_validation", {"spec": spec.model_dump(mode="json"),
                                      "requirement": requirement.model_dump(mode="json") if requirement else None,
                                      "openapi_path": openapi_path}),
    ], spec_id=spec.id)
    return out["specification_validation"]  # type: ignore[return-value]
