"""SDD QA framework CLI.

  python main.py spec REQ-001 [--regenerate]       Flow 1: requirement -> validated spec (stops at approval)
  python main.py approve SPEC-LOGIN-001 --stage spec|test_cases|scripts --by "Name" [--comment ...]
  python main.py design SPEC-LOGIN-001              Flow 2: approved spec -> scenarios, test cases, data
  python main.py automate SPEC-LOGIN-001            Flow 3: approved test cases -> staged, validated scripts
  python main.py execute [SPEC ...] [--tc TC-..] [--suite smoke] [--allow-destructive] [--env local]
  python main.py change SPEC-LOGIN-001              Flow 5: detect/advance a specification change
  python main.py run REQ-001 [REQ-002 ...]          run flows 1-4 per requirement until the next human gate
  python main.py status | trace | report | history SPEC-...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from core.config import settings
from core.logger import get_logger

log = get_logger("sdd.cli")


def _print_state(title: str, state: Any) -> None:
    data = state.model_dump() if hasattr(state, "model_dump") else dict(state)
    print(f"\n=== {title}: {data.get('status')} ===")
    if data.get("spec_id"):
        print(f"  spec          : {data['spec_id']}")
    for g in data.get("gates", []):
        print(f"  gate          : {g['gate']:<28} {g['status']}{' - ' + g['reason'] if g.get('reason') else ''}")
    for key in ("scenario_count", "test_case_count", "execution_id", "summary", "impacted_test_cases",
                "change_id", "staged_files"):
        if data.get(key):
            print(f"  {key:<14}: {data[key]}")
    if data.get("message"):
        print(f"  message       : {data['message']}")
    for f in data.get("findings", [])[:15]:
        print(f"  finding       : [{f['severity']}] {f['code']} {f.get('artifact_id', '')}: {f['message'][:110]}")
    for k, v in data.get("artifacts", {}).items():
        print(f"  artifact      : {k} -> {v}")
    if data.get("next_action"):
        print(f"  NEXT (human)  : {data['next_action']}")


def cmd_spec(a: argparse.Namespace) -> int:
    from flows.specification_flow import SpecificationFlow

    flow = SpecificationFlow()
    flow.kickoff(inputs={"requirement_id": a.requirement_id.upper(), "regenerate": a.regenerate})
    _print_state("Specification Flow", flow.state)
    return 0 if flow.state.status != "NEEDS_CLARIFICATION" else 2


def cmd_design(a: argparse.Namespace) -> int:
    from flows.test_design_flow import TestDesignFlow

    flow = TestDesignFlow()
    flow.kickoff(inputs={"spec_id": a.spec_id})
    _print_state("Test Design Flow", flow.state)
    return 0 if flow.state.status not in ("BLOCKED", "COVERAGE_FAILED") else 2


def cmd_automate(a: argparse.Namespace) -> int:
    from flows.automation_flow import AutomationFlow

    flow = AutomationFlow()
    flow.kickoff(inputs={"spec_id": a.spec_id})
    _print_state("Automation Flow", flow.state)
    return 0 if flow.state.status not in ("BLOCKED", "CODE_VALIDATION_FAILED") else 2


def cmd_execute(a: argparse.Namespace) -> int:
    from flows.execution_flow import ExecutionFlow

    if a.headed:
        os.environ["SDD_HEADED"] = "1"
    if a.slowmo:
        os.environ["SDD_SLOWMO"] = str(a.slowmo)
    flow = ExecutionFlow()
    flow.kickoff(inputs={"spec_ids": a.spec_ids, "test_case_ids": a.tc, "suites": a.suite,
                         "allow_destructive": a.allow_destructive, "allow_production": a.allow_production,
                         "environment": a.env})
    _print_state("Execution Flow", flow.state)
    if flow.state.status == "BLOCKED":
        return 2
    return 0 if not flow.state.summary.get("failed") and not flow.state.summary.get("error") else 1


def cmd_change(a: argparse.Namespace) -> int:
    from flows.change_impact_flow import ChangeImpactFlow

    flow = ChangeImpactFlow()
    flow.kickoff(inputs={"spec_id": a.spec_id})
    _print_state("Specification Change Flow", flow.state)
    return 0


def cmd_approve(a: argparse.Namespace) -> int:
    from versioning.version_manager import ApprovalError, VersionManager

    try:
        rec = VersionManager().approve(a.spec_id, a.stage, a.by, a.comment)
    except ApprovalError as exc:
        print(f"APPROVAL REFUSED: {exc}")
        return 2
    print(f"APPROVED: {rec.spec_id} v{rec.spec_version} stage={rec.stage} by {rec.approved_by} "
          f"(hash {rec.artifact_hash})")
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    """Run flows 1-4 for each requirement, stopping at the first gate that needs a human."""
    from core.artifact_manager import ArtifactManager
    from flows.automation_flow import AutomationFlow
    from flows.execution_flow import ExecutionFlow
    from flows.specification_flow import SpecificationFlow
    from flows.test_design_flow import TestDesignFlow

    ready = []
    for req in a.requirement_ids:
        sf = SpecificationFlow()
        sf.kickoff(inputs={"requirement_id": req.upper()})
        _print_state(f"{req} - Specification Flow", sf.state)
        if sf.state.status != "SPEC_APPROVED":
            continue
        td = TestDesignFlow()
        td.kickoff(inputs={"spec_id": sf.state.spec_id})
        _print_state(f"{req} - Test Design Flow", td.state)
        if td.state.status != "TEST_CASES_APPROVED":
            continue
        af = AutomationFlow()
        af.kickoff(inputs={"spec_id": sf.state.spec_id})
        _print_state(f"{req} - Automation Flow", af.state)
        if af.state.status == "SCRIPTS_APPROVED":
            ready.append(sf.state.spec_id)
    if ready and not a.no_execute:
        ef = ExecutionFlow()
        ef.kickoff(inputs={"spec_ids": ready, "allow_destructive": a.allow_destructive})
        _print_state("Execution Flow", ef.state)
    elif not ready:
        print("\nNo specification is ready for execution yet - complete the human approvals listed above.")
    print(f"\nKnown specifications: {', '.join(ArtifactManager().list_specs())}")
    return 0


def cmd_status(a: argparse.Namespace) -> int:
    from core.artifact_manager import ArtifactManager
    from versioning.version_manager import VersionManager

    am, vm = ArtifactManager(), VersionManager()
    print(f"{'SPEC':<16}{'VER':<6}{'STATUS':<22}{'APPROVED':<12}{'SPEC':<6}{'TCS':<6}{'SCRIPTS':<8}OPEN CHANGE")
    for sid in am.list_specs():
        spec = am.load_spec(sid)
        ok = {s: ("yes" if vm.is_approved(sid, s) else "-") for s in ("spec", "test_cases", "scripts")}
        ch = am.open_change(sid)
        print(f"{sid:<16}{spec.version:<6}{spec.status.value:<22}{','.join(vm.approved_versions(sid)) or '-':<12}"
              f"{ok['spec']:<6}{ok['test_cases']:<6}{ok['scripts']:<8}{ch.id + ' ' + ch.status if ch else '-'}")
    print(f"\nLLM provider: {settings().llm_provider} | environment: {settings().env_name}")
    return 0


def cmd_trace(a: argparse.Namespace) -> int:
    from traceability.engine import TraceabilityEngine, write_traceability_markdown

    data = TraceabilityEngine().build()
    path = write_traceability_markdown(data, settings().path("reports") / "traceability.md")
    print(path.read_text(encoding="utf-8"))
    print(json.dumps(data["coverage"], indent=2))
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    from reporting.dashboard import build_reports

    for k, v in build_reports().items():
        print(f"{k:<12}: {v}")
    return 0


def cmd_history(a: argparse.Namespace) -> int:
    from versioning.version_manager import VersionManager

    vm = VersionManager()
    for v in vm.approved_versions(a.spec_id):
        print(f"v{v}")
        for r in vm.approvals(a.spec_id, v):
            print(f"   {r.approved_at}  {r.stage:<11} by {r.approved_by:<20} hash={r.artifact_hash} {r.comment}")
    from core.artifact_manager import ArtifactManager

    for c in ArtifactManager().load_changes(a.spec_id):
        print(f"{c.id}: v{c.from_version} -> v{c.to_version} [{c.status}] {[x.ac_id + ':' + x.change for x in c.ac_changes]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="main.py", description="Spec-Driven Development QA framework (CrewAI)")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("spec", help="Flow 1: requirement -> validated specification")
    s.add_argument("requirement_id")
    s.add_argument("--regenerate", action="store_true", help="re-run agents (new version if one is approved)")
    s.set_defaults(func=cmd_spec)
    for name, fn, hlp in (("design", cmd_design, "Flow 2: test design"), ("automate", cmd_automate, "Flow 3"),
                          ("change", cmd_change, "Flow 5: specification change impact")):
        sp = sub.add_parser(name, help=hlp)
        sp.add_argument("spec_id")
        sp.set_defaults(func=fn)
    e = sub.add_parser("execute", help="Flow 4: execute approved scripts")
    e.add_argument("spec_ids", nargs="*")
    e.add_argument("--tc", action="append", default=[])
    e.add_argument("--suite", action="append", default=[], help="smoke | sanity | functional | regression")
    e.add_argument("--env", default="")
    e.add_argument("--allow-destructive", action="store_true")
    e.add_argument("--allow-production", action="store_true")
    e.add_argument("--headed", action="store_true", help="show the browser while UI tests run")
    e.add_argument("--slowmo", type=int, default=0, help="delay in ms between browser actions (with --headed)")
    e.set_defaults(func=cmd_execute)
    ap = sub.add_parser("approve", help="human approval gate")
    ap.add_argument("spec_id")
    ap.add_argument("--stage", required=True, choices=["spec", "test_cases", "scripts"])
    ap.add_argument("--by", required=True, help="the human approver's name")
    ap.add_argument("--comment", default="")
    ap.set_defaults(func=cmd_approve)
    r = sub.add_parser("run", help="flows 1-4 until the next human gate")
    r.add_argument("requirement_ids", nargs="+")
    r.add_argument("--no-execute", action="store_true")
    r.add_argument("--allow-destructive", action="store_true")
    r.set_defaults(func=cmd_run)
    for name, fn in (("status", cmd_status), ("trace", cmd_trace), ("report", cmd_report)):
        sub.add_parser(name).set_defaults(func=fn)
    h = sub.add_parser("history", help="approved versions, approvals and changes of a spec")
    h.add_argument("spec_id")
    h.set_defaults(func=cmd_history)
    return p


def main(argv: list[str] | None = None) -> int:
    import os

    args = build_parser().parse_args(argv)
    if os.environ.get("SDD_CREWAI_VERBOSE", "").lower() not in ("1", "true", "yes"):
        try:  # keep the CLI readable; CrewAI's rich flow panels are available with SDD_CREWAI_VERBOSE=1
            from crewai.events.utils.console_formatter import set_suppress_console_output

            set_suppress_console_output(True)
        except ImportError:
            pass
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
