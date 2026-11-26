"""CrewAI agents - one module per QA responsibility (see config/agents.yaml)."""

from agents import (  # noqa: F401
    requirement_agent,
    specification_agent,
    specification_validator,
    test_design_agent,
    test_case_agent,
    ui_design_agent,
    api_design_agent,
    test_data_agent,
    execution_agent,
    failure_analysis_agent,
    reporting_agent,
    change_impact_agent,
)

AGENT_MODULES = {
    requirement_agent.CONFIG_KEY: requirement_agent,
    specification_agent.CONFIG_KEY: specification_agent,
    specification_validator.CONFIG_KEY: specification_validator,
    test_design_agent.CONFIG_KEY: test_design_agent,
    test_case_agent.CONFIG_KEY: test_case_agent,
    ui_design_agent.CONFIG_KEY: ui_design_agent,
    api_design_agent.CONFIG_KEY: api_design_agent,
    test_data_agent.CONFIG_KEY: test_data_agent,
    execution_agent.CONFIG_KEY: execution_agent,
    failure_analysis_agent.CONFIG_KEY: failure_analysis_agent,
    reporting_agent.CONFIG_KEY: reporting_agent,
    change_impact_agent.CONFIG_KEY: change_impact_agent,
}
