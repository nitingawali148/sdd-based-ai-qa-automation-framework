"""Agent 7 - API Automation Design Agent: designs HTTPX/pytest API tests from the OpenAPI contract."""

from __future__ import annotations

from typing import Any

from crewai import Agent

from agents.base import build_agent

CONFIG_KEY = "api_automation_designer"


def create(llm: Any) -> Agent:
    return build_agent(CONFIG_KEY, llm)
