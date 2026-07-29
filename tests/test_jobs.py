"""Job queue and batch enqueue tests (no live LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest

from kb_ontology.ingestion.batch import (
    JOB_TYPE_EXTRACT,
    DocumentRef,
    discover_documents,
    enqueue_extract_jobs,
    make_extract_handler,
)
from kb_ontology.runtime.jobs import SQLiteJobQueue
from kb_ontology.service.app import OntologyService


def test_job_queue_submit_claim_succeed(tmp_path: Path) -> None:
    queue = SQLiteJobQueue.open(tmp_path / "jobs.db")
    job = queue.submit("extract_document", {"path": "/x.md"}, tenant_id="t1")
    assert job.status == "queued"
    claimed = queue.claim("w1", tenant_id="t1")
    assert claimed is not None
    assert claimed.job_id == job.job_id
    assert claimed.status == "running"
    assert claimed.attempts == 1
    queue.succeed(claimed.job_id, {"ok": True})
    done = queue.get(job.job_id)
    assert done is not None
    assert done.status == "succeeded"
    assert done.result == {"ok": True}
    assert queue.claim("w1", tenant_id="t1") is None


def test_job_idempotency(tmp_path: Path) -> None:
    queue = SQLiteJobQueue.open(tmp_path / "jobs.db")
    a = queue.submit(
        "extract_document",
        {"document_id": "d1"},
        idempotency_key="extract:d1",
    )
    b = queue.submit(
        "extract_document",
        {"document_id": "d1"},
        idempotency_key="extract:d1",
    )
    assert a.job_id == b.job_id


def test_job_requeue_resets_terminal(tmp_path: Path) -> None:
    queue = SQLiteJobQueue.open(tmp_path / "jobs.db")
    job = queue.submit(
        "extract_document",
        {"document_id": "d1", "max_tokens": 1000},
        idempotency_key="extract:d1",
    )
    claimed = queue.claim("w1")
    assert claimed is not None
    queue.succeed(claimed.job_id, {"entity_count": 0, "empty": True})
    done = queue.get(job.job_id)
    assert done is not None and done.status == "succeeded"

    again = queue.requeue(
        job.job_id,
        payload_updates={"max_tokens": 6000, "text_limit": 8000},
        reset_attempts=True,
    )
    assert again.status == "queued"
    assert again.attempts == 0
    assert again.payload["max_tokens"] == 6000
    assert again.payload["text_limit"] == 8000
    assert again.result is None
    # Idempotency still points at same job_id unless cleared.
    reused = queue.submit(
        "extract_document",
        {"document_id": "d1"},
        idempotency_key="extract:d1",
    )
    assert reused.job_id == job.job_id
    assert reused.status == "queued"


def test_job_fail_retries_then_terminal(tmp_path: Path) -> None:
    queue = SQLiteJobQueue.open(tmp_path / "jobs.db")
    job = queue.submit("t", {}, max_attempts=2)

    def boom(_payload: dict) -> dict:
        raise RuntimeError("boom")

    first = queue.run_once("w", {"t": boom})
    assert first is not None
    assert first.status == "queued"
    assert first.attempts == 1
    second = queue.run_once("w", {"t": boom})
    assert second is not None
    assert second.status == "failed"
    assert second.attempts == 2


def test_discover_and_enqueue(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a.md").write_text("# A\nhello", encoding="utf-8")
    (root / "b.txt").write_text("B", encoding="utf-8")
    (root / "skip.bin").write_bytes(b"\x00")
    sub = root / "sub"
    sub.mkdir()
    (sub / "c.md").write_text("C", encoding="utf-8")

    docs = discover_documents(root)
    assert len(docs) == 3
    ids = {d.document_id for d in docs}
    assert any("a.md" in i or i.endswith("a.md") for i in ids)

    queue = SQLiteJobQueue.open(tmp_path / "q.db")
    result = enqueue_extract_jobs(queue, docs)
    assert result.files_scanned == 3
    assert len(result.enqueued) == 3

    # second enqueue is idempotent
    again = enqueue_extract_jobs(queue, docs)
    assert again.files_scanned == 3
    # all reused; none newly created beyond the three
    assert len(queue.list(limit=100)) == 3


def test_extract_handler_with_mock_client(tmp_path: Path) -> None:
    from kb_ontology.domains.loader import load_domain_pack
    from kb_ontology.llm.llm_client import LLMChatClient, LLMChatResponse

    domain = Path(__file__).resolve().parents[1] / "domains" / "obc_dcdc"
    pack = load_domain_pack(domain)
    doc = tmp_path / "doc.md"
    doc.write_text(
        "车载 DC-DC转换器 用于将高压电池转换为低压供电。",
        encoding="utf-8",
    )
    db = tmp_path / "ont.db"

    class Fake(LLMChatClient):
        def __init__(self) -> None:  # noqa: D107
            pass

        def chat(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return LLMChatResponse(
                content=(
                    '{"entities":[{"local_key":"e1","class":"Product",'
                    '"canonical_name":"DC-DC转换器",'
                    '"attributes":{"name":"DC-DC转换器","description":"车载直流变换"},'
                    '"text_span":"车载 DC-DC转换器","location":"§1","confidence":0.9}],'
                    '"relations":[]}'
                ),
                model="fake",
                usage_json={},
                raw_response={},
            )

    handler = make_extract_handler(db_path=db, domain_pack=pack, client=Fake())  # type: ignore[arg-type]
    out = handler(
        {
            "path": str(doc),
            "document_id": "doc.md",
            "max_tokens": 1000,
        }
    )
    assert out is not None
    assert out["entity_count"] >= 1
    assert out["store_summary"]["entities"] >= 1


def test_extract_handler_rejects_empty_extraction(tmp_path: Path) -> None:
    from kb_ontology.domains.loader import load_domain_pack
    from kb_ontology.ingestion.batch import EmptyExtractionError
    from kb_ontology.llm.llm_client import LLMChatClient, LLMChatResponse

    domain = Path(__file__).resolve().parents[1] / "domains" / "obc_dcdc"
    pack = load_domain_pack(domain)
    doc = tmp_path / "noise.md"
    doc.write_text("这是一段与本体无关的噪声文本，不应产生实体。", encoding="utf-8")
    db = tmp_path / "ont.db"

    class EmptyFake(LLMChatClient):
        def __init__(self) -> None:  # noqa: D107
            pass

        def chat(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return LLMChatResponse(
                content='{"entities":[],"relations":[]}',
                model="fake",
                usage_json={},
                raw_response={},
            )

    handler = make_extract_handler(
        db_path=db, domain_pack=pack, client=EmptyFake()  # type: ignore[arg-type]
    )
    with pytest.raises(EmptyExtractionError):
        handler({"path": str(doc), "document_id": "noise.md"})
    # Opt-in allow_empty keeps prior succeed-with-zero behaviour.
    out = handler(
        {"path": str(doc), "document_id": "noise.md", "allow_empty": True}
    )
    assert out is not None
    assert out["entity_count"] == 0
    assert out["empty"] is True


def test_service_enqueue_and_list_jobs(tmp_path: Path) -> None:
    domain = Path(__file__).resolve().parents[1] / "domains" / "obc_dcdc"
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "one.md").write_text("x", encoding="utf-8")
    svc = OntologyService(db_path=tmp_path / "ont.db", domain_dir=domain)
    batch = svc.enqueue_extract_batch({"path": str(root), "max_files": 5})
    assert batch["files_scanned"] == 1
    assert batch["enqueued"] == 1
    assert batch["job_type"] == JOB_TYPE_EXTRACT
    listed = svc.list_jobs()
    assert listed["count"] == 1
    job_id = listed["jobs"][0]["job_id"]
    got = svc.get_job(job_id)
    assert got["status"] == "queued"
