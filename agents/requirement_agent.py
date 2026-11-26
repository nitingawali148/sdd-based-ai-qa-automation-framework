"""Agent 1 - Requirement Analysis Agent: reads business requirements and user stories, identifies business rules, inputs, acceptance criteria and ambiguities, and produces a StructuredRequirement."""

from __future__ import annotations

from typing import Any

from crewai import Agent

from agents.base import build_agent

CONFIG_KEY = "requirement_analyst"


def create(llm: Any) -> Agent:
    return build_agent(CONFIG_KEY, llm)
