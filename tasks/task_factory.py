"""Builds CrewAI tasks from config/tasks.yaml with typed `output_pydantic` contracts."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from crewai import Agent, Task
from crewai.tasks.task_output import TaskOutput

from core import models
from core.contract_parser import parse_contract
from core.config import ROOT, load_yaml, settings


@lru_cache(maxsize=1)
def task_configs() -> dict[str, Any]:
    return dict(load_yaml(ROOT / "config" / "tasks.yaml"))


def input_key(task_key: str) -> str:
    """Each task gets its own placeholder so several tasks can share one crew kickoff."""
    return f"{task_key}_input"


def build_task(key: str, agent: Agent, context: list[Task] | None = None) -> Task:
    cfg = task_configs()[key]
    output_model = getattr(models, cfg["output"])
    description = cfg["description"].replace("{payload}", "{" + input_key(key) + "}")
    kwargs: dict[str, Any] = {}
    if context:
        kwargs["context"] = context
    if settings().llm_provider == "offline":
        return Task(description=description, expected_output=cfg["expected_output"], agent=agent,
                    output_pydantic=output_model, **kwargs)
    # Real LLMs: many providers (Groq, OpenAI strict mode) reject non-strict schemas such as free-form maps in
    # response_format. The contract is given in the prompt instead; crews/base.py validates the reply against
    # the same Pydantic model, so nothing outside the contract is accepted.
    schema = json.dumps(output_model.model_json_schema(), separators=(",", ":"))
    expected = (f"{cfg['expected_output']} Return ONLY one complete, valid JSON object (no prose, no code fences, "
                f"no comments, no trailing commas) that validates against this JSON Schema: {schema}")

    def contract_guardrail(output: TaskOutput):  # type: ignore[no-untyped-def]  # CrewAI rejects string annotations
        """Reject replies that do not fit the contract; CrewAI sends the error back to the agent to retry."""
        try:
            parsed = parse_contract(output.raw, output_model)
        except ValueError as exc:
            return False, (f"Your answer is not a valid {output_model.__name__} JSON object: {str(exc)[:600]}. "
                           "Reply again with ONLY the corrected, complete JSON object.")
        return True, parsed.model_dump_json()

    return Task(description=description, expected_output=expected, agent=agent, guardrail=contract_guardrail,
                guardrail_max_retries=3, **kwargs)


def agent_key_for(task_key: str) -> str:
    return str(task_configs()[task_key]["agent"])
