"""Static validation of generated automation before human script approval.

Checks: syntax, forbidden/unsafe constructs, hard-coded secrets, region integrity and traceability markers
(every test maps to an approved, active test case and automation ID).
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
from pathlib import Path

from core.models import CodeValidationReport, Finding, TestCaseSet

FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "breakpoint", "input"}
FORBIDDEN_MODULES = {"subprocess", "socket", "ctypes", "pickle", "shutil"}
FORBIDDEN_ATTRS = {("os", "system"), ("os", "popen"), ("os", "remove"), ("os", "rmdir"), ("os", "unlink")}
_SECRET_ASSIGN = re.compile(r"(password|passwd|secret|token|api_key)\s*=\s*[\"'][^\"'${}]{4,}[\"']", re.I)
REQUIRED_MARKERS = ("spec", "ac", "tc", "automation_id")


def bundle_hash(files: list[Path]) -> str:
    h = hashlib.sha256()
    for f in sorted(files, key=lambda p: p.as_posix()):
        h.update(f.as_posix().encode())
        h.update(f.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def _markers(fn: ast.FunctionDef) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for dec in fn.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Attribute) \
                and target.value.attr == "mark":
            args = [a.value for a in dec.args if isinstance(a, ast.Constant)] if isinstance(dec, ast.Call) else []
            out[target.attr] = [str(a) for a in args]
    return out


def validate_code(spec_id: str, files: list[Path], root: Path, cases: TestCaseSet) -> CodeValidationReport:
    findings: list[Finding] = []

    def add(code: str, sev: str, msg: str, artifact: str = "") -> None:
        findings.append(Finding(code=code, severity=sev, message=msg, artifact_id=artifact))  # type: ignore[arg-type]

    active = {t.id: t for t in cases.test_cases if t.status == "active"}
    seen_tcs: set[str] = set()
    secrets = [v for k, v in os.environ.items() if re.search(r"PASSWORD|SECRET|TOKEN|API_KEY", k) and len(v) >= 6]

    for path in files:
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=rel)
            compile(tree, rel, "exec")
        except SyntaxError as exc:
            add("SYNTAX_ERROR", "error", f"{rel}:{exc.lineno}: {exc.msg}", rel)
            continue
        begins = re.findall(r"^# >>> sdd:begin (\S+)$", text, re.M)
        ends = re.findall(r"^# <<< sdd:end (\S+)$", text, re.M)
        if begins != ends:
            add("REGION_MISMATCH", "error", f"{rel}: generated region markers are unbalanced", rel)
        for secret in secrets:
            if secret in text:
                add("HARDCODED_SECRET", "error", f"{rel}: contains the value of a secret environment variable", rel)
        if _SECRET_ASSIGN.search(text):
            add("HARDCODED_SECRET", "error", f"{rel}: hard-coded credential literal", rel)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                for n in names:
                    if n.split(".")[0] in FORBIDDEN_MODULES:
                        add("FORBIDDEN_IMPORT", "error", f"{rel}:{node.lineno}: import of '{n}' is not allowed", rel)
            elif isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name) and f.id in FORBIDDEN_CALLS:
                    add("FORBIDDEN_CALL", "error", f"{rel}:{node.lineno}: call to '{f.id}' is not allowed", rel)
                if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and (f.value.id, f.attr) \
                        in FORBIDDEN_ATTRS:
                    add("FORBIDDEN_CALL", "error", f"{rel}:{node.lineno}: '{f.value.id}.{f.attr}' is not allowed", rel)
        if "/tests/" not in f"/{rel}":
            continue
        for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]:
            marks = _markers(fn)
            missing = [m for m in REQUIRED_MARKERS if m not in marks]
            if missing:
                add("MISSING_TRACE_MARKER", "error", f"{rel}::{fn.name} lacks markers {missing}", fn.name)
                continue
            tc_id = marks["tc"][0]
            seen_tcs.add(tc_id)
            tc = active.get(tc_id)
            if tc is None:
                add("UNKNOWN_TEST_CASE", "error", f"{rel}::{fn.name} maps to {tc_id}, which is not an active "
                    "approved test case", fn.name)
                continue
            if marks["automation_id"][0] != tc.automation_id:
                add("AUTOMATION_ID_MISMATCH", "error", f"{fn.name}: automation_id {marks['automation_id'][0]} != "
                    f"{tc.automation_id}", fn.name)
            if marks["spec"][0] != spec_id:
                add("SPEC_MISMATCH", "error", f"{fn.name}: spec marker {marks['spec'][0]} != {spec_id}", fn.name)
            if sorted(marks["ac"]) != sorted(tc.ac_ids):
                add("AC_MISMATCH", "error", f"{fn.name}: AC markers {marks['ac']} != test case {tc.ac_ids}", fn.name)
    for tc_id, tc in active.items():
        if tc_id not in seen_tcs:
            add("TEST_CASE_NOT_AUTOMATED", "error", f"{tc_id} ({tc.channel.upper()}) has no automation script", tc_id)
    return CodeValidationReport(spec_id=spec_id, passed=not any(f.severity == "error" for f in findings),
                                files=[p.relative_to(root).as_posix() for p in files], findings=findings,
                                bundle_hash=bundle_hash(files))
