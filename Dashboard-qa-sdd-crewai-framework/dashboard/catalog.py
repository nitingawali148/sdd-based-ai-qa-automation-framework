"""Read-only catalog: agents, flows, the framework's approved test cases and a project snapshot."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from dashboard.config import FRAMEWORK_DIR, RUNS_DIR, framework_available
from dashboard.demo_scenarios import DEMO_SCENARIOS

# Pipeline order used by the live view. Keys match config/agents.yaml of the framework.
AGENTS: list[dict[str, str]] = [
    {"key": "requirement_analyst", "name": "Requirement Analysis", "short": "Analyse", "icon": "📄",
     "flow": "Flow 1", "output": "StructuredRequirement"},
    {"key": "specification_architect", "name": "Specification Architect", "short": "Specify", "icon": "📐",
     "flow": "Flow 1", "output": "FeatureSpec"},
    {"key": "specification_validator", "name": "Specification Validator", "short": "Validate", "icon": "🛡️",
     "flow": "Flow 1", "output": "SpecReview + ValidationReport"},
    {"key": "test_designer", "name": "Test Design", "short": "Design", "icon": "🧭",
     "flow": "Flow 2", "output": "TestScenarioSet"},
    {"key": "test_case_engineer", "name": "Test Case Generation", "short": "Test case", "icon": "📝",
     "flow": "Flow 2", "output": "TestCaseSet"},
    {"key": "test_data_engineer", "name": "Test Data", "short": "Data", "icon": "🧪",
     "flow": "Flow 2", "output": "TestDataSet"},
    {"key": "ui_automation_designer", "name": "UI Automation Design", "short": "UI design", "icon": "🖥️",
     "flow": "Flow 3", "output": "UIAutomationDesign"},
    {"key": "api_automation_designer", "name": "API Automation Design", "short": "API design", "icon": "🔌",
     "flow": "Flow 3", "output": "APIAutomationDesign"},
    {"key": "test_executor", "name": "Test Execution", "short": "Execute", "icon": "▶️",
     "flow": "Flow 4", "output": "ExecutionPlan + pytest results"},
    {"key": "failure_analyst", "name": "Failure Analysis", "short": "Analyse failure", "icon": "🔍",
     "flow": "Flow 4", "output": "FailureAnalysisReport"},
    {"key": "qa_reporter", "name": "Reporting & Traceability", "short": "Report", "icon": "📊",
     "flow": "Flow 4", "output": "ReportNarrative + dashboard"},
    {"key": "change_impact_analyst", "name": "Change Impact", "short": "Change", "icon": "♻️",
     "flow": "Flow 5", "output": "Change narrative"},
]
PIPELINE_KEYS = [a["key"] for a in AGENTS if a["key"] != "change_impact_analyst"]

FLOWS: list[dict[str, Any]] = [
    {"id": 1, "name": "Specification", "command": "python main.py spec REQ-001",
     "steps": ["Parse requirement", "Requirement Analysis agent", "Specification Architect agent",
               "Rule validation + Validator agent", "Human approval: spec"],
     "statuses": ["SPEC_APPROVED", "NEEDS_CLARIFICATION"]},
    {"id": 2, "name": "Test design", "command": "python main.py design SPEC-LOGIN-001",
     "steps": ["Approved spec gate", "Test Design agent", "Stable ID allocation", "Test Case + Test Data agents",
               "Coverage validation", "Human approval: test cases"],
     "statuses": ["TEST_CASES_APPROVED", "COVERAGE_FAILED"]},
    {"id": 3, "name": "Automation", "command": "python main.py automate SPEC-LOGIN-001",
     "steps": ["Approved test case gate", "UI/API classification", "UI + API Automation Design agents",
               "Code renderer (Jinja)", "Code validation", "Human approval: scripts"],
     "statuses": ["SCRIPTS_APPROVED", "CODE_VALIDATION_FAILED"]},
    {"id": 4, "name": "Execution", "command": "python main.py execute",
     "steps": ["Approved + unmodified script gate", "Environment guard", "Test Execution agent (plan)",
               "pytest + Playwright + HTTPX", "Failure Analysis agent", "Reporting agent + dashboard"],
     "statuses": ["EXECUTED", "BLOCKED"]},
    {"id": 5, "name": "Change impact", "command": "python main.py change SPEC-LOGIN-001",
     "steps": ["Diff vs approved version", "Version bump + CHG record", "Change Impact agent",
               "Selective regeneration (tests, script regions)", "Re-execute impacted tests only"],
     "statuses": ["CHANGE_COMPLETE", "NO_CHANGE"]},
]


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None


@lru_cache(maxsize=1)
def agent_profiles() -> dict[str, dict[str, str]]:
    """Role / goal / backstory straight from the framework's config/agents.yaml."""
    data = _load_yaml(FRAMEWORK_DIR / "config" / "agents.yaml") or {}
    return {k: {"role": v.get("role", ""), "goal": " ".join(str(v.get("goal", "")).split()),
                "backstory": " ".join(str(v.get("backstory", "")).split())}
            for k, v in data.items() if isinstance(v, dict)}


def agents() -> list[dict[str, Any]]:
    profiles = agent_profiles()
    return [{**a, **profiles.get(a["key"], {})} for a in AGENTS]


def _features() -> list[Path]:
    root = FRAMEWORK_DIR / "specifications" / "features"
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []


def feature_bundle(feature_dir: Path) -> dict[str, Any]:
    """Everything the live view needs about one feature, read from the framework's artifacts."""
    spec = _load_yaml(feature_dir / "spec.yaml") or {}
    acs = (_load_yaml(feature_dir / "acceptance_criteria.yaml") or {}).get("acceptance_criteria", [])
    cases = (_load_yaml(feature_dir / "test_cases.yaml") or {}).get("test_cases", [])
    scenarios = (_load_yaml(feature_dir / "test_scenarios.yaml") or {}).get("scenarios", [])
    validation = _load_yaml(feature_dir / "validation_report.yaml") or {}
    data = _load_yaml(FRAMEWORK_DIR / "test_data" / f"{feature_dir.name}.yaml") or {}
    sid = spec.get("id", "")
    version = str(spec.get("version", ""))
    approvals = _load_yaml(FRAMEWORK_DIR / "specifications" / "approved" / sid / f"v{version}" / "approvals.yaml") or []
    return {"feature": feature_dir.name, "spec": spec, "acs": {a["id"]: a for a in acs},
            "cases": cases, "scenarios": {s["id"]: s for s in scenarios}, "validation": validation,
            "test_data": data.get("fields", {}), "approvals": approvals}


def real_test_cases() -> list[dict[str, Any]]:
    """Active test cases of every specification whose scripts are approved (they can really run)."""
    if not framework_available():
        return []
    out = []
    for fdir in _features():
        b = feature_bundle(fdir)
        stages = {a.get("stage") for a in b["approvals"]}
        if "scripts" not in stages:
            continue
        for tc in b["cases"]:
            if tc.get("status", "active") != "active":
                continue
            out.append({"id": tc["id"], "title": tc["title"], "channel": tc["channel"],
                        "priority": tc.get("priority", ""), "feature": b["feature"],
                        "spec_id": tc.get("spec_id"), "ac_ids": tc.get("ac_ids", []),
                        "source": "framework", "expected_outcome": None,
                        "group": f"{b['spec'].get('title', b['feature'])} ({tc.get('spec_id')})"})
    return out


def demo_test_cases() -> list[dict[str, Any]]:
    return [{"id": s["id"], "title": s["title"], "channel": s["channel"], "priority": s["priority"],
             "feature": s["feature"], "spec_id": s["spec_id"], "ac_ids": [s["ac_id"]], "source": "simulated",
             "expected_outcome": s["outcome"], "group": f"Demo: {s['feature_title']}"}
            for s in DEMO_SCENARIOS]


def framework_snapshot() -> dict[str, Any]:
    """Real figures from the framework: specs, approvals, executions."""
    if not framework_available():
        return {"available": False, "path": str(FRAMEWORK_DIR)}
    registry = (_load_yaml(FRAMEWORK_DIR / "specifications" / "registry.yaml") or {}).get("specs", {})
    specs = []
    for fdir in _features():
        b = feature_bundle(fdir)
        s = b["spec"]
        specs.append({"id": s.get("id"), "title": s.get("title") or s.get("feature"), "version": str(s.get("version")),
                      "status": registry.get(s.get("id"), {}).get("status", s.get("status")),
                      "acs": len(b["acs"]), "test_cases": len([c for c in b["cases"] if c.get("status", "active") == "active"]),
                      "approvals": sorted({a.get("stage") for a in b["approvals"]}),
                      "validation_passed": bool(b["validation"].get("passed")),
                      "findings": len(b["validation"].get("findings", []))})
    executions = []
    for f in sorted((FRAMEWORK_DIR / "output" / "executions").glob("EXEC-*.json")):
        try:
            run = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        counts: dict[str, int] = {}
        for r in run.get("results", []):
            counts[r.get("outcome", "unknown")] = counts.get(r.get("outcome", "unknown"), 0) + 1
        executions.append({"id": run.get("id"), "started_at": run.get("started_at"), "total": len(run.get("results", [])),
                           **{k: counts.get(k, 0) for k in ("passed", "failed", "skipped", "error")}})
    return {"available": True, "path": str(FRAMEWORK_DIR), "specs": specs, "executions": executions[-15:]}


def dashboard_runs() -> list[dict[str, Any]]:
    out = []
    for f in sorted(RUNS_DIR.glob("RUN-*.json"), reverse=True)[:30]:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out
