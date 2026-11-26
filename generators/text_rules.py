"""Shared, deterministic text rules used by the offline rule engine and by validators."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

VAGUE_TERMS = [
    "quickly", "fast", "appropriate", "adequate", "user-friendly", "user friendly", "etc", "as needed",
    "tbd", "reasonable", "various", "some time", "approximately", "if possible", "should be able",
    r"\bsecure\b", "robust", "intuitive", "properly", "timely",
]
_VAGUE_RE = re.compile(r"(?<![\w-])(" + "|".join(t if t.startswith("\\") else re.escape(t)
                                                   for t in VAGUE_TERMS) + r")(?![\w-])", re.I)
QUOTED = re.compile(r"[\"“”']([^\"“”']{3,})[\"“”']")
STATUS = re.compile(r"\breturns?\s+(?:http\s+)?(\d{3})\b", re.I)


def vague_terms(text: str) -> list[str]:
    return sorted({m.group(1).lower() for m in _VAGUE_RE.finditer(text or "")})


def has_number(text: str) -> bool:
    return bool(re.search(r"\d", text or ""))


def snake(text: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower()
    return re.sub(r"_+", "_", s)


def pascal(text: str) -> str:
    return "".join(p.capitalize() for p in snake(text).split("_") if p)


def similarity(a: str, b: str) -> float:
    norm = lambda s: re.sub(r"\s+", " ", re.sub(r"[^\w\s\"']", " ", (s or "").lower())).strip()  # noqa: E731
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def split_gwt(text: str) -> tuple[str, str, str]:
    """Split 'Given X, when Y, then Z' (given optional). Returns ('', '', '') when not in GWT form."""
    t = text.strip().rstrip(".")
    m = re.match(r"^(?:given\s+(?P<given>.+?),\s*)?when\s+(?P<when>.+?),\s*then\s+(?P<then>.+)$", t, re.I | re.S)
    if not m:
        return "", "", ""
    return (m.group("given") or "").strip(), m.group("when").strip(), m.group("then").strip()


# ----------------------------------------------------------------------------- input classes
_EMPTY = r"(?:empty|blank|missing|no)"
_INVALID = r"(?:invalid|wrong|incorrect)"


def field_data_class(field_names: list[str], clause: str, field_type: str = "") -> str | None:
    """Return the data class a GWT clause implies for a field, or None when the field is not mentioned."""
    c = clause.lower()
    for name in field_names:
        n = re.escape(name.lower())
        if not re.search(rf"\b{n}\b", c):
            continue
        if re.search(rf"\b{_EMPTY}\s+{n}\b|\b{n}\s+(?:is\s+)?(?:empty|blank|missing)\b|\bwithout\s+(?:an?\s+)?{n}\b", c):
            return "empty"
        if re.search(rf"\b{n}\b[^,.;]*?\b(?:shorter than|fewer than|less than)\b", c):
            return "too_short"
        if re.search(rf"\b{n}\b[^,.;]*?\b(?:longer than|more than|exceeds?|exceeding)\b", c):
            return "too_long"
        if re.search(rf"\bunregistered\s+{n}\b|\b{n}\s+(?:that is\s+)?not registered\b", c):
            return "unregistered"
        if re.search(rf"\bsame\s+{n}\b|\bduplicate\s+{n}\b|\bexisting\s+{n}\b", c):
            return "duplicate"
        if re.search(rf"\bmalformed\s+{n}\b|\b{n}\s+in an invalid format\b", c):
            return "malformed"
        if re.search(rf"\b{_INVALID}\s+{n}\b", c):
            return "invalid"
        return "valid"
    return None


def list_mentions(field_names: list[str], clause: str) -> bool:
    c = clause.lower()
    return any(re.search(rf"\b{re.escape(n.lower())}\b", c) for n in field_names)


def classify_ac(text: str) -> str:
    t = text.lower()
    if re.search(r"shorter than|longer than|at least \d|at most \d|exceed|more than \d|fewer than \d|less than \d", t):
        return "boundary"
    if re.search(r"\b(invalid|empty|blank|wrong|incorrect|unregistered|missing|without|unauthenticated|"
                 r"same email|duplicate|error|denied|cannot|not allowed|expired)\b", t):
        return "negative"
    return "positive"
