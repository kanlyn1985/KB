from __future__ import annotations

import pytest

from enterprise_agent_kb.query_rewrite import (
    _has_explicit_constraint_intent,
    _split_long_cjk_sentence_to_anchors,
    _strip_constraint_intent_suffix,
    rewrite_query,
)


def test_rewrite_definition_query() -> None:
    rewritten = rewrite_query("V2G是怎么定义的")
    assert rewritten.query_type == "definition"
    assert rewritten.normalized_query == "V2G"
    assert "V2G" in rewritten.must_terms


def test_rewrite_standard_lifecycle_query() -> None:
    rewritten = rewrite_query("QC/T 1036—2016 的实施日期是什么？")
    assert rewritten.query_type == "lifecycle_lookup"
    assert "QC/T1036—2016" in rewritten.must_terms


def test_rewrite_scope_query() -> None:
    rewritten = rewrite_query("本标准适用于什么范围？")
    assert rewritten.query_type == "scope"


def test_rewrite_constraint_query() -> None:
    rewritten = rewrite_query("逆变器必须满足哪些要求？")
    assert rewritten.query_type == "constraint"


def test_rewrite_generated_requirement_query_rule_first() -> None:
    rewritten = rewrite_query("UDS on IP services overview有哪些要求？")
    assert rewritten.query_type == "constraint"
    assert rewritten.semantic_quality_flags == ["rule_first_semantic_skip"]
    assert rewritten.normalized_query == "UDS on IP services overview"
    assert rewritten.target_topic == "UDS on IP services overview"
    assert "UDS on IP services overview" in rewritten.must_terms


def test_rewrite_generated_requirement_query_preserves_english_topic() -> None:
    rewritten = rewrite_query("Periodic data response message有哪些要求？")
    assert rewritten.query_type == "constraint"
    assert rewritten.normalized_query == "Periodic data response message"
    assert rewritten.must_terms == ["Periodic data response message"]


def test_rewrite_parameter_query() -> None:
    rewritten = rewrite_query("CC阻值有哪些")
    assert rewritten.query_type == "parameter_lookup"
    assert "CC" in rewritten.must_terms


# ── Unit tests for _has_explicit_constraint_intent ─────────────────────────


@pytest.mark.unit
class TestHasExplicitConstraintIntent:
    def test_protection_restart(self) -> None:
        assert _has_explicit_constraint_intent("逆变器保护重启时间") is True

    def test_protection_function(self) -> None:
        assert _has_explicit_constraint_intent("逆变器有哪些保护功能") is True

    def test_overvoltage_requirement(self) -> None:
        assert _has_explicit_constraint_intent("输入过压保护要求有哪些") is True

    def test_plain_parameter_no_match(self) -> None:
        assert _has_explicit_constraint_intent("逆变器额定输出电压") is False

    def test_definition_no_match(self) -> None:
        assert _has_explicit_constraint_intent("什么是保护门") is False


# ── Unit tests for _strip_constraint_intent_suffix ─────────────────────────


@pytest.mark.unit
class TestStripConstraintIntentSuffix:
    def test_function_with_requirement_suffix(self) -> None:
        assert _strip_constraint_intent_suffix("逆变器保护功能有哪些要求") == "逆变器保护"

    def test_function_with_you_na_xie(self) -> None:
        assert _strip_constraint_intent_suffix("逆变器保护功能有哪些") == "逆变器保护"

    def test_you_na_xie_y_pattern(self) -> None:
        assert _strip_constraint_intent_suffix("逆变器有哪些保护功能") == "保护功能"

    def test_simple_requirement_suffix(self) -> None:
        assert _strip_constraint_intent_suffix("输入过压保护要求") == "输入过压保护"

    def test_efficiency_requirement(self) -> None:
        assert _strip_constraint_intent_suffix("逆变器效率要求") == "逆变器效率"

    def test_no_intent_suffix(self) -> None:
        assert _strip_constraint_intent_suffix("QC/T 1036 标准号") == "QC/T 1036 标准号"

    def test_only_intent_markers(self) -> None:
        assert _strip_constraint_intent_suffix("有哪些要求") == ""

    def test_single_intent_marker(self) -> None:
        assert _strip_constraint_intent_suffix("要求") == ""

    def test_intent_word_as_object_part_falls_through(self) -> None:
        # "要求" as object_part is an intent word, so falls through to iterative strip
        assert _strip_constraint_intent_suffix("逆变器有哪些要求") == "逆变器"

    def test_protection_restart_strips_time_suffix(self) -> None:
        # "时间" is stripped as an intent suffix for constraint queries
        assert _strip_constraint_intent_suffix("逆变器保护重启时间") == "逆变器保护重启"

    def test_protection_restart_strips_duration_suffix(self) -> None:
        # "时长" is also stripped as an intent suffix
        assert _strip_constraint_intent_suffix("逆变器保护重启时长") == "逆变器保护重启"


# ---------------------------------------------------------------------------
# Sprint 3 WP3: long-sentence anchor splitting
# ---------------------------------------------------------------------------

def test_split_long_cjk_sentence_temperature_range() -> None:
    anchors = _split_long_cjk_sentence_to_anchors("室外使用的供电设备正常工作的温度范围")
    assert "温度范围" in anchors
    assert "供电设备" in anchors
    assert "室外使用" in anchors


def test_split_long_cjk_sentence_humidity() -> None:
    anchors = _split_long_cjk_sentence_to_anchors("室内设备在最高温度为+40℃时，其相对湿度")
    assert "相对湿度" in anchors
    assert "最高温度" in anchors


def test_split_short_query_returns_empty() -> None:
    # Short queries and Latin queries are unaffected
    assert _split_long_cjk_sentence_to_anchors("V2G") == []
    assert _split_long_cjk_sentence_to_anchors("温度") == []


def test_split_spaced_query_returns_empty() -> None:
    # Queries with spaces are not long no-space CJK sentences
    assert _split_long_cjk_sentence_to_anchors("control pilot circuit 定义") == []


def test_rewrite_scope_query_gets_anchor_should_terms() -> None:
    # A scope query with a long-sentence must_term should now get should_terms
    # anchors (was empty before the split fix).
    rw = rewrite_query("室外使用的供电设备正常工作的温度范围")
    assert "温度范围" in rw.should_terms
    assert "供电设备" in rw.should_terms
