"""Optional Git integration: commit approved snapshots (disabled by default in framework.yaml)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from core.config import ROOT, settings
from core.logger import log


def git_available() -> bool:
    return shutil.which("git") is not None and (ROOT / ".git").exists()


def commit_snapshot(paths: list[Path], message: str) -> bool:
    cfg = settings().section("versioning").get("git", {})
    if not (cfg.get("enabled") and cfg.get("auto_commit")):
        return False
    if not git_available():
        log.warning("Git commit skipped: no git executable or repository at %s", ROOT)
        return False
    rels = [str(p.relative_to(ROOT)) for p in paths]
    subprocess.run(["git", "add", "--", *rels], cwd=ROOT, check=True, timeout=60)
    subprocess.run(["git", "commit", "-m", message, "--", *rels], cwd=ROOT, check=True, timeout=60)
    return True
