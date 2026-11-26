"""Compare two versions of a specification (acceptance-criterion level)."""

from __future__ import annotations

from core.models import ACChange, FeatureSpec

_AC_FIELDS = ("title", "type", "given", "when", "then", "channels", "inputs", "expected_ui", "expected_api", "api",
              "start_page")


def diff_specs(old: FeatureSpec, new: FeatureSpec) -> tuple[list[ACChange], list[str], set[str]]:
    """Return (AC changes, other change notes, AC IDs indirectly impacted by non-AC changes)."""
    changes: list[ACChange] = []
    old_acs = {a.id: a for a in old.acceptance_criteria}
    new_acs = {a.id: a for a in new.acceptance_criteria}
    for ac_id in sorted(set(old_acs) | set(new_acs)):
        o, n = old_acs.get(ac_id), new_acs.get(ac_id)
        if o and not n:
            changes.append(ACChange(ac_id=ac_id, change="removed", old=o.model_dump(mode="json")))
        elif n and not o:
            changes.append(ACChange(ac_id=ac_id, change="added", new=n.model_dump(mode="json")))
        elif o and n and o.content_hash() != n.content_hash():
            od, nd = o.model_dump(mode="json"), n.model_dump(mode="json")
            fields = [f for f in _AC_FIELDS if od.get(f) != nd.get(f)] or ["source_text"]
            changes.append(ACChange(ac_id=ac_id, change="modified", old=od, new=nd, fields_changed=fields))

    notes: list[str] = []
    indirect: set[str] = set()
    old_inputs = {f.name: f.model_dump() for f in old.inputs}
    new_inputs = {f.name: f.model_dump() for f in new.inputs}
    for name in sorted(set(old_inputs) | set(new_inputs)):
        if old_inputs.get(name) != new_inputs.get(name):
            notes.append(f"Input field '{name}' changed")
            indirect |= {a.id for a in new.acceptance_criteria if name in a.inputs}
    old_pages = {p.name: p.model_dump() for p in old.ui_pages}
    new_pages = {p.name: p.model_dump() for p in new.ui_pages}
    for name in sorted(set(old_pages) | set(new_pages)):
        if old_pages.get(name) != new_pages.get(name):
            notes.append(f"UI page '{name}' changed")
            indirect |= {a.id for a in new.acceptance_criteria if a.start_page == name or
                         (a.expected_ui and a.expected_ui.value == name)}
    for label, a, b in (("business rules", old.business_rules, new.business_rules),
                        ("non-functional requirements", old.non_functional, new.non_functional),
                        ("API endpoints", old.api_endpoints, new.api_endpoints)):
        if [x.model_dump() for x in a] != [x.model_dump() for x in b]:
            notes.append(f"{label.capitalize()} changed (review; no automatic test impact)")
    indirect -= {c.ac_id for c in changes}
    return changes, notes, indirect
