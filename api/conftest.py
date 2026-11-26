"""API fixtures: HTTPX client and an admin bearer token obtained through the login API."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from api.clients.api_client import ApiClient


@pytest.fixture(scope="session")
def api(base_url: str) -> Iterator[ApiClient]:
    client = ApiClient(base_url)
    yield client
    client.close()


@pytest.fixture(scope="session")
def auth_token(api: ApiClient) -> str:
    email = os.environ.get("SDD_DEMO_ADMIN_EMAIL")
    password = os.environ.get("SDD_DEMO_ADMIN_PASSWORD")
    if not email or not password:
        pytest.fail("TEST-DATA: SDD_DEMO_ADMIN_EMAIL / SDD_DEMO_ADMIN_PASSWORD are not set (.env)")
    return api.login(email, password)
