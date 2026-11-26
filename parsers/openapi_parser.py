"""OpenAPI 3.x reader: operations, request/response schemas with resolved $refs."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from core.config import ROOT, settings

HTTP_METHODS = ("get", "post", "put", "patch", "delete")


class OpenAPISpec:
    def __init__(self, data: dict[str, Any], source: str = "") -> None:
        self.data = data
        self.source = source

    @classmethod
    def load(cls, path: Path | None = None) -> OpenAPISpec:
        path = path or settings().path("openapi")
        text = path.read_text(encoding="utf-8")
        data = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
        return cls(data, str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path))

    # ------------------------------------------------------------------ refs
    def resolve(self, node: Any, _depth: int = 0) -> Any:
        if _depth > 20:
            return node
        if isinstance(node, dict):
            if "$ref" in node:
                target: Any = self.data
                for part in node["$ref"].lstrip("#/").split("/"):
                    target = target[part]
                return self.resolve(copy.deepcopy(target), _depth + 1)
            return {k: self.resolve(v, _depth + 1) for k, v in node.items()}
        if isinstance(node, list):
            return [self.resolve(v, _depth + 1) for v in node]
        return node

    # ------------------------------------------------------------------ operations
    def operations(self) -> list[dict[str, Any]]:
        ops = []
        for path, item in self.data.get("paths", {}).items():
            for method in HTTP_METHODS:
                op = item.get(method)
                if not op:
                    continue
                ops.append({
                    "method": method.upper(),
                    "path": path,
                    "operation_id": op.get("operationId", f"{method}_{path}"),
                    "summary": op.get("summary", ""),
                    "secured": bool(op.get("security", self.data.get("security", []))),
                    "responses": sorted(op.get("responses", {}).keys()),
                    "has_body": "requestBody" in op,
                    "destructive": method == "delete" or bool(op.get("x-destructive")),
                })
        return ops

    def operation(self, method: str, path: str) -> dict[str, Any] | None:
        return next((o for o in self.operations() if o["method"] == method.upper() and o["path"] == path), None)

    def response_schema(self, method: str, path: str, status: int | str) -> dict[str, Any] | None:
        op = self.data.get("paths", {}).get(path, {}).get(method.lower(), {})
        resp = op.get("responses", {}).get(str(status))
        if not resp:
            return None
        resp = self.resolve(resp)
        content = resp.get("content", {}).get("application/json", {})
        return content.get("schema")

    def request_schema(self, method: str, path: str) -> dict[str, Any] | None:
        op = self.data.get("paths", {}).get(path, {}).get(method.lower(), {})
        body = self.resolve(op.get("requestBody", {}))
        return body.get("content", {}).get("application/json", {}).get("schema")

    def summary(self) -> list[str]:
        return [f"{o['method']} {o['path']} - {o['summary']}" for o in self.operations()]


@lru_cache(maxsize=4)
def load_openapi(path: str | None = None) -> OpenAPISpec:
    return OpenAPISpec.load(Path(path) if path else None)
