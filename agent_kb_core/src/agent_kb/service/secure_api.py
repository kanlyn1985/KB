from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from agent_kb.adapters.openapi import build_openapi_spec
from agent_kb.domains.schema import DomainPack
from agent_kb.embeddings import EmbeddingProvider
from agent_kb.graph import RelationExtractor
from agent_kb.observability import MetricsRegistry, TelemetryExporter, Tracer
from agent_kb.retrieval import ExternalVectorBackend
from agent_kb.runtime import (
    SQLiteDistributedRateLimiter,
    SQLiteJobQueue,
    SQLiteWorkerRegistry,
    TokenBucketRateLimiter,
)
from agent_kb.security import (
    AuthenticationError,
    AuthorizationError,
    Principal,
    TenantDatabaseRouter,
    bearer_token,
    require_permission,
)
from agent_kb.security.audit import AuditLog
from agent_kb.storage import (
    BackupReplicator,
    LegalHoldStore,
    RetentionManager,
    RetentionPolicy,
    SQLiteBackupManager,
    SQLiteKnowledgeStore,
)
from agent_kb.storage.maintenance import KnowledgeMaintenance

from .api import AgentKBService


class Authenticator(Protocol):
    def authenticate(self, raw_key: str) -> Principal: ...


@dataclass(frozen=True)
class HardenedServiceConfig:
    tenant_db_root: Path
    backup_root: Path
    rate_limit_capacity: int = 60
    rate_limit_refill_per_second: float = 1.0
    distributed_rate_limit: bool = False
    rate_limit_window_seconds: int = 60
    worker_lease_seconds: int = 90


class HardenedAgentKBService:
    """Authenticated, tenant-isolated, observable deployment service."""

    def __init__(
        self,
        *,
        config: HardenedServiceConfig,
        authenticator: Authenticator,
        domain_pack: DomainPack | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        external_vector_backend: ExternalVectorBackend | None = None,
        relation_extractor: RelationExtractor | None = None,
        backup_replicators: list[BackupReplicator] | None = None,
        telemetry_exporter: TelemetryExporter | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self.config = config
        self.authenticator = authenticator
        self.domain_pack = domain_pack
        self.embedding_provider = embedding_provider
        self.external_vector_backend = external_vector_backend
        self.relation_extractor = relation_extractor
        self.backup_replicators = list(backup_replicators or [])
        self.telemetry_exporter = telemetry_exporter
        self.tracer = Tracer(telemetry_exporter)
        self.router = TenantDatabaseRouter(config.tenant_db_root)
        self.metrics = metrics or MetricsRegistry()
        self.rate_limiter = TokenBucketRateLimiter(
            capacity=config.rate_limit_capacity,
            refill_per_second=config.rate_limit_refill_per_second,
        )
        self.config.backup_root.mkdir(parents=True, exist_ok=True)

    def authenticate(self, authorization: str | None, requested_tenant: str | None = None) -> Principal:
        principal = self.authenticator.authenticate(bearer_token(authorization))
        if requested_tenant and requested_tenant.strip().lower() != principal.tenant_id:
            raise AuthorizationError("requested tenant does not match authenticated principal")
        return principal

    def consume_rate_limit(self, principal: Principal):
        key = f"{principal.tenant_id}:{principal.principal_id}"
        if not self.config.distributed_rate_limit:
            return self.rate_limiter.consume(key)
        with SQLiteKnowledgeStore(self.router.path_for(principal.tenant_id)) as store:
            return SQLiteDistributedRateLimiter(
                store.connection,
                limit=self.config.rate_limit_capacity,
                window_seconds=self.config.rate_limit_window_seconds,
            ).consume(key)

    def health(self, principal: Principal) -> dict[str, Any]:
        return self._call(
            principal,
            "health:read",
            "health.read",
            "service",
            None,
            lambda service: service.health().to_dict(),
        )

    def query(self, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call(
            principal,
            "query:run",
            "query.run",
            "retrieval",
            None,
            lambda service: service.query(payload),
        )

    def index(self, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call(
            principal,
            "documents:index",
            "documents.index",
            "document",
            _optional_text(payload.get("logical_document_id")),
            lambda service: service.index(payload),
        )

    def feedback(self, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call(
            principal,
            "feedback:write",
            "feedback.write",
            "retrieval_run",
            _optional_text(payload.get("run_id")),
            lambda service: service.feedback(payload),
        )

    def documents(self, principal: Principal, *, include_deleted: bool = False) -> dict[str, Any]:
        return self._call(
            principal,
            "documents:read",
            "documents.read",
            "document",
            None,
            lambda service: {"documents": service.documents(include_deleted=include_deleted)},
        )

    def enqueue_index(self, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
        require_permission(principal, "documents:index")
        db_path = self.router.path_for(principal.tenant_id)
        with SQLiteKnowledgeStore(db_path) as store:
            job = SQLiteJobQueue(store.connection).submit(
                "index_text",
                payload,
                tenant_id=principal.tenant_id,
                max_attempts=max(1, int(payload.get("max_attempts") or 3)),
                idempotency_key=_optional_text(payload.get("idempotency_key")),
            )
            AuditLog(store.connection).record(
                tenant_id=principal.tenant_id,
                principal_id=principal.principal_id,
                action="jobs.index.submit",
                resource_type="background_job",
                resource_id=job.job_id,
                metadata={"idempotency_key": _optional_text(payload.get("idempotency_key"))},
            )
        self.metrics.increment("jobs_submitted_total")
        return job.to_dict()

    def get_job(self, principal: Principal, job_id: str) -> dict[str, Any]:
        require_permission(principal, "documents:read")
        with SQLiteKnowledgeStore(self.router.path_for(principal.tenant_id)) as store:
            job = SQLiteJobQueue(store.connection).get(job_id)
        if job is None or job.tenant_id != principal.tenant_id:
            raise KeyError(job_id)
        return job.to_dict()

    def run_worker_once(self, principal: Principal, *, worker_id: str = "api-worker") -> dict[str, Any]:
        require_permission(principal, "admin:operate")
        db_path = self.router.path_for(principal.tenant_id)
        service = self._tenant_service(principal)
        with SQLiteKnowledgeStore(db_path) as store:
            registry = SQLiteWorkerRegistry(store.connection)
            registry.heartbeat(
                worker_id,
                tenant_id=principal.tenant_id,
                capabilities=["index_text"],
                status="running",
                lease_seconds=self.config.worker_lease_seconds,
            )
            queue = SQLiteJobQueue(store.connection)
            job = queue.run_once(
                worker_id,
                {"index_text": service.index},
                tenant_id=principal.tenant_id,
            )
            registry.heartbeat(
                worker_id,
                tenant_id=principal.tenant_id,
                capabilities=["index_text"],
                status="ready",
                lease_seconds=self.config.worker_lease_seconds,
            )
            if job is not None:
                AuditLog(store.connection).record(
                    tenant_id=principal.tenant_id,
                    principal_id=principal.principal_id,
                    action="jobs.worker.run_once",
                    resource_type="background_job",
                    resource_id=job.job_id,
                    outcome=job.status,
                )
        self.metrics.increment("worker_iterations_total")
        return {"job": job.to_dict() if job else None}

    def workers(self, principal: Principal) -> dict[str, Any]:
        require_permission(principal, "admin:operate")
        with SQLiteKnowledgeStore(self.router.path_for(principal.tenant_id)) as store:
            workers = SQLiteWorkerRegistry(store.connection).list_active(tenant_id=principal.tenant_id)
        return {"workers": [worker.to_dict() for worker in workers]}

    def backup(self, principal: Principal) -> dict[str, Any]:
        require_permission(principal, "admin:operate")
        db_path = self.router.path_for(principal.tenant_id)
        record = SQLiteBackupManager(db_path, tenant_id=principal.tenant_id).create_backup(
            self.config.backup_root / principal.tenant_id
        )
        replications: list[dict[str, Any]] = []
        for replicator in self.backup_replicators:
            result = replicator.replicate(record)
            replications.append(result.to_dict())
        with SQLiteKnowledgeStore(db_path) as store:
            for result in replications:
                store.connection.execute(
                    """
                    INSERT INTO backup_replications(
                        replication_id, backup_id, tenant_id, destination,
                        sha256, size_bytes, verified, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        f"repl_{uuid4().hex}",
                        record.backup_id,
                        principal.tenant_id,
                        result["destination"],
                        result["sha256"],
                        int(result["size_bytes"]),
                        int(bool(result["verified"])),
                    ),
                )
            store.connection.commit()
            AuditLog(store.connection).record(
                tenant_id=principal.tenant_id,
                principal_id=principal.principal_id,
                action="database.backup",
                resource_type="backup",
                resource_id=record.backup_id,
                metadata={
                    "sha256": record.sha256,
                    "size_bytes": record.size_bytes,
                    "replication_count": len(replications),
                },
            )
        self.metrics.increment("backups_created_total")
        return {**record.to_dict(), "replications": replications}

    def purge(self, principal: Principal, logical_document_id: str) -> dict[str, Any]:
        require_permission(principal, "admin:operate")
        db_path = self.router.path_for(principal.tenant_id)
        with SQLiteKnowledgeStore(db_path) as store:
            holds = LegalHoldStore(store.connection).active_for(logical_document_id)
            if holds:
                raise AuthorizationError("document is protected by an active legal hold")
            report = KnowledgeMaintenance(store.connection).purge_document(logical_document_id)
            AuditLog(store.connection).record(
                tenant_id=principal.tenant_id,
                principal_id=principal.principal_id,
                action="documents.purge",
                resource_type="document",
                resource_id=logical_document_id,
                metadata={"deleted_rows": report.deleted_rows},
            )
        external_cleanup: dict[str, int] = {}
        if self.external_vector_backend is not None:
            for source_type, source_ids in {
                "evidence": report.evidence_ids,
                "fact": report.fact_ids,
                "card": report.card_ids,
                "object": report.object_ids,
            }.items():
                external_cleanup[source_type] = self.external_vector_backend.delete(source_type, source_ids)
        self.metrics.increment("documents_purged_total")
        return {**report.to_dict(), "external_vector_cleanup": external_cleanup}

    def place_legal_hold(self, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
        require_permission(principal, "admin:operate")
        document_id = str(payload.get("logical_document_id") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        if not document_id or not reason:
            raise ValueError("logical_document_id and reason are required")
        with SQLiteKnowledgeStore(self.router.path_for(principal.tenant_id)) as store:
            hold = LegalHoldStore(store.connection).place(
                tenant_id=principal.tenant_id,
                logical_document_id=document_id,
                reason=reason,
                created_by=principal.principal_id,
                metadata=dict(payload.get("metadata") or {}),
            )
            AuditLog(store.connection).record(
                tenant_id=principal.tenant_id,
                principal_id=principal.principal_id,
                action="legal_hold.place",
                resource_type="document",
                resource_id=document_id,
                metadata={"hold_id": hold.hold_id},
            )
        return hold.to_dict()

    def release_legal_hold(self, principal: Principal, hold_id: str) -> dict[str, Any]:
        require_permission(principal, "admin:operate")
        with SQLiteKnowledgeStore(self.router.path_for(principal.tenant_id)) as store:
            LegalHoldStore(store.connection).release(hold_id)
            AuditLog(store.connection).record(
                tenant_id=principal.tenant_id,
                principal_id=principal.principal_id,
                action="legal_hold.release",
                resource_type="legal_hold",
                resource_id=hold_id,
            )
        return {"hold_id": hold_id, "status": "released"}

    def run_retention(self, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
        require_permission(principal, "admin:operate")
        policy = RetentionPolicy(
            policy_id=str(payload.get("policy_id") or "default-retention"),
            tenant_id=principal.tenant_id,
            retain_days=max(0, int(payload.get("retain_days") or 0)),
            statuses=tuple(str(value) for value in payload.get("statuses") or ["deprecated", "deleted"]),
            dry_run=bool(payload.get("dry_run", True)),
        )
        db_path = self.router.path_for(principal.tenant_id)
        with SQLiteKnowledgeStore(db_path) as store:
            plan = RetentionManager(store.connection).plan(policy)

        purged: list[str] = []
        held = list(plan.held_document_ids)
        external_cleanup: dict[str, dict[str, int]] = {}
        if not policy.dry_run:
            for document_id in plan.purgeable_document_ids:
                try:
                    result = self.purge(principal, document_id)
                except AuthorizationError:
                    held.append(document_id)
                    continue
                purged.append(document_id)
                external_cleanup[document_id] = dict(result.get("external_vector_cleanup") or {})

        with SQLiteKnowledgeStore(db_path) as store:
            run = RetentionManager(store.connection).record(
                policy,
                plan,
                purged_document_ids=purged,
                held_document_ids=held,
            )
            AuditLog(store.connection).record(
                tenant_id=principal.tenant_id,
                principal_id=principal.principal_id,
                action="retention.run",
                resource_type="retention_policy",
                resource_id=policy.policy_id,
                metadata={
                    "dry_run": run.dry_run,
                    "eligible": len(run.eligible_document_ids),
                    "held": len(run.held_document_ids),
                    "purged": len(run.purged_document_ids),
                    "external_cleanup_documents": len(external_cleanup),
                },
            )
        return {**run.to_dict(), "external_vector_cleanup": external_cleanup}

    def audit_events(self, principal: Principal, *, limit: int = 100) -> dict[str, Any]:
        require_permission(principal, "admin:operate")
        with SQLiteKnowledgeStore(self.router.path_for(principal.tenant_id)) as store:
            events = AuditLog(store.connection).list(tenant_id=principal.tenant_id, limit=limit)
        return {"events": [event.to_dict() for event in events]}

    def metrics_snapshot(self, principal: Principal) -> dict[str, Any]:
        require_permission(principal, "admin:operate")
        snapshot = self.metrics.snapshot().to_dict()
        if self.telemetry_exporter is not None:
            try:
                self.telemetry_exporter.export_metrics(snapshot)
            except Exception as exc:
                snapshot["telemetry_export_error"] = f"{type(exc).__name__}: {exc}"
        return snapshot

    def openapi(self, principal: Principal) -> dict[str, Any]:
        require_permission(principal, "health:read")
        return build_openapi_spec()

    def _tenant_service(self, principal: Principal) -> AgentKBService:
        return AgentKBService(
            db_path=self.router.path_for(principal.tenant_id),
            domain_pack=self.domain_pack,
            embedding_provider=self.embedding_provider,
            external_vector_backend=self.external_vector_backend,
            relation_extractor=self.relation_extractor,
            tenant_id=principal.tenant_id,
        )

    def _call(
        self,
        principal: Principal,
        permission: str,
        action: str,
        resource_type: str,
        resource_id: str | None,
        operation,
    ) -> dict[str, Any]:
        require_permission(principal, permission)
        db_path = self.router.path_for(principal.tenant_id)
        metric_name = action.replace(".", "_")
        self.metrics.increment(f"{metric_name}_requests_total")
        try:
            with self.tracer.span(
                action,
                attributes={
                    "tenant.id": principal.tenant_id,
                    "principal.id": principal.principal_id,
                    "resource.type": resource_type,
                },
            ):
                with self.metrics.timer(f"{metric_name}_duration"):
                    result = operation(self._tenant_service(principal))
        except Exception:
            self.metrics.increment(f"{metric_name}_errors_total")
            if db_path.exists():
                with SQLiteKnowledgeStore(db_path) as store:
                    AuditLog(store.connection).record(
                        tenant_id=principal.tenant_id,
                        principal_id=principal.principal_id,
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        outcome="error",
                    )
            raise
        with SQLiteKnowledgeStore(db_path) as store:
            AuditLog(store.connection).record(
                tenant_id=principal.tenant_id,
                principal_id=principal.principal_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome="success",
            )
        return result


def create_secure_http_server(
    service: HardenedAgentKBService,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "AgentKBCore/0.4"

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _dispatch(self, method: str) -> None:
            request_id = f"req_{uuid4().hex}"
            try:
                principal = service.authenticate(
                    self.headers.get("Authorization"),
                    self.headers.get("X-Tenant-ID"),
                )
                decision = service.consume_rate_limit(principal)
                if not decision.allowed:
                    self._write_json(
                        HTTPStatus.TOO_MANY_REQUESTS,
                        {"error": "rate_limited", "retry_after_seconds": decision.retry_after_seconds},
                        request_id=request_id,
                        extra_headers={"Retry-After": str(max(1, int(decision.retry_after_seconds + 0.999)))},
                    )
                    return
                payload = self._read_json() if method == "POST" else {}
                status, result = self._route(method, principal, payload)
                self._write_json(
                    status,
                    result,
                    request_id=request_id,
                    extra_headers={"X-RateLimit-Remaining": str(int(decision.remaining))},
                )
            except AuthenticationError as exc:
                self._write_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized", "detail": str(exc)}, request_id=request_id)
            except AuthorizationError as exc:
                self._write_json(HTTPStatus.FORBIDDEN, {"error": "forbidden", "detail": str(exc)}, request_id=request_id)
            except KeyError as exc:
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found", "detail": str(exc)}, request_id=request_id)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": type(exc).__name__, "detail": str(exc)}, request_id=request_id)
            except Exception as exc:  # pragma: no cover - final transport boundary
                self._write_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": type(exc).__name__, "detail": str(exc)},
                    request_id=request_id,
                )

        def _route(self, method: str, principal: Principal, payload: dict[str, Any]) -> tuple[HTTPStatus, Any]:
            path = self.path.split("?", 1)[0]
            if method == "GET" and path == "/v1/health":
                return HTTPStatus.OK, service.health(principal)
            if method == "GET" and path == "/v1/documents":
                include_deleted = "include_deleted=true" in self.path.lower()
                return HTTPStatus.OK, service.documents(principal, include_deleted=include_deleted)
            if method == "GET" and path == "/v1/metrics":
                return HTTPStatus.OK, service.metrics_snapshot(principal)
            if method == "GET" and path == "/v1/openapi.json":
                return HTTPStatus.OK, service.openapi(principal)
            if method == "GET" and path == "/v1/audit":
                return HTTPStatus.OK, service.audit_events(principal)
            if method == "GET" and path == "/v1/admin/workers":
                return HTTPStatus.OK, service.workers(principal)
            if method == "GET" and path.startswith("/v1/jobs/"):
                return HTTPStatus.OK, service.get_job(principal, path.rsplit("/", 1)[-1])
            if method == "POST" and path == "/v1/query":
                return HTTPStatus.OK, service.query(principal, payload)
            if method == "POST" and path == "/v1/index":
                return HTTPStatus.CREATED, service.index(principal, payload)
            if method == "POST" and path == "/v1/feedback":
                return HTTPStatus.CREATED, service.feedback(principal, payload)
            if method == "POST" and path == "/v1/jobs/index":
                return HTTPStatus.ACCEPTED, service.enqueue_index(principal, payload)
            if method == "POST" and path == "/v1/admin/worker-once":
                return HTTPStatus.OK, service.run_worker_once(principal, worker_id=str(payload.get("worker_id") or "api-worker"))
            if method == "POST" and path == "/v1/admin/backup":
                return HTTPStatus.CREATED, service.backup(principal)
            if method == "POST" and path == "/v1/admin/purge":
                logical_id = str(payload.get("logical_document_id") or "")
                if not logical_id:
                    raise ValueError("logical_document_id is required")
                return HTTPStatus.OK, service.purge(principal, logical_id)
            if method == "POST" and path == "/v1/admin/legal-holds":
                return HTTPStatus.CREATED, service.place_legal_hold(principal, payload)
            if method == "POST" and path == "/v1/admin/legal-holds/release":
                hold_id = str(payload.get("hold_id") or "")
                if not hold_id:
                    raise ValueError("hold_id is required")
                return HTTPStatus.OK, service.release_legal_hold(principal, hold_id)
            if method == "POST" and path == "/v1/admin/retention":
                return HTTPStatus.OK, service.run_retention(principal, payload)
            raise KeyError(path)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 10 * 1024 * 1024:
                raise ValueError("request body exceeds 10 MiB")
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
            request_id: str,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            if isinstance(payload, dict):
                payload = {**payload, "request_id": request_id}
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Request-ID", request_id)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'none'")
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((host, port), Handler)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
