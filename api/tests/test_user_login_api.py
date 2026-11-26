"""Generated API tests for SPEC-LOGIN-001 - User Login.

Source of truth: specifications/features/user-login/ and specifications/api/openapi.yaml.
Do not hand-edit generated regions: change the specification and regenerate.
"""

from __future__ import annotations

import pytest

from api.clients.api_client import ApiClient
from api.services.resource_service import create_resource, item_path  # noqa: F401
from api.validators.response_validator import expect_body_contains, expect_schema, expect_status  # noqa: F401
from utils.test_data import TestData

DATA = TestData.for_feature('user-login')


# >>> sdd:begin API-TEST-LOGIN-002
@pytest.mark.spec('SPEC-LOGIN-001', '1.0')
@pytest.mark.ac('AC-001')
@pytest.mark.tc('TC-LOGIN-002')
@pytest.mark.automation_id('API-TEST-LOGIN-002')
@pytest.mark.priority('P1')
@pytest.mark.api
@pytest.mark.functional
@pytest.mark.regression
@pytest.mark.smoke
def test_tc_login_002_submit_a_valid_email_and_password(api: ApiClient) -> None:
    """TC-LOGIN-002: Submit a valid email and password -> they are navigated to the Dashboard page [API]

    Acceptance criteria: AC-001 (SPEC-LOGIN-001 v1.0, ac_hash c32e81e34e758d29)
    Expected: Response status is 200, body contains "access_token"
    """
    payload = DATA.payload({'email': 'valid', 'password': 'valid'})
    path = '/api/auth/login'
    response = api.request('POST', path, json=payload, token=None)
    expect_status(response, 200)
    expect_body_contains(response, 'access_token')
# <<< sdd:end API-TEST-LOGIN-002


# >>> sdd:begin API-TEST-LOGIN-004
@pytest.mark.spec('SPEC-LOGIN-001', '1.0')
@pytest.mark.ac('AC-002')
@pytest.mark.tc('TC-LOGIN-004')
@pytest.mark.automation_id('API-TEST-LOGIN-004')
@pytest.mark.priority('P2')
@pytest.mark.api
@pytest.mark.functional
@pytest.mark.regression
def test_tc_login_004_submit_an_invalid_password(api: ApiClient) -> None:
    """TC-LOGIN-004: Submit an invalid password -> "Invalid email or password" shown [API]

    Acceptance criteria: AC-002 (SPEC-LOGIN-001 v1.0, ac_hash f65ed310fb478d6a)
    Expected: Response status is 401, body contains "Invalid email or password"
    """
    payload = DATA.payload({'email': 'valid', 'password': 'invalid'})
    path = '/api/auth/login'
    response = api.request('POST', path, json=payload, token=None)
    expect_status(response, 401)
    expect_body_contains(response, 'Invalid email or password')
# <<< sdd:end API-TEST-LOGIN-004


# >>> sdd:begin API-TEST-LOGIN-008
@pytest.mark.spec('SPEC-LOGIN-001', '1.0')
@pytest.mark.ac('AC-005')
@pytest.mark.tc('TC-LOGIN-008')
@pytest.mark.automation_id('API-TEST-LOGIN-008')
@pytest.mark.priority('P2')
@pytest.mark.api
@pytest.mark.functional
@pytest.mark.regression
def test_tc_login_008_submits_it_with_a_password(api: ApiClient) -> None:
    """TC-LOGIN-008: Submits it with a password -> "Invalid email or password" shown [API]

    Acceptance criteria: AC-005 (SPEC-LOGIN-001 v1.0, ac_hash 30e5018e8624b349)
    Expected: Response status is 401, body contains "Invalid email or password"
    """
    payload = DATA.payload({'email': 'unregistered', 'password': 'valid'})
    path = '/api/auth/login'
    response = api.request('POST', path, json=payload, token=None)
    expect_status(response, 401)
    expect_body_contains(response, 'Invalid email or password')
# <<< sdd:end API-TEST-LOGIN-008
