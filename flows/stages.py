"""Lifecycle stage services used by the CrewAI Flows.

Each function consumes the persisted, validated output of the previous stage, calls the relevant crew,
applies deterministic guardrails and persists its own output. Gates are checked by the Flows.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from core.artifact_manager import ArtifactManager, write_yaml
from core.config import ROOT, settings
from core.logger import audit, log
from core.models import (
    AutomationSpec,
    ChangeRecord,
    CodeValidationReport,
    CoverageReport,
    ExecutionRun,
    FailureAnalysisReport,
    FeatureSpec,
    Finding,
    SpecStatus,
    TestCaseSet,
    TestDataSet,
    TestScenarioSet,
    ValidationReport,
    utc_now,
)
from core.script_manifest import verify_scripts
from crews.analysis_crew import run_execution_planning, run_failure_analysis
from crews.automation_crew import run_automation_crew
from crews.specification_crew import run_spec_review_crew, run_specification_crew
from crews.test_design_crew import run_test_design_crew
from generators import code_renderer as cr
from parsers.openapi_parser import OpenAPISpec
from parsers.requirement_parser import parse_requirement
from traceability.id_allocator import merge_scenarios, merge_test_cases
from validators.code_validator import validate_code
from validators.coverage_validator import validate_coverage
from validators.spec_validator import validate_spec
from versioning.version_manager import VersionManager, bump


def _openapi_path() -> str:
    p = settings().path("openapi")
    return str(p) if p.exists() else ""


def _openapi() -> OpenAPISpec | None:
    p = _openapi_path()
    return OpenAPISpec.load(Path(p)) if p else None


def _rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p)


# ============================================================================ 1. specification
def generate_specification(requirement_id: str, regenerate: bool = False) -> tuple[FeatureSpec, bool]:
    """Analyse the requirement and create the spec. Returns (spec, generated?). Never overwrites an existing
    working spec unless `regenerate` is set; never touches approved snapshots."""
    am, vm = ArtifactManager(), VersionManager()
    path = am.find_requirement_file(requirement_id)
    doc = parse_requirement(path)
    existing_id = am.spec_for_requirement(requirement_id)
    if existing_id and am.spec_exists(existing_id) and not regenerate:
        spec = am.load_spec(existing_id)
        if spec.source_requirement_hash and spec.source_requirement_hash != doc.source_hash:
            log.warning("%s changed since %s was generated. Re-run with --regenerate (creates a new version) or "
                        "edit the specification and run `change`.", requirement_id, existing_id)
        return spec, False
    meta: dict[str, Any] = {"openapi_path": _openapi_path(), "version": "1.0"}
    if existing_id:
        meta["spec_id"] = existing_id
        latest = vm.latest_approved_version(existing_id)
        if latest:
            meta["version"] = bump(latest, settings().section("versioning").get("bump_on_change", "minor"))
    payload = doc.to_payload()
    payload["source_file"] = _rel(path)
    requirement, spec = run_specification_crew(payload, meta)
    requirement.source_file = _rel(path)
    spec.status = SpecStatus.DRAFT
    am.save_requirement_analysis(requirement)
    am.save_spec(spec)
    audit.write("artifact", kind="specification", spec_id=spec.id, version=spec.version,
                requirement_id=requirement_id, generated_by=spec.generated_by)
    return spec, True


def validate_specification(spec_id: str) -> ValidationReport:
    """Rule validation (hard gate) + Specification Validation Agent review (advisory)."""
    am, vm = ArtifactManager(), VersionManager()
    spec = am.load_spec(spec_id)
    req = am.load_requirement_analysis(spec.requirement_ids[0]) if spec.requirement_ids else None
    report = validate_spec(spec, req, _openapi())
    review = run_spec_review_crew(spec, req, _openapi_path())
    known = {(f.code, f.artifact_id) for f in report.findings}
    for f in review.findings:
        if (f.code, f.artifact_id) not in known:
            f.source = "ai"
            if f.severity == "error":
                report.passed = False
            report.findings.append(f)
    if review.summary:
        report.findings.append(Finding(code="AGENT_SUMMARY", severity="info", message=review.summary, source="ai"))
    am.save(spec_id, "validation", report)
    if not vm.spec_is_approved(spec_id):
        spec.status = SpecStatus.VALIDATED if report.passed else SpecStatus.NEEDS_CLARIFICATION
        am.save_spec(spec)
    if not report.passed:
        write_clarification_request(spec, report)
    return report


def write_clarification_request(spec: FeatureSpec, report: ValidationReport) -> Path:
    am = ArtifactManager()
    lines = [f"# Clarification request: {spec.id} v{spec.version}", "",
             f"Requirement(s): {', '.join(spec.requirement_ids)}. The specification cannot be approved until these "
             "items are resolved in the requirement or the specification.", "",
             "| # | Severity | Code | Item | Question / issue |", "|---|---|---|---|---|"]
    for i, f in enumerate([f for f in report.findings if f.severity in ("error", "warning")], 1):
        lines.append(f"| {i} | {f.severity} | {f.code} | {f.artifact_id} | {f.message} |")
    path = am.spec_dir(spec.id) / "clarification_request.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ============================================================================ 2. test design
def design_tests(spec_id: str, only_ac_ids: list[str] | None = None) -> tuple[TestScenarioSet, TestCaseSet,
                                                                              CoverageReport]:
    am, vm = ArtifactManager(), VersionManager()
    spec = vm.load_approved(spec_id)
    assert spec is not None, "approved specification required"
    scenarios, cases, data = run_test_design_crew(spec, only_ac_ids)
    scope = set(only_ac_ids) if only_ac_ids else None
    valid_acs = {a.id for a in spec.acceptance_criteria}
    merged_sc = merge_scenarios(spec.feature_code, am.load(spec_id, "scenarios"), scenarios, scope, valid_acs)
    merged_sc.spec_version = spec.version
    merged_tc = merge_test_cases(spec.feature_code, am.load(spec_id, "test_cases"), cases, merged_sc, scope)
    merged_tc.spec_version = spec.version
    am.save(spec_id, "scenarios", merged_sc)
    am.save(spec_id, "test_cases", merged_tc)
    existing = am.load_test_data(spec.feature)
    if existing:  # preserve curated values; add only what is new
        for field, classes in data.fields.items():
            existing.fields.setdefault(field, {})
            for cls, expr in classes.items():
                existing.fields[field].setdefault(cls, expr)
        existing.spec_version = spec.version
        data = TestDataSet.model_validate(existing.model_dump())
    am.save_test_data(data)
    coverage = validate_coverage(spec, merged_sc, merged_tc)
    am.save(spec_id, "coverage", coverage)
    write_test_cases_markdown(spec, merged_tc)
    audit.write("artifact", kind="test_design", spec_id=spec_id, version=spec.version,
                scenarios=len(merged_sc.scenarios), test_cases=len(merged_tc.test_cases),
                selective=bool(scope), scope=sorted(scope or []))
    return merged_sc, merged_tc, coverage


def write_test_cases_markdown(spec: FeatureSpec, cases: TestCaseSet) -> Path:
    lines = [f"# Test cases - {spec.id} v{spec.version} ({spec.title})", "",
             "Generated from `test_cases.yaml`; approve with `python main.py approve "
             f"{spec.id} --stage test_cases --by \"<name>\"`.", ""]
    for t in cases.test_cases:
        lines += [f"## {t.id}: {t.title}" + ("  _(obsolete)_" if t.status != "active" else ""),
                  f"- **AC:** {', '.join(t.ac_ids)} | **Scenario:** {t.scenario_id} | **Channel:** {t.channel.upper()} "
                  f"| **Priority:** {t.priority} | **Automation:** {t.automation_id} | **Spec version:** {t.spec_version}",
                  "- **Preconditions:** " + "; ".join(t.preconditions), "", "| # | Action | Target | Data | Expected |",
                  "|---|---|---|---|---|"]
        lines += [f"| {s.n} | {s.action} | {s.target} | {s.data} | {s.expected} |" for s in t.steps]
        lines += ["", f"**Expected result:** {t.expected_result}", ""]
    path = ArtifactManager().spec_dir(spec.id) / "test_cases.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ============================================================================ 3. automation
def generate_automation(spec_id: str, only_test_case_ids: list[str] | None = None) -> tuple[CodeValidationReport,
                                                                                            list[str]]:
    am, vm = ArtifactManager(), VersionManager()
    spec = vm.load_approved(spec_id)
    cases: TestCaseSet = am.load(spec_id, "test_cases")
    assert spec is not None and cases is not None
    active = [t for t in cases.test_cases if t.status == "active"]
    in_scope = [t for t in active if not only_test_case_ids or t.id in only_test_case_ids]
    need_ui = any(t.channel == "ui" for t in in_scope)
    need_api = any(t.channel == "api" for t in in_scope)
    ui_design, api_design = run_automation_crew(spec, cases, _openapi_path(), need_ui, need_api, only_test_case_ids)

    automation: AutomationSpec = am.load(spec_id, "automation") or AutomationSpec(
        spec_id=spec_id, spec_version=spec.version, feature=spec.feature)
    if ui_design:
        if automation.ui and only_test_case_ids:
            keep = [t for t in automation.ui.tests if t.test_case_id not in {d.test_case_id for d in ui_design.tests}]
            ui_design.tests = sorted(keep + ui_design.tests, key=lambda t: t.automation_id)
        automation.ui = ui_design
    if api_design:
        if automation.api and only_test_case_ids:
            keep = [t for t in automation.api.tests if t.test_case_id not in {d.test_case_id for d in api_design.tests}]
            api_design.tests = sorted(keep + api_design.tests, key=lambda t: t.automation_id)
        automation.api = api_design
    active_ids = {t.id for t in active}
    if automation.ui:
        automation.ui.tests = [t for t in automation.ui.tests if t.test_case_id in active_ids]
    if automation.api:
        automation.api.tests = [t for t in automation.api.tests if t.test_case_id in active_ids]
    automation.spec_version = spec.version
    automation.updated_at = utc_now()
    am.save(spec_id, "automation", automation)

    staging = settings().path("staging") / spec_id
    if staging.exists():
        import shutil
        shutil.rmtree(staging)
    staged: list[Path] = []
    regenerate = {t.automation_id for t in in_scope} if only_test_case_ids else None
    obsolete = {t.automation_id for t in cases.test_cases if t.status != "active" and t.automation_id}

    def stage(rel: str, text: str, always: bool) -> None:
        current = ROOT / rel
        if not always and current.exists() and current.read_text(encoding="utf-8") == text:
            return
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        staged.append(dest)

    if automation.ui and automation.ui.tests:
        for page in automation.ui.pages:
            stage(f"ui/pages/{page.module}.py", cr.render_page_object(page, spec), always=False)
        regions = cr.render_ui_regions(automation.ui, spec, cases)
        target = cr.ui_test_file(ROOT / "ui" / "tests", spec)
        order = [t.automation_id for t in sorted(automation.ui.tests, key=lambda t: t.automation_id)]
        text = cr.merge_regions(cr.ui_header(spec, automation.ui),
                                target.read_text(encoding="utf-8") if target.exists() else None,
                                regions, regenerate, order, obsolete)
        stage(_rel(target), text, always=True)
    if automation.api and automation.api.tests:
        regions = cr.render_api_regions(automation.api, spec, cases)
        target = cr.api_test_file(ROOT / "api" / "tests", spec)
        order = [t.automation_id for t in sorted(automation.api.tests, key=lambda t: t.automation_id)]
        text = cr.merge_regions(cr.api_header(spec), target.read_text(encoding="utf-8") if target.exists() else None,
                                regions, regenerate, order, obsolete)
        stage(_rel(target), text, always=True)

    report = validate_code(spec_id, staged, staging, cases)
    am.save(spec_id, "code_validation", report)
    audit.write("artifact", kind="automation", spec_id=spec_id, staged=[_rel(p) for p in staged],
                selective=bool(only_test_case_ids), passed=report.passed)
    return report, [_rel(p) for p in staged]


# ============================================================================ 4. execution
def next_execution_id() -> str:
    d = settings().path("executions")
    nums = [int(m.group(1)) for p in d.glob("EXEC-*.json") if (m := re.match(r"EXEC-(\d+)", p.stem))]
    return f"EXEC-{(max(nums) + 1) if nums else 1:04d}"


def runnable_specs(spec_ids: list[str] | None) -> tuple[list[str], list[str]]:
    """Specs whose scripts are approved and unmodified. Returns (runnable, problems)."""
    am, vm = ArtifactManager(), VersionManager()
    runnable, problems = [], []
    for sid in spec_ids or am.list_specs():
        if not vm.is_approved(sid, "scripts"):
            problems.append(f"{sid}: scripts are not approved for the current specification version")
            continue
        automation = am.load(sid, "automation")
        issues = verify_scripts(automation.scripts if automation else [])
        if issues:
            problems += [f"{sid}: {i}" for i in issues]
            continue
        runnable.append(sid)
    return runnable, problems


def execute_tests(spec_ids: list[str], test_case_ids: list[str] | None = None, suites: list[str] | None = None,
                  allow_destructive: bool = False, environment: str = "", allow_production: bool = False,
                  ) -> ExecutionRun:
    am = ArtifactManager()
    plan = run_execution_planning({"spec_ids": spec_ids, "test_case_ids": test_case_ids or [],
                                   "suites": suites or []})
    exec_id = next_execution_id()
    exec_cfg = settings().section("execution")
    results_file = settings().path("executions") / f"{exec_id}.json"
    out_dir = ROOT / "output" / "test-results" / exec_id
    files = sorted({r.file for sid in spec_ids for r in (am.load(sid, "automation").scripts or [])})
    cmd = [sys.executable, "-m", "pytest", *files, "--exec-id", exec_id, "--results-file", str(results_file),
           "-p", "no:cacheprovider", "--output", str(out_dir), "--screenshot", "only-on-failure",
           "--tracing", "retain-on-failure", "--browser", exec_cfg.get("browser", "chromium"),
           "--timeout", str(exec_cfg.get("per_test_timeout_seconds", 120)), "-q"]
    for sid in spec_ids:
        cmd += ["--spec-id", sid]
    for tc in plan.test_case_ids:
        cmd += ["--tc", tc]
    if plan.suites:
        cmd += ["-m", " or ".join(plan.suites)]
    if exec_cfg.get("headed") or os.environ.get("SDD_HEADED") == "1":
        cmd.append("--headed")
    if os.environ.get("SDD_SLOWMO"):
        cmd += ["--slowmo", os.environ["SDD_SLOWMO"]]
    if allow_destructive:
        cmd.append("--allow-destructive")
    if allow_production:
        cmd.append("--allow-production")
    if environment:
        cmd += ["--sdd-env", environment]
    log.info("Execution %s: %s", exec_id, " ".join(cmd[3:]))
    audit.write("execution_started", execution_id=exec_id, specs=spec_ids, plan=plan.model_dump(), command=cmd[3:])
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=int(exec_cfg.get("timeout_seconds", 900)))
        exit_code, stdout = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        exit_code, stdout = -1, f"TIMEOUT after {exc.timeout}s\n{exc.stdout or ''}"
    log_path = settings().path("executions") / f"{exec_id}.log"
    log_path.write_text(stdout, encoding="utf-8")
    if results_file.exists():
        run = ExecutionRun.model_validate(json.loads(results_file.read_text(encoding="utf-8")))
    else:  # pytest crashed before writing results: record the run with NO results (never fabricate)
        run = ExecutionRun(id=exec_id, started_at=utc_now(), finished_at=utc_now(), command=cmd[3:],
                           exit_code=exit_code, selection={"error": stdout[-2000:]})
    run.command = cmd[3:]
    run.exit_code = exit_code
    run.selection["plan_rationale"] = plan.rationale
    run.selection["log"] = _rel(log_path)
    results_file.write_text(json.dumps(run.model_dump(mode="json"), indent=2), encoding="utf-8")
    audit.write("execution_finished", execution_id=exec_id, exit_code=exit_code, **run.summary)
    return run


def analyse_failures(run: ExecutionRun) -> FailureAnalysisReport:
    am = ArtifactManager()
    changes = [c for c in am.load_changes() if c.status != "NO_CHANGE"]
    report = run_failure_analysis(run, changes)
    out = settings().path("analysis")
    write_yaml(out / f"{run.id}-failure-analysis.yaml", report,
               "AI/heuristic failure analysis - probable causes, separate from verified execution results")
    return report


# ============================================================================ 5. change impact
def latest_change(spec_id: str) -> ChangeRecord | None:
    recs = ArtifactManager().load_changes(spec_id)
    return recs[-1] if recs else None
