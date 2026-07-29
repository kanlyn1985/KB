"""Batch document discovery and extract job enqueue/run helpers."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from kb_ontology.domains.schema import DomainPack
from kb_ontology.extraction.extractor import extract_document
from kb_ontology.llm.llm_client import LLMChatClient
from kb_ontology.runtime.jobs import BackgroundJob, SQLiteJobQueue
from kb_ontology.storage.store import OntologyStore

_logger = logging.getLogger(__name__)

JOB_TYPE_EXTRACT = "extract_document"


class EmptyExtractionError(RuntimeError):
    """Raised when extract_document returns zero entities for non-empty text.

    Lets the job queue retry (or mark failed) instead of recording a hollow
    ``succeeded`` result that blocks idempotent re-queue.
    """

DEFAULT_EXTENSIONS = frozenset({".md", ".txt", ".markdown"})


@dataclass(frozen=True)
class DocumentRef:
    path: Path
    document_id: str
    relative_path: str

    def to_dict(self) -> dict[str, str]:
        return {
            "path": str(self.path),
            "document_id": self.document_id,
            "relative_path": self.relative_path,
        }


@dataclass
class BatchEnqueueResult:
    enqueued: list[BackgroundJob] = field(default_factory=list)
    skipped_existing: int = 0
    files_scanned: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_scanned": self.files_scanned,
            "enqueued": len(self.enqueued),
            "skipped_existing": self.skipped_existing,
            "job_ids": [j.job_id for j in self.enqueued],
        }


def discover_documents(
    root: str | Path,
    *,
    extensions: Sequence[str] | None = None,
    recursive: bool = True,
    max_files: int | None = None,
    exclude_dir_names: Sequence[str] | None = None,
) -> list[DocumentRef]:
    """Walk a directory (or accept a single file) and return DocumentRefs.

    ``document_id`` is a stable slug from the relative path (or file stem).
    """
    root_path = Path(root).resolve()
    exts = {
        e if e.startswith(".") else f".{e}"
        for e in (extensions or DEFAULT_EXTENSIONS)
    }
    exclude = set(exclude_dir_names or ("node_modules", ".git", "__pycache__", ".venv"))

    files: list[Path] = []
    if root_path.is_file():
        if root_path.suffix.lower() in exts:
            files = [root_path]
    elif root_path.is_dir():
        iterator: Iterable[Path]
        if recursive:
            iterator = root_path.rglob("*")
        else:
            iterator = root_path.glob("*")
        for path in iterator:
            if not path.is_file():
                continue
            if any(part in exclude for part in path.parts):
                continue
            if path.suffix.lower() not in exts:
                continue
            files.append(path)
    else:
        raise FileNotFoundError(f"path not found: {root_path}")

    files = sorted(files)
    if max_files is not None:
        files = files[: max(0, int(max_files))]

    base = root_path if root_path.is_dir() else root_path.parent
    refs: list[DocumentRef] = []
    for path in files:
        try:
            rel = str(path.relative_to(base))
        except ValueError:
            rel = path.name
        doc_id = _document_id_from_relative(rel)
        refs.append(DocumentRef(path=path, document_id=doc_id, relative_path=rel))
    return refs


def enqueue_extract_jobs(
    queue: SQLiteJobQueue,
    docs: Sequence[DocumentRef],
    *,
    tenant_id: str = "default",
    max_tokens: int = 4000,
    max_attempts: int = 3,
    text_limit: int | None = 8000,
) -> BatchEnqueueResult:
    """Submit extract_document jobs with path-based idempotency keys.

    Re-submitting the same document_id returns the existing job (idempotent).
    ``enqueued`` lists jobs that are not yet terminal-succeeded; succeeded
    reuses increment ``skipped_existing``.

    ``text_limit`` caps characters sent to the LLM (None = full file). Default
    8000 keeps long strategy markdown inside typical context budgets.
    """
    result = BatchEnqueueResult(files_scanned=len(docs))
    seen_job_ids: set[str] = set()
    for doc in docs:
        key = f"extract:{doc.document_id}"
        prior = queue.connection.execute(
            """
            SELECT job_id FROM job_idempotency
            WHERE tenant_id = ? AND idempotency_key = ?
            """,
            (tenant_id, key),
        ).fetchone()
        payload: dict[str, Any] = {
            "path": str(doc.path),
            "document_id": doc.document_id,
            "relative_path": doc.relative_path,
            "max_tokens": int(max_tokens),
        }
        if text_limit is not None:
            payload["text_limit"] = int(text_limit)
        job = queue.submit(
            JOB_TYPE_EXTRACT,
            payload,
            tenant_id=tenant_id,
            max_attempts=max_attempts,
            idempotency_key=key,
        )
        reused = prior is not None and str(prior["job_id"]) == job.job_id
        if reused and job.status == "succeeded":
            result.skipped_existing += 1
            continue
        if job.job_id in seen_job_ids:
            continue
        seen_job_ids.add(job.job_id)
        result.enqueued.append(job)
    return result


def make_extract_handler(
    *,
    db_path: str | Path,
    domain_pack: DomainPack,
    client: LLMChatClient,
) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
    """Build a job handler that reads a file and runs extract_document."""

    def handler(payload: dict[str, Any]) -> dict[str, Any] | None:
        path = Path(str(payload.get("path") or ""))
        document_id = str(payload.get("document_id") or path.stem or "doc")
        max_tokens = int(payload.get("max_tokens") or 4000)
        allow_empty = bool(payload.get("allow_empty") or False)
        # Optional head truncate for oversized markdown (LLM context budget).
        text_limit = payload.get("text_limit")
        if not path.is_file():
            raise FileNotFoundError(f"document not found: {path}")
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            return {
                "document_id": document_id,
                "entity_count": 0,
                "relation_count": 0,
                "empty": True,
                "empty_reason": "blank_file",
            }
        if text_limit is not None:
            try:
                limit = int(text_limit)
            except (TypeError, ValueError):
                limit = 0
            if limit > 0 and len(text) > limit:
                text = text[:limit]
        with OntologyStore(db_path) as store:
            result = extract_document(
                text,
                document_id=document_id,
                domain_pack=domain_pack,
                store=store,
                client=client,
                max_tokens=max_tokens,
            )
            stats = store.stats()
        if result.entity_count == 0 and not allow_empty:
            raise EmptyExtractionError(
                f"empty extraction for {document_id} "
                f"(chars={len(text)}, path={path})"
            )
        return {
            "document_id": document_id,
            "entity_count": result.entity_count,
            "relation_count": result.relation_count,
            "store_summary": stats,
            "path": str(path),
            "empty": result.entity_count == 0,
        }

    return handler


def run_extract_worker_once(
    queue: SQLiteJobQueue,
    *,
    db_path: str | Path,
    domain_pack: DomainPack,
    client: LLMChatClient,
    worker_id: str = "worker-1",
    tenant_id: str | None = None,
) -> BackgroundJob | None:
    """Claim and process one extract_document job."""
    handler = make_extract_handler(
        db_path=db_path, domain_pack=domain_pack, client=client
    )
    return queue.run_once(
        worker_id,
        {JOB_TYPE_EXTRACT: handler},
        tenant_id=tenant_id,
    )


def run_extract_worker_loop(
    queue: SQLiteJobQueue,
    *,
    db_path: str | Path,
    domain_pack: DomainPack,
    client: LLMChatClient,
    worker_id: str = "worker-1",
    tenant_id: str | None = None,
    max_jobs: int | None = None,
    idle_sleep_seconds: float = 0.5,
) -> list[BackgroundJob]:
    """Process jobs until queue is idle or max_jobs reached."""
    import time

    handler = make_extract_handler(
        db_path=db_path, domain_pack=domain_pack, client=client
    )
    handlers = {JOB_TYPE_EXTRACT: handler}
    done: list[BackgroundJob] = []
    idle_rounds = 0
    while max_jobs is None or len(done) < max_jobs:
        job = queue.run_once(worker_id, handlers, tenant_id=tenant_id)
        if job is None:
            idle_rounds += 1
            if idle_rounds >= 2:
                break
            time.sleep(idle_sleep_seconds)
            continue
        idle_rounds = 0
        done.append(job)
        _logger.info(
            "job %s status=%s type=%s",
            job.job_id,
            job.status,
            job.job_type,
        )
    return done


def _document_id_from_relative(rel: str) -> str:
    cleaned = (
        rel.replace("\\", "/")
        .replace("/", "__")
        .replace(" ", "_")
        .replace("..", ".")
    )
    # Keep readable; if too long, append hash of full path
    if len(cleaned) <= 180:
        return cleaned
    digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]
    stem = Path(rel).stem[:80]
    return f"{stem}__{digest}"
