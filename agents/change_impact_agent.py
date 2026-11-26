"""Agent 12 - Change Impact Agent: explains specification changes and their impacted artifacts."""

from __future__ import annotations

from typing import Any

from crewai import Agent

from agents.base import build_agent

CONFIG_KEY = "change_impact_analyst"


def create(llm: Any) -> Agent:
    return build_agent(CONFIG_KEY, llm)
