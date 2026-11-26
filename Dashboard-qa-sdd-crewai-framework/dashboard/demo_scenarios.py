"""Sample (dummy) scenarios for demonstrations.

These are SIMULATED: the agent activity and the outcome are scripted so a demo can show every path of the
framework (pass, application defect, automation issue, spec drift, test data issue, environment issue, and a
specification blocked at the validation gate). The dashboard labels them "simulated" everywhere; real results
only ever come from the framework's pytest run.
"""

from __future__ import annotations

from typing import Any


def _ui(page: str, path: str, fields: dict[str, str], submit: str) -> dict[str, Any]:
    return {"page": page, "path": path, "locators": fields, "submit": submit}


def _api(method: str, path: str, status: int, body: str = "", auth: bool = True, schema: bool = False,
         destructive: bool = False) -> dict[str, Any]:
    return {"method": method, "path": path, "expected_status": status, "body_contains": body, "auth": auth,
            "validate_schema": schema, "destructive": destructive}


DEMO_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "DEMO-CART-001", "title": "Add an in-stock product to the cart [UI]", "feature": "shopping-cart",
        "feature_title": "Shopping Cart", "spec_id": "SPEC-CART-001", "req_id": "REQ-101", "ac_id": "AC-001",
        "channel": "ui", "priority": "P1", "type": "positive",
        "requirement": "Given a signed-in shopper on a product page, when they click Add to cart, then the cart "
                       "badge shows 1 and the message \"Added to cart\" is displayed.",
        "given": "a signed-in shopper on a product page", "when": "they click Add to cart",
        "then": "the message \"Added to cart\" is displayed",
        "inputs": {"product_id": "valid", "quantity": "valid"},
        "data": {"product_id": "${env:DEMO_PRODUCT_ID}", "quantity": "1"},
        "steps": [("navigate", "Product page (/products/42)", "", "Product page is displayed"),
                  ("fill", "Quantity", "valid", ""), ("click", "Add to cart button", "", ""),
                  ("verify", "", "", "Message \"Added to cart\" is displayed")],
        "design": _ui("Product", "/products/{id}", {"quantity": "get_by_label('Quantity')"},
                      "get_by_role('button', name='Add to cart')"),
        "outcome": "passed",
    },
    {
        "id": "DEMO-CART-002", "title": "Apply an expired coupon shows \"Coupon has expired\" [UI]",
        "feature": "shopping-cart", "feature_title": "Shopping Cart", "spec_id": "SPEC-CART-001",
        "req_id": "REQ-101", "ac_id": "AC-004", "channel": "ui", "priority": "P2", "type": "negative",
        "requirement": "Given a cart with items, when the shopper applies an expired coupon, then the error "
                       "message \"Coupon has expired\" is displayed.",
        "given": "a cart with items", "when": "the shopper applies an expired coupon",
        "then": "the error message \"Coupon has expired\" is displayed",
        "inputs": {"coupon": "invalid"}, "data": {"coupon": "EXPIRED-2024"},
        "steps": [("navigate", "Cart page (/cart)", "", "Cart page is displayed"),
                  ("fill", "Coupon code", "invalid", ""), ("click", "Apply button", "", ""),
                  ("verify", "", "", "Message \"Coupon has expired\" is displayed")],
        "design": _ui("Cart", "/cart", {"coupon": "get_by_label('Coupon code')"},
                      "get_by_role('button', name='Apply')"),
        "outcome": "failed", "fail_step": 4,
        "failure": {"category": "APPLICATION_DEFECT", "confidence": 0.85,
                    "message": "SDD-EXPECTED message \"Coupon has expired\" to be displayed; actual visible "
                               "messages: ['Invalid coupon']",
                    "expected": "\"Coupon has expired\"", "actual": "['Invalid coupon']",
                    "root_cause": "The application returns a generic coupon error for expired coupons; the "
                                  "specification (unchanged since approval) requires a specific message.",
                    "recommendation": "Raise a defect against the coupon service; the test is correct."},
    },
    {
        "id": "DEMO-CHK-001", "title": "Checkout with a valid card places the order [UI]", "feature": "checkout",
        "feature_title": "Checkout", "spec_id": "SPEC-CHK-001", "req_id": "REQ-102", "ac_id": "AC-001",
        "channel": "ui", "priority": "P1", "type": "positive",
        "requirement": "Given a cart with items, when the shopper pays with a valid card, then they are navigated "
                       "to the Order Confirmation page.",
        "given": "a cart with items", "when": "the shopper pays with a valid card",
        "then": "they are navigated to the Order Confirmation page",
        "inputs": {"card_number": "valid", "expiry": "valid", "cvv": "valid"},
        "data": {"card_number": "${env:DEMO_TEST_CARD}", "expiry": "${faker:future_month}", "cvv": "${repeat:1:3}"},
        "steps": [("navigate", "Checkout page (/checkout)", "", "Checkout page is displayed"),
                  ("fill", "Card number", "valid", ""), ("fill", "Expiry", "valid", ""), ("fill", "CVV", "valid", ""),
                  ("click", "Pay now button", "", ""), ("verify", "", "", "User is navigated to Order Confirmation")],
        "design": _ui("Checkout", "/checkout", {"card_number": "get_by_label('Card number')",
                                                 "expiry": "get_by_label('Expiry')", "cvv": "get_by_label('CVV')"},
                      "get_by_role('button', name='Pay now')"),
        "outcome": "passed",
    },
    {
        "id": "DEMO-CHK-002", "title": "POST /api/orders without a token returns 401 [API]", "feature": "checkout",
        "feature_title": "Checkout", "spec_id": "SPEC-CHK-001", "req_id": "REQ-102", "ac_id": "AC-006",
        "channel": "api", "priority": "P1", "type": "negative",
        "requirement": "Given an unauthenticated client, when it creates an order, then the API returns 401.",
        "given": "an unauthenticated client", "when": "it creates an order", "then": "the API returns 401",
        "inputs": {"items": "valid"}, "data": {"items": "[{\"product_id\": 42, \"qty\": 1}]"},
        "steps": [("request", "POST /api/orders", "items: <valid>, no Authorization header", ""),
                  ("verify", "", "", "Response status is 401")],
        "design": _api("POST", "/api/orders", 401, auth=False), "outcome": "passed",
    },
    {
        "id": "DEMO-SRCH-001", "title": "Search for \"laptop\" lists matching products [UI]", "feature": "search",
        "feature_title": "Product Search", "spec_id": "SPEC-SRCH-001", "req_id": "REQ-103", "ac_id": "AC-001",
        "channel": "ui", "priority": "P2", "type": "positive",
        "requirement": "Given the Home page, when the user searches for \"laptop\", then the Search Results page "
                       "shows at least 1 product.",
        "given": "the Home page", "when": "the user searches for \"laptop\"",
        "then": "they are navigated to the Search Results page",
        "inputs": {"query": "valid"}, "data": {"query": "laptop"},
        "steps": [("navigate", "Home page (/)", "", "Home page is displayed"), ("fill", "Search", "valid", ""),
                  ("click", "Search button", "", ""), ("verify", "", "", "Search Results page is displayed")],
        "design": _ui("Home", "/", {"query": "get_by_label('Search products')"},
                      "get_by_role('button', name='Search')"),
        "outcome": "failed", "fail_step": 2,
        "failure": {"category": "AUTOMATION_ISSUE", "confidence": 0.8,
                    "message": "TimeoutError: Locator.fill: Timeout 10000ms exceeded. waiting for "
                               "get_by_label('Search products')",
                    "expected": "Search field labelled 'Search products'", "actual": "No element with that label",
                    "root_cause": "The search box is labelled 'Search' in the application; the page object uses "
                                  "'Search products'.",
                    "recommendation": "Fix the UI page definition in the spec (element label) and regenerate the "
                                      "page object; no application change needed."},
    },
    {
        "id": "DEMO-PROF-001", "title": "PATCH /api/profile with a 51-character name returns 422 [API]",
        "feature": "profile", "feature_title": "User Profile", "spec_id": "SPEC-PROF-001", "req_id": "REQ-104",
        "ac_id": "AC-003", "channel": "api", "priority": "P2", "type": "boundary",
        "requirement": "Given a signed-in user, when they save a display name longer than 50 characters, then "
                       "the API returns 422.",
        "given": "a signed-in user", "when": "they save a display name longer than 50 characters",
        "then": "the API returns 422", "inputs": {"display_name": "too_long"},
        "data": {"display_name": "${repeat:x:51}"},
        "steps": [("request", "PATCH /api/profile", "display_name: <too_long>", ""),
                  ("verify", "", "", "Response status is 422")],
        "design": _api("PATCH", "/api/profile", 422), "outcome": "passed",
    },
    {
        "id": "DEMO-INV-001", "title": "GET /api/invoices/{id} matches the OpenAPI schema [API]",
        "feature": "billing", "feature_title": "Billing", "spec_id": "SPEC-BILL-001", "req_id": "REQ-105",
        "ac_id": "AC-002", "channel": "api", "priority": "P1", "type": "positive",
        "requirement": "Given an existing invoice, when the client retrieves it, then the API returns 200 and "
                       "the body contains \"total_amount\".",
        "given": "an existing invoice", "when": "the client retrieves it",
        "then": "the API returns 200 with \"total_amount\"", "inputs": {"invoice_id": "valid"},
        "data": {"invoice_id": "${fixture:invoice_id}"},
        "steps": [("request", "GET /api/invoices/{id}", "invoice_id: <valid>", ""),
                  ("verify", "", "", "Status 200, body contains \"total_amount\", schema valid")],
        "design": _api("GET", "/api/invoices/{invoice_id}", 200, "total_amount", schema=True),
        "outcome": "failed", "fail_step": 2,
        "failure": {"category": "SPEC_IMPLEMENTATION_DRIFT", "confidence": 0.9,
                    "message": "SDD-EXPECTED body to contain \"total_amount\"; actual body keys: ['id', 'amount', "
                               "'currency', 'status']",
                    "expected": "\"total_amount\"", "actual": "['id', 'amount', 'currency', 'status']",
                    "root_cause": "CHG-007 renamed total_amount -> amount in the API, but the approved "
                                  "specification still says total_amount.",
                    "recommendation": "Decide which is right: update the spec (python main.py change "
                                      "SPEC-BILL-001) or revert the API change."},
    },
    {
        "id": "DEMO-RESET-001", "title": "Password reset email arrives \"quickly\" [UI]", "feature": "password-reset",
        "feature_title": "Password Reset", "spec_id": "SPEC-RESET-001", "req_id": "REQ-003", "ac_id": "AC-001",
        "channel": "ui", "priority": "P2", "type": "positive",
        "requirement": "Given a registered user, when they request a password reset, then they receive an email "
                       "quickly.",
        "given": "a registered user", "when": "they request a password reset",
        "then": "they receive an email quickly", "inputs": {"email": "valid"},
        "data": {"email": "${env:SDD_DEMO_USER_EMAIL}"}, "steps": [], "design": {},
        "outcome": "blocked",
        "blocked": [{"code": "AC_VAGUE", "message": "AC-001 uses the vague term 'quickly'. State the exact expected "
                                                    "outcome."},
                    {"code": "AC_UI_EXPECTATION_UNMEASURABLE",
                     "message": "Expected UI result is not measurable ('they receive an email quickly'). Quote the "
                                "exact message or name the target page."},
                    {"code": "OPEN_QUESTION", "message": "TBD: how long is the reset link valid?"}],
    },
    {
        "id": "DEMO-NOTIF-001", "title": "GET /api/notifications returns the unread list [API]",
        "feature": "notifications", "feature_title": "Notifications", "spec_id": "SPEC-NOTIF-001",
        "req_id": "REQ-106", "ac_id": "AC-001", "channel": "api", "priority": "P3", "type": "positive",
        "requirement": "Given a signed-in user, when they list notifications, then the API returns 200 and the "
                       "body contains \"unread\".",
        "given": "a signed-in user", "when": "they list notifications",
        "then": "the API returns 200 with \"unread\"", "inputs": {}, "data": {},
        "steps": [("request", "GET /api/notifications", "", ""), ("verify", "", "", "Status 200, body contains \"unread\"")],
        "design": _api("GET", "/api/notifications", 200, "unread"),
        "outcome": "error", "fail_step": 1,
        "failure": {"category": "ENVIRONMENT_ISSUE", "confidence": 0.95,
                    "message": "httpx.ConnectError: [WinError 10061] Connection refused (notifications-service:8443)",
                    "expected": "HTTP response", "actual": "Connection refused",
                    "root_cause": "The notifications service is not running in the QA environment.",
                    "recommendation": "Start or redeploy notifications-service, then re-run only this test case "
                                      "(--tc DEMO-NOTIF-001)."},
    },
    {
        "id": "DEMO-REG-001", "title": "Register with an existing email shows \"Email already registered\" [UI]",
        "feature": "registration", "feature_title": "Registration", "spec_id": "SPEC-REG-001", "req_id": "REQ-107",
        "ac_id": "AC-003", "channel": "ui", "priority": "P1", "type": "negative",
        "requirement": "Given an existing account, when a visitor registers with the same email, then the error "
                       "message \"Email already registered\" is displayed.",
        "given": "an existing account", "when": "a visitor registers with the same email",
        "then": "the error message \"Email already registered\" is displayed",
        "inputs": {"email": "duplicate", "password": "valid"},
        "data": {"email": "${env:SDD_DEMO_USER_EMAIL}", "password": "${faker:password:12}"},
        "steps": [("navigate", "Register page (/register)", "", "Register page is displayed"),
                  ("fill", "Email", "duplicate", ""), ("fill", "Password", "valid", ""),
                  ("click", "Create account button", "", ""),
                  ("verify", "", "", "Message \"Email already registered\" is displayed")],
        "design": _ui("Register", "/register", {"email": "get_by_label('Email')", "password": "get_by_label('Password')"},
                      "get_by_role('button', name='Create account')"),
        "outcome": "passed",
    },
    {
        "id": "DEMO-REG-002", "title": "Register with an 8-character password (at minimum) succeeds [UI]",
        "feature": "registration", "feature_title": "Registration", "spec_id": "SPEC-REG-001", "req_id": "REQ-107",
        "ac_id": "AC-005", "channel": "ui", "priority": "P2", "type": "boundary",
        "requirement": "Given the Register page, when a visitor registers with a password of exactly 8 characters, "
                       "then they are navigated to the Welcome page.",
        "given": "the Register page", "when": "a visitor registers with a password of exactly 8 characters",
        "then": "they are navigated to the Welcome page", "inputs": {"email": "unregistered", "password": "at_min"},
        "data": {"email": "${faker:unique_email}", "password": "${repeat:x:8}"},
        "steps": [("navigate", "Register page (/register)", "", "Register page is displayed"),
                  ("fill", "Email", "unregistered", ""), ("fill", "Password", "at_min", ""),
                  ("click", "Create account button", "", ""), ("verify", "", "", "User is navigated to Welcome")],
        "design": _ui("Register", "/register", {"email": "get_by_label('Email')", "password": "get_by_label('Password')"},
                      "get_by_role('button', name='Create account')"),
        "outcome": "passed",
    },
    {
        "id": "DEMO-PAY-001", "title": "Refund a settled payment returns 200 [API]", "feature": "payments",
        "feature_title": "Payments", "spec_id": "SPEC-PAY-001", "req_id": "REQ-108", "ac_id": "AC-002",
        "channel": "api", "priority": "P1", "type": "positive",
        "requirement": "Given a settled payment, when an admin refunds it, then the API returns 200 and the body "
                       "contains \"refunded\".",
        "given": "a settled payment", "when": "an admin refunds it", "then": "the API returns 200 with \"refunded\"",
        "inputs": {"payment_id": "valid"}, "data": {"payment_id": "${env:DEMO_SETTLED_PAYMENT_ID}"},
        "steps": [("request", "POST /api/payments/{id}/refund", "payment_id: <valid>", ""),
                  ("verify", "", "", "Status 200, body contains \"refunded\"")],
        "design": _api("POST", "/api/payments/{payment_id}/refund", 200, "refunded"),
        "outcome": "failed", "fail_step": 1,
        "failure": {"category": "TEST_DATA_ISSUE", "confidence": 0.9,
                    "message": "TestDataError: TEST-DATA: environment variable DEMO_SETTLED_PAYMENT_ID is not set",
                    "expected": "a settled payment id", "actual": "variable not set",
                    "root_cause": "The test data expression needs DEMO_SETTLED_PAYMENT_ID, which is missing from the "
                                  "environment's .env.",
                    "recommendation": "Add DEMO_SETTLED_PAYMENT_ID to .env for this environment and re-run."},
    },
    {
        "id": "DEMO-ORD-001", "title": "DELETE /api/orders/{id} cancels a pending order [API]", "feature": "checkout",
        "feature_title": "Checkout", "spec_id": "SPEC-CHK-001", "req_id": "REQ-102", "ac_id": "AC-008",
        "channel": "api", "priority": "P2", "type": "positive",
        "requirement": "Given a pending order, when the shopper cancels it, then the API returns 204.",
        "given": "a pending order", "when": "the shopper cancels it", "then": "the API returns 204",
        "inputs": {"order_id": "valid"}, "data": {"order_id": "${fixture:pending_order}"},
        "steps": [("request", "DELETE /api/orders/{id}", "order_id: <valid>", ""), ("verify", "", "", "Status 204")],
        "design": _api("DELETE", "/api/orders/{order_id}", 204, destructive=True), "outcome": "passed",
    },
]

BY_ID = {s["id"]: s for s in DEMO_SCENARIOS}
