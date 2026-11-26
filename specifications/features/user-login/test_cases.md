# Test cases - SPEC-LOGIN-001 v1.0 (User Login)

Generated from `test_cases.yaml`; approve with `python main.py approve SPEC-LOGIN-001 --stage test_cases --by "<name>"`.

## TC-LOGIN-001: Submit a valid email and password -> they are navigated to the Dashboard page [UI]
- **AC:** AC-001 | **Scenario:** TS-LOGIN-001 | **Channel:** UI | **Priority:** P1 | **Automation:** UI-TEST-LOGIN-001 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (UI); Given a registered user; Registered user credentials are provided through environment variables

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | navigate | Login page (/login) |  | Login page is displayed |
| 2 | fill | Email | valid |  |
| 3 | fill | Password | valid |  |
| 4 | click | Sign in button |  |  |
| 5 | verify |  |  | User is navigated to the Dashboard page |

**Expected result:** User is navigated to the Dashboard page

## TC-LOGIN-002: Submit a valid email and password -> they are navigated to the Dashboard page [API]
- **AC:** AC-001 | **Scenario:** TS-LOGIN-002 | **Channel:** API | **Priority:** P1 | **Automation:** API-TEST-LOGIN-002 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (API); Given a registered user; Endpoint is public (no authentication required); Registered user credentials are provided through environment variables

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | request | POST /api/auth/login | email: <valid>, password: <valid> |  |
| 2 | verify |  |  | Response status is 200, body contains "access_token" |

**Expected result:** Response status is 200, body contains "access_token"

## TC-LOGIN-003: Submit an invalid password -> "Invalid email or password" shown [UI]
- **AC:** AC-002 | **Scenario:** TS-LOGIN-003 | **Channel:** UI | **Priority:** P2 | **Automation:** UI-TEST-LOGIN-003 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (UI); Given a registered user; Registered user credentials are provided through environment variables

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | navigate | Login page (/login) |  | Login page is displayed |
| 2 | fill | Email | valid |  |
| 3 | fill | Password | invalid |  |
| 4 | click | Sign in button |  |  |
| 5 | verify |  |  | Message "Invalid email or password" is displayed |

**Expected result:** Message "Invalid email or password" is displayed

## TC-LOGIN-004: Submit an invalid password -> "Invalid email or password" shown [API]
- **AC:** AC-002 | **Scenario:** TS-LOGIN-004 | **Channel:** API | **Priority:** P2 | **Automation:** API-TEST-LOGIN-004 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (API); Given a registered user; Endpoint is public (no authentication required); Registered user credentials are provided through environment variables

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | request | POST /api/auth/login | email: <valid>, password: <invalid> |  |
| 2 | verify |  |  | Response status is 401, body contains "Invalid email or password" |

**Expected result:** Response status is 401, body contains "Invalid email or password"

## TC-LOGIN-005: Submits an empty email -> "Email is required" shown [UI]
- **AC:** AC-003 | **Scenario:** TS-LOGIN-005 | **Channel:** UI | **Priority:** P2 | **Automation:** UI-TEST-LOGIN-005 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (UI); Given the Login page

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | navigate | Login page (/login) |  | Login page is displayed |
| 2 | fill | Email | empty |  |
| 3 | fill | Password | valid |  |
| 4 | click | Sign in button |  |  |
| 5 | verify |  |  | Message "Email is required" is displayed |

**Expected result:** Message "Email is required" is displayed

## TC-LOGIN-006: Submits an empty password -> "Password is required" shown [UI]
- **AC:** AC-004 | **Scenario:** TS-LOGIN-006 | **Channel:** UI | **Priority:** P2 | **Automation:** UI-TEST-LOGIN-006 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (UI); Given the Login page

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | navigate | Login page (/login) |  | Login page is displayed |
| 2 | fill | Email | valid |  |
| 3 | fill | Password | empty |  |
| 4 | click | Sign in button |  |  |
| 5 | verify |  |  | Message "Password is required" is displayed |

**Expected result:** Message "Password is required" is displayed

## TC-LOGIN-007: Submits it with a password -> "Invalid email or password" shown [UI]
- **AC:** AC-005 | **Scenario:** TS-LOGIN-007 | **Channel:** UI | **Priority:** P2 | **Automation:** UI-TEST-LOGIN-007 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (UI); Given an unregistered email; Registered user credentials are provided through environment variables

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | navigate | Login page (/login) |  | Login page is displayed |
| 2 | fill | Email | unregistered |  |
| 3 | fill | Password | valid |  |
| 4 | click | Sign in button |  |  |
| 5 | verify |  |  | Message "Invalid email or password" is displayed |

**Expected result:** Message "Invalid email or password" is displayed

## TC-LOGIN-008: Submits it with a password -> "Invalid email or password" shown [API]
- **AC:** AC-005 | **Scenario:** TS-LOGIN-008 | **Channel:** API | **Priority:** P2 | **Automation:** API-TEST-LOGIN-008 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (API); Given an unregistered email; Endpoint is public (no authentication required); Registered user credentials are provided through environment variables

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | request | POST /api/auth/login | email: <unregistered>, password: <valid> |  |
| 2 | verify |  |  | Response status is 401, body contains "Invalid email or password" |

**Expected result:** Response status is 401, body contains "Invalid email or password"

## TC-LOGIN-009: Submits a password shorter than 8 characters -> "Password must be at least 8 characters" shown [UI]
- **AC:** AC-006 | **Scenario:** TS-LOGIN-009 | **Channel:** UI | **Priority:** P2 | **Automation:** UI-TEST-LOGIN-009 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (UI); Given the Login page

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | navigate | Login page (/login) |  | Login page is displayed |
| 2 | fill | Email | valid |  |
| 3 | fill | Password | too_short |  |
| 4 | click | Sign in button |  |  |
| 5 | verify |  |  | Message "Password must be at least 8 characters" is displayed |

**Expected result:** Message "Password must be at least 8 characters" is displayed

## TC-LOGIN-010: password with exactly 8 characters does not show "Password must be at least 8 characters" [UI]
- **AC:** AC-006 | **Scenario:** TS-LOGIN-010 | **Channel:** UI | **Priority:** P2 | **Automation:** UI-TEST-LOGIN-010 | **Spec version:** 1.0
- **Preconditions:** Application is reachable at the configured base URL (UI); Given the Login page

| # | Action | Target | Data | Expected |
|---|---|---|---|---|
| 1 | navigate | Login page (/login) |  | Login page is displayed |
| 2 | fill | Email | valid |  |
| 3 | fill | Password | at_min |  |
| 4 | click | Sign in button |  |  |
| 5 | verify |  |  | Message "Password must be at least 8 characters" is not displayed |

**Expected result:** Message "Password must be at least 8 characters" is not displayed
