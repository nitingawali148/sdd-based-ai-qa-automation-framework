"""Agent 4 - Test Design Agent: derives positive, negative and boundary scenarios from approved acceptance criteria."""

from __future__ import annotations

from typing import Any

from crewai import Agent

from agents.base import build_agent

CONFIG_KEY = "test_designer"


def create(llm: Any) -> Agent:
    return build_agent(CONFIG_KEY, llm)
