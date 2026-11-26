"""Agent 10 - Failure Analysis Agent: classifies failures and recommends actions (probable analysis, kept separate from verified results)."""

from __future__ import annotations

from typing import Any

from crewai import Agent

from agents.base import build_agent

CONFIG_KEY = "failure_analyst"


def create(llm: Any) -> Agent:
    return build_agent(CONFIG_KEY, llm)
