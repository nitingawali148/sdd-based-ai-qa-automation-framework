"""Agent 5 - Test Case Generation Agent: writes detailed test cases with steps, data and expected results."""

from __future__ import annotations

from typing import Any

from crewai import Agent

from agents.base import build_agent

CONFIG_KEY = "test_case_engineer"


def create(llm: Any) -> Agent:
    return build_agent(CONFIG_KEY, llm)
