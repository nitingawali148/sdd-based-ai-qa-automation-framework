"""Specification versioning and human approval gates.

* Approved versions are immutable snapshots: specifications/approved/<SPEC>/v<version>/ (files made read-only).
* An approval binds a stage (spec | test_cases | scripts) to the exact content hash a human reviewed.
  Editing the artifact afterwards silently invalidates the approval.
* Nothing in the framework calls `approve()` except the CLI command a human runs.
"""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

from core.artifact_manager import ArtifactManager, read_yaml, write_yaml
from core.config import ROOT, settings
from core.logger import audit, log
from core.models import ApprovalRecord, FeatureSpec, SpecStatus, TestCaseSet, stable_hash
from core.script_manifest import records_from_files
from versioning.git_manager import commit_snapshot


class ApprovalError(RuntimeError):
    pass


def bump(version: str, kind: str = "minor") -> str:
    major, minor = (int(x) for x in version.split("."))
    return f"{major + 1}.0" if kind == "major" else f"{major}.{minor + 1}"


def test_cases_hash(cases: TestCaseSet) -> str:
    return stable_hash([t.model_dump(mode="json") for t in cases.test_cases])


def scripts_hash(records: list) -> str:  # type: ignore[type-arg]
    return stable_hash([(r.automation_id, r.code_hash) for r in records])


class VersionManager:
    def __init__(self) -> None:
        self.am = ArtifactManager()

    # ------------------------------------------------------------------ snapshots
    def version_dir(self, spec_id: str, version: str) -> Path:
        return self.am.approved / spec_id / f"v{version}"

    def approved_versions(self, spec_id: str) -> list[str]:
        d = self.am.approved / spec_id
        if not d.exists():
            return []
        vs = [p.name[1:] for p in d.iterdir() if p.is_dir() and p.name.startswith("v")]
        return sorted(vs, key=lambda v: tuple(int(x) for x in v.split(".")))

    def latest_approved_version(self, spec_id: str) -> str | None:
        vs = self.approved_versions(spec_id)
        return vs[-1] if vs else None

    def load_approved(self, spec_id: str, version: str | None = None) -> FeatureSpec | None:
        version = version or self.latest_approved_version(spec_id)
        if not version:
            return None
        return self.am.load_spec_dir(self.version_dir(spec_id, version))

    def approvals(self, spec_id: str, version: str) -> list[ApprovalRecord]:
        data = read_yaml(self.version_dir(spec_id, version) / "approvals.yaml") or []
        return [ApprovalRecord.model_validate(r) for r in data]

    def _record(self, rec: ApprovalRecord) -> None:
        path = self.version_dir(rec.spec_id, rec.spec_version) / "approvals.yaml"
        data = read_yaml(path) or []
        data.append(rec.model_dump(mode="json"))
        write_yaml(path, data, f"Human approvals for {rec.spec_id} v{rec.spec_version} (append-only)")
        audit.write("approval", stage=rec.stage, spec_id=rec.spec_id, version=rec.spec_version,
                    approved_by=rec.approved_by, artifact_hash=rec.artifact_hash, comment=rec.comment)

    # ------------------------------------------------------------------ status queries
    def spec_is_approved(self, spec_id: str) -> bool:
        """The working spec is exactly the latest approved version."""
        latest = self.latest_approved_version(spec_id)
        if not latest:
            return False
        working = self.am.load_spec(spec_id)
        approved = self.load_approved(spec_id, latest)
        return bool(approved and working.version == latest and working.content_hash() == approved.content_hash())

    def current_hash(self, spec_id: str, stage: str) -> str:
        if stage == "spec":
            return self.am.load_spec(spec_id).content_hash()
        if stage == "test_cases":
            cases = self.am.load(spec_id, "test_cases")
            return test_cases_hash(cases) if cases else ""
        automation = self.am.load(spec_id, "automation")
        return scripts_hash(automation.scripts) if automation and automation.scripts else ""

    def is_approved(self, spec_id: str, stage: str) -> bool:
        if not self.spec_is_approved(spec_id):
            return False
        if stage == "spec":
            return True
        version = self.latest_approved_version(spec_id) or ""
        recs = [r for r in self.approvals(spec_id, version) if r.stage == stage]
        return bool(recs) and recs[-1].artifact_hash == self.current_hash(spec_id, stage)

    # ------------------------------------------------------------------ approvals (human only)
    def approve(self, spec_id: str, stage: str, approved_by: str, comment: str = "") -> ApprovalRecord:
        if not approved_by or approved_by.strip().lower() in ("agent", "ai", "auto", "system", "crewai"):
            raise ApprovalError("Approvals must name a human reviewer (--by \"Full Name\").")
        if stage not in settings().section("approval").get("required_stages", ["spec", "test_cases", "scripts"]):
            raise ApprovalError(f"Stage '{stage}' is not an approval stage")
        handler = {"spec": self._approve_spec, "test_cases": self._approve_test_cases,
                   "scripts": self._approve_scripts}[stage]
        return handler(spec_id, approved_by.strip(), comment)

    def _approve_spec(self, spec_id: str, by: str, comment: str) -> ApprovalRecord:
        from parsers.openapi_parser import OpenAPISpec
        from validators.spec_validator import validate_spec

        spec = self.am.load_spec(spec_id)
        req = self.am.load_requirement_analysis(spec.requirement_ids[0]) if spec.requirement_ids else None
        openapi_path = settings().path("openapi")
        report = validate_spec(spec, req, OpenAPISpec.load(openapi_path) if openapi_path.exists() else None)
        if not report.passed:
            raise ApprovalError(f"{spec_id} v{spec.version} has {len(report.errors)} blocking validation error(s); "
                                "it cannot be approved. Run the Specification flow and resolve them.")
        vdir = self.version_dir(spec_id, spec.version)
        if vdir.exists():
            raise ApprovalError(f"{spec_id} v{spec.version} is already approved and immutable. Change the "
                                f"specification and run `python main.py change {spec_id}` to create a new version.")
        previous = self.latest_approved_version(spec_id)
        spec.status = SpecStatus.APPROVED
        self.am.save_spec(spec)
        vdir.mkdir(parents=True)
        src = self.am.spec_dir(spec_id)
        files = []
        for name in ("spec.yaml", "acceptance_criteria.yaml", "spec.md"):
            shutil.copy2(src / name, vdir / name)
            (vdir / name).chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
            files.append(vdir / name)
        rec = ApprovalRecord(stage="spec", spec_id=spec_id, spec_version=spec.version, approved_by=by,
                             artifact_hash=spec.content_hash(), comment=comment)
        self._record(rec)
        reg = self.am.registry()["specs"].get(spec_id, {})
        versions = sorted(set(reg.get("approved_versions", [])) | {spec.version},
                          key=lambda v: tuple(int(x) for x in v.split(".")))
        superseded = sorted(set(reg.get("superseded_versions", [])) | ({previous} if previous else set()))
        self.am.update_registry(spec_id, approved_version=spec.version, approved_versions=versions,
                                superseded_versions=superseded, status=SpecStatus.APPROVED.value)
        commit_snapshot(files + [vdir / "approvals.yaml"], f"Approve {spec_id} v{spec.version} by {by}")
        log.info("Approved %s v%s (spec) by %s", spec_id, spec.version, by)
        return rec

    def _approve_test_cases(self, spec_id: str, by: str, comment: str) -> ApprovalRecord:
        from validators.coverage_validator import validate_coverage

        if not self.spec_is_approved(spec_id):
            raise ApprovalError(f"{spec_id}: the working specification is not the approved version")
        spec = self.am.load_spec(spec_id)
        scenarios, cases = self.am.load(spec_id, "scenarios"), self.am.load(spec_id, "test_cases")
        if not cases or not scenarios:
            raise ApprovalError(f"{spec_id}: no test cases yet - run the Test Design flow")
        cov = validate_coverage(spec, scenarios, cases)
        if not cov.passed:
            raise ApprovalError(f"{spec_id}: coverage validation fails ({len(cov.uncovered_acs)} uncovered AC)")
        h = test_cases_hash(cases)
        vdir = self.version_dir(spec_id, spec.version)
        shutil.copy2(self.am.path_of(spec_id, "test_cases"), vdir / f"test_cases.{h}.yaml")
        rec = ApprovalRecord(stage="test_cases", spec_id=spec_id, spec_version=spec.version, approved_by=by,
                             artifact_hash=h, comment=comment)
        self._record(rec)
        return rec

    def _approve_scripts(self, spec_id: str, by: str, comment: str) -> ApprovalRecord:
        from validators.code_validator import validate_code

        if not self.is_approved(spec_id, "test_cases"):
            raise ApprovalError(f"{spec_id}: test cases are not approved (or changed since approval)")
        spec = self.am.load_spec(spec_id)
        staging = settings().path("staging") / spec_id
        files = sorted(p for p in staging.rglob("*.py")) if staging.exists() else []
        if not files:
            raise ApprovalError(f"{spec_id}: no staged scripts - run the Automation flow")
        cases = self.am.load(spec_id, "test_cases")
        report = validate_code(spec_id, files, staging, cases)
        stored = self.am.load(spec_id, "code_validation")
        if not report.passed:
            raise ApprovalError(f"{spec_id}: staged scripts fail code validation ({len(report.findings)} findings)")
        if not stored or stored.bundle_hash != report.bundle_hash:
            raise ApprovalError(f"{spec_id}: staged scripts changed after validation - re-run the Automation flow")
        # promote staged files into the framework and archive the reviewed bundle with the version
        promoted = []
        archive = self.version_dir(spec_id, spec.version) / f"scripts.{report.bundle_hash}"
        for f in files:
            rel = f.relative_to(staging)
            dest = ROOT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            (archive / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, archive / rel)
            promoted.append(dest)
        records = records_from_files(promoted, cases)
        automation = self.am.load(spec_id, "automation")
        automation.scripts = records
        self.am.save(spec_id, "automation", automation)
        shutil.rmtree(staging)
        rec = ApprovalRecord(stage="scripts", spec_id=spec_id, spec_version=spec.version, approved_by=by,
                             artifact_hash=scripts_hash(records), comment=comment)
        self._record(rec)
        log.info("Approved and promoted %d script file(s) for %s", len(promoted), spec_id)
        return rec
