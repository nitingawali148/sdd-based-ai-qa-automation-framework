"""Agent 11 - Reporting and Traceability Agent: summarises coverage, traceability and execution."""

from __future__ import annotations

from typing import Any

from crewai import Agent

from agents.base import build_agent

CONFIG_KEY = "qa_reporter"


def create(llm: Any) -> Agent:
    return build_agent(CONFIG_KEY, llm)
