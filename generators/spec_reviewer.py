"""Specification Validation Agent rules (offline): review a spec and explain the findings."""

from __future__ import annotations

from typing import Any

from core.models import FeatureSpec, Finding, SpecReview, StructuredRequirement
from parsers.openapi_parser import OpenAPISpec
from validators.spec_validator import validate_spec


def review(payload: dict[str, Any], blackboard: dict[str, Any] | None = None) -> SpecReview:
    spec = FeatureSpec.model_validate(payload["spec"])
    req = StructuredRequirement.model_validate(payload["requirement"]) if payload.get("requirement") else None
    openapi = None
    if payload.get("openapi_path"):
        from pathlib import Path
        openapi = OpenAPISpec.load(Path(payload["openapi_path"]))
    report = validate_spec(spec, req, openapi)
    # The offline reviewer adds only observations the hard rules do not make; rule findings are merged by the flow.
    findings: list[Finding] = []
    messages: dict[str, list[str]] = {}
    for ac in spec.acceptance_criteria:
        if ac.expected_ui and ac.expected_ui.kind == "message":
            messages.setdefault(ac.expected_ui.value, []).append(ac.id)
    for msg, ids in messages.items():
        if len(ids) > 1:
            findings.append(Finding(code="SHARED_MESSAGE", severity="info", source="ai", artifact_id=",".join(ids),
                                    message=f"{', '.join(ids)} expect the same message \"{msg}\". Confirm this is "
                                            "intentional (e.g. not revealing which credential was wrong)."))
    errors = len(report.errors)
    summary = (f"{spec.id} v{spec.version}: {len(spec.acceptance_criteria)} acceptance criteria reviewed, "
               f"{errors} blocking issue(s), {len(report.warnings)} warning(s). "
               + ("Ready for human approval." if errors == 0 else "Return to the author for clarification."))
    return SpecReview(spec_id=spec.id, findings=findings, summary=summary)
