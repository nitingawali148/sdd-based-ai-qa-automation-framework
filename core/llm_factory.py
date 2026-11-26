"""LLM factory for CrewAI agents: Ollama, OpenAI or the offline rule engine.

The offline provider is a real CrewAI `BaseLLM`. Agents, tasks and crews run through the normal CrewAI
machinery, but the "model" is the deterministic rule engine in `generators/`. Each task description
carries a routing marker `[[sdd-task:<key>]]` and its input between `<<<INPUT` / `INPUT>>>`; the offline
LLM dispatches to the matching generator and returns schema-valid JSON. With a real LLM the same marker
and payload are simply part of the prompt.

Offline output is clearly labelled `offline-rule-engine` in every artifact it produces.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from crewai import LLM, BaseLLM
from pydantic import BaseModel, PrivateAttr

from core.config import settings
from core.logger import audit

OFFLINE_LABEL = "offline-rule-engine"
_TASK_MARKER = re.compile(r"\[\[sdd-task:([a-z0-9_]+)\]\]")
_INPUT_BLOCK = re.compile(r"<<<INPUT\s*(.*?)\s*INPUT>>>", re.S)


def _messages_text(messages: Any) -> str:
    if isinstance(messages, str):
        return messages
    parts = []
    for m in messages or []:
        content = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
        if isinstance(content, list):
            content = " ".join(str(c.get("text", "")) if isinstance(c, dict) else str(c) for c in content)
        parts.append(str(content))
    return "\n".join(parts)


class OfflineRuleEngineLLM(BaseLLM):
    """Deterministic, offline `BaseLLM` used for reproducible runs, CI and demos."""

    _blackboard: dict[str, Any] = PrivateAttr(default_factory=dict)

    def call(  # type: ignore[override]
        self,
        messages: Any,
        tools: Any = None,
        callbacks: Any = None,
        available_functions: Any = None,
        from_task: Any = None,
        from_agent: Any = None,
        response_model: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> str:
        from generators.registry import HANDLERS  # local import: generators import core

        text = _messages_text(messages)
        keys = _TASK_MARKER.findall(text)
        if not keys:
            # Not a routed task (e.g. a CrewAI-internal call). Echo the last structured answer if any.
            last = self._blackboard.get("__last__")
            return json.dumps(last) if last is not None else "{}"
        key = keys[-1]
        blocks = _INPUT_BLOCK.findall(text)
        payload: dict[str, Any] = json.loads(blocks[-1]) if blocks else {}
        handler = HANDLERS.get(key)
        if handler is None:
            raise ValueError(f"Offline rule engine has no handler for task '{key}'")
        result = handler(payload, self._blackboard)
        data = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
        self._blackboard[key] = result
        self._blackboard["__last__"] = data
        audit.write("llm_call", provider=OFFLINE_LABEL, task=key,
                    agent=getattr(from_agent, "role", ""), output_chars=len(json.dumps(data)))
        body = json.dumps(data, ensure_ascii=False)
        if response_model is not None:
            return body
        return f"Thought: I applied the {key} rules to the specification input.\nFinal Answer: {body}"

    def supports_function_calling(self) -> bool:
        return False

    def supports_stop_words(self) -> bool:
        return False

    def get_context_window_size(self) -> int:
        return 1_000_000

    def get_input_tokens_count(self, messages: Any, tools: Any = None, response_model: Any = None) -> int:
        return len(_messages_text(messages)) // 4


def create_llm() -> BaseLLM:
    """Create a fresh LLM per crew run (the offline engine keeps a per-crew blackboard)."""
    s = settings()
    provider = s.llm_provider
    if provider == "offline":
        return OfflineRuleEngineLLM(model=OFFLINE_LABEL)
    if provider == "ollama":
        return LLM(model=f"ollama/{s.llm_model}", base_url=os.environ.get("OLLAMA_BASE_URL",
                                                                          "http://localhost:11434"),
                   temperature=s.llm_temperature)
    if provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set (.env)")
        return LLM(model=s.llm_model, temperature=s.llm_temperature)
    if provider == "groq":
        # Groq exposes an OpenAI-compatible API; CrewAI's native OpenAI client is pointed at it.
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("LLM_PROVIDER=groq but GROQ_API_KEY is not set (.env)")
        return LLM(model=s.llm_model, provider="openai", api_key=key, temperature=s.llm_temperature,
                   max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "32000")), timeout=300,
                   base_url=os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"))
    raise ValueError(f"Unsupported LLM_PROVIDER '{provider}' (use offline | ollama | openai | groq)")


def generator_label() -> str:
    s = settings()
    return OFFLINE_LABEL if s.llm_provider == "offline" else f"{s.llm_provider}:{s.llm_model}"
