"""Automation script manifest: which generated region implements which test case, with code hashes.

Used to (1) record approved scripts, (2) detect scripts edited after approval (restricted execution) and
(3) detect outdated scripts whose acceptance criterion changed.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from core.config import ROOT
from core.models import ScriptRecord, TestCaseSet
from generators.code_renderer import code_hash, parse_regions


def records_from_files(files: list[Path], cases: TestCaseSet, base: Path = ROOT) -> list[ScriptRecord]:
    by_aid = {t.automation_id: t for t in cases.test_cases if t.automation_id}
    out: list[ScriptRecord] = []
    for f in files:
        if not f.name.startswith("test_"):
            continue
        for aid, region in parse_regions(f.read_text(encoding="utf-8")).items():
            tc = by_aid.get(aid)
            if tc is None:
                continue
            fn = re.search(r"^def (test_\w+)\(", region, re.M)
            out.append(ScriptRecord(automation_id=aid, test_case_id=tc.id, ac_ids=tc.ac_ids, channel=tc.channel,
                                    file=f.relative_to(base).as_posix(), function=fn.group(1) if fn else "",
                                    code_hash=code_hash(region), ac_hash=tc.ac_hash, spec_version=tc.spec_version))
    return sorted(out, key=lambda r: r.automation_id)


def verify_scripts(records: list[ScriptRecord]) -> list[str]:
    """Return human-readable problems: missing files/regions or code changed after approval."""
    problems = []
    cache: dict[str, dict[str, str]] = {}
    for r in records:
        path = ROOT / r.file
        if not path.exists():
            problems.append(f"{r.automation_id}: {r.file} is missing")
            continue
        regions = cache.setdefault(r.file, parse_regions(path.read_text(encoding="utf-8")))
        region = regions.get(r.automation_id)
        if region is None:
            problems.append(f"{r.automation_id}: region not found in {r.file}")
        elif code_hash(region) != r.code_hash:
            problems.append(f"{r.automation_id}: {r.file} was modified after approval (hash mismatch)")
        else:
            try:
                ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                problems.append(f"{r.file}: syntax error {exc.msg}")
    return problems
