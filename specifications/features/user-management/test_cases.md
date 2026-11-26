# Test cases - SPEC-USERS-001 v1.0 (User Management API)

Generated from `test_cases.yaml`; approve with `python main.py approve SPEC-USERS-001 --stage test_cases --by "<name>"`.

## TC-USERS-001: Create a user with a valid name, email and role -> the API returns 201 and the created user [API]
- **AC:** AC-001 | **Scenario:** TS-USERS-001 | **Channel:** API | **Priority:** P1 | **Automation:** API-TEST-USERS-001 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (API); Given an authenticated admin; A valid access token is obtained for an authenticated admin

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | request | POST /api/users | name: <valid>, email: <valid>, role: <valid> |  |
| 2 | verify |  |  | Response status is 201, body matches the OpenAPI response schema |

**Expected result:** Response status is 201, body matches the OpenAPI response schema

## TC-USERS-002: Create a user with the same email -> "Email already exists" shown [API]
- **AC:** AC-002 | **Scenario:** TS-USERS-002 | **Channel:** API | **Priority:** P2 | **Automation:** API-TEST-USERS-002 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (API); Given an authenticated admin and an existing user; A valid access token is obtained for an authenticated admin; A resource with the same unique values already exists (created in test setup)

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | request | POST /api/users | name: <valid>, email: <duplicate>, role: <valid> |  |
| 2 | verify |  |  | Response status is 409, body contains "Email already exists" |

**Expected result:** Response status is 409, body contains "Email already exists"

## TC-USERS-003: Create a user with an empty email -> the API returns 422 [API]
- **AC:** AC-003 | **Scenario:** TS-USERS-003 | **Channel:** API | **Priority:** P2 | **Automation:** API-TEST-USERS-003 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (API); Given an authenticated admin; A valid access token is obtained for an authenticated admin

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | request | POST /api/users | name: <valid>, email: <empty>, role: <valid> |  |
| 2 | verify |  |  | Response status is 422 |

**Expected result:** Response status is 422

## TC-USERS-004: Retrieve the user by id -> the API returns 200 and the user [API]
- **AC:** AC-004 | **Scenario:** TS-USERS-004 | **Channel:** API | **Priority:** P1 | **Automation:** API-TEST-USERS-004 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (API); Given an authenticated admin and an existing user; A valid access token is obtained for an authenticated admin; A resource exists (created through the API in test setup)

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | request | GET /api/users/{user_id} |  |  |
| 2 | verify |  |  | Response status is 200, body matches the OpenAPI response schema |

**Expected result:** Response status is 200, body matches the OpenAPI response schema

## TC-USERS-005: List users -> the API returns 200 and the list of users [API]
- **AC:** AC-005 | **Scenario:** TS-USERS-005 | **Channel:** API | **Priority:** P1 | **Automation:** API-TEST-USERS-005 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (API); Given an authenticated admin; A valid access token is obtained for an authenticated admin

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | request | GET /api/users |  |  |
| 2 | verify |  |  | Response status is 200, body matches the OpenAPI response schema |

**Expected result:** Response status is 200, body matches the OpenAPI response schema

## TC-USERS-006: Update the user with a valid name, email and role -> the API returns 200 and the updated user [API]
- **AC:** AC-006 | **Scenario:** TS-USERS-006 | **Channel:** API | **Priority:** P1 | **Automation:** API-TEST-USERS-006 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (API); Given an authenticated admin and an existing user; A valid access token is obtained for an authenticated admin; A resource exists (created through the API in test setup)

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | request | PUT /api/users/{user_id} | name: <valid>, email: <valid>, role: <valid> |  |
| 2 | verify |  |  | Response status is 200, body matches the OpenAPI response schema |

**Expected result:** Response status is 200, body matches the OpenAPI response schema

## TC-USERS-007: Partially update the user role -> the API returns 200 and the updated user [API]
- **AC:** AC-007 | **Scenario:** TS-USERS-007 | **Channel:** API | **Priority:** P1 | **Automation:** API-TEST-USERS-007 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (API); Given an authenticated admin and an existing user; A valid access token is obtained for an authenticated admin; A resource exists (created through the API in test setup)

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | request | PATCH /api/users/{user_id} | role: <valid> |  |
| 2 | verify |  |  | Response status is 200, body matches the OpenAPI response schema |

**Expected result:** Response status is 200, body matches the OpenAPI response schema

## TC-USERS-008: Delete the user -> the API returns 204 [API]
- **AC:** AC-008 | **Scenario:** TS-USERS-008 | **Channel:** API | **Priority:** P1 | **Automation:** API-TEST-USERS-008 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (API); Given an authenticated admin and an existing user; A valid access token is obtained for an authenticated admin; A resource exists (created through the API in test setup)

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | request | DELETE /api/users/{user_id} |  |  |
| 2 | verify |  |  | Response status is 204 |

**Expected result:** Response status is 204

## TC-USERS-009: List users -> the API returns 401 [API]
- **AC:** AC-009 | **Scenario:** TS-USERS-009 | **Channel:** API | **Priority:** P2 | **Automation:** API-TEST-USERS-009 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (API); Given an unauthenticated client; No Authorization header is sent

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | request | GET /api/users |  |  |
| 2 | verify |  |  | Response status is 401 |

**Expected result:** Response status is 401
