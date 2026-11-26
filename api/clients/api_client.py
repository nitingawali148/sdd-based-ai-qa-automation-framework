"""Thin HTTPX client: base URL, bearer auth, correlation IDs, timeouts and masked request logging."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from core.logger import get_logger, mask

log = get_logger("sdd.api")


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, follow_redirects=False)

    def request(self, method: str, path: str, *, json: Any = None, params: dict[str, Any] | None = None,
                token: str | None = None, headers: dict[str, str] | None = None) -> httpx.Response:
        hdrs = {"X-Correlation-ID": uuid.uuid4().hex[:12], "Accept": "application/json", **(headers or {})}
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        response = self._client.request(method.upper(), path, json=json, params=params, headers=hdrs)
        log.debug("%s %s -> %s (cid=%s) body=%s", method.upper(), path, response.status_code,
                  hdrs["X-Correlation-ID"], mask(json))
        return response

    def get(self, path: str, **kw: Any) -> httpx.Response:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> httpx.Response:
        return self.request("POST", path, **kw)

    def put(self, path: str, **kw: Any) -> httpx.Response:
        return self.request("PUT", path, **kw)

    def patch(self, path: str, **kw: Any) -> httpx.Response:
        return self.request("PATCH", path, **kw)

    def delete(self, path: str, **kw: Any) -> httpx.Response:
        return self.request("DELETE", path, **kw)

    def login(self, email: str, password: str, path: str = "/api/auth/login") -> str:
        response = self.post(path, json={"email": email, "password": password})
        if response.status_code != 200:
            raise RuntimeError(f"Login failed for test account ({response.status_code}): {response.text[:200]}")
        return str(response.json()["access_token"])

    def close(self) -> None:
        self._client.close()
