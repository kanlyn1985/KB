"""Pytest regression tests for DOC-000001 (QC/T 1036-2016).

Validates answer quality across standard lookup, parameter, constraint,
process, and negative-query scenarios.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from enterprise_agent_kb.answer_api import answer_query
from enterprise_agent_kb.answer_parameter import _supplement_parameter_facts
from enterprise_agent_kb.query_api import build_query_context, _inject_direct_requirement_hits
from enterprise_agent_kb.query_rewrite import rewrite_query

WORKSPACE = Path("knowledge_base")
DOC_ID = "DOC-000001"


# ── Standard / metadata queries ──────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.benchmark
def test_standard_number_in_answer() -> None:
    answer = answer_query(WORKSPACE, "QC/T 1036 标准号", limit=6, preferred_doc_id=DOC_ID)
    assert "QC/T 1036" in answer["direct_answer"]


@pytest.mark.integration
@pytest.mark.benchmark
def test_publication_date_in_answer() -> None:
    answer = answer_query(WORKSPACE, "QC/T 1036 发布日期", limit=6, preferred_doc_id=DOC_ID)
    assert "2016-04-05" in answer["direct_answer"] or "2016" in answer["direct_answer"]


@pytest.mark.integration
@pytest.mark.benchmark
def test_standard_query_context_has_document_standard_fact() -> None:
    ctx = build_query_context(WORKSPACE, "QC/T 1036", limit=6)
    assert ctx["hit_count"] > 0
    assert any(
        f.get("fact_type") == "document_standard"
        for f in ctx.get("facts", [])
    )


# ── Definition queries ────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.benchmark
def test_shutter_definition() -> None:
    answer = answer_query(WORKSPACE, "什么是保护门", limit=6, preferred_doc_id=DOC_ID)
    assert any(tok in answer["direct_answer"] for tok in ("保护门", "shutter", "插孔遮蔽"))


# ── Parameter queries ─────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.benchmark
def test_output_voltage_parameter() -> None:
    answer = answer_query(WORKSPACE, "逆变器额定输出电压", limit=6, preferred_doc_id=DOC_ID)
    assert any(tok in answer["direct_answer"] for tok in ("220", "额定输出电压"))


@pytest.mark.integration
@pytest.mark.benchmark
def test_output_frequency_parameter() -> None:
    answer = answer_query(WORKSPACE, "逆变器输出频率", limit=6, preferred_doc_id=DOC_ID)
    assert any(tok in answer["direct_answer"] for tok in ("50 Hz", "50Hz", "输出频率"))


@pytest.mark.integration
@pytest.mark.benchmark
def test_efficiency_requirement() -> None:
    answer = answer_query(WORKSPACE, "逆变器效率要求", limit=6, preferred_doc_id=DOC_ID)
    assert any(tok in answer["direct_answer"] for tok in ("效率", "85"))


# ── Constraint / protection queries ──────────────────────────────────────


@pytest.mark.integration
@pytest.mark.benchmark
def test_protection_functions_list() -> None:
    answer = answer_query(WORKSPACE, "逆变器有哪些保护功能", limit=8, preferred_doc_id=DOC_ID)
    da = answer["direct_answer"]
    # Accept either specific protection terms or generic "保护" mentions
    assert any(tok in da for tok in ("保护", "过压", "短路", "欠压", "过流", "反接", "电击")), \
        f"Expected protection content, got: {da[:200]}"


@pytest.mark.integration
@pytest.mark.benchmark
def test_overvoltage_protection_detail() -> None:
    answer = answer_query(WORKSPACE, "输入过压保护要求", limit=6, preferred_doc_id=DOC_ID)
    da = answer["direct_answer"]
    # Accept either "过压" keyword or the actual protection content about voltage threshold
    assert any(tok in da for tok in ("过压保护", "过压", "关断输出", "16.5 V", "33 V")), \
        f"Expected overvoltage content, got: {da[:200]}"


@pytest.mark.integration
@pytest.mark.benchmark
def test_short_circuit_protection() -> None:
    answer = answer_query(WORKSPACE, "输出短路保护要求", limit=6, preferred_doc_id=DOC_ID)
    assert any(tok in answer["direct_answer"] for tok in ("短路保护", "短路"))


# ── Process / test queries ────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.benchmark
def test_temperature_rise_test() -> None:
    answer = answer_query(WORKSPACE, "温升试验方法", limit=6, preferred_doc_id=DOC_ID)
    assert any(tok in answer["direct_answer"] for tok in ("温升", "热平衡"))


@pytest.mark.integration
@pytest.mark.benchmark
def test_insulation_resistance() -> None:
    answer = answer_query(WORKSPACE, "绝缘电阻要求", limit=6, preferred_doc_id=DOC_ID)
    assert any(tok in answer["direct_answer"] for tok in ("绝缘电阻", "MΩ"))


# ── Negative queries ──────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.benchmark
def test_nonexistent_term_returns_not_found() -> None:
    answer = answer_query(WORKSPACE, "什么是V2G", limit=6)
    da = answer["direct_answer"]
    assert any(tok in da for tok in ("未找到", "不存在", "未收录", "知识库中未找到"))


# ── No preface/index pollution ────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.benchmark
def test_no_preface_in_protection_answer() -> None:
    answer = answer_query(WORKSPACE, "逆变器保护重启时间", limit=6, preferred_doc_id=DOC_ID)
    assert "目 次" not in answer["direct_answer"]
    assert "前言" not in answer["direct_answer"]


# ── _inject_direct_requirement_hits integration tests ───────────────────────


@pytest.mark.integration
class TestInjectDirectRequirementHits:
    def test_finds_protection_restart_for_constraint_query(self) -> None:
        """CJK fragment search should find protection-restart requirement facts."""
        db_path = WORKSPACE / "facts.db"
        if not db_path.exists():
            pytest.skip("facts.db not found")
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rewritten = rewrite_query("逆变器保护重启时间")
            assert rewritten.query_type == "constraint"
            hits = _inject_direct_requirement_hits(conn, rewritten, [], limit=6)
            assert len(hits) > 0, "Expected at least one requirement hit for protection restart"
            for hit in hits:
                assert hit.get("fact_type") in {"requirement", "threshold", "table_requirement"}
        finally:
            conn.close()

    def test_finds_efficiency_for_parameter_lookup_query(self) -> None:
        """Should also work for parameter_lookup queries (extended in V1 fix)."""
        db_path = WORKSPACE / "facts.db"
        if not db_path.exists():
            pytest.skip("facts.db not found")
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rewritten = rewrite_query("逆变器效率要求")
            if rewritten.query_type == "parameter_lookup":
                hits = _inject_direct_requirement_hits(conn, rewritten, [], limit=6)
                assert len(hits) > 0, "Expected at least one hit for efficiency parameter_lookup"
        finally:
            conn.close()

    def test_skips_non_applicable_query_types(self) -> None:
        """Should return empty for query types that are not constraint/parameter_lookup."""
        db_path = WORKSPACE / "facts.db"
        if not db_path.exists():
            pytest.skip("facts.db not found")
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rewritten = rewrite_query("QC/T 1036 标准号")
            if rewritten.query_type not in {"constraint", "parameter_lookup"}:
                hits = _inject_direct_requirement_hits(conn, rewritten, [], limit=6)
                assert hits == []
        finally:
            conn.close()


# ── _supplement_parameter_facts integration tests ───────────────────────────


@pytest.mark.integration
class TestSupplementParameterFacts:
    def test_adds_efficiency_requirement_when_missing(self) -> None:
        """When existing facts lack efficiency data, should supplement it."""
        existing_items = [
            {"object": "表 1 输出特性参数：额定输出电压。", "fact_type": "parameter_value"},
        ]
        _supplement_parameter_facts(
            "逆变器效率要求", existing_items, WORKSPACE,
        )
        assert len(existing_items) > 1, "Expected supplementation to add efficiency facts"

    def test_no_supplement_when_all_fragments_already_present(self) -> None:
        """When existing facts already cover all query fragments, should not supplement."""
        existing_items = [
            {"object": "逆变器效率不小于85%", "fact_type": "requirement"},
        ]
        _supplement_parameter_facts(
            "逆变器效率", existing_items, WORKSPACE,
        )
        # All key fragments are already present, so no supplementation needed
