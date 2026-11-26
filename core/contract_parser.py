"""Parse and validate LLM replies against the Pydantic artifact contracts.

Used by the CrewAI task guardrail (so the agent gets the error and retries) and by the crew runner.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


def extract_json(raw: str) -> str:
    """Take the outermost JSON object from an LLM reply (tolerates code fences / leading prose)."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


def drop_nulls(value: Any) -> Any:
    """LLMs often emit null for 'empty'; drop nulls so contract defaults apply (required fields still fail)."""
    if isinstance(value, dict):
        return {k: drop_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [drop_nulls(v) for v in value if v is not None]
    return value


def parse_contract(raw: str, model_cls: type[BaseModel]) -> BaseModel:
    """Raise ValueError (JSONDecodeError / ValidationError) when the reply does not fit the contract."""
    return model_cls.model_validate(drop_nulls(json.loads(extract_json(raw))))
