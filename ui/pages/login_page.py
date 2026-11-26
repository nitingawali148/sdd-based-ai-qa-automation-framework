"""Page object for the Login page (/login).

Generated from SPEC-LOGIN-001 (automation_spec.yaml). Locators use accessible labels and roles taken from
the specification's UI section. Regenerated only when the page definition in the specification changes.
"""

from __future__ import annotations

from playwright.sync_api import Page

from ui.base.base_page import BasePage


class LoginPage(BasePage):
    NAME = 'Login'
    PATH = '/login'

    def __init__(self, page: Page, base_url: str) -> None:
        super().__init__(page, base_url)
        self.email = page.get_by_label('Email', exact=True)
        self.password = page.get_by_label('Password', exact=True)
        self.sign_in = page.get_by_role('button', name='Sign in', exact=True)

    def fill_form(self, email: str | None = None, password: str | None = None) -> 'LoginPage':
        """Fill the form. `None` leaves a field untouched (used for 'missing' test data)."""
        self.fill(self.email, email)
        self.fill(self.password, password)
        return self

    def submit(self) -> 'LoginPage':
        self.sign_in.click()
        return self
