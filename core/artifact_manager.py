"""Reads and writes every SDD artifact. The only module that knows the on-disk layout.

specifications/
  registry.yaml                          spec_id -> feature, requirements, version, status
  requirements/REQ-001.md                raw business requirement (human-authored)
  requirements/analysis/REQ-001.yaml     structured requirement (Requirement Analysis Agent)
  features/<feature>/spec.yaml           feature specification (machine-readable, source of truth)
  features/<feature>/acceptance_criteria.yaml
  features/<feature>/spec.md             human-readable rendering of the two files above
  features/<feature>/validation_report.yaml
  features/<feature>/test_scenarios.yaml
  features/<feature>/test_cases.yaml
  features/<feature>/coverage_report.yaml
  features/<feature>/automation_spec.yaml
  approved/<SPEC>/v<version>/...         immutable approved snapshots + approvals.yaml
  changes/CHG-001.yaml                   change records
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, TypeVar

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel

from core.config import ROOT, settings
from core.models import (
    AcceptanceCriterion,
    AutomationSpec,
    ChangeRecord,
    CodeValidationReport,
    CoverageReport,
    FeatureSpec,
    StructuredRequirement,
    TestCaseSet,
    TestDataSet,
    TestScenarioSet,
    ValidationReport,
    utc_now,
)

M = TypeVar("M", bound=BaseModel)


class _Dumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str_presenter)


def dump_yaml(data: Any) -> str:
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=110)


def write_yaml(path: Path, data: Any, header: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    text = (f"# {header}\n" if header else "") + dump_yaml(data)
    path.write_text(text, encoding="utf-8")
    return path


def read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None


def templates() -> Environment:
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), undefined=StrictUndefined,
                      trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    env.filters["pyrepr"] = repr
    return env


class ArtifactManager:
    def __init__(self) -> None:
        s = settings()
        self.specs_root = s.path("specifications")
        self.requirements = s.path("requirements")
        self.features = s.path("features")
        self.approved = s.path("approved")
        self.changes = s.path("changes")
        self.test_data_dir = s.path("test_data")
        self.registry_path = self.specs_root / "registry.yaml"

    # ------------------------------------------------------------------ registry
    def registry(self) -> dict[str, Any]:
        data = read_yaml(self.registry_path) or {}
        data.setdefault("specs", {})
        return data

    def _save_registry(self, data: dict[str, Any]) -> None:
        write_yaml(self.registry_path, data, "Specification registry - maintained by the framework")

    def update_registry(self, spec_id: str, **fields: Any) -> None:
        reg = self.registry()
        entry = reg["specs"].setdefault(spec_id, {})
        entry.update(fields)
        entry["updated_at"] = utc_now()
        self._save_registry(reg)

    def list_specs(self) -> list[str]:
        return sorted(self.registry()["specs"])

    def feature_of(self, spec_id: str) -> str:
        entry = self.registry()["specs"].get(spec_id)
        if not entry:
            raise KeyError(f"Unknown specification {spec_id}. Known: {', '.join(self.list_specs()) or 'none'}")
        return str(entry["feature"])

    def spec_for_requirement(self, req_id: str) -> str | None:
        for spec_id, entry in self.registry()["specs"].items():
            if req_id in entry.get("requirement_ids", []):
                return str(spec_id)
        return None

    def feature_dir(self, feature: str) -> Path:
        d = self.features / feature
        d.mkdir(parents=True, exist_ok=True)
        return d

    def spec_dir(self, spec_id: str) -> Path:
        return self.feature_dir(self.feature_of(spec_id))

    # ------------------------------------------------------------------ requirements
    def requirement_files(self) -> list[Path]:
        exts = {".md", ".yaml", ".yml", ".json", ".pdf", ".docx"}
        return sorted(p for p in self.requirements.iterdir() if p.is_file() and p.suffix.lower() in exts)

    def find_requirement_file(self, req_id: str) -> Path:
        for p in self.requirement_files():
            if p.stem.upper() == req_id.upper():
                return p
        raise FileNotFoundError(f"No requirement file for {req_id} in {self.requirements}")

    def save_requirement_analysis(self, req: StructuredRequirement) -> Path:
        return write_yaml(self.requirements / "analysis" / f"{req.id}.yaml", req,
                          f"Structured requirement {req.id} - generated by {req.analysed_by}. Review before use.")

    def load_requirement_analysis(self, req_id: str) -> StructuredRequirement | None:
        data = read_yaml(self.requirements / "analysis" / f"{req_id}.yaml")
        return StructuredRequirement.model_validate(data) if data else None

    # ------------------------------------------------------------------ specifications
    def spec_exists(self, spec_id: str) -> bool:
        try:
            return (self.spec_dir(spec_id) / "spec.yaml").exists()
        except KeyError:
            return False

    def save_spec(self, spec: FeatureSpec) -> Path:
        """Write spec.yaml + acceptance_criteria.yaml + spec.md and update the registry."""
        spec.updated_at = utc_now()
        d = self.feature_dir(spec.feature)
        body = spec.model_dump(mode="json", exclude={"acceptance_criteria"})
        write_yaml(d / "spec.yaml", body, f"{spec.id} v{spec.version} - feature specification (source of truth)")
        acs = {"spec_id": spec.id, "spec_version": spec.version,
               "acceptance_criteria": [a.model_dump(mode="json") for a in spec.acceptance_criteria]}
        write_yaml(d / "acceptance_criteria.yaml", acs, f"{spec.id} v{spec.version} - acceptance criteria")
        (d / "spec.md").write_text(self.render_spec_md(spec), encoding="utf-8")
        self.update_registry(spec.id, feature=spec.feature, requirement_ids=spec.requirement_ids,
                             title=spec.title, version=spec.version, status=spec.status.value)
        return d / "spec.yaml"

    def load_spec(self, spec_id: str) -> FeatureSpec:
        d = self.spec_dir(spec_id)
        body = read_yaml(d / "spec.yaml")
        if body is None:
            raise FileNotFoundError(f"{spec_id}: spec.yaml not found in {d}")
        acs = read_yaml(d / "acceptance_criteria.yaml") or {}
        body["acceptance_criteria"] = acs.get("acceptance_criteria", [])
        return FeatureSpec.model_validate(body)

    def load_spec_dir(self, d: Path) -> FeatureSpec:
        body = read_yaml(d / "spec.yaml")
        acs = read_yaml(d / "acceptance_criteria.yaml") or {}
        body["acceptance_criteria"] = acs.get("acceptance_criteria", [])
        return FeatureSpec.model_validate(body)

    def render_spec_md(self, spec: FeatureSpec) -> str:
        return templates().get_template("spec.md.j2").render(spec=spec)

    # ------------------------------------------------------------------ generic feature artifacts
    _FILES: dict[str, tuple[str, type[BaseModel]]] = {
        "validation": ("validation_report.yaml", ValidationReport),
        "scenarios": ("test_scenarios.yaml", TestScenarioSet),
        "test_cases": ("test_cases.yaml", TestCaseSet),
        "coverage": ("coverage_report.yaml", CoverageReport),
        "automation": ("automation_spec.yaml", AutomationSpec),
        "code_validation": ("code_validation_report.yaml", CodeValidationReport),
    }

    def save(self, spec_id: str, kind: str, model: BaseModel) -> Path:
        name, _ = self._FILES[kind]
        return write_yaml(self.spec_dir(spec_id) / name, model, f"{spec_id} - {kind.replace('_', ' ')}")

    def load(self, spec_id: str, kind: str) -> Any:
        name, cls = self._FILES[kind]
        data = read_yaml(self.spec_dir(spec_id) / name)
        return cls.model_validate(data) if data else None

    def path_of(self, spec_id: str, kind: str) -> Path:
        return self.spec_dir(spec_id) / self._FILES[kind][0]

    # ------------------------------------------------------------------ test data
    def save_test_data(self, data: TestDataSet) -> Path:
        return write_yaml(self.test_data_dir / f"{data.feature}.yaml", data,
                          "Test data - values are expressions resolved at runtime; no hard-coded credentials")

    def load_test_data(self, feature: str) -> TestDataSet | None:
        raw = read_yaml(self.test_data_dir / f"{feature}.yaml")
        return TestDataSet.model_validate(raw) if raw else None

    # ------------------------------------------------------------------ change records
    def next_change_id(self) -> str:
        nums = [int(m.group(1)) for p in self.changes.glob("CHG-*.yaml")
                if (m := re.match(r"CHG-(\d+)", p.stem))]
        return f"CHG-{(max(nums) + 1) if nums else 1:03d}"

    def save_change(self, rec: ChangeRecord) -> Path:
        return write_yaml(self.changes / f"{rec.id}.yaml", rec, f"Change record {rec.id} for {rec.spec_id}")

    def load_changes(self, spec_id: str | None = None) -> list[ChangeRecord]:
        out = []
        for p in sorted(self.changes.glob("CHG-*.yaml")):
            rec = ChangeRecord.model_validate(read_yaml(p))
            if spec_id is None or rec.spec_id == spec_id:
                out.append(rec)
        return out

    def open_change(self, spec_id: str) -> ChangeRecord | None:
        pending = [c for c in self.load_changes(spec_id) if c.status in ("PENDING_SPEC_APPROVAL", "REGENERATED")]
        return pending[-1] if pending else None


def ac_index(spec: FeatureSpec) -> dict[str, AcceptanceCriterion]:
    return {a.id: a for a in spec.acceptance_criteria}


artifacts = ArtifactManager
