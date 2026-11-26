"""Agent 9 - Test Execution Agent: plans the run; pytest executes deterministically."""

from __future__ import annotations

from typing import Any

from crewai import Agent

from agents.base import build_agent

CONFIG_KEY = "test_executor"


def create(llm: Any) -> Agent:
    return build_agent(CONFIG_KEY, llm)
