"""SDD pytest plugin: selection by test case / spec, safety guards, and verified result capture.

Results are written ONLY from pytest's own reports; nothing here (or anywhere) fabricates an outcome.
Each result maps to: automation ID -> test case -> acceptance criteria -> specification + version.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from core.config import ROOT, settings
from core.models import ExecutionRun, TestResult

_RESULTS: dict[str, TestResult] = {}
_STARTED = ""


def pytest_addoption(parser: pytest.Parser) -> None:
    g = parser.getgroup("sdd", "Spec-Driven Development")
    g.addoption("--tc", action="append", default=[], help="Run only these test case IDs (repeatable)")
    g.addoption("--spec-id", action="append", default=[], help="Run only tests of these specifications")
    g.addoption("--exec-id", default="", help="Execution ID (set by the Execution flow)")
    g.addoption("--results-file", default="", help="Where to write the execution result JSON")
    g.addoption("--sdd-env", default="", help="Target environment from config/framework.yaml")
    g.addoption("--allow-destructive", action="store_true", help="Allow tests marked destructive")
    g.addoption("--allow-production", action="store_true", help="Allow running against a production environment")


def pytest_configure(config: pytest.Config) -> None:
    global _STARTED
    _STARTED = datetime.now(UTC).isoformat(timespec="seconds")
    if config.getoption("--sdd-env"):
        os.environ["SDD_ENV"] = config.getoption("--sdd-env")
    env = settings().environment()
    if env.get("production") and not config.getoption("--allow-production"):
        pytest.exit(f"BLOCKED: environment '{env['name']}' is marked production. Test execution against production "
                    "is disabled by default (use --allow-production with an approved change).", returncode=4)


def _marker_args(item: pytest.Item, name: str) -> tuple[Any, ...]:
    m = item.get_closest_marker(name)
    return tuple(m.args) if m else ()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    tcs = set(config.getoption("--tc"))
    specs = set(config.getoption("--spec-id"))
    if tcs or specs:
        keep, drop = [], []
        for item in items:
            tc = (_marker_args(item, "tc") or ("",))[0]
            spec = (_marker_args(item, "spec") or ("",))[0]
            ok = (not tcs or tc in tcs) and (not specs or spec in specs)
            (keep if ok else drop).append(item)
        if drop:
            config.hook.pytest_deselected(items=drop)
        items[:] = keep
    env = settings().environment()
    allow = config.getoption("--allow-destructive") or bool(env.get("allow_destructive"))
    if not allow:
        skip = pytest.mark.skip(reason="destructive operation needs approval (--allow-destructive)")
        for item in items:
            if item.get_closest_marker("destructive"):
                item.add_marker(skip)


def _result_for(item: pytest.Item) -> TestResult:
    if item.nodeid not in _RESULTS:
        spec = _marker_args(item, "spec")
        _RESULTS[item.nodeid] = TestResult(
            nodeid=item.nodeid,
            automation_id=(_marker_args(item, "automation_id") or ("",))[0],
            test_case_id=(_marker_args(item, "tc") or ("",))[0],
            ac_ids=list(_marker_args(item, "ac")),
            spec_id=spec[0] if spec else "",
            spec_version=spec[1] if len(spec) > 1 else "",
            channel="ui" if item.get_closest_marker("ui") else ("api" if item.get_closest_marker("api") else ""),
            outcome="passed",
        )
    return _RESULTS[item.nodeid]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]):  # type: ignore[no-untyped-def]
    outcome = yield
    rep: pytest.TestReport = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)
    res = _result_for(item)
    res.duration_s = round(res.duration_s + rep.duration, 3)
    if rep.skipped and res.outcome == "passed":
        res.outcome = "skipped"
        res.message = str(rep.longrepr[-1]) if isinstance(rep.longrepr, tuple) else str(rep.longrepr or "")
    elif rep.failed:
        res.outcome = "failed" if rep.when == "call" else "error"
        if call.excinfo is not None:
            res.error_type = call.excinfo.typename
            res.message = str(call.excinfo.value)[:2000]
        res.traceback = (rep.longreprtext or "")[-3000:]


def _attach_artifacts(results: list[TestResult], output_dir: Path) -> None:
    shots = ROOT / "output" / "screenshots"
    for r in results:
        if r.automation_id:
            shot = shots / f"{r.automation_id}.png"
            if shot.exists() and r.outcome in ("failed", "error"):
                r.screenshot = str(shot.relative_to(ROOT))
        if output_dir.exists() and r.outcome in ("failed", "error"):
            func = r.nodeid.split("::")[-1].lower().replace("_", "-")
            for trace in output_dir.rglob("trace.zip"):
                if func[:40] in trace.parent.name.lower():
                    r.trace = str(trace.relative_to(ROOT)) if trace.is_relative_to(ROOT) else str(trace)
                    break


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    results_file = config.getoption("--results-file")
    if not results_file and not _RESULTS:
        return
    env = settings().environment()
    try:
        output_dir = Path(config.getoption("--output"))
    except (ValueError, TypeError):
        output_dir = ROOT / "test-results"
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    results = list(_RESULTS.values())
    _attach_artifacts(results, output_dir)
    reg_path = ROOT / "specifications" / "registry.yaml"
    versions: dict[str, Any] = {}
    if reg_path.exists():
        import yaml
        versions = {k: v.get("approved_version") or v.get("version")
                    for k, v in (yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}).get("specs", {}).items()}
    run = ExecutionRun(
        id=config.getoption("--exec-id") or "ADHOC", started_at=_STARTED,
        finished_at=datetime.now(UTC).isoformat(timespec="seconds"), environment=env["name"],
        base_url=env.get("base_url", ""), exit_code=int(exitstatus),
        selection={"test_case_ids": config.getoption("--tc"), "spec_ids": config.getoption("--spec-id"),
                   "markexpr": config.getoption("-m") or "", "approved_spec_versions": versions},
        results=results)
    path = Path(results_file) if results_file else ROOT / "output" / "executions" / "adhoc-latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(run.model_dump(mode="json"), indent=2), encoding="utf-8")
