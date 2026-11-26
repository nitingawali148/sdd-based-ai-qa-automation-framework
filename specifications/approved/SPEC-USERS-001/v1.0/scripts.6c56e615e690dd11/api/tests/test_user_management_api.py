"""Generated API tests for SPEC-USERS-001 - User Management API.

Source of truth: specifications/features/user-management/ and specifications/api/openapi.yaml.
Do not hand-edit generated regions: change the specification and regenerate.
"""

from __future__ import annotations

import pytest

from api.clients.api_client import ApiClient
from api.services.resource_service import create_resource, item_path  # noqa: F401
from api.validators.response_validator import expect_body_contains, expect_schema, expect_status  # noqa: F401
from utils.test_data import TestData

DATA = TestData.for_feature('user-management')


# >>> sdd:begin API-TEST-USERS-001
@pytest.mark.spec('SPEC-USERS-001', '1.0')
@pytest.mark.ac('AC-001')
@pytest.mark.tc('TC-USERS-001')
@pytest.mark.automation_id('API-TEST-USERS-001')
@pytest.mark.priority('P1')
@pytest.mark.api
@pytest.mark.functional
@pytest.mark.regression
@pytest.mark.smoke
def test_tc_users_001_create_a_user_with_a_valid_name(api: ApiClient, auth_token: str) -> None:
    """TC-USERS-001: Create a user with a valid name, email and role -> the API returns 201 and the created user [API]

    Acceptance criteria: AC-001 (SPEC-USERS-001 v1.0, ac_hash 2b87107a58887693)
    Expected: Response status is 201, body matches the OpenAPI response schema
    """
    payload = DATA.payload({'name': 'valid', 'email': 'valid', 'role': 'valid'})
    path = '/api/users'
    response = api.request('POST', path, json=payload, token=auth_token)
    expect_status(response, 201)
    expect_schema(response, 'POST', '/api/users', 201)
# <<< sdd:end API-TEST-USERS-001


# >>> sdd:begin API-TEST-USERS-002
@pytest.mark.spec('SPEC-USERS-001', '1.0')
@pytest.mark.ac('AC-002')
@pytest.mark.tc('TC-USERS-002')
@pytest.mark.automation_id('API-TEST-USERS-002')
@pytest.mark.priority('P2')
@pytest.mark.api
@pytest.mark.functional
@pytest.mark.regression
def test_tc_users_002_create_a_user_with_the_same_email(api: ApiClient, auth_token: str) -> None:
    """TC-USERS-002: Create a user with the same email -> "Email already exists" shown [API]

    Acceptance criteria: AC-002 (SPEC-USERS-001 v1.0, ac_hash d8a57b1d988ede4d)
    Expected: Response status is 409, body contains "Email already exists"
    """
    payload = DATA.payload({'name': 'valid', 'email': 'duplicate', 'role': 'valid'})
    create_resource(api, '/api/users', payload, token=auth_token)
    path = '/api/users'
    response = api.request('POST', path, json=payload, token=auth_token)
    expect_status(response, 409)
    expect_body_contains(response, 'Email already exists')
# <<< sdd:end API-TEST-USERS-002


# >>> sdd:begin API-TEST-USERS-003
@pytest.mark.spec('SPEC-USERS-001', '1.0')
@pytest.mark.ac('AC-003')
@pytest.mark.tc('TC-USERS-003')
@pytest.mark.automation_id('API-TEST-USERS-003')
@pytest.mark.priority('P2')
@pytest.mark.api
@pytest.mark.functional
@pytest.mark.regression
def test_tc_users_003_create_a_user_with_an_empty_email(api: ApiClient, auth_token: str) -> None:
    """TC-USERS-003: Create a user with an empty email -> the API returns 422 [API]

    Acceptance criteria: AC-003 (SPEC-USERS-001 v1.0, ac_hash 82a30f3568447392)
    Expected: Response status is 422
    """
    payload = DATA.payload({'name': 'valid', 'email': 'empty', 'role': 'valid'})
    path = '/api/users'
    response = api.request('POST', path, json=payload, token=auth_token)
    expect_status(response, 422)
# <<< sdd:end API-TEST-USERS-003


# >>> sdd:begin API-TEST-USERS-004
@pytest.mark.spec('SPEC-USERS-001', '1.0')
@pytest.mark.ac('AC-004')
@pytest.mark.tc('TC-USERS-004')
@pytest.mark.automation_id('API-TEST-USERS-004')
@pytest.mark.priority('P1')
@pytest.mark.api
@pytest.mark.functional
@pytest.mark.regression
@pytest.mark.smoke
def test_tc_users_004_retrieve_the_user_by_id(api: ApiClient, auth_token: str) -> None:
    """TC-USERS-004: Retrieve the user by id -> the API returns 200 and the user [API]

    Acceptance criteria: AC-004 (SPEC-USERS-001 v1.0, ac_hash efd019eae9c4f559)
    Expected: Response status is 200, body matches the OpenAPI response schema
    """
    existing = create_resource(api, '/api/users', DATA.payload({'name': "valid", 'email': "valid", 'role': "valid"}), token=auth_token)
    path = item_path('/api/users/{user_id}', existing["id"])
    response = api.request('GET', path, token=auth_token)
    expect_status(response, 200)
    expect_schema(response, 'GET', '/api/users/{user_id}', 200)
# <<< sdd:end API-TEST-USERS-004


# >>> sdd:begin API-TEST-USERS-005
@pytest.mark.spec('SPEC-USERS-001', '1.0')
@pytest.mark.ac('AC-005')
@pytest.mark.tc('TC-USERS-005')
@pytest.mark.automation_id('API-TEST-USERS-005')
@pytest.mark.priority('P1')
@pytest.mark.api
@pytest.mark.functional
@pytest.mark.regression
@pytest.mark.smoke
def test_tc_users_005_list_users(api: ApiClient, auth_token: str) -> None:
    """TC-USERS-005: List users -> the API returns 200 and the list of users [API]

    Acceptance criteria: AC-005 (SPEC-USERS-001 v1.0, ac_hash 42e52956c8f211a5)
    Expected: Response status is 200, body matches the OpenAPI response schema
    """
    path = '/api/users'
    response = api.request('GET', path, token=auth_token)
    expect_status(response, 200)
    expect_schema(response, 'GET', '/api/users', 200)
# <<< sdd:end API-TEST-USERS-005


# >>> sdd:begin API-TEST-USERS-006
@pytest.mark.spec('SPEC-USERS-001', '1.0')
@pytest.mark.ac('AC-006')
@pytest.mark.tc('TC-USERS-006')
@pytest.mark.automation_id('API-TEST-USERS-006')
@pytest.mark.priority('P1')
@pytest.mark.api
@pytest.mark.functional
@pytest.mark.regression
@pytest.mark.smoke
def test_tc_users_006_update_the_user_with_a_valid_name(api: ApiClient, auth_token: str) -> None:
    """TC-USERS-006: Update the user with a valid name, email and role -> the API returns 200 and the updated user [API]

    Acceptance criteria: AC-006 (SPEC-USERS-001 v1.0, ac_hash e5653eef2f84d321)
    Expected: Response status is 200, body matches the OpenAPI response schema
    """
    payload = DATA.payload({'name': 'valid', 'email': 'valid', 'role': 'valid'})
    existing = create_resource(api, '/api/users', DATA.payload({'name': "valid", 'email': "valid", 'role': "valid"}), token=auth_token)
    path = item_path('/api/users/{user_id}', existing["id"])
    response = api.request('PUT', path, json=payload, token=auth_token)
    expect_status(response, 200)
    expect_schema(response, 'PUT', '/api/users/{user_id}', 200)
# <<< sdd:end API-TEST-USERS-006


# >>> sdd:begin API-TEST-USERS-007
@pytest.mark.spec('SPEC-USERS-001', '1.0')
@pytest.mark.ac('AC-007')
@pytest.mark.tc('TC-USERS-007')
@pytest.mark.automation_id('API-TEST-USERS-007')
@pytest.mark.priority('P1')
@pytest.mark.api
@pytest.mark.functional
@pytest.mark.regression
@pytest.mark.smoke
def test_tc_users_007_partially_update_the_user_role(api: ApiClient, auth_token: str) -> None:
    """TC-USERS-007: Partially update the user role -> the API returns 200 and the updated user [API]

    Acceptance criteria: AC-007 (SPEC-USERS-001 v1.0, ac_hash 86e4f98b20ddea13)
    Expected: Response status is 200, body matches the OpenAPI response schema
    """
    payload = DATA.payload({'role': 'valid'})
    existing = create_resource(api, '/api/users', DATA.payload({'name': "valid", 'email': "valid", 'role': "valid"}), token=auth_token)
    path = item_path('/api/users/{user_id}', existing["id"])
    response = api.request('PATCH', path, json=payload, token=auth_token)
    expect_status(response, 200)
    expect_schema(response, 'PATCH', '/api/users/{user_id}', 200)
# <<< sdd:end API-TEST-USERS-007


# >>> sdd:begin API-TEST-USERS-008
@pytest.mark.spec('SPEC-USERS-001', '1.0')
@pytest.mark.ac('AC-008')
@pytest.mark.tc('TC-USERS-008')
@pytest.mark.automation_id('API-TEST-USERS-008')
@pytest.mark.priority('P1')
@pytest.mark.api
@pytest.mark.functional
@pytest.mark.regression
@pytest.mark.smoke
@pytest.mark.destructive
def test_tc_users_008_delete_the_user(api: ApiClient, auth_token: str) -> None:
    """TC-USERS-008: Delete the user -> the API returns 204 [API]

    Acceptance criteria: AC-008 (SPEC-USERS-001 v1.0, ac_hash 336030c3eb77fbad)
    Expected: Response status is 204
    """
    existing = create_resource(api, '/api/users', DATA.payload({'name': "valid", 'email': "valid", 'role': "valid"}), token=auth_token)
    path = item_path('/api/users/{user_id}', existing["id"])
    response = api.request('DELETE', path, token=auth_token)
    expect_status(response, 204)
# <<< sdd:end API-TEST-USERS-008


# >>> sdd:begin API-TEST-USERS-009
@pytest.mark.spec('SPEC-USERS-001', '1.0')
@pytest.mark.ac('AC-009')
@pytest.mark.tc('TC-USERS-009')
@pytest.mark.automation_id('API-TEST-USERS-009')
@pytest.mark.priority('P2')
@pytest.mark.api
@pytest.mark.functional
@pytest.mark.regression
def test_tc_users_009_list_users(api: ApiClient) -> None:
    """TC-USERS-009: List users -> the API returns 401 [API]

    Acceptance criteria: AC-009 (SPEC-USERS-001 v1.0, ac_hash 437d82bb445f2000)
    Expected: Response status is 401
    """
    path = '/api/users'
    response = api.request('GET', path, token=None)
    expect_status(response, 401)
# <<< sdd:end API-TEST-USERS-009
