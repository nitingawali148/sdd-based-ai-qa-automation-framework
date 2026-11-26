"""Generated UI tests for SPEC-LOGIN-001 - User Login.

Source of truth: specifications/features/user-login/ (spec.yaml, acceptance_criteria.yaml, test_cases.yaml).
Do not hand-edit generated regions: change the specification and regenerate. Regions of tests that are not
impacted by a change are preserved verbatim.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from ui.pages.login_page import LoginPage  # noqa: F401
from ui.pages.dashboard_page import DashboardPage  # noqa: F401
from utils.test_data import TestData

DATA = TestData.for_feature('user-login')


# >>> sdd:begin UI-TEST-LOGIN-001
@pytest.mark.spec('SPEC-LOGIN-001', '1.0')
@pytest.mark.ac('AC-001')
@pytest.mark.tc('TC-LOGIN-001')
@pytest.mark.automation_id('UI-TEST-LOGIN-001')
@pytest.mark.priority('P1')
@pytest.mark.ui
@pytest.mark.functional
@pytest.mark.regression
@pytest.mark.smoke
def test_tc_login_001_submit_a_valid_email_and_password(page: Page, base_url: str) -> None:
    """TC-LOGIN-001: Submit a valid email and password -> they are navigated to the Dashboard page [UI]

    Acceptance criteria: AC-001 (SPEC-LOGIN-001 v1.0, ac_hash c32e81e34e758d29)
    Expected: User is navigated to the Dashboard page
    """
    login_page = LoginPage(page, base_url).open()
    login_page.fill_form(
        email=DATA.value('email', 'valid'),
        password=DATA.value('password', 'valid'),
    )
    login_page.submit()
    DashboardPage(page, base_url).expect_loaded()
# <<< sdd:end UI-TEST-LOGIN-001


# >>> sdd:begin UI-TEST-LOGIN-003
@pytest.mark.spec('SPEC-LOGIN-001', '1.0')
@pytest.mark.ac('AC-002')
@pytest.mark.tc('TC-LOGIN-003')
@pytest.mark.automation_id('UI-TEST-LOGIN-003')
@pytest.mark.priority('P2')
@pytest.mark.ui
@pytest.mark.functional
@pytest.mark.regression
def test_tc_login_003_submit_an_invalid_password(page: Page, base_url: str) -> None:
    """TC-LOGIN-003: Submit an invalid password -> "Invalid email or password" shown [UI]

    Acceptance criteria: AC-002 (SPEC-LOGIN-001 v1.0, ac_hash f65ed310fb478d6a)
    Expected: Message "Invalid email or password" is displayed
    """
    login_page = LoginPage(page, base_url).open()
    login_page.fill_form(
        email=DATA.value('email', 'valid'),
        password=DATA.value('password', 'invalid'),
    )
    login_page.submit()
    login_page.expect_message('Invalid email or password')
# <<< sdd:end UI-TEST-LOGIN-003


# >>> sdd:begin UI-TEST-LOGIN-005
@pytest.mark.spec('SPEC-LOGIN-001', '1.0')
@pytest.mark.ac('AC-003')
@pytest.mark.tc('TC-LOGIN-005')
@pytest.mark.automation_id('UI-TEST-LOGIN-005')
@pytest.mark.priority('P2')
@pytest.mark.ui
@pytest.mark.functional
@pytest.mark.regression
def test_tc_login_005_submits_an_empty_email(page: Page, base_url: str) -> None:
    """TC-LOGIN-005: Submits an empty email -> "Email is required" shown [UI]

    Acceptance criteria: AC-003 (SPEC-LOGIN-001 v1.0, ac_hash eae7857569b8f21d)
    Expected: Message "Email is required" is displayed
    """
    login_page = LoginPage(page, base_url).open()
    login_page.fill_form(
        email=DATA.value('email', 'empty'),
        password=DATA.value('password', 'valid'),
    )
    login_page.submit()
    login_page.expect_message('Email is required')
# <<< sdd:end UI-TEST-LOGIN-005


# >>> sdd:begin UI-TEST-LOGIN-006
@pytest.mark.spec('SPEC-LOGIN-001', '1.0')
@pytest.mark.ac('AC-004')
@pytest.mark.tc('TC-LOGIN-006')
@pytest.mark.automation_id('UI-TEST-LOGIN-006')
@pytest.mark.priority('P2')
@pytest.mark.ui
@pytest.mark.functional
@pytest.mark.regression
def test_tc_login_006_submits_an_empty_password(page: Page, base_url: str) -> None:
    """TC-LOGIN-006: Submits an empty password -> "Password is required" shown [UI]

    Acceptance criteria: AC-004 (SPEC-LOGIN-001 v1.0, ac_hash caa11d0a94a85131)
    Expected: Message "Password is required" is displayed
    """
    login_page = LoginPage(page, base_url).open()
    login_page.fill_form(
        email=DATA.value('email', 'valid'),
        password=DATA.value('password', 'empty'),
    )
    login_page.submit()
    login_page.expect_message('Password is required')
# <<< sdd:end UI-TEST-LOGIN-006


# >>> sdd:begin UI-TEST-LOGIN-007
@pytest.mark.spec('SPEC-LOGIN-001', '1.0')
@pytest.mark.ac('AC-005')
@pytest.mark.tc('TC-LOGIN-007')
@pytest.mark.automation_id('UI-TEST-LOGIN-007')
@pytest.mark.priority('P2')
@pytest.mark.ui
@pytest.mark.functional
@pytest.mark.regression
def test_tc_login_007_submits_it_with_a_password(page: Page, base_url: str) -> None:
    """TC-LOGIN-007: Submits it with a password -> "Invalid email or password" shown [UI]

    Acceptance criteria: AC-005 (SPEC-LOGIN-001 v1.0, ac_hash 30e5018e8624b349)
    Expected: Message "Invalid email or password" is displayed
    """
    login_page = LoginPage(page, base_url).open()
    login_page.fill_form(
        email=DATA.value('email', 'unregistered'),
        password=DATA.value('password', 'valid'),
    )
    login_page.submit()
    login_page.expect_message('Invalid email or password')
# <<< sdd:end UI-TEST-LOGIN-007


# >>> sdd:begin UI-TEST-LOGIN-009
@pytest.mark.spec('SPEC-LOGIN-001', '1.0')
@pytest.mark.ac('AC-006')
@pytest.mark.tc('TC-LOGIN-009')
@pytest.mark.automation_id('UI-TEST-LOGIN-009')
@pytest.mark.priority('P2')
@pytest.mark.ui
@pytest.mark.functional
@pytest.mark.regression
def test_tc_login_009_submits_a_password_shorter_than_8_characters(page: Page, base_url: str) -> None:
    """TC-LOGIN-009: Submits a password shorter than 8 characters -> "Password must be at least 8 characters" shown [UI]

    Acceptance criteria: AC-006 (SPEC-LOGIN-001 v1.0, ac_hash cc1bf909cc6eb56e)
    Expected: Message "Password must be at least 8 characters" is displayed
    """
    login_page = LoginPage(page, base_url).open()
    login_page.fill_form(
        email=DATA.value('email', 'valid'),
        password=DATA.value('password', 'too_short'),
    )
    login_page.submit()
    login_page.expect_message('Password must be at least 8 characters')
# <<< sdd:end UI-TEST-LOGIN-009


# >>> sdd:begin UI-TEST-LOGIN-010
@pytest.mark.spec('SPEC-LOGIN-001', '1.0')
@pytest.mark.ac('AC-006')
@pytest.mark.tc('TC-LOGIN-010')
@pytest.mark.automation_id('UI-TEST-LOGIN-010')
@pytest.mark.priority('P2')
@pytest.mark.ui
@pytest.mark.functional
@pytest.mark.regression
def test_tc_login_010_password_with_exactly_8_characters_does_not(page: Page, base_url: str) -> None:
    """TC-LOGIN-010: password with exactly 8 characters does not show "Password must be at least 8 characters" [UI]

    Acceptance criteria: AC-006 (SPEC-LOGIN-001 v1.0, ac_hash cc1bf909cc6eb56e)
    Expected: Message "Password must be at least 8 characters" is not displayed
    """
    login_page = LoginPage(page, base_url).open()
    login_page.fill_form(
        email=DATA.value('email', 'valid'),
        password=DATA.value('password', 'at_min'),
    )
    login_page.submit()
    login_page.expect_no_message('Password must be at least 8 characters')
# <<< sdd:end UI-TEST-LOGIN-010
