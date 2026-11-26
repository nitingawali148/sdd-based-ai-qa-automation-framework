"""Console logging + structured, append-only audit log (JSONL) with secret masking."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from core.config import ROOT

_SECRET_KEYS = re.compile(r"(password|passwd|secret|token|api[_-]?key|authorization)", re.I)


def _secret_values() -> list[str]:
    vals = []
    for k, v in os.environ.items():
        if _SECRET_KEYS.search(k) and v and len(v) >= 4:
            vals.append(v)
    return sorted(vals, key=len, reverse=True)


def mask(value: Any) -> Any:
    """Mask secret-looking keys and any known secret value from the environment."""
    if isinstance(value, dict):
        return {k: ("***" if _SECRET_KEYS.search(str(k)) and v else mask(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(v) for v in value]
    if isinstance(value, str):
        for secret in _secret_values():
            value = value.replace(secret, "***")
        return value
    return value


def get_logger(name: str = "sdd") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s", "%H:%M:%S"))
        logger.addHandler(handler)
        logger.setLevel(os.environ.get("SDD_LOG_LEVEL", "INFO"))
        logger.propagate = False
    return logger


class AuditLog:
    """Append-only JSONL audit trail. Every agent run, gate decision and approval is recorded."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or ROOT / "output" / "audit" / "audit.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "event": event, **mask(fields)}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        return record

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    @contextmanager
    def agent_run(self, agent: str, task: str, **ctx: Any) -> Iterator[dict[str, Any]]:
        """Time an agent/crew execution and record outcome."""
        info: dict[str, Any] = {}
        start = time.perf_counter()
        status = "success"
        try:
            yield info
        except Exception as exc:  # noqa: BLE001
            status = "error"
            info["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self.write("agent_run", agent=agent, task=task, status=status,
                       duration_s=round(time.perf_counter() - start, 3), **ctx, **info)


audit = AuditLog()
log = get_logger()
