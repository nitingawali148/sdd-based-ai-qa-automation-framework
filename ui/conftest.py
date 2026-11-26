"""UI fixtures: failure screenshots named after the automation ID."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.sync_api import Page

from core.config import ROOT


@pytest.fixture(autouse=True)
def _screenshot_on_failure(request: pytest.FixtureRequest, page: Page) -> Iterator[None]:
    yield
    rep = getattr(request.node, "rep_call", None)
    if rep is not None and rep.failed:
        marker = request.node.get_closest_marker("automation_id")
        name = marker.args[0] if marker else request.node.name
        path = ROOT / "output" / "screenshots" / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=str(path), full_page=True)
        except Exception:  # noqa: BLE001 - evidence capture must never mask the real failure
            pass
