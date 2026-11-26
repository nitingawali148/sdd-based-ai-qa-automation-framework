"""Framework configuration: config/framework.yaml + .env (secrets only in .env)."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)
if not (ROOT / ".env").exists():
    load_dotenv(ROOT / ".env.example", override=False)

# CrewAI must stay local: no telemetry, no tracing uploads.
for _k, _v in {"CREWAI_DISABLE_TELEMETRY": "true", "OTEL_SDK_DISABLED": "true",
               "CREWAI_TRACING_ENABLED": "false", "PYTHONIOENCODING": "utf-8"}.items():
    os.environ.setdefault(_k, _v)

_ENV_REF = re.compile(r"\$\{([A-Z0-9_]+)(?::([^}]*))?\}")


def expand_env(value: Any) -> Any:
    """Expand ${VAR} / ${VAR:default} references recursively."""
    if isinstance(value, str):
        return _ENV_REF.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    return value


class Settings:
    """Read-only view over framework.yaml with typed helpers."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    # ---- paths -------------------------------------------------------------
    def path(self, key: str) -> Path:
        p = ROOT / self.data["paths"][key]
        if not p.suffix:
            p.mkdir(parents=True, exist_ok=True)
        return p

    # ---- LLM ---------------------------------------------------------------
    @property
    def llm_provider(self) -> str:
        return os.environ.get("LLM_PROVIDER", "offline").strip().lower()

    @property
    def llm_model(self) -> str:
        if self.llm_provider == "openai":
            return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        if self.llm_provider == "groq":
            return os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
        return os.environ.get("LLM_MODEL", "llama3.1:8b")

    @property
    def llm_temperature(self) -> float:
        return float(os.environ.get("LLM_TEMPERATURE", "0.1"))

    # ---- environments -------------------------------------------------------
    @property
    def env_name(self) -> str:
        return os.environ.get("SDD_ENV", "local")

    def environment(self, name: str | None = None) -> dict[str, Any]:
        name = name or self.env_name
        envs = self.data.get("environments", {})
        if name not in envs:
            raise KeyError(f"Unknown environment '{name}'. Known: {', '.join(envs)}")
        return {"name": name, **expand_env(envs[name])}

    def section(self, key: str) -> dict[str, Any]:
        return dict(self.data.get(key, {}))


@lru_cache(maxsize=1)
def settings() -> Settings:
    with (ROOT / "config" / "framework.yaml").open(encoding="utf-8") as fh:
        return Settings(yaml.safe_load(fh))


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)
