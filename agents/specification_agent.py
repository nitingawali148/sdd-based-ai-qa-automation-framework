"""Agent 2 - Specification Architect Agent: converts an analysed requirement into a versioned FeatureSpec (Markdown + YAML)."""

from __future__ import annotations

from typing import Any

from crewai import Agent

from agents.base import build_agent

CONFIG_KEY = "specification_architect"


def create(llm: Any) -> Agent:
    return build_agent(CONFIG_KEY, llm)
