from __future__ import annotations


def generate_python_client(*, class_name: str = "AgentKBClient") -> str:
    """Generate a dependency-free Python client for the hardened JSON API."""

    return f'''from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


class AgentKBClientError(RuntimeError):
    pass


@dataclass
class {class_name}:
    base_url: str
    api_key: str
    tenant_id: str | None = None
    timeout_seconds: float = 30.0

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/v1/health")

    def documents(self, *, include_deleted: bool = False) -> dict[str, Any]:
        query = "?include_deleted=true" if include_deleted else ""
        return self._request("GET", "/v1/documents" + query)

    def query(self, query: str, *, top_k: int = 12) -> dict[str, Any]:
        return self._request("POST", "/v1/query", {{"query": query, "top_k": top_k}})

    def index(self, text: str, *, title: str = "untitled", **metadata: Any) -> dict[str, Any]:
        payload = {{"text": text, "title": title, **metadata}}
        return self._request("POST", "/v1/index", payload)

    def feedback(self, run_id: str, rating: int, *, comment: str = "") -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/feedback",
            {{"run_id": run_id, "rating": rating, "comment": comment}},
        )

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {{
            "Accept": "application/json",
            "Authorization": f"Bearer {{self.api_key}}",
        }}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.tenant_id:
            headers["X-Tenant-ID"] = self.tenant_id
        outbound = request.Request(
            self.base_url.rstrip("/") + path,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(outbound, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AgentKBClientError(f"HTTP {{exc.code}}: {{detail}}") from exc
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AgentKBClientError(f"request failed: {{type(exc).__name__}}") from exc
        if not isinstance(result, dict):
            raise AgentKBClientError("response must be a JSON object")
        return result
'''
