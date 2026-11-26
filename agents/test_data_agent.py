"""Agent 8 - Test Data Agent: defines positive, negative and boundary data without hard-coded credentials."""

from __future__ import annotations

from typing import Any

from crewai import Agent

from agents.base import build_agent

CONFIG_KEY = "test_data_engineer"


def create(llm: Any) -> Agent:
    return build_agent(CONFIG_KEY, llm)
