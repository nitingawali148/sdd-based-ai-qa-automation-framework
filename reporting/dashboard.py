"""Builds the QA dashboard (reports/dashboard.html), traceability matrix and summary JSON.

Verified data (specs, approvals, test cases, pytest results) and AI analysis (failure analysis, narrative)
are kept in separate, labelled sections.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from core.artifact_manager import ArtifactManager, read_yaml, templates
from core.config import ROOT, settings
from core.logger import audit, log
from core.models import utc_now
from crews.analysis_crew import run_reporting
from traceability.engine import TraceabilityEngine, write_traceability_markdown

MERMAID = {
    "architecture": """flowchart LR
  subgraph SPEC[Specification Management]
    R[Requirements MD/YAML/JSON/PDF/DOCX] --> P[Parsers]
    P --> S[(Feature specs spec.yaml + ACs)]
    S --> V[Validators]
    S --> VM[Versioning approved snapshots]
  end
  subgraph AI[CrewAI]
    F[Flows - orchestration] --> C[Crews]
    C --> A[12 specialised agents]
    A --> L{{LLM: Ollama / OpenAI / offline rule engine}}
  end
  subgraph AUT[Automation]
    T[Test cases] --> G[Code renderer]
    G --> UI[Playwright POM]
    G --> API[HTTPX + pytest]
  end
  S --> F
  F --> T
  UI --> X[Pytest execution]
  API --> X
  X --> TR[Traceability engine] --> D[Dashboard]
  VM --> TR""",
    "lifecycle": """flowchart LR
  A[Business requirement] --> B[Requirement analysis]
  B --> C[Specification creation]
  C --> D{Specification validation}
  D -- errors --> Q[Clarification request]
  D -- passed --> E{{Human spec approval}}
  E --> F[Test scenarios]
  F --> G[Test cases + test data]
  G --> H{Coverage validation}
  H --> I{{Human test case approval}}
  I --> J[UI / API automation design]
  J --> K[Script generation]
  K --> L{Code validation}
  L --> M{{Human script approval}}
  M --> N[Pytest execution]
  N --> O[Failure analysis]
  O --> P[QA reporting]""",
    "agents": """flowchart LR
  RA[Requirement Analysis] --> SA[Specification Architect]
  SA --> SV[Specification Validator]
  SV --> TD[Test Design]
  TD --> TC[Test Case Generation]
  TD --> TDA[Test Data]
  TC --> UIA[UI Automation Design]
  TC --> APIA[API Automation Design]
  UIA --> EX[Test Execution]
  APIA --> EX
  EX --> FA[Failure Analysis]
  FA --> RP[Reporting & Traceability]
  CI[Change Impact] --> TD""",
    "automation": """sequenceDiagram
  participant TC as Approved test cases
  participant UI as UI design agent
  participant API as API design agent
  participant R as Code renderer
  participant V as Code validator
  participant H as Human reviewer
  participant P as Pytest
  TC->>UI: UI test cases
  TC->>API: API test cases + OpenAPI
  UI->>R: page objects + test designs
  API->>R: endpoint test designs
  R->>V: staged scripts
  V->>H: validation report
  H->>P: approve -> promote scripts
  P-->>P: execute, capture screenshots/traces""",
    "change": """flowchart TD
  U[Spec edited: AC changed] --> C[Compare with approved version]
  C --> D[AC diff + version bump]
  D --> I[Impact: scenarios, test cases, scripts]
  I --> H1{{Approve new spec version}}
  H1 --> R1[Regenerate impacted test cases only]
  R1 --> H2{{Approve test cases}}
  H2 --> R2[Regenerate impacted script regions only]
  R2 --> H3{{Approve scripts}}
  H3 --> X[Re-execute impacted tests]
  X --> RP[Updated reports]""",
}


def _failure_analyses() -> list[dict[str, Any]]:
    out = []
    for p in sorted(settings().path("analysis").glob("EXEC-*-failure-analysis.yaml")):
        data = read_yaml(p) or {}
        out.append(data)
    return out


def _agent_history() -> list[dict[str, Any]]:
    events = [e for e in audit.read() if e.get("event") in ("agent_run", "flow", "approval", "change_detected",
                                                             "execution_finished")]
    return events[-300:]


def build_reports(with_narrative: bool = True) -> dict[str, str]:
    reports = settings().path("reports")
    data = TraceabilityEngine().build()
    am = ArtifactManager()
    changes = [c.model_dump(mode="json") for c in am.load_changes()]
    analyses = _failure_analyses()
    history = _agent_history()
    runs = data["executions"]
    last = runs[-1] if runs else None
    last_fa = analyses[-1] if analyses else None

    latest_by_aid: dict[str, dict[str, Any]] = {}
    exec_dir = settings().path("executions")
    for r in runs:
        path = exec_dir / f"{r['id']}.json"
        if path.exists():
            for res in json.loads(path.read_text(encoding="utf-8")).get("results", []):
                latest_by_aid[res.get("automation_id") or res["nodeid"]] = {**res, "execution_id": r["id"]}
    channel_outcomes: dict[str, Counter[str]] = {"ui": Counter(), "api": Counter()}
    for res in latest_by_aid.values():
        if res.get("channel") in channel_outcomes:
            channel_outcomes[res["channel"]][res["outcome"]] += 1

    narrative = None
    if with_narrative:
        try:
            narrative = run_reporting({"coverage": data["coverage"], "last_execution": last,
                                       "uncovered_requirements": data["uncovered_requirements"],
                                       "outdated_scripts": data["outdated_scripts"],
                                       "failure_summary": (last_fa or {}).get("summary", "")}).model_dump()
        except Exception as exc:  # noqa: BLE001 - the report must still render without the narrative
            log.warning("Reporting agent unavailable: %s", exc)

    agent_counts = Counter(e.get("agent") or e.get("task") for e in history if e.get("event") == "agent_run")
    payload = {
        "generated_at": utc_now(), "llm": settings().llm_provider, "trace": data, "changes": changes,
        "failure_analysis": last_fa, "all_failure_analyses": analyses, "history": history,
        "agent_counts": dict(agent_counts), "latest_results": list(latest_by_aid.values()),
        "channel_outcomes": {k: dict(v) for k, v in channel_outcomes.items()}, "narrative": narrative,
    }
    html = templates().get_template("dashboard.html.j2").render(
        data=payload, data_json=json.dumps(payload, default=str).replace("</", "<\\/"), mermaid=MERMAID)
    dash = reports / "dashboard.html"
    dash.write_text(html, encoding="utf-8")
    trace_md = write_traceability_markdown(data, reports / "traceability.md")
    summary = reports / "summary.json"
    summary.write_text(json.dumps({"generated_at": payload["generated_at"], "coverage": data["coverage"],
                                   "last_execution": last, "uncovered_requirements": data["uncovered_requirements"],
                                   "outdated_scripts": data["outdated_scripts"]}, indent=2), encoding="utf-8")
    log.info("Dashboard written to %s", dash.relative_to(ROOT))
    return {"dashboard": str(dash), "traceability": str(trace_md), "summary": str(summary)}


def dashboard_path() -> Path:
    return settings().path("reports") / "dashboard.html"
