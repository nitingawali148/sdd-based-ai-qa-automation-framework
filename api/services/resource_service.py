"""Generic resource helpers used for API test preconditions (setup through the public API only)."""

from __future__ import annotations

import re
from typing import Any

from api.clients.api_client import ApiClient


def create_resource(api: ApiClient, collection_path: str, payload: dict[str, Any], token: str | None) -> dict[str, Any]:
    response = api.post(collection_path, json=payload, token=token)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Precondition failed: POST {collection_path} -> {response.status_code}: "
                           f"{response.text[:200]}")
    return dict(response.json())


def item_path(template: str, resource_id: Any) -> str:
    """'/api/users/{user_id}' + 7 -> '/api/users/7' (the last path parameter is the resource id)."""
    return re.sub(r"\{[^}]+\}(?!.*\{)", str(resource_id), template)
