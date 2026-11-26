"""Structured CrewAI Flow state shared between stages.

Flows keep only identifiers, statuses and small summaries in state; the artifacts themselves live on disk
(specifications/...), so every stage consumes the *validated, persisted* output of the previous stage.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GateDecision(BaseModel):
    gate: str
    status: str  # PASSED | BLOCKED | AWAITING_APPROVAL
    reason: str = ""


class BaseFlowState(BaseModel):
    spec_id: str = ""
    status: str = "STARTED"
    message: str = ""
    gates: list[GateDecision] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)  # name -> path
    next_action: str = ""

    def gate(self, gate: str, status: str, reason: str = "") -> None:
        self.gates.append(GateDecision(gate=gate, status=status, reason=reason))


class SpecificationFlowState(BaseFlowState):
    requirement_id: str = ""
    requirement_file: str = ""
    regenerate: bool = False
    findings: list[dict[str, Any]] = Field(default_factory=list)


class TestDesignFlowState(BaseFlowState):
    __test__ = False
    scenario_count: int = 0
    test_case_count: int = 0
    coverage: dict[str, Any] = Field(default_factory=dict)
    only_ac_ids: list[str] = Field(default_factory=list)  # selective regeneration


class AutomationFlowState(BaseFlowState):
    ui_test_cases: list[str] = Field(default_factory=list)
    api_test_cases: list[str] = Field(default_factory=list)
    only_test_case_ids: list[str] = Field(default_factory=list)  # selective regeneration
    staged_files: list[str] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)


class ExecutionFlowState(BaseFlowState):
    spec_ids: list[str] = Field(default_factory=list)
    test_case_ids: list[str] = Field(default_factory=list)
    suites: list[str] = Field(default_factory=list)
    execution_id: str = ""
    summary: dict[str, int] = Field(default_factory=dict)
    allow_destructive: bool = False
    allow_production: bool = False
    environment: str = ""


class ChangeImpactFlowState(BaseFlowState):
    change_id: str = ""
    impacted_test_cases: list[str] = Field(default_factory=list)
    impacted_ac_ids: list[str] = Field(default_factory=list)
    execution_id: str = ""
