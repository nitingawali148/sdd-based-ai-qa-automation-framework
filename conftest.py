"""Root pytest fixtures: target environment, demo application lifecycle and base URL."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import pytest

from core.config import settings


@pytest.fixture(scope="session")
def sdd_environment() -> dict[str, Any]:
    return settings().environment()


@pytest.fixture(scope="session", autouse=True)
def demo_application(sdd_environment: dict[str, Any]) -> Iterator[None]:
    """Start the local demo app for the 'local' environment (never for remote environments)."""
    if not sdd_environment.get("start_demo_app"):
        yield
        return
    from demo_app.server import DemoServer

    parsed = urlparse(sdd_environment["base_url"])
    server = DemoServer(parsed.hostname or "127.0.0.1", parsed.port or 8765)
    started = server.start()
    yield
    if started:
        server.stop()


@pytest.fixture(scope="session")
def base_url(sdd_environment: dict[str, Any]) -> str:
    return str(sdd_environment["base_url"]).rstrip("/")
