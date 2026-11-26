"""Page object for the Dashboard page (/dashboard).

Generated from SPEC-LOGIN-001 (automation_spec.yaml). Locators use accessible labels and roles taken from
the specification's UI section. Regenerated only when the page definition in the specification changes.
"""

from __future__ import annotations

from playwright.sync_api import Page

from ui.base.base_page import BasePage


class DashboardPage(BasePage):
    NAME = 'Dashboard'
    PATH = '/dashboard'

    def __init__(self, page: Page, base_url: str) -> None:
        super().__init__(page, base_url)
        self.dashboard = page.get_by_role('heading', name='Dashboard', exact=True)
        self.sign_out = page.get_by_role('button', name='Sign out', exact=True)

    def submit(self) -> 'DashboardPage':
        self.sign_out.click()
        return self
