"""Deterministic API assertions. Failure messages carry expected-vs-actual evidence for failure analysis."""

from __future__ import annotations

import httpx
import jsonschema

from parsers.openapi_parser import load_openapi


def _body(response: httpx.Response) -> str:
    return response.text[:500]


def expect_status(response: httpx.Response, expected: int) -> None:
    if response.status_code != expected:
        raise AssertionError(f"SDD-EXPECTED status {expected} but got {response.status_code} for "
                             f"{response.request.method} {response.request.url.path}; actual body: {_body(response)}")


def expect_body_contains(response: httpx.Response, text: str) -> None:
    if text not in response.text:
        raise AssertionError(f"SDD-EXPECTED body to contain \"{text}\"; actual body: {_body(response)}")


def expect_schema(response: httpx.Response, method: str, path: str, status: int) -> None:
    schema = load_openapi().response_schema(method, path, status)
    if schema is None:
        raise AssertionError(f"No OpenAPI response schema for {method} {path} {status}")
    try:
        jsonschema.validate(response.json(), schema)
    except jsonschema.ValidationError as exc:
        raise AssertionError(f"SDD-EXPECTED body to match the OpenAPI schema for {method} {path} {status}: "
                             f"{exc.message}; actual body: {_body(response)}") from exc
