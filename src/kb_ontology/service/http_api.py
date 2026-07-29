"""HTTP API: trusted (no auth) and secure (API-key + RBAC) servers.

Lean rewrite of agent_kb_core service patterns for OntologyStore + ContextPack.
"""

from __future__ import annotations

import json
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse

from kb_ontology.observability.metrics import MetricsRegistry
from kb_ontology.runtime.rate_limit import TokenBucketRateLimiter
from kb_ontology.security.audit import AuditLog
from kb_ontology.security.auth import (
    APIKeyAuthenticator,
    AuthenticationError,
    AuthorizationError,
    Principal,
    TenantDatabaseRouter,
    bearer_token,
    require_permission,
)
from kb_ontology.service.app import OntologyService


class _Authenticator(Protocol):
    def authenticate(self, raw_key: str) -> Principal: ...


OPENAPI_SPEC: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {
        "title": "kb-ontology API",
        "version": "0.1.0",
        "description": "Ontology-driven agent knowledge backend",
    },
    "paths": {
        "/v1/health": {
            "get": {
                "summary": "Health check",
                "security": [{"bearerAuth": []}],
                "responses": {"200": {"description": "ok"}},
            }
        },
        "/v1/query": {
            "post": {
                "summary": "Answer query → ContextPack",
                "security": [{"bearerAuth": []}],
                "responses": {"200": {"description": "ContextPack JSON"}},
            }
        },
        "/v1/extract": {
            "post": {
                "summary": "Extract ontology from document text",
                "security": [{"bearerAuth": []}],
                "responses": {"201": {"description": "Extraction summary"}},
            }
        },
        "/v1/metrics": {
            "get": {
                "summary": "In-process metrics snapshot",
                "security": [{"bearerAuth": []}],
                "responses": {"200": {"description": "metrics"}},
            }
        },
        "/v1/audit": {
            "get": {
                "summary": "List audit events for tenant",
                "security": [{"bearerAuth": []}],
                "responses": {"200": {"description": "events"}},
            }
        },
        "/v1/jobs": {
            "get": {
                "summary": "List background jobs",
                "security": [{"bearerAuth": []}],
                "responses": {"200": {"description": "jobs"}},
            }
        },
        "/v1/jobs/extract-batch": {
            "post": {
                "summary": "Enqueue extract jobs for a directory/file",
                "security": [{"bearerAuth": []}],
                "responses": {"202": {"description": "batch enqueue result"}},
            }
        },
        "/v1/jobs/worker-once": {
            "post": {
                "summary": "Process one queued extract job",
                "security": [{"bearerAuth": []}],
                "responses": {"200": {"description": "job result or idle"}},
            }
        },
        "/v1/openapi.json": {
            "get": {
                "summary": "OpenAPI document",
                "responses": {"200": {"description": "spec"}},
            }
        },
    },
    "components": {
        "securitySchemes": {
            "bearerAuth": {"type": "http", "scheme": "bearer"},
        }
    },
}


def create_http_server(
    service: OntologyService,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> ThreadingHTTPServer:
    """Trusted embedded JSON server (no auth). Prefer secure server for real deploys."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "KBOntology/0.1"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path in ("/health", "/v1/health"):
                self._write_json(HTTPStatus.OK, service.health().to_dict())
                return
            if path == "/v1/metrics":
                self._write_json(HTTPStatus.OK, service.metrics_snapshot())
                return
            if path == "/v1/openapi.json":
                self._write_json(HTTPStatus.OK, OPENAPI_SPEC)
                return
            if path == "/v1/jobs":
                status = (parse_qs(parsed.query).get("status") or [None])[0]
                limit = _query_int(parsed.query, "limit", 100)
                self._write_json(
                    HTTPStatus.OK,
                    service.list_jobs(status=status, limit=limit),
                )
                return
            if path.startswith("/v1/jobs/") and path != "/v1/jobs/extract-batch":
                job_id = path[len("/v1/jobs/") :]
                if job_id and job_id not in ("worker-once", "extract-batch"):
                    try:
                        self._write_json(HTTPStatus.OK, service.get_job(job_id))
                    except KeyError as exc:
                        self._write_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": "not_found", "detail": str(exc)},
                        )
                    return
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                payload = self._read_json()
                if path == "/v1/query":
                    self._write_json(HTTPStatus.OK, service.query(payload))
                    return
                if path == "/v1/extract":
                    self._write_json(HTTPStatus.CREATED, service.extract(payload))
                    return
                if path == "/v1/jobs/extract-batch":
                    self._write_json(
                        HTTPStatus.ACCEPTED,
                        service.enqueue_extract_batch(payload),
                    )
                    return
                if path == "/v1/jobs/worker-once":
                    worker_id = str(payload.get("worker_id") or "worker-1")
                    self._write_json(
                        HTTPStatus.OK,
                        service.worker_once(worker_id=worker_id),
                    )
                    return
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            except (ValueError, KeyError, TypeError, RuntimeError) as exc:
                self._write_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": type(exc).__name__, "detail": str(exc)},
                )
            except Exception as exc:  # pragma: no cover
                self._write_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": type(exc).__name__, "detail": str(exc)},
                )

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _write_json(self, status: HTTPStatus, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode(
                "utf-8"
            )
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((host, port), Handler)


class SecureServiceContext:
    """Per-request wiring for multi-tenant secure API."""

    def __init__(
        self,
        *,
        authenticator: _Authenticator,
        tenant_router: TenantDatabaseRouter,
        domain_dir: Path | None = None,
        domain_pack: Any = None,
        metrics: MetricsRegistry | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
        client: Any = None,
        audit_db_path: Path | None = None,
    ) -> None:
        self.authenticator = authenticator
        self.tenant_router = tenant_router
        self.domain_dir = domain_dir
        self.domain_pack = domain_pack
        self.metrics = metrics or MetricsRegistry()
        self.rate_limiter = rate_limiter or TokenBucketRateLimiter(
            capacity=120, refill_per_second=2.0
        )
        self.client = client
        self.audit_db_path = audit_db_path or (
            tenant_router.root_dir / "_audit.sqlite3"
        )
        self._services: dict[str, OntologyService] = {}

    def service_for(self, tenant_id: str) -> OntologyService:
        if tenant_id not in self._services:
            db_path = self.tenant_router.path_for(tenant_id)
            self._services[tenant_id] = OntologyService(
                db_path=db_path,
                domain_pack=self.domain_pack,
                domain_dir=self.domain_dir,
                client=self.client,
                metrics=self.metrics,
                tenant_id=tenant_id,
            )
        return self._services[tenant_id]

    def audit_log(self) -> AuditLog:
        self.audit_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.audit_db_path), check_same_thread=False)
        return AuditLog(conn)


def create_secure_http_server(
    context: SecureServiceContext,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> ThreadingHTTPServer:
    """API-key authenticated multi-tenant server."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "KBOntologySecure/0.1"

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

        def _dispatch(self, method: str) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if method == "GET" and path == "/v1/openapi.json":
                    self._write_json(HTTPStatus.OK, OPENAPI_SPEC)
                    return

                principal = self._authenticate()
                decision = context.rate_limiter.consume(principal.principal_id)
                if not decision.allowed:
                    self._write_json(
                        HTTPStatus.TOO_MANY_REQUESTS,
                        {
                            "error": "rate_limited",
                            "retry_after_seconds": decision.retry_after_seconds,
                        },
                        extra_headers={
                            "Retry-After": str(int(decision.retry_after_seconds) + 1)
                        },
                    )
                    return

                service = context.service_for(principal.tenant_id)
                audit = context.audit_log()

                if method == "GET" and path in ("/health", "/v1/health"):
                    require_permission(principal, "health:read")
                    self._write_json(HTTPStatus.OK, service.health().to_dict())
                    return
                if method == "GET" and path == "/v1/metrics":
                    require_permission(principal, "metrics:read")
                    self._write_json(HTTPStatus.OK, service.metrics_snapshot())
                    return
                if method == "GET" and path == "/v1/audit":
                    require_permission(principal, "health:read")
                    if not principal.allows("*") and "admin" not in principal.roles:
                        # readers may only see own events
                        events = audit.list(
                            tenant_id=principal.tenant_id,
                            principal_id=principal.principal_id,
                            limit=_query_int(parsed.query, "limit", 50),
                        )
                    else:
                        events = audit.list(
                            tenant_id=principal.tenant_id,
                            limit=_query_int(parsed.query, "limit", 100),
                        )
                    self._write_json(
                        HTTPStatus.OK,
                        {"events": [e.to_dict() for e in events]},
                    )
                    return
                if method == "POST" and path == "/v1/query":
                    require_permission(principal, "query:run")
                    payload = self._read_json()
                    self._write_json(
                        HTTPStatus.OK,
                        service.query(payload, principal=principal, audit=audit),
                    )
                    return
                if method == "POST" and path == "/v1/extract":
                    require_permission(principal, "extract:run")
                    payload = self._read_json()
                    self._write_json(
                        HTTPStatus.CREATED,
                        service.extract(payload, principal=principal, audit=audit),
                    )
                    return
                if method == "GET" and path == "/v1/jobs":
                    require_permission(principal, "jobs:read")
                    status = (parse_qs(parsed.query).get("status") or [None])[0]
                    limit = _query_int(parsed.query, "limit", 100)
                    self._write_json(
                        HTTPStatus.OK,
                        service.list_jobs(
                            status=status,
                            limit=limit,
                            principal=principal,
                            audit=audit,
                        ),
                    )
                    return
                if method == "GET" and path.startswith("/v1/jobs/"):
                    job_id = path[len("/v1/jobs/") :]
                    if job_id and job_id not in ("worker-once", "extract-batch"):
                        require_permission(principal, "jobs:read")
                        try:
                            self._write_json(HTTPStatus.OK, service.get_job(job_id))
                        except KeyError as exc:
                            self._write_json(
                                HTTPStatus.NOT_FOUND,
                                {"error": "not_found", "detail": str(exc)},
                            )
                        return
                if method == "POST" and path == "/v1/jobs/extract-batch":
                    require_permission(principal, "jobs:write")
                    payload = self._read_json()
                    self._write_json(
                        HTTPStatus.ACCEPTED,
                        service.enqueue_extract_batch(
                            payload, principal=principal, audit=audit
                        ),
                    )
                    return
                if method == "POST" and path == "/v1/jobs/worker-once":
                    require_permission(principal, "jobs:write")
                    payload = self._read_json()
                    worker_id = str(payload.get("worker_id") or "worker-1")
                    self._write_json(
                        HTTPStatus.OK,
                        service.worker_once(
                            worker_id=worker_id,
                            principal=principal,
                            audit=audit,
                        ),
                    )
                    return
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            except AuthenticationError as exc:
                self._write_json(
                    HTTPStatus.UNAUTHORIZED,
                    {"error": "authentication_error", "detail": str(exc)},
                )
            except AuthorizationError as exc:
                self._write_json(
                    HTTPStatus.FORBIDDEN,
                    {"error": "authorization_error", "detail": str(exc)},
                )
            except (ValueError, KeyError, TypeError) as exc:
                self._write_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": type(exc).__name__, "detail": str(exc)},
                )
            except Exception as exc:  # pragma: no cover
                self._write_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": type(exc).__name__, "detail": str(exc)},
                )

        def _authenticate(self) -> Principal:
            token = bearer_token(self.headers.get("Authorization"))
            return context.authenticator.authenticate(token)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _write_json(
            self,
            status: HTTPStatus,
            payload: Any,
            *,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode(
                "utf-8"
            )
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((host, port), Handler)


def build_secure_context_from_environment(
    *,
    tenant_db_root: str | Path,
    domain_dir: str | Path | None = None,
) -> SecureServiceContext:
    authenticator = APIKeyAuthenticator.from_environment()
    return SecureServiceContext(
        authenticator=authenticator,
        tenant_router=TenantDatabaseRouter(tenant_db_root),
        domain_dir=Path(domain_dir) if domain_dir else None,
    )


def _query_int(query: str, name: str, default: int) -> int:
    values = parse_qs(query).get(name) or []
    if not values:
        return default
    try:
        return max(1, int(values[0]))
    except ValueError:
        return default
