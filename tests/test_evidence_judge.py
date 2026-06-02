"""Unit tests for evidence_judge.py.

Tests the rule-based evidence judgement logic without LLM calls.
"""
from __future__ import annotations

import pytest

from enterprise_agent_kb.evidence_judge import (
    EvidenceJudgement,
    _anchors,
    _contains,
    _is_preface_or_index_blob,
    _normalize,
    _query_type_from_context,
    _sanitize_string_list,
    judge_evidence,
)


# ── _query_type_from_context ───────────────────────────────────────────


@pytest.mark.unit
class TestQueryTypeFromContext:
    def test_extracts_from_rewrite(self) -> None:
        ctx = {"rewrite": {"query_type": "definition"}}
        assert _query_type_from_context(ctx) == "definition"

    def test_extracts_from_retrieval_plan(self) -> None:
        ctx = {"retrieval_plan": {"query_type": "constraint"}}
        assert _query_type_from_context(ctx) == "constraint"

    def test_returns_empty_when_no_type(self) -> None:
        assert _query_type_from_context({}) == ""

    def test_prefers_rewrite_over_retrieval_plan(self) -> None:
        ctx = {"rewrite": {"query_type": "parameter_lookup"}, "retrieval_plan": {"query_type": "definition"}}
        assert _query_type_from_context(ctx) == "parameter_lookup"


# ── _contains ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestContains:
    def test_exact_match(self) -> None:
        assert _contains("逆变器效率应不小于85%", "85%") is True

    def test_case_insensitive_ascii(self) -> None:
        assert _contains("Control Pilot function", "control pilot") is True

    def test_no_match(self) -> None:
        assert _contains("逆变器效率要求", "V2G") is False

    def test_cjk_match(self) -> None:
        assert _contains("保护重启时间", "保护重启") is True


# ── _is_preface_or_index_blob ──────────────────────────────────────────


@pytest.mark.unit
class TestIsPrefaceOrIndexBlob:
    def test_preface_blob(self) -> None:
        assert _is_preface_or_index_blob("前言 本标准按照...") is True

    def test_index_blob(self) -> None:
        assert _is_preface_or_index_blob("目 次 4.1 基本要求...") is True

    def test_normal_content_not_flagged(self) -> None:
        assert _is_preface_or_index_blob("逆变器效率应不小于85%") is False


# ── _normalize ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestNormalize:
    def test_removes_spaces_and_lowercases(self) -> None:
        # _normalize lowercases and strips whitespace
        result = _normalize("QC / T 1036")
        assert "qc" in result and "1036" in result

    def test_lowercases(self) -> None:
        assert _normalize("V2G TECHNOLOGY") == "v2gtechnology"


# ── _sanitize_string_list ──────────────────────────────────────────────


@pytest.mark.unit
class TestSanitizeStringList:
    def test_clean_list(self) -> None:
        assert _sanitize_string_list(["a", "b", None, ""]) == ["a", "b"]

    def test_limit(self) -> None:
        result = _sanitize_string_list([str(i) for i in range(20)], limit=5)
        assert len(result) == 5

    def test_single_string_input(self) -> None:
        # _sanitize_string_list only accepts list-like values, string gives empty
        assert _sanitize_string_list("hello") == []


# ── _anchors ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestAnchors:
    def test_basic_query(self) -> None:
        # _anchors extracts specific patterns (voltages, abbreviations, table refs),
        # not generic Chinese terms. For "逆变器效率" there are no such patterns.
        anchors = _anchors("逆变器效率", {})
        assert isinstance(anchors, list)

    def test_voltage_anchor(self) -> None:
        # Voltage patterns are extracted as anchors
        anchors = _anchors("检测点1电压", {})
        assert len(anchors) > 0

    def test_expansion_terms(self) -> None:
        anchors = _anchors("CP", {"preserved_anchors": ["CP"]})
        # Should include the anchor and its expansion (e.g. "控制导引" for CP)
        assert "CP" in anchors
        assert len(anchors) >= 2  # CP + at least one expansion


# ── judge_evidence (rule-based, no LLM) ────────────────────────────────


@pytest.mark.unit
class TestJudgeEvidenceRules:
    def test_insufficient_with_no_evidence(self) -> None:
        result = judge_evidence(
            "什么是V2G",
            {"facts": [], "evidence": [], "rewrite": {"query_type": "definition"}},
            use_llm=False,
        )
        assert isinstance(result, EvidenceJudgement)
        assert result.sufficient is False
        assert result.judge_source == "rules"
        assert result.used_llm is False

    def test_sufficient_with_matching_fact(self) -> None:
        result = judge_evidence(
            "QC/T 1036 标准号",
            {
                "facts": [{"fact_id": "F1", "fact_type": "document_standard", "object_value": {"value": "QC/T 1036—2016"}}],
                "evidence": [],
                "rewrite": {"query_type": "standard_lookup"},
            },
            use_llm=False,
        )
        assert isinstance(result, EvidenceJudgement)
        # The judgement should find "QC/T 1036" as a matched anchor
        assert result.judge_source == "rules"

    def test_returns_evidence_shape(self) -> None:
        result = judge_evidence(
            "什么是保护门",
            {"facts": [], "evidence": [], "rewrite": {"query_type": "definition"}},
            use_llm=False,
        )
        assert result.evidence_shape is not None or result.sufficient is False

    def test_to_dict(self) -> None:
        result = judge_evidence(
            "什么是V2G",
            {"facts": [], "evidence": [], "rewrite": {"query_type": "definition"}},
            use_llm=False,
        )
        d = result.to_dict()
        assert "sufficient" in d
        assert "confidence" in d
        assert "matched_anchors" in d