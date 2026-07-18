from pathlib import Path

from agent_kb.context import AgentContextPack, judge_context_pack
from agent_kb.domains.loader import load_domain_pack
from agent_kb.pipeline import (
    add_persistent_feedback,
    compile_text_to_store,
    query_persistent_store,
)
from agent_kb.query.understanding import understand_query
from agent_kb.storage import SQLiteKnowledgeStore


ROOT = Path(__file__).resolve().parents[1]


def test_sqlite_round_trip_hybrid_query_and_feedback(tmp_path: Path) -> None:
    pack = load_domain_pack(ROOT / "domains" / "obc_dcdc")
    db_path = tmp_path / "agent-kb.sqlite3"
    text = (
        "DCDC 输出纹波在额定负载下应不大于 30mVpp。\n\n"
        "输出纹波测试方法应使用示波器在低压输出端测量。"
    )

    index, store_summary = compile_text_to_store(
        text,
        title="DCDC persistent sample",
        db_path=db_path,
        domain_pack=pack,
        max_evidence_chars=120,
    )

    assert db_path.exists()
    assert index.summary["facts"] >= 1
    assert store_summary["retrieval_cards"] >= 1
    assert store_summary["facts"] >= 1
    assert store_summary["evidence"] >= 1

    result = query_persistent_store(
        "输出纹波要求是多少？",
        db_path=db_path,
        domain_pack=pack,
        retrieval_top_k=12,
    )

    assert result.query_frame.target_objects[0].object_id == "DCDC_OUTPUT_RIPPLE"
    assert "DCDC_OUTPUT_RIPPLE" in result.retrieval_result.selected_object_ids
    assert any(card.object_id == "DCDC_OUTPUT_RIPPLE" for card in result.context_pack.retrieval_cards)
    assert any(fact.subject == "DCDC_OUTPUT_RIPPLE" for fact in result.context_pack.facts)
    assert result.context_pack.evidence
    assert result.evidence_judgement.status in {"partial", "sufficient"}
    assert result.run_id.startswith("run_")

    feedback_id = add_persistent_feedback(
        db_path=db_path,
        run_id=result.run_id,
        rating=1,
        comment="retrieval is relevant",
    )
    assert feedback_id.startswith("fb_")

    with SQLiteKnowledgeStore(db_path) as store:
        persisted_run = store.get_run(result.run_id)
        assert persisted_run is not None
        assert persisted_run["query"] == "输出纹波要求是多少？"
        assert store.summary()["feedback"] == 1


def test_persistent_search_returns_domain_linked_candidates(tmp_path: Path) -> None:
    pack = load_domain_pack(ROOT / "domains" / "obc_dcdc")
    db_path = tmp_path / "search.sqlite3"
    compile_text_to_store(
        "LV ripple shall not exceed 30mVpp under rated load.",
        title="English ripple requirement",
        db_path=db_path,
        domain_pack=pack,
    )
    frame = understand_query("LV ripple limit?", domain_pack=pack)

    with SQLiteKnowledgeStore(db_path) as store:
        candidates = store.search(frame, limit=20)
        view = store.load_index_view()

    assert view.retrieval_cards
    assert view.context_facts
    assert candidates
    assert any(
        candidate.payload.get("object_id") == "DCDC_OUTPUT_RIPPLE"
        or candidate.payload.get("subject") == "DCDC_OUTPUT_RIPPLE"
        for candidate in candidates
    )


def test_evidence_judge_marks_empty_context_insufficient() -> None:
    pack = load_domain_pack(ROOT / "domains" / "obc_dcdc")
    frame = understand_query("输出纹波要求是多少？", domain_pack=pack)
    judgement = judge_context_pack(AgentContextPack(query_frame=frame))

    assert judgement.status == "insufficient"
    assert judgement.score < 0.4
    assert judgement.missing_shapes
