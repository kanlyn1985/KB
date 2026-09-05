from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from agent_kb.domains.schema import DomainPack
from agent_kb.embeddings import EmbeddingProvider
from agent_kb.graph import RelationExtractor
from agent_kb.pipeline.persistent_context import add_persistent_feedback
from agent_kb.pipeline.production_context import (
    compile_text_to_production_store,
    list_production_documents,
    query_production_store,
    set_production_document_status,
)
from agent_kb.retrieval.external_vector import ExternalVectorBackend
from agent_kb.storage.migrations import SchemaMigrator
from agent_kb.storage.sqlite_store import SQLiteKnowledgeStore


@dataclass(frozen=True)
class ServiceHealth:
    status: str
    schema_version: int
    store_summary: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "schema_version": self.schema_version,
            "store_summary": dict(self.store_summary),
        }


class AgentKBService:
    """Application service used by HTTP, CLI, MCP, or embedded adapters."""

    def __init__(
        self,
        *,
        db_path: str | Path,
        domain_pack: DomainPack | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        external_vector_backend: ExternalVectorBackend | None = None,
        relation_extractor: RelationExtractor | None = None,
        tenant_id: str = "default",
    ) -> None:
        self.db_path = Path(db_path)
        self.domain_pack = domain_pack
        self.embedding_provider = embedding_provider
        self.external_vector_backend = external_vector_backend
        self.relation_extractor = relation_extractor
        self.tenant_id = tenant_id

    def health(self) -> ServiceHealth:
        with SQLiteKnowledgeStore(self.db_path) as store:
            migrator = SchemaMigrator(store.connection)
            migrator.migrate()
            return ServiceHealth(
                status="ok",
                schema_version=migrator.current_version(),
                store_summary=store.summary(),
            )

    def index(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or "")
        if not text.strip():
            raise ValueError("text is required")
        result = compile_text_to_production_store(
            text,
            title=str(payload.get("title") or "untitled"),
            db_path=self.db_path,
            domain_pack=self.domain_pack,
            embedding_provider=self.embedding_provider,
            external_vector_backend=self.external_vector_backend,
            relation_extractor=self.relation_extractor,
            tenant_id=self.tenant_id,
            source_type=str(payload.get("source_type") or "text"),
            source_uri=_optional_text(payload.get("source_uri")),
            version_label=_optional_text(payload.get("version_label")),
            logical_document_id=_optional_text(payload.get("logical_document_id")),
            metadata=dict(payload.get("metadata") or {}),
            max_evidence_chars=max(100, int(payload.get("max_evidence_chars") or 900)),
        )
        return result.to_dict()

    def query(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query") or "")
        if not query.strip():
            raise ValueError("query is required")
        result = query_production_store(
            query,
            db_path=self.db_path,
            domain_pack=self.domain_pack,
            embedding_provider=self.embedding_provider,
            external_vector_backend=self.external_vector_backend,
            retrieval_top_k=max(1, int(payload.get("top_k") or 12)),
        )
        return result.to_dict()

    def feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or "")
        if not run_id:
            raise ValueError("run_id is required")
        feedback_id = add_persistent_feedback(
            db_path=self.db_path,
            run_id=run_id,
            rating=int(payload.get("rating") or 0),
            comment=str(payload.get("comment") or ""),
            metadata=dict(payload.get("metadata") or {}),
        )
        return {"feedback_id": feedback_id, "run_id": run_id}

    def documents(self, *, include_deleted: bool = False) -> list[dict[str, Any]]:
        return [
            item.to_dict()
            for item in list_production_documents(self.db_path, include_deleted=include_deleted)
        ]

    def set_document_status(self, logical_document_id: str, status: str) -> dict[str, str]:
        set_production_document_status(self.db_path, logical_document_id, status)
        return {"logical_document_id": logical_document_id, "status": status}


def create_http_server(
    service: AgentKBService,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> ThreadingHTTPServer:
    """Create a basic JSON server for trusted embedded deployments.

    Internet-facing deployments should use `create_secure_http_server`.
    """

    class Handler(BaseHTTPRequestHandler):
        server_version = "AgentKBCore/0.3"

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health" or self.path == "/v1/health":
                self._write_json(HTTPStatus.OK, service.health().to_dict())
                return
            if self.path.startswith("/v1/documents"):
                include_deleted = "include_deleted=true" in self.path.lower()
                self._write_json(HTTPStatus.OK, {"documents": service.documents(include_deleted=include_deleted)})
                return
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            try:
                payload = self._read_json()
                if self.path == "/v1/index":
                    self._write_json(HTTPStatus.CREATED, service.index(payload))
                    return
                if self.path == "/v1/query":
                    self._write_json(HTTPStatus.OK, service.query(payload))
                    return
                if self.path == "/v1/feedback":
                    self._write_json(HTTPStatus.CREATED, service.feedback(payload))
                    return
                if self.path.startswith("/v1/documents/") and self.path.endswith("/status"):
                    logical_id = self.path.split("/")[3]
                    status = str(payload.get("status") or "")
                    self._write_json(HTTPStatus.OK, service.set_document_status(logical_id, status))
                    return
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            except (ValueError, KeyError, TypeError) as exc:
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": type(exc).__name__, "detail": str(exc)})
            except Exception as exc:  # pragma: no cover - final service boundary
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
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((host, port), Handler)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
