"""Unit tests for the Phase 1 evaluator.

Covers:
  - Token overlap scoring (CJK, English, mixed, edge cases)
  - Substantive filter (noise detection)
  - Question generation (term_def, explain, requirement, param_lookup)
  - Hybrid scoring (LLM + token-overlap fallback)
  - Edge cases (empty inputs, very long inputs, CJK ranges, alphanumeric prefixes)
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from enterprise_agent_kb.evaluation.evaluator import (
    COVERAGE_THRESHOLD,
    EvalResult,
    ScoreResult,
    _extract_tokens,
    _generate_questions_for_point,
    _is_degraded_answer,
    _is_noise_expected_point,
    _is_substantive,
    _load_questions,
    _parse_llm_coverage,
    _token_overlap_ratio,
    compute_coverage,
    merge_shard_results,
    score_answer,
    score_answer_hybrid,
    shard_result_from_dict,
)


# ---------------------------------------------------------------------------
# Token extraction and overlap
# ---------------------------------------------------------------------------

def test_extract_tokens_chinese_sentence() -> None:
    tokens = _extract_tokens("汽车电源逆变器")
    # The function should include the multi-char token "汽车电源逆变器"
    # (extracted as a 2-8 char CJK term) and/or individual chars.
    has_term = ("汽车电源逆变器" in tokens
                or "汽车电源" in tokens
                or "电源逆变" in tokens
                or ("汽" in tokens and "车" in tokens))
    assert has_term, f"Expected some token for 汽车电源逆变器, got {tokens}"
    # Stopwords should be filtered
    assert "的" not in tokens


def test_extract_tokens_filters_stopwords() -> None:
    tokens = _extract_tokens("这是关于测试的句子")
    assert "的" not in tokens
    assert "是" not in tokens
    # Real content tokens preserved
    assert "测试" in tokens or "句" in tokens or "子" in tokens


def test_extract_tokens_handles_mixed_alphanumeric() -> None:
    tokens = _extract_tokens("DC60V circuit breaker")
    # "60V" is captured as a number+unit token
    assert "60V" in tokens
    # Letters from "circuit"/"breaker" are preserved as individual chars
    # (CJK-friendly tokenizer splits on word boundaries)
    assert "c" in tokens
    assert "i" in tokens
    # Stop words and short tokens filtered? Check that meaningful content
    # is present
    assert len(tokens) > 0


def test_token_overlap_full_match() -> None:
    ratio = _token_overlap_ratio("汽车电源逆变器", "汽车电源逆变器")
    assert ratio == pytest.approx(1.0, abs=0.01)


def test_token_overlap_no_match() -> None:
    ratio = _token_overlap_ratio("汽车", "飞机")
    assert ratio == 0.0


def test_token_overlap_partial_match() -> None:
    # Half the tokens match
    ratio = _token_overlap_ratio("汽车电源", "汽车飞机")
    assert 0.0 < ratio < 1.0


def test_token_overlap_empty_point() -> None:
    # Empty point_text returns 0
    assert _token_overlap_ratio("任何答案", "") == 0.0


def test_token_overlap_paraphrase() -> None:
    # Paraphrased answer (different words, same meaning) should still score
    ratio = _token_overlap_ratio("汽车电源逆变器把直流变为交流", "汽车电源逆变器")
    assert ratio > 0.3


# ---------------------------------------------------------------------------
# Substantive filter
# ---------------------------------------------------------------------------

def test_is_substantive_normal() -> None:
    assert _is_substantive({"point": "汽车电源逆变器是一种变流器。"}) is True


def test_is_substantive_filters_intro() -> None:
    assert _is_substantive({"point": "本标准规定了汽车电源逆变器的术语和定义。"}) is False
    assert _is_substantive({"point": "下列文件对于本标准的应用是必不可少的。"}) is False
    assert _is_substantive({"point": "GB/T 1036—2016 规定了某种要求。"}) is False


def test_is_substantive_filters_toc() -> None:
    # Pure TOC line (many dots)
    assert _is_substantive({"point": "1............................................."}) is False
    assert _is_substantive({"point": "3.1 术语 .................. 1"}) is False


def test_is_substantive_filters_empty() -> None:
    assert _is_substantive({"point": ""}) is False
    assert _is_substantive({"point": "   "}) is False


def test_is_substantive_filters_short() -> None:
    # Too short
    assert _is_substantive({"point": "标准"}) is False


def test_is_substantive_filters_html() -> None:
    assert _is_substantive({"point": "<div>html only</div>"}) is False


# ---------------------------------------------------------------------------
# Sprint 3 P3: noise expected-point detection + degradation-answer guard
# ---------------------------------------------------------------------------

def test_is_noise_expected_point_flags_cover_metadata() -> None:
    assert _is_noise_expected_point(
        "PUBLICPUBLIC\n过程参考模型\n版本 4.0\n标题:\nAutomotive SPICE 作者: VDA"
    ) is True


def test_is_noise_expected_point_flags_page_header() -> None:
    assert _is_noise_expected_point("1/148\nCCU 软件功能开发需求规格书") is True


def test_is_noise_expected_point_flags_sc_table_row() -> None:
    assert _is_noise_expected_point(
        "7.4.3.1 SC44047 FSR07 V1 DCDC 温度检测\n编号:SC44047"
    ) is True


def test_is_noise_expected_point_flags_english_descriptor() -> None:
    assert _is_noise_expected_point(
        "The Systems Engineering process group includes the subsystem SYS.4"
    ) is True


def test_is_noise_expected_point_keeps_real_paragraph() -> None:
    # Real V2G paragraph (DOC-000013) must NOT be flagged as noise.
    assert _is_noise_expected_point(
        "山博轩和杨郁构建了一套“2+1”的源网荷储交直流绿色微能源网，光伏发电累计85万千瓦时。"
    ) is False


def test_generate_questions_skips_noise_generic_hint() -> None:
    # A noise point (cover metadata) must yield no question at all, not a
    # meaningless 'explain'/'generic_hint' question. The noise check runs at
    # the top of _generate_questions_for_point, before any pattern match.
    p = {"point": "PUBLICPUBLIC\n过程参考模型\n版本 4.0\n标题:\nAutomotive SPICE 作者: VDA", "section": "1", "page": 1}
    assert _generate_questions_for_point(p) == []
    # SC-code table row also skipped
    p2 = {"point": "7.4.3.1 SC44047 FSR07 V1 DCDC 温度检测\n编号:SC44047 版本:V1", "section": "7", "page": 1}
    assert _generate_questions_for_point(p2) == []


def test_is_degraded_answer_flags_refusal() -> None:
    assert _is_degraded_answer("当前候选证据不足以给出确定性答案。期望证据形状：term_definition。") is True
    assert _is_degraded_answer("知识库中未找到与该查询相关的信息。") is True


def test_is_degraded_answer_keeps_real_answer() -> None:
    # Short but real Chinese answers must NOT be flagged as degraded.
    assert _is_degraded_answer("汽车电源逆变器") is False
    assert _is_degraded_answer("控制导引电路 control pilot circuit: 设计用于信号传输。") is False


def test_score_answer_degradation_forces_zero_coverage() -> None:
    # A degradation answer that shares tokens with the expected point must
    # score 0.0 (not a false high overlap from shared process/definition tokens).
    result = score_answer(
        "Q",
        "当前候选证据不足以给出确定性答案。期望证据形状：term_definition、parameter_definition、process_activity。",
        [{"point": "The Systems Engineering process group includes process activity definitions."}],
    )
    assert result.coverage == 0.0
    assert result.pass_ is False



# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------

def test_generate_questions_term_definition() -> None:
    p = {"point": "**汽车电源逆变器  automotive DC-AC Power Inverter**\n一种把汽车直流电转化为交流电的变流器。"}
    qs = _generate_questions_for_point(p)
    assert len(qs) >= 1
    # First variant should be a term_def-style question
    question, template = qs[0]
    assert "term_def" in template
    assert "汽车电源逆变器" in question


def test_generate_questions_requirement_with_应() -> None:
    p = {"point": "当输入电压为额定值时，逆变器效率应不小于85%。"}
    qs = _generate_questions_for_point(p)
    assert len(qs) >= 1
    question, template = qs[0]
    assert "requirement" in template or "requirement_noun" in template
    assert "逆变器效率" in question


def test_generate_questions_param_with_unit() -> None:
    p = {"point": "当输入电压为额定值时，逆变器效率应不小于85%。"}
    qs = _generate_questions_for_point(p)
    # Should generate either a requirement or param_lookup question
    assert len(qs) >= 1
    assert any("template" in q[1] or "param" in q[1] or "requirement" in q[1] for q in qs)


def test_generate_questions_range_skipped() -> None:
    # CJK range like "-25℃～+40℃" should NOT trigger param_lookup
    p = {"point": "室外使用的供电设备正常工作的温度范围为-25℃～+40℃。"}
    qs = _generate_questions_for_point(p)
    # Should not produce a "的℃值是多少?" question
    for q, t in qs:
        assert "的℃值是多少" not in q, f"Should not generate range param_lookup: {q}"


def test_generate_questions_alphanumeric_prefix() -> None:
    # DC60V should NOT trigger param_lookup (alphanumeric prefix)
    p = {"point": "触器K1、K2内侧电压降到DC60V 以下时。"}
    qs = _generate_questions_for_point(p)
    for q, t in qs:
        # Should not be "的V值是多少?" (wrong number extracted from DC60V)
        assert "的V值是多少" not in q


def test_generate_questions_short_subject() -> None:
    # Subject should be at least 6 chars after cleanup
    p = {"point": "A.1.1.8 空载损耗：逆变器空载损耗应不大于3%或50W。"}
    qs = _generate_questions_for_point(p)
    assert len(qs) >= 1


def test_generate_questions_dedup() -> None:
    # If two templates produce same question text, only one is returned
    p = {"point": "汽车电源逆变器是一种把汽车直流电转化为交流电的变流器。"}
    qs = _generate_questions_for_point(p)
    texts = [q for q, _ in qs]
    assert len(texts) == len(set(texts))


def test_generate_questions_explain_template() -> None:
    # No term_def, no "应", but has a value/range → explain template
    p = {"point": "室外使用的供电设备正常工作的温度范围为-25℃～+40℃。"}
    qs = _generate_questions_for_point(p)
    assert len(qs) >= 1
    # Should not be a "请解释: <full sentence>" query
    for q, t in qs:
        assert not (q.startswith("请解释:") and len(q) > 30), \
            f"Explain template should extract a short subject, not full sentence: {q}"


# ---------------------------------------------------------------------------
# Score answer
# ---------------------------------------------------------------------------

def test_score_answer_empty_expected() -> None:
    result = score_answer("Q", "any answer", [])
    assert result.coverage == 0.0
    assert result.pass_ is False


def test_score_answer_pass() -> None:
    expected = [{"point": "汽车电源逆变器把直流变为交流"}]
    result = score_answer("Q", "汽车电源逆变器把直流变为交流", expected)
    assert result.coverage >= COVERAGE_THRESHOLD
    assert result.pass_ is True


def test_score_answer_fail() -> None:
    expected = [{"point": "汽车电源逆变器"}]
    result = score_answer("Q", "飞机起飞", expected)
    assert result.coverage < COVERAGE_THRESHOLD
    assert result.pass_ is False


def test_score_answer_multi_point_average() -> None:
    expected = [
        {"point": "汽车电源逆变器"},
        {"point": "逆变器是变流器"},
    ]
    # Answer matches one out of two
    result = score_answer("Q", "汽车电源逆变器", expected)
    assert 0.0 < result.coverage < 1.0


# ---------------------------------------------------------------------------
# Compute coverage
# ---------------------------------------------------------------------------

def test_compute_coverage_consistent_with_score() -> None:
    expected = [{"point": "汽车电源逆变器"}]
    coverage = compute_coverage("Q", "汽车电源逆变器", expected)
    score_cov = score_answer("Q", "汽车电源逆变器", expected).coverage
    assert coverage == pytest.approx(score_cov, abs=0.01)


def test_compute_coverage_empty() -> None:
    assert compute_coverage("Q", "answer", []) == 0.0


# ---------------------------------------------------------------------------
# LLM scoring parser
# ---------------------------------------------------------------------------

def test_parse_llm_coverage_valid() -> None:
    text = '{"coverage": 0.7, "reason": "partial match"}'
    assert _parse_llm_coverage(text) == 0.7


def test_parse_llm_coverage_in_markdown() -> None:
    text = 'Some preamble\n```json\n{"coverage": 0.5, "reason": "x"}\n```\nMore text'
    assert _parse_llm_coverage(text) == 0.5


def test_parse_llm_coverage_with_other_text() -> None:
    text = 'Here is my analysis:\n{"coverage": 0.3, "reason": "low"}\nThanks.'
    assert _parse_llm_coverage(text) == 0.3


def test_parse_llm_coverage_invalid() -> None:
    assert _parse_llm_coverage("") is None
    assert _parse_llm_coverage("no json here") is None
    assert _parse_llm_coverage('{"coverage": "abc"}') is None  # wrong type
    assert _parse_llm_coverage('{"coverage": 1.5}') is None  # out of range
    assert _parse_llm_coverage('{"coverage": -0.1}') is None  # out of range


# ---------------------------------------------------------------------------
# Hybrid scoring (with LLM mocked)
# ---------------------------------------------------------------------------

def test_hybrid_uses_llm_when_available() -> None:
    with patch(
        "enterprise_agent_kb.evaluation.evaluator._llm_score",
        return_value=0.8,
    ):
        result = score_answer_hybrid(
            "Q",
            "汽车电源逆变器把直流变为交流",
            [{"point": "汽车电源逆变器"}],
        )
        assert result.coverage == 0.8
        assert result.template_id == "llm"


def test_hybrid_falls_back_to_token_overlap() -> None:
    with patch(
        "enterprise_agent_kb.evaluation.evaluator._llm_score",
        return_value=None,
    ):
        result = score_answer_hybrid(
            "Q",
            "汽车电源逆变器",
            [{"point": "汽车电源逆变器"}],
        )
        # Token overlap should give near 1.0
        assert result.coverage > 0.8
        assert result.template_id == "token_overlap_fallback"


def test_hybrid_handles_empty_expected() -> None:
    result = score_answer_hybrid("Q", "any", [])
    assert result.coverage == 0.0
    assert result.pass_ is False


# ---------------------------------------------------------------------------
# Question loading
# ---------------------------------------------------------------------------

def test_load_questions_v1_golden() -> None:
    # Should load from expected_points table when sample_qa files are absent
    questions = _load_questions("v1", "golden")
    assert len(questions) > 0
    for q in questions:
        assert "doc_id" in q
        assert "question" in q
        assert "matched_points" in q


def test_load_questions_unknown_suite() -> None:
    questions = _load_questions("v1", "unknown_suite")
    # Should still return some questions (or empty if sample_qa missing)
    assert isinstance(questions, list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_coverage_threshold_is_reasonable() -> None:
    # Should be between 0.1 and 0.5 (lenient but not trivial)
    assert 0.1 <= COVERAGE_THRESHOLD <= 0.5


# ---------------------------------------------------------------------------
# EvalResult structure
# ---------------------------------------------------------------------------

def test_evalresult_to_dict() -> None:
    r = EvalResult(
        suite="golden", total=10, passed=5, pass_rate=0.5,
        avg_coverage=0.4, multi_prompt_stability=1.0,
    )
    d = r.to_dict()
    assert d["suite"] == "golden"
    assert d["total"] == 10
    assert d["passed"] == 5
    assert d["pass_rate"] == 0.5


# ---------------------------------------------------------------------------
# Sprint 3 WP8: sharded run merge
# ---------------------------------------------------------------------------

def _shard_score(idx: int, doc: str, cov: float, passed: bool) -> ScoreResult:
    return ScoreResult(
        question=f"q{idx}", doc_id=doc, system_answer=f"a{idx}",
        coverage=cov, pass_=passed, template_id="t",
        multi_prompt_stable=True,
        safety={"citation_correct": passed} if passed else {},
    )


def test_to_full_dict_includes_per_question() -> None:
    r = EvalResult(
        suite="golden", total=1, passed=1, pass_rate=1.0,
        avg_coverage=0.5, multi_prompt_stability=1.0,
        per_question=[_shard_score(1, "DOC-A", 0.5, True)],
    )
    d = r.to_full_dict()
    assert "per_question" in d
    assert len(d["per_question"]) == 1
    assert d["per_question"][0]["doc_id"] == "DOC-A"


def test_shard_result_roundtrip() -> None:
    r = EvalResult(
        suite="golden", total=2, passed=1, pass_rate=0.5,
        avg_coverage=0.3, multi_prompt_stability=1.0,
        per_question=[_shard_score(1, "DOC-A", 0.5, True),
                      _shard_score(2, "DOC-A", 0.1, False)],
    )
    back = shard_result_from_dict(r.to_full_dict())
    assert back.total == 2
    assert back.passed == 1
    assert len(back.per_question) == 2


def test_merge_shard_results_aggregates() -> None:
    s1 = EvalResult(
        suite="golden", total=2, passed=1, pass_rate=0.5,
        avg_coverage=0.3, multi_prompt_stability=1.0,
        per_question=[_shard_score(1, "DOC-A", 0.5, True),
                      _shard_score(2, "DOC-A", 0.1, False)],
    )
    s2 = EvalResult(
        suite="golden", total=2, passed=2, pass_rate=1.0,
        avg_coverage=0.8, multi_prompt_stability=1.0,
        per_question=[_shard_score(3, "DOC-B", 0.9, True),
                      _shard_score(4, "DOC-B", 0.7, True)],
    )
    m = merge_shard_results([s1, s2])
    assert m.total == 4
    assert m.passed == 3
    assert m.pass_rate == 0.75
    assert "DOC-A" in m.by_doc and "DOC-B" in m.by_doc
    assert m.by_doc["DOC-B"]["passed"] == 2
    assert m.safety_metrics["citation_correct_rate"] == 0.75


def test_merge_shard_results_from_dicts() -> None:
    s1 = EvalResult(
        suite="golden", total=1, passed=1, pass_rate=1.0,
        avg_coverage=0.5, multi_prompt_stability=1.0,
        per_question=[_shard_score(1, "DOC-A", 0.5, True)],
    )
    d = s1.to_full_dict()
    m = merge_shard_results([d])
    assert m.total == 1
    assert m.passed == 1
