"""Live pipeline: walks each selected test case through the framework's agents and streams events.

Two sources, always labelled:
  * framework  - a real, approved test case. Design-time agents (analysis -> automation design) ran when the
                 artifacts were produced; their recorded output is replayed from the approved artifacts. The
                 Test Execution stage REALLY runs pytest in the framework, and the outcome comes only from the
                 framework's pytest plugin. Real failures are classified with the framework's own rules.
  * simulated  - a dummy demo scenario with scripted agent activity and a scripted outcome.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from dashboard.catalog import AGENTS, PIPELINE_KEYS, _features, feature_bundle
from dashboard.config import FRAMEWORK_DIR, RUNS_DIR, framework_python
from dashboard.demo_scenarios import BY_ID as DEMO

AGENT_NAME = {a["key"]: a["name"] for a in AGENTS}
STOP_FLAGS: dict[str, asyncio.Event] = {}


class Stopped(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id() -> str:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    n = len(list(RUNS_DIR.glob("RUN-*.json"))) + 1
    while (RUNS_DIR / f"RUN-{n:04d}.json").exists():
        n += 1
    return f"RUN-{n:04d}"


# ----------------------------------------------------------------------------------------- helpers
def _ev(kind: str, **data: Any) -> dict[str, Any]:
    return {"type": kind, "ts": time.time(), **data}


def _find_real(tc_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    for fdir in _features():
        b = feature_bundle(fdir)
        for tc in b["cases"]:
            if tc["id"] == tc_id:
                return b, tc
    return None


def _code_region(automation_id: str) -> tuple[str, str]:
    for folder in ("ui/tests", "api/tests"):
        for f in sorted((FRAMEWORK_DIR / folder).glob("test_*.py")):
            text = f.read_text(encoding="utf-8")
            start = text.find(f"# >>> sdd:begin {automation_id}")
            if start >= 0:
                end = text.find(f"# <<< sdd:end {automation_id}", start)
                end = text.find("\n", end) if end >= 0 else len(text)
                return f"{folder}/{f.name}", text[start:end]
    return "", ""


def _classify_real(result: dict[str, Any]) -> dict[str, Any]:
    """Use the framework's own rule-based classifier; fall back to a minimal one."""
    try:
        if str(FRAMEWORK_DIR) not in sys.path:
            sys.path.insert(0, str(FRAMEWORK_DIR))
        from generators.analysis import classify  # type: ignore[import-not-found]

        item = classify(result, {})
        return {"category": item.category, "confidence": item.confidence, "root_cause": item.root_cause,
                "expected": item.expected, "actual": item.actual, "recommendation": item.recommendation,
                "message": result.get("message", ""), "source": "framework rules"}
    except Exception as exc:  # noqa: BLE001
        msg = result.get("message", "")
        cat = ("ENVIRONMENT_ISSUE" if "Connect" in msg or "refused" in msg else
               "AUTOMATION_ISSUE" if "Timeout" in msg else "APPLICATION_DEFECT" if "SDD-EXPECTED" in msg else "UNKNOWN")
        return {"category": cat, "confidence": 0.4, "root_cause": f"(fallback classifier: {exc})", "expected": "",
                "actual": "", "recommendation": "Inspect the traceback and screenshot.", "message": msg,
                "source": "fallback rules"}


# ----------------------------------------------------------------------------------------- stage content
def _real_stage_outputs(b: dict[str, Any], tc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    spec, ac = b["spec"], b["acs"].get((tc.get("ac_ids") or [""])[0], {})
    scen = b["scenarios"].get(tc.get("scenario_id", ""), {})
    approvals = {a.get("stage"): a for a in b["approvals"]}
    findings = [f for f in b["validation"].get("findings", []) if f.get("artifact_id") in (ac.get("id"), spec.get("id"))]
    exp_api = ac.get("expected_api") or {}
    api = ac.get("api") or {}
    file, region = _code_region(tc.get("automation_id", ""))
    data_rows = [[f, cls, str((b["test_data"].get(f) or {}).get(cls, ""))] for f, cls in (tc.get("test_data") or {}).items()]
    design_key = "ui_automation_designer" if tc["channel"] == "ui" else "api_automation_designer"
    out = {
        "requirement_analyst": {"title": f"{ac.get('requirement_id', '')} analysed", "fields": [
            ["Requirement", ac.get("requirement_id", "")], ["Feature", spec.get("title") or b["feature"]],
            ["Acceptance criterion", ac.get("id", "")], ["Channels", ", ".join(ac.get("channels", [])).upper()],
            ["Source text", ac.get("source_text", "")]]},
        "specification_architect": {"title": f"{spec.get('id')} v{spec.get('version')}", "fields": [
            ["Given", ac.get("given", "")], ["When", ac.get("when", "")], ["Then", ac.get("then", "")],
            ["Type", ac.get("type", "")],
            ["Inputs", ", ".join(f"{k}={v}" for k, v in (ac.get("inputs") or {}).items())],
            ["API binding", f"{api.get('method')} {api.get('path')}" if api else "-"],
            ["Expected API", f"{exp_api.get('status_code')} {exp_api.get('body_contains', '')}".strip() if exp_api else "-"]]},
        "specification_validator": {
            "title": "Validation gate passed" if b["validation"].get("passed") else "Validation gate failed",
            "badge": {"text": "GATE PASSED" if b["validation"].get("passed") else "GATE BLOCKED",
                      "tone": "good" if b["validation"].get("passed") else "critical"},
            "fields": [["Rule findings (this AC / spec)", str(len(findings))],
                       ["Spec approved by", approvals.get("spec", {}).get("approved_by", "-")],
                       ["Approval hash", approvals.get("spec", {}).get("artifact_hash", "-")],
                       ["Approved at", approvals.get("spec", {}).get("approved_at", "-")]],
            "list": [f"[{f.get('severity')}] {f.get('code')}: {f.get('message')}" for f in findings][:5]},
        "test_designer": {"title": scen.get("id", tc.get("scenario_id", "")), "fields": [
            ["Scenario", scen.get("id", tc.get("scenario_id", ""))], ["Stable key", tc.get("key", "")],
            ["Type", scen.get("type", "")], ["Channel", tc["channel"].upper()]]},
        "test_case_engineer": {"title": f"{tc['id']} ({tc.get('priority', '')})", "fields": [
            ["Preconditions", "; ".join(tc.get("preconditions", []))], ["Expected result", tc.get("expected_result", "")],
            ["Approved by", approvals.get("test_cases", {}).get("approved_by", "-")]],
            "table": {"columns": ["#", "Action", "Target", "Data", "Expected"],
                      "rows": [[s.get("n"), s.get("action"), s.get("target"), s.get("data"), s.get("expected")]
                               for s in tc.get("steps", [])]}},
        "test_data_engineer": {"title": f"{len(data_rows)} field(s)",
                               "table": {"columns": ["Field", "Class", "Expression"], "rows": data_rows},
                               "fields": [["Rule", "Credentials come from ${env:...}; never literal secrets"]]},
        design_key: {"title": tc.get("automation_id", ""), "fields": [
            ["Automation ID", tc.get("automation_id", "")], ["File", file or "-"],
            ["Scripts approved by", approvals.get("scripts", {}).get("approved_by", "-")]],
            "code": {"lang": "python", "text": region or "(region not found)"}},
    }
    return out


def _demo_stage_outputs(s: dict[str, Any]) -> dict[str, dict[str, Any]]:
    d = s.get("design", {})
    design_key = "ui_automation_designer" if s["channel"] == "ui" else "api_automation_designer"
    if s["channel"] == "ui" and d:
        fn = f"test_{s['id'].lower().replace('-', '_')}"
        lines = [f"# >>> sdd:begin {s['channel'].upper()}-TEST-{s['id']}",
                 f"@pytest.mark.spec('{s['spec_id']}', '1.0')", f"@pytest.mark.ac('{s['ac_id']}')",
                 f"@pytest.mark.tc('{s['id']}')", f"def {fn}(page: Page, base_url: str) -> None:",
                 f"    p = {d['page']}Page(page, base_url).open()"]
        lines += [f"    p.fill('{k}', DATA.value('{k}', '{s['inputs'].get(k, 'valid')}'))  # {loc}"
                  for k, loc in d["locators"].items()]
        lines += [f"    p.submit()  # {d['submit']}", "    p.expect_outcome(...)", f"# <<< sdd:end {s['channel'].upper()}-TEST-{s['id']}"]
        code = "\n".join(lines)
    elif d:
        code = "\n".join([f"# >>> sdd:begin API-TEST-{s['id']}", f"@pytest.mark.tc('{s['id']}')",
                          *(["@pytest.mark.destructive"] if d.get("destructive") else []),
                          f"def test_{s['id'].lower().replace('-', '_')}(api: ApiClient) -> None:",
                          f"    r = api.request('{d['method']}', '{d['path']}', auth={d['auth']})",
                          f"    expect_status(r, {d['expected_status']})",
                          *([f"    expect_body_contains(r, '{d['body_contains']}')"] if d.get("body_contains") else []),
                          *(["    validate_schema(r, openapi)"] if d.get("validate_schema") else []),
                          f"# <<< sdd:end API-TEST-{s['id']}"])
    else:
        code = ""
    blocked = s["outcome"] == "blocked"
    return {
        "requirement_analyst": {"title": f"{s['req_id']} analysed (simulated)", "fields": [
            ["Requirement", s["req_id"]], ["Feature", s["feature_title"]], ["Acceptance criterion", s["ac_id"]],
            ["Channel", s["channel"].upper()], ["Source text", s["requirement"]]]},
        "specification_architect": {"title": f"{s['spec_id']} v1.0", "fields": [
            ["Given", s["given"]], ["When", s["when"]], ["Then", s["then"]], ["Type", s["type"]],
            ["Inputs", ", ".join(f"{k}={v}" for k, v in s["inputs"].items()) or "-"]]},
        "specification_validator": (
            {"title": "Validation gate BLOCKED", "badge": {"text": "GATE BLOCKED", "tone": "critical"},
             "fields": [["Blocking findings", str(len(s.get("blocked", [])))],
                        ["Next step", "clarification_request.md sent to the business owner"]],
             "list": [f"[error] {b['code']}: {b['message']}" for b in s.get("blocked", [])]} if blocked else
            {"title": "Validation gate passed", "badge": {"text": "GATE PASSED", "tone": "good"},
             "fields": [["Rule findings", "0 errors"], ["Spec approved by", "Demo Reviewer (simulated)"]]}),
        "test_designer": {"title": f"TS for {s['ac_id']}", "fields": [
            ["Stable key", f"{s['ac_id']}:{s['channel']}:base"], ["Type", s["type"]], ["Channel", s["channel"].upper()]]},
        "test_case_engineer": {"title": f"{s['id']} ({s['priority']})", "fields": [["Expected result", s["then"]]],
                               "table": {"columns": ["#", "Action", "Target", "Data", "Expected"],
                                         "rows": [[i + 1, *st] for i, st in enumerate(s["steps"])]}},
        "test_data_engineer": {"title": f"{len(s['data'])} field(s)", "table": {
            "columns": ["Field", "Class", "Expression"],
            "rows": [[k, s["inputs"].get(k, "valid"), v] for k, v in s["data"].items()]}},
        design_key: {"title": f"{s['channel'].upper()}-TEST-{s['id']}", "fields": (
            [["Page object", f"{d.get('page')}Page ({d.get('path')})"], ["Submit", d.get("submit", "")]]
            if s["channel"] == "ui" else
            [["Endpoint", f"{d.get('method')} {d.get('path')}"], ["Expected status", str(d.get("expected_status"))],
             ["Auth", str(d.get("auth"))], ["Destructive", str(d.get("destructive"))]]) if d else [],
            "code": {"lang": "python", "text": code}},
    }


_LOGS = {
    "requirement_analyst": ["Parsing requirement document", "Extracting business rules and input fields",
                            "Keeping AC IDs and exact source text", "Scanning for vague terms"],
    "specification_architect": ["Splitting AC into Given / When / Then", "Assigning input data classes",
                                "Defining measurable UI / API expectations", "Binding API criteria to OpenAPI"],
    "specification_validator": ["Running deterministic rule gate (spec_validator.py)",
                                "Checking measurability, conflicts and traceability", "Agent review: adding findings"],
    "test_designer": ["Creating scenario per AC x channel", "Allocating stable ID by key", "Checking boundary companions"],
    "test_case_engineer": ["Writing numbered steps", "Setting data classes per field", "Setting priority and tags"],
    "test_data_engineer": ["Resolving data class expressions", "Credentials -> ${env:...} (no literal secrets)"],
    "ui_automation_designer": ["Designing page object", "Choosing role / label locators", "Rendering Jinja template",
                               "Code validation: syntax, forbidden calls, markers"],
    "api_automation_designer": ["Reading OpenAPI operation", "Designing request + assertions", "Rendering Jinja template",
                                "Code validation: syntax, forbidden calls, markers"],
}


# ----------------------------------------------------------------------------------------- runner
class Runner:
    def __init__(self, run_id: str, ids: list[str], speed: float, headed: bool) -> None:
        self.run_id, self.ids, self.speed, self.headed = run_id, ids, max(0.25, min(speed, 4.0)), headed
        self.stop = STOP_FLAGS.setdefault(run_id, asyncio.Event())
        self.cases: list[dict[str, Any]] = []
        self.agent_stats: dict[str, dict[str, float]] = {k: {"runs": 0, "seconds": 0.0} for k in PIPELINE_KEYS}
        self.proc: subprocess.Popen[bytes] | None = None

    async def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds / self.speed
        while True:
            if self.stop.is_set():
                raise Stopped()
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.1, remaining))

    async def _agent(self, tc: str, key: str, output: dict[str, Any] | None, logs: list[str], status: str = "done",
                     base: float = 0.6) -> AsyncIterator[dict[str, Any]]:
        started = time.monotonic()
        yield _ev("agent_start", tc=tc, agent=key, name=AGENT_NAME[key])
        n = max(1, len(logs))
        for i, line in enumerate(logs):
            await self._sleep(base * random.uniform(0.6, 1.2))
            yield _ev("agent_log", tc=tc, agent=key, level="info", msg=line, progress=round((i + 1) / n * 100))
        await self._sleep(base * 0.4)
        dur = round(time.monotonic() - started, 2)
        if status in ("done", "failed", "blocked"):
            self.agent_stats[key]["runs"] += 1
            self.agent_stats[key]["seconds"] += dur
        yield _ev("agent_done", tc=tc, agent=key, status=status, output=output or {}, duration=dur)

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        started = _now()
        t0 = time.monotonic()
        catalog = []
        for tc_id in self.ids:
            real = _find_real(tc_id)
            if real:
                catalog.append({"id": tc_id, "title": real[1]["title"], "channel": real[1]["channel"], "source": "framework"})
            elif tc_id in DEMO:
                s = DEMO[tc_id]
                catalog.append({"id": tc_id, "title": s["title"], "channel": s["channel"], "source": "simulated"})
        yield _ev("run_start", run_id=self.run_id, total=len(catalog), cases=catalog, headed=self.headed,
                  speed=self.speed, framework=str(FRAMEWORK_DIR))
        stopped = False
        try:
            for i, c in enumerate(catalog):
                yield _ev("case_start", tc=c["id"], index=i, title=c["title"], channel=c["channel"], source=c["source"])
                case_t0 = time.monotonic()
                gen = self._real_case(c["id"]) if c["source"] == "framework" else self._demo_case(c["id"])
                result: dict[str, Any] = {}
                async for ev in gen:
                    if ev["type"] == "case_result":
                        result = ev["result"]
                        continue
                    yield ev
                result.update({"id": c["id"], "title": c["title"], "channel": c["channel"], "source": c["source"],
                               "duration": round(time.monotonic() - case_t0, 2)})
                self.cases.append(result)
                yield _ev("case_done", **{k: v for k, v in result.items() if k != "type"}, tc=c["id"])
        except (Stopped, asyncio.CancelledError) as exc:
            stopped = True
            self._kill()
            if isinstance(exc, asyncio.CancelledError):
                self._save(started, t0, stopped=True)
                raise
        summary = self._save(started, t0, stopped)
        yield _ev("run_done", **summary)
        STOP_FLAGS.pop(self.run_id, None)

    def _kill(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.kill()

    def _save(self, started: str, t0: float, stopped: bool) -> dict[str, Any]:
        counts = {k: sum(1 for c in self.cases if c.get("outcome") == k) for k in ("passed", "failed", "error", "blocked")}
        summary = {"run_id": self.run_id, "started_at": started, "finished_at": _now(), "stopped": stopped,
                   "duration": round(time.monotonic() - t0, 2), "total": len(self.cases), **counts,
                   "real": sum(1 for c in self.cases if c["source"] == "framework"),
                   "simulated": sum(1 for c in self.cases if c["source"] == "simulated"),
                   "agent_stats": self.agent_stats, "cases": self.cases}
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        (RUNS_DIR / f"{self.run_id}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    # ------------------------------------------------------------------ simulated scenario
    async def _demo_case(self, tc_id: str) -> AsyncIterator[dict[str, Any]]:
        s = DEMO[tc_id]
        outs = _demo_stage_outputs(s)
        design_key = "ui_automation_designer" if s["channel"] == "ui" else "api_automation_designer"
        for key in PIPELINE_KEYS[:3]:
            status = "blocked" if key == "specification_validator" and s["outcome"] == "blocked" else "done"
            async for ev in self._agent(tc_id, key, outs[key], _LOGS[key], status):
                yield ev
            if status == "blocked":
                for rest in PIPELINE_KEYS[3:]:
                    yield _ev("agent_done", tc=tc_id, agent=rest, status="skipped", duration=0,
                              output={"title": "Not reached: specification blocked at the validation gate"})
                yield _ev("case_result", result={"outcome": "blocked", "category": "SPEC_BLOCKED",
                                                 "message": "; ".join(b["code"] for b in s["blocked"])})
                return
        for key in ("test_designer", "test_case_engineer", "test_data_engineer"):
            async for ev in self._agent(tc_id, key, outs[key], _LOGS[key]):
                yield ev
        for key in ("ui_automation_designer", "api_automation_designer"):
            if key == design_key:
                async for ev in self._agent(tc_id, key, outs[key], _LOGS[key]):
                    yield ev
            else:
                yield _ev("agent_done", tc=tc_id, agent=key, status="skipped", duration=0,
                          output={"title": f"Not needed: {s['channel'].upper()} test case"})
        # execution (scripted)
        exec_t0 = time.monotonic()
        yield _ev("agent_start", tc=tc_id, agent="test_executor", name=AGENT_NAME["test_executor"])
        yield _ev("agent_log", tc=tc_id, agent="test_executor", level="info", progress=5,
                  msg=f"ExecutionPlan: run {tc_id} (simulated pytest session)")
        fail_step = s.get("fail_step")
        outcome = s["outcome"]
        for n, (action, target, data, expected) in enumerate(s["steps"], start=1):
            await self._sleep(0.9 * random.uniform(0.7, 1.3))
            if fail_step == n:
                yield _ev("agent_log", tc=tc_id, agent="test_executor", level="error",
                          msg=f"step {n} {action} {target} -> {s['failure']['message']}",
                          progress=round(n / len(s["steps"]) * 100))
                break
            yield _ev("agent_log", tc=tc_id, agent="test_executor", level="ok",
                      msg=f"step {n} ✓ {action} {target} {('[' + data + ']') if data else ''} {expected}".strip(),
                      progress=round(n / len(s["steps"]) * 100))
        dur = round(time.monotonic() - exec_t0, 2)
        self.agent_stats["test_executor"]["runs"] += 1
        self.agent_stats["test_executor"]["seconds"] += dur
        yield _ev("agent_done", tc=tc_id, agent="test_executor", status="done" if outcome == "passed" else "failed",
                  duration=dur, output={"title": f"Outcome: {outcome.upper()} (simulated)",
                                        "badge": {"text": outcome.upper(), "tone": "good" if outcome == "passed" else "critical"},
                                        "fields": [["Duration", f"{dur}s"],
                                                   ["Message", s.get("failure", {}).get("message", "-")]]})
        async for ev in self._analysis(tc_id, outcome, s.get("failure")):
            yield ev
        async for ev in self._report(tc_id, s["req_id"], s["spec_id"], s["ac_id"], f"{s['channel'].upper()}-TEST-{tc_id}",
                                     outcome, simulated=True):
            yield ev
        yield _ev("case_result", result={"outcome": outcome, "category": s.get("failure", {}).get("category", ""),
                                         "message": s.get("failure", {}).get("message", "")})

    # ------------------------------------------------------------------ real framework test case
    async def _real_case(self, tc_id: str) -> AsyncIterator[dict[str, Any]]:
        found = _find_real(tc_id)
        assert found
        b, tc = found
        outs = _real_stage_outputs(b, tc)
        design_key = "ui_automation_designer" if tc["channel"] == "ui" else "api_automation_designer"
        replay = "Replaying recorded output from the approved artifacts"
        for key in PIPELINE_KEYS[:6]:
            async for ev in self._agent(tc_id, key, outs[key], [replay, *_LOGS[key][:2]], base=0.35):
                yield ev
        for key in ("ui_automation_designer", "api_automation_designer"):
            if key == design_key:
                async for ev in self._agent(tc_id, key, outs[key], [replay, *_LOGS[key][:2]], base=0.35):
                    yield ev
            else:
                yield _ev("agent_done", tc=tc_id, agent=key, status="skipped", duration=0,
                          output={"title": f"Not needed: {tc['channel'].upper()} test case"})
        # REAL execution
        result: dict[str, Any] = {}
        async for ev in self._pytest(tc_id):
            if ev["type"] == "pytest_result":
                result = ev["result"]
                continue
            yield ev
        outcome = result.get("outcome", "error")
        if outcome == "skipped":
            outcome = "skipped"
        failure = _classify_real(result) if outcome in ("failed", "error") else None
        async for ev in self._analysis(tc_id, outcome, failure):
            yield ev
        ac = (tc.get("ac_ids") or [""])[0]
        async for ev in self._report(tc_id, b["acs"].get(ac, {}).get("requirement_id", ""), tc.get("spec_id", ""), ac,
                                     tc.get("automation_id", ""), outcome, simulated=False):
            yield ev
        yield _ev("case_result", result={"outcome": outcome, "category": (failure or {}).get("category", ""),
                                         "message": result.get("message", "")})

    async def _pytest(self, tc_id: str) -> AsyncIterator[dict[str, Any]]:
        key = "test_executor"
        work = RUNS_DIR / self.run_id
        work.mkdir(parents=True, exist_ok=True)
        results = work / f"{tc_id}.json"
        log = work / f"{tc_id}.log"
        cmd = [framework_python(), "-m", "pytest", "ui/tests", "api/tests", "--tc", tc_id,
               "--exec-id", f"{self.run_id}-{tc_id}", "--results-file", str(results), "-p", "no:cacheprovider",
               "--output", str(work / "test-results"), "--screenshot", "only-on-failure", "--browser", "chromium",
               "--timeout", "120", "-q", "-o", "console_output_style=classic"]
        if self.headed:
            cmd += ["--headed", "--slowmo", "300"]
        t0 = time.monotonic()
        yield _ev("agent_start", tc=tc_id, agent=key, name=AGENT_NAME[key])
        yield _ev("agent_log", tc=tc_id, agent=key, level="info", progress=5,
                  msg=f"REAL pytest: {' '.join(cmd[3:7])} ... (framework: {FRAMEWORK_DIR.name})")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        with open(log, "wb") as fh:
            self.proc = subprocess.Popen(cmd, cwd=FRAMEWORK_DIR, stdout=fh, stderr=subprocess.STDOUT, env=env)
        pos, progress = 0, 10
        while True:
            done = self.proc.poll() is not None
            if self.stop.is_set():
                self._kill()
                raise Stopped()
            try:
                with open(log, "rb") as fh:
                    fh.seek(pos)
                    chunk = fh.read()
                    pos += len(chunk)
            except OSError:
                chunk = b""
            for line in chunk.decode("utf-8", "replace").splitlines():
                line = line.strip()
                if line:
                    progress = min(95, progress + 5)
                    level = "error" if any(w in line for w in ("FAILED", "Error", "error")) else \
                        "ok" if "passed" in line or "PASSED" in line else "info"
                    yield _ev("agent_log", tc=tc_id, agent=key, level=level, msg=line[:400], progress=progress)
            if done:
                break
            await asyncio.sleep(0.4)
        dur = round(time.monotonic() - t0, 2)
        self.agent_stats[key]["runs"] += 1
        self.agent_stats[key]["seconds"] += dur
        rec: dict[str, Any] = {}
        try:
            data = json.loads(results.read_text(encoding="utf-8"))
            rec = next((r for r in data.get("results", []) if r.get("test_case_id") == tc_id), {})
        except (OSError, json.JSONDecodeError):
            pass
        if not rec:
            tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-3:] if log.exists() else []
            rec = {"outcome": "error", "message": "pytest produced no result for this test case (nothing fabricated). "
                                                  + " | ".join(tail), "test_case_id": tc_id}
        outcome = rec.get("outcome", "error")
        yield _ev("agent_done", tc=tc_id, agent=key, status="done" if outcome == "passed" else "failed", duration=dur,
                  output={"title": f"Outcome: {outcome.upper()} (real pytest)",
                          "badge": {"text": outcome.upper(), "tone": "good" if outcome == "passed" else "critical"},
                          "fields": [["Node", rec.get("nodeid", "-")], ["Duration (pytest)", f"{rec.get('duration_s', '-')}s"],
                                     ["Exit code", str(self.proc.returncode)], ["Message", rec.get("message") or "-"],
                                     ["Screenshot", rec.get("screenshot") or "-"], ["Log", str(log)]]})
        yield _ev("pytest_result", result=rec)

    async def _analysis(self, tc_id: str, outcome: str, failure: dict[str, Any] | None) -> AsyncIterator[dict[str, Any]]:
        key = "failure_analyst"
        if outcome == "passed" or not failure:
            yield _ev("agent_done", tc=tc_id, agent=key, status="skipped", duration=0,
                      output={"title": "No failure to analyse"})
            return
        out = {"title": f"{failure['category']} (probable)",
               "badge": {"text": failure["category"], "tone": "serious"},
               "fields": [["Confidence", f"{round(float(failure.get('confidence', 0.5)) * 100)}%"],
                          ["Expected", failure.get("expected") or "-"], ["Actual", failure.get("actual") or "-"],
                          ["Probable root cause", failure.get("root_cause", "")],
                          ["Recommendation", failure.get("recommendation", "")],
                          ["Source", failure.get("source", "scripted demo analysis")]]}
        async for ev in self._agent(tc_id, key, out, ["Reading expected vs actual evidence", "Checking recent spec changes",
                                                      f"Classifying: {failure['category']}"], "done"):
            yield ev

    async def _report(self, tc_id: str, req: str, spec: str, ac: str, auto: str, outcome: str,
                      simulated: bool) -> AsyncIterator[dict[str, Any]]:
        chain = [req, spec, ac, tc_id, auto, f"{self.run_id}: {outcome.upper()}"]
        out = {"title": "Traceability updated", "fields": [["Trace", "  →  ".join(c for c in chain if c)],
                                                           ["Result source", "simulated (demo)" if simulated else "pytest plugin (verified)"]]}
        async for ev in self._agent(tc_id, "qa_reporter", out, ["Linking result to REQ → SPEC → AC → TC",
                                                                "Updating coverage and summary"], base=0.3):
            yield ev
