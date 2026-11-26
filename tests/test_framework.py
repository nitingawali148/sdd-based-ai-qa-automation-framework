"""Framework unit tests (no LLM, no browser, no approvals): python -m pytest tests -p no:cacheprovider"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from core.config import ROOT
from core.models import FeatureSpec, TestCaseSet
from generators.analysis import classify
from generators.code_renderer import merge_regions, parse_regions
from generators.requirement_analyzer import analyze
from generators.spec_builder import build_spec
from generators.test_design import build_test_cases, design_scenarios
from parsers.openapi_parser import OpenAPISpec
from parsers.requirement_parser import parse_requirement
from traceability.id_allocator import merge_scenarios, merge_test_cases
from utils.test_data import resolve
from validators.code_validator import validate_code
from validators.coverage_validator import validate_coverage
from validators.spec_validator import validate_spec
from versioning.spec_diff import diff_specs

REQS = ROOT / "specifications" / "requirements"
OPENAPI = str(ROOT / "specifications" / "api" / "openapi.yaml")


def _spec(req_id: str) -> tuple[FeatureSpec, object]:
    doc = parse_requirement(REQS / f"{req_id}.md")
    req = analyze({"document": doc.to_payload()})
    return build_spec({"openapi_path": OPENAPI}, {"requirement_analysis": req}), req


def test_requirement_parsing_keeps_ids_and_channels() -> None:
    req = analyze({"document": parse_requirement(REQS / "REQ-001.md").to_payload()})
    assert [a.id for a in req.acceptance_criteria] == [f"AC-00{i}" for i in range(1, 7)]
    assert req.acceptance_criteria[0].channels == ["ui", "api"]
    assert req.input_fields[1].min_length == 8 and req.input_fields[1].max_length == 64


def test_valid_spec_passes_and_ambiguous_spec_is_blocked() -> None:
    spec, req = _spec("REQ-001")
    assert validate_spec(spec, req, OpenAPISpec.load()).passed
    bad, bad_req = _spec("REQ-003")
    report = validate_spec(bad, bad_req, OpenAPISpec.load())
    assert not report.passed
    assert {"OPEN_QUESTION", "AC_VAGUE", "AC_UI_EXPECTATION_UNMEASURABLE"} <= {f.code for f in report.errors}


def test_invented_acceptance_criterion_is_rejected() -> None:
    spec, req = _spec("REQ-001")
    extra = copy.deepcopy(spec.acceptance_criteria[0])
    extra.id = "AC-099"
    spec.acceptance_criteria.append(extra)
    codes = {f.code for f in validate_spec(spec, req, OpenAPISpec.load()).errors}
    assert "AC_NOT_IN_REQUIREMENT" in codes


def test_api_binding_from_openapi() -> None:
    spec, _ = _spec("REQ-002")
    by_id = {a.id: a for a in spec.acceptance_criteria}
    assert (by_id["AC-007"].api.method, by_id["AC-007"].inputs) == ("PATCH", {"role": "valid"})
    assert by_id["AC-009"].api.auth is False and by_id["AC-009"].expected_api.status_code == 401
    assert by_id["AC-002"].api.precondition == "duplicate"


def _design(spec: FeatureSpec, only: list[str] | None = None, existing=None):  # type: ignore[no-untyped-def]
    sc = design_scenarios({"spec": spec.model_dump(mode="json"), "only_ac_ids": only or []})
    tc = build_test_cases({"spec": spec.model_dump(mode="json")}, {"test_scenarios": sc})
    valid = {a.id for a in spec.acceptance_criteria}
    sc = merge_scenarios(spec.feature_code, existing[0] if existing else None, sc, set(only) if only else None, valid)
    tc = merge_test_cases(spec.feature_code, existing[1] if existing else None, tc, sc, set(only) if only else None)
    return sc, tc


def test_full_coverage_and_boundary_companion() -> None:
    spec, _ = _spec("REQ-001")
    sc, tc = _design(spec)
    assert validate_coverage(spec, sc, tc).passed
    assert any(s.key.startswith("AC-006:ui:at_min") and s.expected.negate for s in sc.scenarios)
    assert all(t.automation_id for t in tc.test_cases)


def test_selective_regeneration_preserves_unaffected_ids() -> None:
    spec, _ = _spec("REQ-001")
    sc0, tc0 = _design(spec)
    new = copy.deepcopy(spec)
    new.ac("AC-002").expected_ui.value = "Incorrect email or password"
    changes, _, _ = diff_specs(spec, new)
    assert [c.ac_id for c in changes] == ["AC-002"]
    sc1, tc1 = _design(new, ["AC-002"], (copy.deepcopy(sc0), copy.deepcopy(tc0)))
    assert [t.id for t in tc1.test_cases] == [t.id for t in tc0.test_cases]
    changed = [b.id for a, b in zip(tc0.test_cases, tc1.test_cases, strict=True) if a != b]
    assert changed and all("AC-002" in next(t for t in tc1.test_cases if t.id == c).ac_ids for c in changed)


def test_region_merge_keeps_unselected_regions_verbatim() -> None:
    old = "H\n\n# >>> sdd:begin A-1\nold a\n# <<< sdd:end A-1\n\n# >>> sdd:begin A-2\nold b\n# <<< sdd:end A-2\n"
    new = {"A-1": "# >>> sdd:begin A-1\nnew a\n# <<< sdd:end A-1\n", "A-2": "# >>> sdd:begin A-2\nnew b\n# <<< sdd:end A-2\n"}
    merged = parse_regions(merge_regions("H", old, new, {"A-1"}, ["A-1", "A-2"], set()))
    assert "new a" in merged["A-1"] and "old b" in merged["A-2"]


def test_code_validator_rejects_unsafe_and_untraced_code(tmp_path: Path) -> None:
    f = tmp_path / "tests" / "test_x.py"
    f.parent.mkdir()
    f.write_text("import subprocess\n\ndef test_a():\n    password = 'hunter22'\n", encoding="utf-8")
    report = validate_code("SPEC-X-001", [f], tmp_path, TestCaseSet(spec_id="SPEC-X-001", spec_version="1.0"))
    codes = {x.code for x in report.findings}
    assert {"FORBIDDEN_IMPORT", "HARDCODED_SECRET", "MISSING_TRACE_MARKER"} <= codes and not report.passed


@pytest.mark.parametrize(("message", "category"), [
    ("httpx.ConnectError: Connection refused", "ENVIRONMENT_ISSUE"),
    ("SDD-EXPECTED status 409 but got 201; actual body: {}", "APPLICATION_DEFECT"),
    ("TimeoutError: waiting for get_by_label('Email')", "AUTOMATION_ISSUE"),
    ("TestDataError: TEST-DATA: environment variable X is not set", "TEST_DATA_ISSUE"),
])
def test_failure_classification(message: str, category: str) -> None:
    item = classify({"message": message, "error_type": "", "ac_ids": ["AC-001"]}, {})
    assert item.category == category


def test_spec_drift_classification() -> None:
    item = classify({"message": "SDD-EXPECTED message \"New\" to be displayed; actual visible messages: ['Old']",
                     "ac_ids": ["AC-002"]}, {"AC-002": "CHG-001"})
    assert item.category == "SPEC_IMPLEMENTATION_DRIFT" and item.actual == "['Old']"


def test_test_data_expressions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDD_X", "v")
    assert resolve("${env:SDD_X}") == "v"
    assert resolve("${repeat:x:7}") == "x" * 7
    assert resolve("${omit}") is None
    assert resolve("${faker:unique_email}").endswith("@example.test")
