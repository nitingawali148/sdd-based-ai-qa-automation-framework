"""Generic crew runner: build agents + tasks, kick off sequentially, return typed outputs, audit the run."""

from __future__ import annotations

import json
import time
from typing import Any

from crewai import Crew, Process, Task
from pydantic import BaseModel

from agents.base import build_agent
from core import models
from core.config import ROOT
from core.contract_parser import parse_contract
from core.llm_factory import create_llm, generator_label
from core.logger import audit, log
from tasks.task_factory import agent_key_for, build_task, input_key, task_configs


class CrewRunError(RuntimeError):
    pass


def _to_json(payload: Any) -> str:
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, default=str)


def run_crew(name: str, steps: list[tuple[str, dict[str, Any]]], spec_id: str = "") -> dict[str, BaseModel]:
    """Run tasks sequentially in one crew. `steps` = [(task_key, payload), ...].

    Context between tasks follows config/tasks.yaml (`context:`). Returns {task_key: pydantic output}.
    """
    llm = create_llm()
    agents: dict[str, Any] = {}
    tasks: dict[str, Task] = {}
    inputs: dict[str, str] = {}
    for key, payload in steps:
        akey = agent_key_for(key)
        agent = agents.setdefault(akey, build_agent(akey, llm))
        ctx = [tasks[c] for c in task_configs()[key].get("context", []) if c in tasks]
        tasks[key] = build_task(key, agent, ctx or None)
        inputs[input_key(key)] = _to_json(payload)
    crew = Crew(agents=list(agents.values()), tasks=list(tasks.values()), process=Process.sequential, verbose=False)
    started = time.perf_counter()
    log.info("Crew %-24s | %d task(s) | %s | LLM=%s", name, len(tasks), ", ".join(tasks), generator_label())
    status = "success"
    try:
        crew.kickoff(inputs=inputs)
    except Exception as exc:  # noqa: BLE001
        status = "error"
        audit.write("crew_run", crew=name, spec_id=spec_id, status=status, error=str(exc)[:500],
                    tasks=list(tasks), llm=generator_label())
        raise CrewRunError(f"Crew '{name}' failed: {exc}") from exc
    duration = round(time.perf_counter() - started, 3)
    outputs: dict[str, BaseModel] = {}
    for key, task in tasks.items():
        out = task.output
        model_cls = getattr(models, task_configs()[key]["output"])
        value = getattr(out, "pydantic", None) if out else None
        if value is None and out is not None and getattr(out, "json_dict", None):
            value = model_cls.model_validate(out.json_dict)
        if value is None and out is not None:
            try:
                value = parse_contract(out.raw, model_cls)
            except ValueError as exc:
                rejected = ROOT / "output" / "audit" / "rejected" / f"{name}-{key}-{int(time.time())}.txt"
                rejected.parent.mkdir(parents=True, exist_ok=True)
                rejected.write_text(out.raw, encoding="utf-8")
                audit.write("agent_output_rejected", crew=name, task=key, llm=generator_label(),
                            error=str(exc)[:800], raw_file=str(rejected.relative_to(ROOT)))
                raise CrewRunError(f"Task '{key}' did not return a valid {model_cls.__name__}: {exc}") from exc
        if value is None:
            raise CrewRunError(f"Task '{key}' produced no output")
        outputs[key] = value
        audit.write("agent_run", crew=name, task=key, agent=task.agent.role if task.agent else "",
                    spec_id=spec_id, status=status, llm=generator_label(), duration_s=duration)
    audit.write("crew_run", crew=name, spec_id=spec_id, status=status, tasks=list(tasks), llm=generator_label(),
                duration_s=duration)
    return outputs
