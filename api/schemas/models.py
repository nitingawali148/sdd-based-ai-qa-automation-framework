"""Pydantic models mirroring the OpenAPI components (typed access in hand-written API helpers)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"]


class User(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    name: str
    email: str
    role: Literal["admin", "viewer"]
    created_at: str


class ErrorBody(BaseModel):
    detail: str
