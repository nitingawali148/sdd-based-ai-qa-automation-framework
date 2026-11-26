"""Builds CrewAI agents from config/agents.yaml with a provider-specific LLM."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from crewai import Agent

from core.config import ROOT, load_yaml

SHARED_RULES = (
    " Rules: the approved specification is the single source of truth; never invent acceptance criteria; "
    "never modify an approved specification; never fabricate test results; when information is missing or "
    "ambiguous, report it instead of guessing. Return only data that fits the requested JSON contract."
)


@lru_cache(maxsize=1)
def agent_configs() -> dict[str, Any]:
    return dict(load_yaml(ROOT / "config" / "agents.yaml"))


def build_agent(key: str, llm: Any) -> Agent:
    cfg = agent_configs()[key]
    return Agent(
        role=cfg["role"].strip(),
        goal=cfg["goal"].strip(),
        backstory=cfg["backstory"].strip() + SHARED_RULES,
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=3,
        respect_context_window=True,
    )
