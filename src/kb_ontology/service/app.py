"""Application service: health, query, extract, jobs against OntologyStore."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kb_ontology.domains.loader import load_domain_pack
from kb_ontology.domains.schema import DomainPack
from kb_ontology.extraction.extractor import ExtractionResult, extract_document
from kb_ontology.ingestion.batch import (
    JOB_TYPE_EXTRACT,
    discover_documents,
    enqueue_extract_jobs,
    run_extract_worker_once,
)
from kb_ontology.llm.llm_client import LLMChatClient
from kb_ontology.observability.metrics import MetricsRegistry
from kb_ontology.pipeline import answer_query
from kb_ontology.runtime.jobs import SQLiteJobQueue
from kb_ontology.security.audit import AuditLog
from kb_ontology.security.auth import Principal
from kb_ontology.storage.store import OntologyStore


@dataclass(frozen=True)
class ServiceHealth:
    status: str
    version: str
    store_summary: dict[str, int]
    domain_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "version": self.version,
            "store_summary": dict(self.store_summary),
            "domain_id": self.domain_id,
        }


class OntologyService:
    """Facade used by HTTP (and future CLI/MCP) adapters."""

    def __init__(
        self,
        *,
        db_path: str | Path,
        domain_pack: DomainPack | None = None,
        domain_dir: str | Path | None = None,
        client: LLMChatClient | None = None,
        metrics: MetricsRegistry | None = None,
        tenant_id: str = "default",
    ) -> None:
        self.db_path = Path(db_path)
        if domain_pack is not None:
            self.domain_pack = domain_pack
        elif domain_dir is not None:
            self.domain_pack = load_domain_pack(Path(domain_dir))
        else:
            self.domain_pack = None
        self._client = client
        self.metrics = metrics or MetricsRegistry()
        self.tenant_id = tenant_id
        # Companion queue DB next to the ontology store.
        self._job_queue_path = Path(str(self.db_path) + ".jobs")

    def job_queue(self) -> SQLiteJobQueue:
        return SQLiteJobQueue.open(self._job_queue_path)

    def _llm(self) -> LLMChatClient | None:
        if self._client is not None:
            return self._client
        try:
            self._client = LLMChatClient.from_environment()
        except Exception:
            return None
        return self._client

    def health(self) -> ServiceHealth:
        from kb_ontology import __version__

        with OntologyStore(self.db_path) as store:
            summary = store.stats()
        return ServiceHealth(
            status="ok",
            version=__version__,
            store_summary=summary,
            domain_id=self.domain_pack.domain_id if self.domain_pack else None,
        )

    def query(
        self,
        payload: dict[str, Any],
        *,
        principal: Principal | None = None,
        audit: AuditLog | None = None,
    ) -> dict[str, Any]:
        text = str(payload.get("query") or payload.get("text") or "").strip()
        if not text:
            raise ValueError("query is required")
        use_llm_understanding = bool(payload.get("use_llm_understanding", False))
        use_llm_judgement = bool(payload.get("use_llm_judgement", False))
        client = self._llm() if (use_llm_understanding or use_llm_judgement) else None

        with self.metrics.timer("service.query"):
            with OntologyStore(self.db_path) as store:
                pack = answer_query(
                    store,
                    text,
                    domain_pack=self.domain_pack,
                    domain=self.domain_pack.domain_id if self.domain_pack else None,
                    client=client,
                    use_llm_understanding=use_llm_understanding,
                    use_llm_judgement=use_llm_judgement,
                )
        self.metrics.increment("service.query.ok")
        result = pack.to_dict()
        if audit and principal:
            audit.record(
                tenant_id=principal.tenant_id,
                principal_id=principal.principal_id,
                action="query:run",
                resource_type="query",
                resource_id=None,
                outcome="success",
                metadata={
                    "intent": pack.intent,
                    "hit_count": len(pack.hits),
                    "strategy": pack.recommended_answer_strategy,
                },
            )
        return result

    def extract(
        self,
        payload: dict[str, Any],
        *,
        principal: Principal | None = None,
        audit: AuditLog | None = None,
    ) -> dict[str, Any]:
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("text is required")
        if self.domain_pack is None:
            raise ValueError("domain pack is required for extraction")
        document_id = str(payload.get("document_id") or "doc_anonymous").strip()
        client = self._llm()
        if client is None:
            raise RuntimeError("LLM client is not configured")

        with self.metrics.timer("service.extract"):
            with OntologyStore(self.db_path) as store:
                result: ExtractionResult = extract_document(
                    text,
                    document_id=document_id,
                    domain_pack=self.domain_pack,
                    store=store,
                    client=client,
                    max_tokens=int(payload.get("max_tokens") or 4000),
                )
                stats = store.stats()
        self.metrics.increment("service.extract.ok")
        out = {
            "document_id": document_id,
            "entity_count": result.entity_count,
            "relation_count": result.relation_count,
            "store_summary": stats,
            "entities": [e.to_dict() for e in result.entities],
            "relations": [r.to_dict() for r in result.relations],
        }
        if audit and principal:
            audit.record(
                tenant_id=principal.tenant_id,
                principal_id=principal.principal_id,
                action="extract:run",
                resource_type="document",
                resource_id=document_id,
                outcome="success",
                metadata={
                    "entity_count": result.entity_count,
                    "relation_count": result.relation_count,
                },
            )
        return out

    def metrics_snapshot(self) -> dict[str, Any]:
        return self.metrics.snapshot().to_dict()

    def enqueue_extract_batch(
        self,
        payload: dict[str, Any],
        *,
        principal: Principal | None = None,
        audit: AuditLog | None = None,
    ) -> dict[str, Any]:
        """Discover files under path/root and enqueue extract_document jobs."""
        root = payload.get("path") or payload.get("root")
        if not root:
            raise ValueError("path is required")
        docs = discover_documents(
            root,
            recursive=bool(payload.get("recursive", True)),
            max_files=payload.get("max_files"),
            extensions=payload.get("extensions"),
        )
        queue = self.job_queue()
        result = enqueue_extract_jobs(
            queue,
            docs,
            tenant_id=self.tenant_id,
            max_tokens=int(payload.get("max_tokens") or 4000),
            max_attempts=int(payload.get("max_attempts") or 3),
        )
        self.metrics.increment("service.jobs.enqueued", len(result.enqueued))
        out = result.to_dict()
        out["job_type"] = JOB_TYPE_EXTRACT
        if audit and principal:
            audit.record(
                tenant_id=principal.tenant_id,
                principal_id=principal.principal_id,
                action="jobs:write",
                resource_type="job_batch",
                resource_id=str(root),
                outcome="success",
                metadata={
                    "enqueued": out["enqueued"],
                    "files_scanned": out["files_scanned"],
                },
            )
        return out

    def list_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        principal: Principal | None = None,
        audit: AuditLog | None = None,
    ) -> dict[str, Any]:
        queue = self.job_queue()
        jobs = queue.list(
            status=status, tenant_id=self.tenant_id, limit=limit
        )
        out = {"jobs": [j.to_dict() for j in jobs], "count": len(jobs)}
        if audit and principal:
            audit.record(
                tenant_id=principal.tenant_id,
                principal_id=principal.principal_id,
                action="jobs:read",
                resource_type="job",
                outcome="success",
                metadata={"count": len(jobs), "status": status},
            )
        return out

    def get_job(self, job_id: str) -> dict[str, Any]:
        job = self.job_queue().get(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
        return job.to_dict()

    def worker_once(
        self,
        *,
        worker_id: str = "worker-1",
        principal: Principal | None = None,
        audit: AuditLog | None = None,
    ) -> dict[str, Any]:
        """Process at most one queued extract job (needs LLM + domain pack)."""
        if self.domain_pack is None:
            raise ValueError("domain pack is required for worker")
        client = self._llm()
        if client is None:
            raise RuntimeError("LLM client is not configured")
        queue = self.job_queue()
        with self.metrics.timer("service.worker_once"):
            job = run_extract_worker_once(
                queue,
                db_path=self.db_path,
                domain_pack=self.domain_pack,
                client=client,
                worker_id=worker_id,
                tenant_id=self.tenant_id,
            )
        if job is None:
            self.metrics.increment("service.worker.idle")
            return {"processed": False, "job": None}
        self.metrics.increment(f"service.worker.{job.status}")
        out = {"processed": True, "job": job.to_dict()}
        if audit and principal:
            audit.record(
                tenant_id=principal.tenant_id,
                principal_id=principal.principal_id,
                action="jobs:write",
                resource_type="job",
                resource_id=job.job_id,
                outcome="success" if job.status == "succeeded" else job.status,
                metadata={"status": job.status, "job_type": job.job_type},
            )
        return out
