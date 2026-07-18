from pathlib import Path

from agent_kb.domains.loader import load_domain_pack
from agent_kb.embeddings import HashEmbeddingProvider, cosine_similarity
from agent_kb.evaluation import evaluate_feedback
from agent_kb.graph import GraphEdge, SQLiteGraphStore
from agent_kb.pipeline import (
    add_persistent_feedback,
    compile_text_to_production_store,
    list_production_documents,
    query_production_store,
)
from agent_kb.query.understanding import understand_query
from agent_kb.retrieval.vector import SQLiteVectorIndex
from agent_kb.service import AgentKBService
from agent_kb.storage import DocumentLifecycleStore, SchemaMigrator, SQLiteKnowledgeStore


ROOT = Path(__file__).resolve().parents[1]


def test_hash_embedding_provider_is_deterministic() -> None:
    provider = HashEmbeddingProvider(dimensions=64)
    first, second, unrelated = provider.embed(["输出纹波", "输出纹波", "测试流程"])

    assert first == second
    assert len(first) == 64
    assert cosine_similarity(first, second) == 1.0
    assert cosine_similarity(first, unrelated) < 1.0


def test_phase6_migrations_lifecycle_vector_and_graph(tmp_path: Path) -> None:
    db = tmp_path / "phase6.sqlite3"
    pack = load_domain_pack(ROOT / "domains" / "obc_dcdc")
    result = compile_text_to_production_store(
        "DCDC 输出纹波在额定负载下应不大于 30mVpp。",
        title="Ripple requirement",
        db_path=db,
        domain_pack=pack,
        logical_document_id="ldoc_ripple",
        version_label="v1",
    )

    assert result.schema_version == 3
    assert result.vector_summary.vector_count > 0
    assert result.document_version.logical_document_id == "ldoc_ripple"

    with SQLiteKnowledgeStore(db) as store:
        assert SchemaMigrator(store.connection).current_version() == 3
        assert SQLiteVectorIndex(store.connection).summary().vector_count > 0
        graph = SQLiteGraphStore(store.connection)
        graph.upsert_relations(
            [
                GraphEdge(
                    edge_id="edge_test",
                    domain="obc_dcdc",
                    relation_type="verified_by",
                    source_object_id="DCDC_OUTPUT_RIPPLE",
                    target_object_id="DCDC_RIPPLE_TEST_METHOD",
                    confidence=0.9,
                    status="verified",
                )
            ]
        )
        frame = understand_query("输出纹波怎么测试？", domain_pack=pack)
        candidates = graph.search(frame, limit=5)
        assert any(item.source_id == "DCDC_RIPPLE_TEST_METHOD" for item in candidates)

        lifecycle = DocumentLifecycleStore(store.connection)
        record = lifecycle.get("ldoc_ripple")
        assert record is not None
        assert record.active_version_id == result.document_version.version_id


def test_production_pipeline_versions_query_feedback_and_service(tmp_path: Path) -> None:
    db = tmp_path / "runtime.sqlite3"
    pack = load_domain_pack(ROOT / "domains" / "obc_dcdc")

    first = compile_text_to_production_store(
        "DCDC 输出纹波在额定负载下应不大于 30mVpp。",
        title="Ripple requirements",
        db_path=db,
        domain_pack=pack,
        source_uri="requirements/ripple.txt",
        logical_document_id="ldoc_ripple",
        version_label="v1",
    )
    second = compile_text_to_production_store(
        "DCDC 输出纹波在额定负载下应不大于 25mVpp。",
        title="Ripple requirements",
        db_path=db,
        domain_pack=pack,
        source_uri="requirements/ripple.txt",
        logical_document_id="ldoc_ripple",
        version_label="v2",
    )

    documents = list_production_documents(db)
    assert len(documents) == 1
    assert len(documents[0].versions) == 2
    assert documents[0].active_version_id == second.document_version.version_id
    assert documents[0].active_version_id != first.document_version.version_id

    query = query_production_store(
        "输出纹波要求是多少？",
        db_path=db,
        domain_pack=pack,
    )
    assert query.retrieval_result.candidates
    assert query.context_pack.evidence
    assert query.schema_version == 3

    add_persistent_feedback(
        db_path=db,
        run_id=query.run_id,
        rating=1,
        comment="relevant",
        metadata={"reason": "correct_object"},
    )
    report = evaluate_feedback(db)
    assert report.feedback_count == 1
    assert report.positive_rate == 1.0

    service = AgentKBService(db_path=db, domain_pack=pack)
    health = service.health()
    assert health.status == "ok"
    assert health.schema_version == 3
    response = service.query({"query": "LV ripple limit?", "top_k": 5})
    assert response["retrieval_result"]["candidates"]
