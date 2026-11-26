"""Flow 4 - Execution Flow.

Approved Scripts (gate: approved + unmodified) -> Pytest Execution -> Result Collection
-> Failure Analysis -> Report Generation
"""

from __future__ import annotations

from crewai.flow.flow import Flow, listen, or_, router, start

from core.config import settings
from core.logger import audit
from core.state import ExecutionFlowState
from flows import stages
from reporting.dashboard import build_reports


class ExecutionFlow(Flow[ExecutionFlowState]):
    @start()
    def check_scripts(self) -> list[str]:
        runnable, problems = stages.runnable_specs(self.state.spec_ids or None)
        self.state.spec_ids = runnable
        self.state.message = "; ".join(problems)
        return runnable

    @router(check_scripts)
    def script_gate(self) -> str:
        env = settings().environment(self.state.environment or None)
        if env.get("production") and not self.state.allow_production:
            self.state.gate("environment", "BLOCKED", f"'{env['name']}' is a production environment")
            return "blocked"
        if not self.state.spec_ids:
            self.state.gate("approved_scripts", "BLOCKED", self.state.message or "no approved scripts")
            return "blocked"
        self.state.gate("approved_scripts", "PASSED", ", ".join(self.state.spec_ids))
        return "run"

    @listen("run")
    def execute(self) -> None:
        run = stages.execute_tests(self.state.spec_ids, self.state.test_case_ids or None, self.state.suites or None,
                                   self.state.allow_destructive, self.state.environment, self.state.allow_production)
        self.state.execution_id = run.id
        self.state.summary = run.summary
        self.state.artifacts["execution"] = str(settings().path("executions") / f"{run.id}.json")
        if not run.results:
            self.state.message = "pytest produced no results - see the execution log (nothing was fabricated)"

    @listen(execute)
    def analyse(self) -> None:
        from core.models import ExecutionRun
        import json
        from pathlib import Path

        run = ExecutionRun.model_validate(json.loads(Path(self.state.artifacts["execution"]).read_text("utf-8")))
        try:
            report = stages.analyse_failures(run)
        except Exception as exc:  # noqa: BLE001 - analysis is advisory; results are already stored
            audit.write("failure_analysis_unavailable", execution_id=run.id, error=str(exc)[:500])
            self.state.message = (f"AI failure analysis unavailable ({type(exc).__name__}: {str(exc)[:160]}). "
                                  "Test results are unaffected.")
            return
        self.state.artifacts["failure_analysis"] = str(settings().path("analysis") / f"{run.id}-failure-analysis.yaml")
        self.state.message = report.summary

    @listen(analyse)
    def report(self) -> None:
        paths = build_reports()
        self.state.artifacts.update(paths)
        self.state.status = "EXECUTED"

    @listen("blocked")
    def on_blocked(self) -> None:
        self.state.status = "BLOCKED"
        self.state.next_action = "Approve the scripts (python main.py approve <SPEC> --stage scripts) before executing"

    @listen(or_(report, on_blocked))
    def finish(self) -> ExecutionFlowState:
        audit.write("flow", flow="execution", specs=self.state.spec_ids, status=self.state.status,
                    execution_id=self.state.execution_id, summary=self.state.summary)
        return self.state
