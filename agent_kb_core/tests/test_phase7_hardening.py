from pathlib import Path

import pytest

from agent_kb.adapters import AgentKBMCPAdapter, build_openapi_spec
from agent_kb.domains.loader import load_domain_pack
from agent_kb.embeddings import HashEmbeddingProvider, RemoteJSONEmbeddingProvider
from agent_kb.evaluation import GraphGoldenEdge, evaluate_graph_edges
from agent_kb.graph import GraphEdge
from agent_kb.pipeline import compile_text_to_production_store, query_production_store
from agent_kb.retrieval import InMemoryVectorBackend
from agent_kb.runtime import SQLiteJobQueue, TokenBucketRateLimiter
from agent_kb.security import APIKeyAuthenticator, AuthorizationError, TenantDatabaseRouter, require_permission
from agent_kb.service import AgentKBService, HardenedAgentKBService, HardenedServiceConfig
from agent_kb.storage import SQLiteBackupManager, SQLiteKnowledgeStore


ROOT = Path(__file__).resolve().parents[1]
ADMIN_KEY = "admin-key-00000000000000000000"
READER_KEY = "reader-key-0000000000000000000"


def _authenticator() -> APIKeyAuthenticator:
    return APIKeyAuthenticator.from_mapping(
        {
            ADMIN_KEY: {
                "principal_id": "admin-a",
                "tenant_id": "tenant-a",
                "roles": ["admin"],
            },
            READER_KEY: {
                "principal_id": "reader-b",
                "tenant_id": "tenant-b",
                "roles": ["reader"],
            },
        }
    )


def test_auth_rbac_tenant_routing_and_rate_limit(tmp_path: Path) -> None:
    auth = _authenticator()
    admin = auth.authenticate(ADMIN_KEY)
    reader = auth.authenticate(READER_KEY)

    assert admin.tenant_id == "tenant-a"
    assert reader.tenant_id == "tenant-b"
    require_permission(admin, "admin:operate")
    with pytest.raises(AuthorizationError):
        require_permission(reader, "documents:index")

    router = TenantDatabaseRouter(tmp_path / "tenants")
    assert router.path_for("tenant-a") != router.path_for("tenant-b")

    limiter = TokenBucketRateLimiter(capacity=2, refill_per_second=1.0)
    assert limiter.consume("principal", now=100.0).allowed
    assert limiter.consume("principal", now=100.0).allowed
    denied = limiter.consume("principal", now=100.0)
    assert not denied.allowed
    assert limiter.consume("principal", now=101.0).allowed


def test_external_vector_backend_and_remote_secret_redaction(tmp_path: Path) -> None:
    pack = load_domain_pack(ROOT / "domains" / "obc_dcdc")
    provider = HashEmbeddingProvider(dimensions=64)
    backend = InMemoryVectorBackend()
    db = tmp_path / "external.sqlite3"

    indexed = compile_text_to_production_store(
        "DCDC 输出纹波在额定负载下应不大于 30mVpp。",
        title="Ripple",
        db_path=db,
        domain_pack=pack,
        embedding_provider=provider,
        external_vector_backend=backend,
        logical_document_id="ldoc_external",
    )
    assert indexed.external_vector_count > 0

    result = query_production_store(
        "LV ripple limit?",
        db_path=db,
        domain_pack=pack,
        embedding_provider=provider,
        external_vector_backend=backend,
    )
    assert result.retrieval_result.candidates
    assert any(
        "external_vector_similarity" in candidate.reasons
        or "multi_adapter_corroboration" in candidate.reasons
        for candidate in result.retrieval_result.candidates
    )

    remote = RemoteJSONEmbeddingProvider(
        endpoint="https://embedding.invalid/v1/embeddings",
        model="learned-model",
        dimensions=768,
        api_key="never-print-this-secret",
    )
    assert "never-print-this-secret" not in repr(remote)


def test_jobs_backup_purge_hardened_service_and_tenant_isolation(tmp_path: Path) -> None:
    pack = load_domain_pack(ROOT / "domains" / "obc_dcdc")
    hardened = HardenedAgentKBService(
        config=HardenedServiceConfig(
            tenant_db_root=tmp_path / "tenant-db",
            backup_root=tmp_path / "backups",
            rate_limit_capacity=100,
            rate_limit_refill_per_second=100.0,
        ),
        authenticator=_authenticator(),
        domain_pack=pack,
    )
    admin = hardened.authenticate(f"Bearer {ADMIN_KEY}", "tenant-a")
    reader = hardened.authenticate(f"Bearer {READER_KEY}", "tenant-b")

    indexed = hardened.index(
        admin,
        {
            "text": "DCDC 输出纹波在额定负载下应不大于 30mVpp。",
            "title": "Ripple",
            "logical_document_id": "ldoc_secure",
            "version_label": "v1",
        },
    )
    assert indexed["schema_version"] == 8
    assert len(hardened.documents(admin)["documents"]) == 1
    assert hardened.documents(reader)["documents"] == []

    queued = hardened.enqueue_index(
        admin,
        {
            "text": "输出纹波测试方法应使用示波器测量。",
            "title": "Ripple test",
            "logical_document_id": "ldoc_job",
        },
    )
    assert queued["status"] == "queued"
    completed = hardened.run_worker_once(admin, worker_id="test-worker")
    assert completed["job"]["status"] == "succeeded"

    backup = hardened.backup(admin)
    backup_path = Path(str(backup["path"]))
    assert backup_path.exists()
    assert SQLiteBackupManager.verify(backup_path)

    purge = hardened.purge(admin, "ldoc_secure")
    assert purge["deleted_rows"]["documents"] == 1
    remaining = {item["logical_document_id"] for item in hardened.documents(admin)["documents"]}
    assert "ldoc_secure" not in remaining
    assert "ldoc_job" in remaining

    audit = hardened.audit_events(admin)
    assert audit["events"]
    metrics = hardened.metrics_snapshot(admin)
    assert metrics["counters"]["documents_index_requests_total"] >= 1


def test_job_queue_graph_evaluation_openapi_and_mcp(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite3"
    with SQLiteKnowledgeStore(db) as store:
        queue = SQLiteJobQueue(store.connection)
        job = queue.submit("echo", {"value": 7}, tenant_id="default")
        finished = queue.run_once("worker-1", {"echo": lambda payload: {"value": payload["value"]}})
        assert finished is not None
        assert finished.job_id == job.job_id
        assert finished.status == "succeeded"
        assert finished.result == {"value": 7}

    predicted = [
        GraphEdge(
            edge_id="edge_1",
            domain="generic",
            relation_type="related_to",
            source_object_id="A",
            target_object_id="B",
            confidence=1.0,
        )
    ]
    report = evaluate_graph_edges(
        predicted,
        [GraphGoldenEdge(relation_type="related_to", source_object_id="B", target_object_id="A")],
    )
    assert report.precision == 1.0
    assert report.recall == 1.0
    assert report.f1 == 1.0

    spec = build_openapi_spec()
    assert spec["openapi"] == "3.1.0"
    assert "/v1/query" in spec["paths"]

    service = AgentKBService(db_path=tmp_path / "mcp.sqlite3")
    adapter = AgentKBMCPAdapter(service)
    names = {tool["name"] for tool in adapter.list_tools()}
    assert "agent_kb_query" in names
    assert adapter.call_tool("agent_kb_health", {})["schema_version"] == 8
