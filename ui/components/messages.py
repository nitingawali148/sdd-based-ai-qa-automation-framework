"""Reusable component: reads alert / validation messages rendered by the application."""

from __future__ import annotations

from playwright.sync_api import Page

MESSAGE_SELECTOR = "[role=alert], .error, .field-error, .validation-message, .invalid-feedback"


class MessageArea:
    def __init__(self, page: Page) -> None:
        self.page = page

    def visible_texts(self) -> list[str]:
        texts: list[str] = []
        loc = self.page.locator(MESSAGE_SELECTOR)
        for i in range(loc.count()):
            item = loc.nth(i)
            if item.is_visible():
                t = (item.inner_text() or "").strip()
                if t and t not in texts:
                    texts.append(t)
        return texts
