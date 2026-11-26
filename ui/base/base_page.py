"""BasePage: navigation, safe input, and message assertions with expected-vs-actual evidence."""

from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect

from ui.components.messages import MessageArea

DEFAULT_TIMEOUT_MS = 5_000


class BasePage:
    NAME = "Base"
    PATH = "/"

    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.messages = MessageArea(page)

    # ------------------------------------------------------------------ navigation
    def open(self) -> BasePage:
        self.page.goto(f"{self.base_url}{self.PATH}")
        return self

    def expect_loaded(self) -> BasePage:
        pattern = re.compile(re.escape(self.PATH) + r"/?(?:[?#].*)?$")
        try:
            expect(self.page).to_have_url(pattern, timeout=DEFAULT_TIMEOUT_MS)
        except AssertionError as exc:
            raise AssertionError(
                f"SDD-EXPECTED navigation to the {self.NAME} page ({self.PATH}); actual URL: {self.page.url}; "
                f"visible messages: {self.messages.visible_texts()}") from exc
        return self

    # ------------------------------------------------------------------ input
    @staticmethod
    def fill(locator: Locator, value: str | None) -> None:
        if value is None:  # 'missing' data class: leave the field untouched
            return
        locator.fill(value)

    # ------------------------------------------------------------------ assertions
    def expect_message(self, text: str) -> BasePage:
        try:
            expect(self.page.get_by_text(text, exact=True).first).to_be_visible(timeout=DEFAULT_TIMEOUT_MS)
        except AssertionError as exc:
            raise AssertionError(f"SDD-EXPECTED message \"{text}\" to be displayed; actual visible messages: "
                                 f"{self.messages.visible_texts()}") from exc
        return self

    def expect_no_message(self, text: str) -> BasePage:
        self.page.wait_for_load_state("domcontentloaded")
        visible = self.messages.visible_texts()
        if text in visible:
            raise AssertionError(f"SDD-EXPECTED message \"{text}\" NOT to be displayed; actual visible messages: "
                                 f"{visible}")
        return self
