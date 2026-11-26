"""Stable ID allocation and selective merge of regenerated artifacts.

IDs are keyed by a deterministic `key` (AC + channel + variant). Regenerating keeps the ID; brand-new keys
get the next free number; artifacts whose AC was removed are kept but marked `obsolete` (never deleted).
Artifacts outside the regeneration scope are preserved byte-for-byte.
"""

from __future__ import annotations

import re

from core.models import TestCase, TestCaseSet, TestScenario, TestScenarioSet


def _next_number(ids: list[str]) -> int:
    nums = [int(m.group(1)) for i in ids if (m := re.search(r"-(\d+)$", i))]
    return (max(nums) + 1) if nums else 1


def merge_scenarios(code: str, existing: TestScenarioSet | None, fresh: TestScenarioSet,
                    regenerated_ac_ids: set[str] | None, valid_ac_ids: set[str]) -> TestScenarioSet:
    old = {s.key: s for s in (existing.scenarios if existing else [])}
    in_scope = (lambda s: True) if regenerated_ac_ids is None else (lambda s: bool(set(s.ac_ids) & regenerated_ac_ids))
    counter = _next_number([s.id for s in old.values()])
    result: list[TestScenario] = []
    fresh_keys = set()
    for s in fresh.scenarios:
        if not in_scope(s):
            continue
        fresh_keys.add(s.key)
        prev = old.get(s.key)
        if prev:
            s.id = prev.id
        else:
            s.id = f"TS-{code}-{counter:03d}"
            counter += 1
        result.append(s)
    for key, prev in old.items():
        if key in fresh_keys:
            continue
        if not set(prev.ac_ids) <= valid_ac_ids or in_scope(prev):
            # AC removed, or AC regenerated but this variant no longer applies
            prev.status = "obsolete"
        result.append(prev)
    result.sort(key=lambda s: s.id)
    fresh.scenarios = result
    return fresh


def merge_test_cases(code: str, existing: TestCaseSet | None, fresh: TestCaseSet,
                     scenarios: TestScenarioSet, regenerated_ac_ids: set[str] | None) -> TestCaseSet:
    old = {t.key: t for t in (existing.test_cases if existing else [])}
    sc_by_key = {s.key: s for s in scenarios.scenarios}
    in_scope = (lambda t: True) if regenerated_ac_ids is None else (lambda t: bool(set(t.ac_ids) & regenerated_ac_ids))
    counter = _next_number([t.id for t in old.values()])
    result: list[TestCase] = []
    fresh_keys = set()
    for t in fresh.test_cases:
        if not in_scope(t):
            continue
        fresh_keys.add(t.key)
        prev = old.get(t.key)
        t.id = prev.id if prev else f"TC-{code}-{counter:03d}"
        if not prev:
            counter += 1
        t.scenario_id = sc_by_key[t.key].id if t.key in sc_by_key else t.scenario_id
        num = t.id.rsplit("-", 1)[-1]
        t.automation_id = f"{'UI' if t.channel == 'ui' else 'API'}-TEST-{code}-{num}"
        result.append(t)
    for key, prev in old.items():
        if key in fresh_keys:
            continue
        sc = sc_by_key.get(key)
        if sc is None or sc.status == "obsolete":
            prev.status = "obsolete"
        result.append(prev)
    result.sort(key=lambda t: t.id)
    fresh.test_cases = result
    return fresh
