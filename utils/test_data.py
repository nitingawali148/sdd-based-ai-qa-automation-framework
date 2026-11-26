"""Runtime test-data resolver for test_data/<feature>.yaml.

Expressions:
  ${env:VAR}            value from the environment (.env) - credentials live only there
  ${faker:unique_email} unique address on a reserved test domain
  ${faker:password:N}   random password of length N
  ${faker:name|word}    Faker values
  ${repeat:x:N}         'x' repeated N times (boundary values)
  ${omit}               leave the field out / untouched
"""

from __future__ import annotations

import os
import re
import secrets
import string
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from core.config import ROOT

OMIT = None
_EXPR = re.compile(r"^\$\{([a-z]+)(?::([^:}]*))?(?::([^}]*))?\}$")


class TestDataError(KeyError):
    """Raised when a data class or environment variable is missing (classified as TEST_DATA_ISSUE)."""


@lru_cache(maxsize=1)
def _faker() -> Any:
    from faker import Faker

    return Faker()


def resolve(expr: str) -> str | None:
    m = _EXPR.match(expr or "")
    if not m:
        return expr
    kind, a, b = m.group(1), m.group(2), m.group(3)
    if kind == "omit":
        return OMIT
    if kind == "env":
        if a not in os.environ:
            raise TestDataError(f"TEST-DATA: environment variable {a} is not set (.env)")
        return os.environ[a]
    if kind == "repeat":
        return (a or "x") * int(b or 1)
    if kind == "faker":
        if a == "unique_email":
            return f"qa.{uuid.uuid4().hex[:10]}@example.test"
        if a == "password":
            n = int(b or 12)
            alphabet = string.ascii_letters + string.digits
            return "Qa!" + "".join(secrets.choice(alphabet) for _ in range(max(n - 3, 1)))
        return str(getattr(_faker(), a)())
    raise TestDataError(f"TEST-DATA: unknown expression {expr}")


class TestData:
    __test__ = False

    def __init__(self, feature: str, fields: dict[str, dict[str, str]]) -> None:
        self.feature = feature
        self.fields = fields

    @classmethod
    def for_feature(cls, feature: str, root: Path | None = None) -> TestData:
        path = (root or ROOT / "test_data") / f"{feature}.yaml"
        if not path.exists():
            raise TestDataError(f"TEST-DATA: {path} not found - run the Test Design flow first")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(feature, data.get("fields", {}))

    def value(self, field: str, data_class: str) -> str | None:
        try:
            expr = self.fields[field][data_class]
        except KeyError as exc:
            raise TestDataError(f"TEST-DATA: no '{data_class}' value for field '{field}' in {self.feature}") from exc
        return resolve(expr)

    def payload(self, classes: dict[str, str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for field, cls in classes.items():
            v = self.value(field, cls)
            if v is not OMIT:
                out[field] = v
        return out
