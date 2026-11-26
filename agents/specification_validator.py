"""Agent 3 - Specification Validation Agent: reviews specs for completeness, conflicts, ambiguity and traceability (deterministic rules in validators/spec_validator.py are the hard gate)."""

from __future__ import annotations

from typing import Any

from crewai import Agent

from agents.base import build_agent

CONFIG_KEY = "specification_validator"


def create(llm: Any) -> Agent:
    return build_agent(CONFIG_KEY, llm)
