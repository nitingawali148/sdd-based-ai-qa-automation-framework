"""Typed artifact contracts for every stage of the SDD lifecycle.

Every artifact carries a reference to its parent (requirement -> spec -> AC -> scenario -> test case ->
automation script -> execution result). These models are also used as CrewAI `output_pydantic` contracts,
so an LLM can only hand back data that fits the contract.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

Channel = Literal["ui", "api"]
Severity = Literal["error", "warning", "info"]
Priority = Literal["P1", "P2", "P3"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def stable_hash(obj: Any) -> str:
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json")
    raw = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class SpecStatus(str, Enum):
    DRAFT = "DRAFT"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"


# --------------------------------------------------------------------------- findings
class Finding(BaseModel):
    code: str
    severity: Severity
    message: str
    artifact_id: str = ""
    source: Literal["rule", "ai"] = "rule"


class TextItem(BaseModel):
    id: str
    text: str


# --------------------------------------------------------------------------- requirement
class InputField(BaseModel):
    name: str
    type: str = "string"  # string | email | password | integer | enum
    required: bool = True
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    enum: list[str] = Field(default_factory=list)
    label: str | None = None
    description: str = ""


class RawAcceptanceCriterion(BaseModel):
    id: str
    text: str
    channels: list[Channel] = Field(default_factory=list)
    api_text: str = ""  # API-specific "then" clause, e.g. 'returns 401 with "Invalid email or password"'


class UIElement(BaseModel):
    label: str
    role: str = "text"  # textbox | button | alert | heading | link | text


class UIPage(BaseModel):
    name: str
    path: str
    elements: list[UIElement] = Field(default_factory=list)


class APIEndpointRef(BaseModel):
    method: str
    path: str
    summary: str = ""


class StructuredRequirement(BaseModel):
    """Output of the Requirement Analysis Agent."""

    id: str
    title: str
    feature: str
    feature_code: str
    priority: Priority = "P2"
    user_story: str = ""
    objective: str = ""
    business_rules: list[str] = Field(default_factory=list)
    input_fields: list[InputField] = Field(default_factory=list)
    acceptance_criteria: list[RawAcceptanceCriterion] = Field(default_factory=list)
    ui_pages: list[UIPage] = Field(default_factory=list)
    api_endpoints: list[APIEndpointRef] = Field(default_factory=list)
    non_functional: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    ambiguities: list[Finding] = Field(default_factory=list)
    source_file: str = ""
    source_hash: str = ""
    analysed_by: str = ""


# --------------------------------------------------------------------------- specification
class Expectation(BaseModel):
    kind: Literal["navigate", "message", "status", "unknown"] = "unknown"
    value: str = ""  # page name | message text | status code (as text)
    negate: bool = False  # True -> "message must NOT be shown"
    status_code: int | None = None
    body_contains: str = ""
    validate_schema: bool = False

    def describe(self) -> str:
        if self.kind == "navigate":
            return f"User is navigated to the {self.value} page"
        if self.kind == "message":
            return f"Message \"{self.value}\" is {'not ' if self.negate else ''}displayed"
        if self.kind == "status":
            parts = [f"Response status is {self.status_code}"]
            if self.body_contains:
                parts.append(f"body contains \"{self.body_contains}\"")
            if self.validate_schema:
                parts.append("body matches the OpenAPI response schema")
            return ", ".join(parts)
        return "UNDEFINED - expected result is not measurable"


class APIBinding(BaseModel):
    method: str
    path: str
    operation_id: str = ""
    auth: bool = True
    precondition: Literal["none", "existing_resource", "duplicate"] = "none"


class AcceptanceCriterion(BaseModel):
    id: str
    title: str
    type: Literal["positive", "negative", "boundary"] = "positive"
    given: str = ""
    when: str = ""
    then: str = ""
    channels: list[Channel] = Field(default_factory=list)
    inputs: dict[str, str] = Field(default_factory=dict)  # field -> data class (valid, empty, invalid, ...)
    expected_ui: Expectation | None = None
    expected_api: Expectation | None = None
    api: APIBinding | None = None
    start_page: str = ""
    requirement_id: str = ""
    source_text: str = ""

    def content_hash(self) -> str:
        return stable_hash(self.model_dump(mode="json"))


class FeatureSpec(BaseModel):
    """Output of the Specification Architect Agent. The single source of truth for a feature."""

    id: str
    version: str = "1.0"
    title: str
    feature: str
    feature_code: str
    requirement_ids: list[str]
    status: SpecStatus = SpecStatus.DRAFT
    priority: Priority = "P2"
    objective: str = ""
    user_story: str = ""
    functional_requirements: list[TextItem] = Field(default_factory=list)
    business_rules: list[TextItem] = Field(default_factory=list)
    inputs: list[InputField] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    ui_pages: list[UIPage] = Field(default_factory=list)
    api_endpoints: list[APIEndpointRef] = Field(default_factory=list)
    non_functional: list[TextItem] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    generated_by: str = ""
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    source_requirement_hash: str = ""

    def ac(self, ac_id: str) -> AcceptanceCriterion | None:
        return next((a for a in self.acceptance_criteria if a.id == ac_id), None)

    def content_hash(self) -> str:
        return stable_hash(self.model_dump(mode="json", exclude={"status", "created_at", "updated_at",
                                                                   "generated_by"}))


class ValidationReport(BaseModel):
    spec_id: str
    spec_version: str
    passed: bool
    findings: list[Finding] = Field(default_factory=list)
    checked_at: str = Field(default_factory=utc_now)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]


class SpecReview(BaseModel):
    """Qualitative findings from the Specification Validation Agent (merged with rule findings)."""

    spec_id: str
    findings: list[Finding] = Field(default_factory=list)
    summary: str = ""


# --------------------------------------------------------------------------- test design
class TestScenario(BaseModel):
    __test__ = False  # not a pytest test class
    id: str
    key: str  # stable identity used to preserve IDs across regeneration
    title: str
    type: Literal["positive", "negative", "boundary"]
    channel: Channel
    ac_ids: list[str]
    inputs: dict[str, str] = Field(default_factory=dict)
    expected: Expectation
    priority: Priority = "P2"
    tags: list[str] = Field(default_factory=list)
    spec_id: str
    spec_version: str
    ac_hash: str
    status: Literal["active", "obsolete"] = "active"


class TestScenarioSet(BaseModel):
    __test__ = False  # not a pytest test class
    spec_id: str
    spec_version: str
    scenarios: list[TestScenario] = Field(default_factory=list)
    coverage_notes: list[Finding] = Field(default_factory=list)
    generated_by: str = ""


class TestStep(BaseModel):
    __test__ = False  # not a pytest test class
    n: int
    action: str
    target: str = ""
    data: str = ""
    expected: str = ""


class TestCase(BaseModel):
    __test__ = False  # not a pytest test class
    id: str
    key: str
    scenario_id: str
    title: str
    channel: Channel
    ac_ids: list[str]
    spec_id: str
    spec_version: str
    ac_hash: str
    priority: Priority = "P2"
    preconditions: list[str] = Field(default_factory=list)
    steps: list[TestStep] = Field(default_factory=list)
    test_data: dict[str, str] = Field(default_factory=dict)  # field -> data class
    expected: Expectation
    expected_result: str = ""
    start_page: str = ""
    api: APIBinding | None = None
    automation_id: str = ""
    tags: list[str] = Field(default_factory=list)
    status: Literal["active", "obsolete"] = "active"


class TestCaseSet(BaseModel):
    __test__ = False  # not a pytest test class
    spec_id: str
    spec_version: str
    test_cases: list[TestCase] = Field(default_factory=list)
    generated_by: str = ""


class TestDataSet(BaseModel):
    __test__ = False  # not a pytest test class
    feature: str
    spec_id: str
    spec_version: str
    # field -> data class -> value expression (${env:VAR}, ${faker:...}, ${repeat:a:9} or literal)
    fields: dict[str, dict[str, str]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    generated_by: str = ""


class CoverageReport(BaseModel):
    spec_id: str
    spec_version: str
    passed: bool
    ac_total: int
    ac_covered: int
    uncovered_acs: list[str] = Field(default_factory=list)
    scenarios_by_type: dict[str, int] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)


# --------------------------------------------------------------------------- automation design
class Locator(BaseModel):
    key: str
    strategy: Literal["label", "role", "text", "test_id", "css"]
    value: str
    role: str = ""


class PageObjectDesign(BaseModel):
    page: str  # spec page name, e.g. "Login"
    class_name: str
    module: str
    path: str
    locators: list[Locator] = Field(default_factory=list)
    form_fields: dict[str, str] = Field(default_factory=dict)  # input field -> locator key
    submit_key: str = ""


class UITestDesign(BaseModel):
    automation_id: str
    test_case_id: str
    function_name: str
    start_page: str
    fill: dict[str, str] = Field(default_factory=dict)  # field -> data class
    submit: bool = True
    assertion: Expectation


class UIAutomationDesign(BaseModel):
    spec_id: str
    spec_version: str
    pages: list[PageObjectDesign] = Field(default_factory=list)
    tests: list[UITestDesign] = Field(default_factory=list)
    generated_by: str = ""


class APITestDesign(BaseModel):
    automation_id: str
    test_case_id: str
    function_name: str
    method: str
    path: str
    operation_id: str = ""
    auth: bool = True
    precondition: Literal["none", "existing_resource", "duplicate"] = "none"
    payload: dict[str, str] = Field(default_factory=dict)  # field -> data class
    expected_status: int
    body_contains: str = ""
    validate_schema: bool = False
    destructive: bool = False


class APIAutomationDesign(BaseModel):
    spec_id: str
    spec_version: str
    tests: list[APITestDesign] = Field(default_factory=list)
    generated_by: str = ""


class ScriptRecord(BaseModel):
    automation_id: str
    test_case_id: str
    ac_ids: list[str]
    channel: Channel
    file: str
    function: str
    code_hash: str
    ac_hash: str
    spec_version: str


class AutomationSpec(BaseModel):
    spec_id: str
    spec_version: str
    feature: str
    framework: str = "python-playwright-pytest-pom + httpx"
    ui: UIAutomationDesign | None = None
    api: APIAutomationDesign | None = None
    scripts: list[ScriptRecord] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now)


class CodeValidationReport(BaseModel):
    spec_id: str
    passed: bool
    files: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    bundle_hash: str = ""


# --------------------------------------------------------------------------- execution
class ExecutionPlan(BaseModel):
    suites: list[str] = Field(default_factory=list)  # marker expressions e.g. ["smoke"]
    test_case_ids: list[str] = Field(default_factory=list)
    channels: list[Channel] = Field(default_factory=lambda: ["ui", "api"])
    rationale: str = ""


class TestResult(BaseModel):
    __test__ = False  # not a pytest test class
    nodeid: str
    automation_id: str = ""
    test_case_id: str = ""
    ac_ids: list[str] = Field(default_factory=list)
    spec_id: str = ""
    spec_version: str = ""
    channel: str = ""
    outcome: Literal["passed", "failed", "skipped", "error"]
    duration_s: float = 0.0
    error_type: str = ""
    message: str = ""
    traceback: str = ""
    screenshot: str = ""
    trace: str = ""


class ExecutionRun(BaseModel):
    id: str
    started_at: str
    finished_at: str = ""
    environment: str = ""
    base_url: str = ""
    command: list[str] = Field(default_factory=list)
    selection: dict[str, Any] = Field(default_factory=dict)
    exit_code: int | None = None
    results: list[TestResult] = Field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        out = {"total": len(self.results), "passed": 0, "failed": 0, "skipped": 0, "error": 0}
        for r in self.results:
            out[r.outcome] += 1
        return out


class FailureAnalysisItem(BaseModel):
    automation_id: str
    test_case_id: str
    nodeid: str = ""
    category: Literal["APPLICATION_DEFECT", "AUTOMATION_ISSUE", "ENVIRONMENT_ISSUE",
                      "SPEC_IMPLEMENTATION_DRIFT", "TEST_DATA_ISSUE", "UNKNOWN"]
    confidence: float = 0.5
    root_cause: str
    expected: str = ""
    actual: str = ""
    evidence: list[str] = Field(default_factory=list)
    recommendation: str = ""
    source: Literal["rule", "ai"] = "rule"


class FailureAnalysisReport(BaseModel):
    execution_id: str
    items: list[FailureAnalysisItem] = Field(default_factory=list)
    summary: str = ""
    generated_by: str = ""
    disclaimer: str = ("AI/heuristic analysis is a probable explanation. Verified facts are the execution "
                       "results in output/executions; they are never altered by analysis.")


class ReportNarrative(BaseModel):
    headline: str
    highlights: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    generated_by: str = ""


# --------------------------------------------------------------------------- versioning / governance
class ApprovalRecord(BaseModel):
    stage: Literal["spec", "test_cases", "scripts"]
    spec_id: str
    spec_version: str
    approved_by: str
    approved_at: str = Field(default_factory=utc_now)
    artifact_hash: str
    comment: str = ""


class ACChange(BaseModel):
    ac_id: str
    change: Literal["added", "modified", "removed"]
    old: dict[str, Any] | None = None
    new: dict[str, Any] | None = None
    fields_changed: list[str] = Field(default_factory=list)


class ImpactSet(BaseModel):
    acceptance_criteria: list[str] = Field(default_factory=list)
    scenarios: list[str] = Field(default_factory=list)
    test_cases: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
    unaffected_test_cases: list[str] = Field(default_factory=list)


class ChangeRecord(BaseModel):
    id: str
    spec_id: str
    from_version: str
    to_version: str
    created_at: str = Field(default_factory=utc_now)
    ac_changes: list[ACChange] = Field(default_factory=list)
    other_changes: list[str] = Field(default_factory=list)
    impact: ImpactSet = Field(default_factory=ImpactSet)
    status: Literal["PENDING_SPEC_APPROVAL", "REGENERATED", "EXECUTED", "NO_CHANGE"] = "PENDING_SPEC_APPROVAL"
    analysis: str = ""
    history: list[str] = Field(default_factory=list)
