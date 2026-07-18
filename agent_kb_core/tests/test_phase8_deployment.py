from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_kb.adapters import AgentKBMCPAdapter, MCPJSONRPCServer, generate_python_client
from agent_kb.domains.loader import load_domain_pack
from agent_kb.observability import InMemoryTelemetryExporter, Tracer
from agent_kb.pipeline import compile_text_to_production_store
from agent_kb.retrieval import QdrantVectorBackend, VectorRecord
from agent_kb.runtime import SQLiteDistributedRateLimiter, SQLiteJobQueue, SQLiteWorkerRegistry
from agent_kb.security import AuthenticationError, JSONFileSecretProvider, RotatingAPIKeyAuthenticator
from agent_kb.service import AgentKBService, TLSConfig
from agent_kb.storage import (
    DocumentLifecycleStore,
    FilesystemBackupReplicator,
    LegalHoldStore,
    RetentionManager,
    RetentionPolicy,
    SQLiteBackupManager,
    SQLiteKnowledgeStore,
)
from agent_kb.testing import ChaosInjector, ChaosPolicy, run_load_test, run_security_probes


ROOT = Path(__file__).resolve().parents[1]
KEY_A = "phase8-key-a-000000000000000000"
KEY_B = "phase8-key-b-000000000000000000"


def test_secret_rotation_and_generated_client(tmp_path: Path) -> None:
    secret_file = tmp_path / "secrets.json"
    secret_file.write_text(
        json.dumps(
            {
                "api_keys": {
                    KEY_A: {
                        "principal_id": "operator-a",
                        "tenant_id": "tenant-a",
                        "roles": ["admin"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    auth = RotatingAPIKeyAuthenticator(
        JSONFileSecretProvider(secret_file),
        secret_name="api_keys",
        refresh_interval_seconds=1.0,
    )
    assert auth.authenticate(KEY_A).principal_id == "operator-a"

    secret_file.write_text(
        json.dumps(
            {
                "api_keys": {
                    KEY_B: {
                        "principal_id": "operator-b",
                        "tenant_id": "tenant-a",
                        "roles": ["admin"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    assert auth.refresh(force=True)
    with pytest.raises(AuthenticationError):
        auth.authenticate(KEY_A)
    assert auth.authenticate(KEY_B).principal_id == "operator-b"

    source = generate_python_client(class_name="GeneratedAgentKBClient")
    compile(source, "<generated-agent-kb-client>", "exec")
    assert "class GeneratedAgentKBClient" in source


def test_distributed_rate_limit_worker_registry_and_idempotent_jobs(tmp_path: Path) -> None:
    db = tmp_path / "coordination.sqlite3"
    now = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)
    with SQLiteKnowledgeStore(db) as store:
        limiter = SQLiteDistributedRateLimiter(store.connection, limit=2, window_seconds=60)
        assert limiter.consume("tenant:user", now=now).allowed
        assert limiter.consume("tenant:user", now=now).allowed
        denied = limiter.consume("tenant:user", now=now)
        assert not denied.allowed
        assert denied.retry_after_seconds == 60.0

        registry = SQLiteWorkerRegistry(store.connection)
        registry.heartbeat(
            "worker-a",
            tenant_id="tenant-a",
            capabilities=["index_text"],
            now=now,
            lease_seconds=90,
        )
        active = registry.list_active(tenant_id="tenant-a", now=now)
        assert [item.worker_id for item in active] == ["worker-a"]

        queue = SQLiteJobQueue(store.connection)
        first = queue.submit(
            "echo",
            {"value": 1},
            tenant_id="tenant-a",
            idempotency_key="same-request",
        )
        second = queue.submit(
            "echo",
            {"value": 999},
            tenant_id="tenant-a",
            idempotency_key="same-request",
        )
        assert first.job_id == second.job_id
        finished = queue.run_once(
            "worker-a",
            {"echo": lambda payload: payload},
            tenant_id="tenant-a",
        )
        assert finished is not None
        assert finished.result == {"value": 1}


def test_retention_legal_hold_backup_replication_and_mcp(tmp_path: Path) -> None:
    db = tmp_path / "retention.sqlite3"
    pack = load_domain_pack(ROOT / "domains" / "obc_dcdc")
    for document_id, value in (("ldoc_hold", 30), ("ldoc_purge", 25)):
        compile_text_to_production_store(
            f"DCDC 输出纹波在额定负载下应不大于 {value}mVpp。",
            title=document_id,
            db_path=db,
            domain_pack=pack,
            logical_document_id=document_id,
        )

    with SQLiteKnowledgeStore(db) as store:
        lifecycle = DocumentLifecycleStore(store.connection)
        lifecycle.set_status("ldoc_hold", "deprecated")
        lifecycle.set_status("ldoc_purge", "deprecated")
        store.connection.execute(
            "UPDATE documents SET updated_at = '2000-01-01T00:00:00Z'"
        )
        hold = LegalHoldStore(store.connection).place(
            tenant_id="tenant-a",
            logical_document_id="ldoc_hold",
            reason="litigation",
            created_by="admin-a",
        )
        run = RetentionManager(store.connection).execute(
            RetentionPolicy(
                policy_id="policy-a",
                tenant_id="tenant-a",
                retain_days=1,
                dry_run=False,
            ),
            now=datetime(2026, 7, 18, tzinfo=UTC),
        )
        assert run.held_document_ids == ["ldoc_hold"]
        assert run.purged_document_ids == ["ldoc_purge"]
        assert lifecycle.get("ldoc_hold") is not None
        assert lifecycle.get("ldoc_purge") is None
        LegalHoldStore(store.connection).release(hold.hold_id)

    backup = SQLiteBackupManager(db, tenant_id="tenant-a").create_backup(tmp_path / "backups")
    replication = FilesystemBackupReplicator(tmp_path / "replica").replicate(backup)
    assert replication.verified
    assert Path(replication.destination).exists()

    service = AgentKBService(db_path=db, domain_pack=pack)
    transport = MCPJSONRPCServer(AgentKBMCPAdapter(service))
    initialized = transport.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert initialized is not None
    assert initialized["result"]["serverInfo"]["version"] == "0.4.0"
    tools = transport.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert tools is not None
    assert any(item["name"] == "agent_kb_query" for item in tools["result"]["tools"])


def test_qdrant_contract_telemetry_tls_and_reliability_harness(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(outbound, timeout):
        body = json.loads((outbound.data or b"{}").decode("utf-8"))
        calls.append((outbound.method, outbound.full_url, body))
        if outbound.full_url.endswith("/points/query"):
            return FakeResponse(
                {
                    "status": "ok",
                    "result": {
                        "points": [
                            {
                                "score": 0.91,
                                "payload": {
                                    "source_type": "fact",
                                    "source_id": "fact-1",
                                    "object_id": "OBJECT_1",
                                },
                            }
                        ]
                    },
                }
            )
        return FakeResponse({"status": "ok", "result": {"status": "acknowledged"}})

    monkeypatch.setattr("agent_kb.retrieval.qdrant.request.urlopen", fake_urlopen)
    backend = QdrantVectorBackend(
        base_url="https://qdrant.example",
        collection_name="agent-kb",
        api_key="secret-not-in-repr",
    )
    record = VectorRecord(
        source_type="fact",
        source_id="fact-1",
        object_id="OBJECT_1",
        vector=[1.0, 0.0],
        payload={"evidence_ids": ["ev-1"]},
    )
    assert backend.upsert([record]) == 1
    candidates = backend.search([1.0, 0.0], limit=3)
    assert candidates[0].source_id == "fact-1"
    assert backend.delete("fact", ["fact-1"]) == 1
    assert calls[0][0] == "PUT"
    assert calls[1][1].endswith("/points/query")
    assert calls[2][1].endswith("/points/delete?wait=true")
    assert "secret-not-in-repr" not in repr(backend)

    exporter = InMemoryTelemetryExporter()
    tracer = Tracer(exporter)
    with tracer.span("test.operation", attributes={"tenant.id": "tenant-a"}):
        pass
    assert len(exporter.spans) == 1
    assert exporter.spans[0].status == "ok"

    class FailingExporter:
        def export_spans(self, spans):
            raise RuntimeError("collector unavailable")

        def export_metrics(self, metrics):
            raise RuntimeError("collector unavailable")

    safe_tracer = Tracer(FailingExporter())
    with safe_tracer.span("safe.operation"):
        pass
    assert safe_tracer.export_error_count == 1

    with pytest.raises(FileNotFoundError):
        TLSConfig(
            certificate_file=tmp_path / "missing.crt",
            private_key_file=tmp_path / "missing.key",
        ).validate()

    report = run_load_test(lambda index: index * 2, request_count=20, concurrency=4)
    assert report.success_count == 20
    assert report.error_count == 0
    chaos = ChaosInjector(lambda: "ok", ChaosPolicy(failure_rate=1.0, seed=1))
    with pytest.raises(RuntimeError, match="injected chaos failure"):
        chaos()
    probes = run_security_probes(
        [
            ("true-probe", lambda: True),
            ("false-probe", lambda: False),
        ]
    )
    assert [item.passed for item in probes] == [True, False]
