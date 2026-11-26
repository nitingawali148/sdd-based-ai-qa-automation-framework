"""Paths and settings for the dashboard.

The dashboard sits next to the framework and reads its artifacts (read-only). It never writes into the
framework's specifications; its own run records go to ./runs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent.parent


def _locate_framework() -> Path:
    """SDD_FRAMEWORK_DIR, else the parent folder (dashboard inside the framework repo), else a sibling folder."""
    if os.environ.get("SDD_FRAMEWORK_DIR"):
        return Path(os.environ["SDD_FRAMEWORK_DIR"]).resolve()
    parent = DASHBOARD_DIR.parent
    if (parent / "main.py").exists() and (parent / "specifications").exists():
        return parent.resolve()
    return (parent / "qa-sdd-crewai-framework").resolve()


FRAMEWORK_DIR = _locate_framework()
RUNS_DIR = DASHBOARD_DIR / "runs"
STATIC_DIR = DASHBOARD_DIR / "static"

HOST = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("DASHBOARD_PORT", "8090"))


def framework_python() -> str:
    """Python interpreter used to run the framework's pytest suite (the framework's own venv)."""
    for candidate in (FRAMEWORK_DIR / ".venv" / "Scripts" / "python.exe", FRAMEWORK_DIR / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def framework_available() -> bool:
    return (FRAMEWORK_DIR / "main.py").exists() and (FRAMEWORK_DIR / "specifications").exists()
