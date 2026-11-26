"""Agent 6 - UI Automation Design Agent: designs Playwright Page Object Model automation."""

from __future__ import annotations

from typing import Any

from crewai import Agent

from agents.base import build_agent

CONFIG_KEY = "ui_automation_designer"


def create(llm: Any) -> Agent:
    return build_agent(CONFIG_KEY, llm)
