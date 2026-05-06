from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3

import pytest

from enterprise_agent_kb.answer_api import answer_query
from enterprise_agent_kb.answer_policy import select_answer_policy
from enterprise_agent_kb import advanced_query_planner
from enterprise_agent_kb import evidence_judge
from enterprise_agent_kb import query_expansion
from enterprise_agent_kb import query_semantic_parser
from enterprise_agent_kb.query_ambiguity import detect_query_ambiguity
from enterprise_agent_kb.knowledge_units import _knowledge_unit, _normalize_unit_metadata
from enterprise_agent_kb.query_api import build_query_context
from enterprise_agent_kb.query_api import _rewrite_with_expansion
from enterprise_agent_kb.query_rewrite import rewrite_query


WORKSPACE = Path("knowledge_base")


class _FakeLLMResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def _text_llm_payload(text: str) -> dict[str, object]:
    return {"content": [{"type": "text", "text": text}]}


def _disable_query_llms(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_llm(*args, **kwargs) -> str:
        raise RuntimeError("LLM disabled for deterministic regression test")

    monkeypatch.setattr(query_semantic_parser, "_call_astron_text", fail_llm)
    monkeypatch.setattr(query_expansion, "_call_astron_text", fail_llm)
    monkeypatch.setattr(advanced_query_planner, "_call_astron_text", fail_llm)
    monkeypatch.setattr(evidence_judge, "_call_astron_text", fail_llm)
    monkeypatch.setenv("EAKB_ENABLE_LLM_EVIDENCE_JUDGE", "0")
    query_semantic_parser.parse_semantic_query.cache_clear()
    query_expansion.expand_query.cache_clear()
    advanced_query_planner.plan_advanced_query.cache_clear()


def test_knowledge_unit_normalization_separates_raw_layout_noise_from_canonical_title() -> None:
    noisy = _normalize_unit_metadata(
        unit_type="procedure",
        title="53\nPUBLIC",
        content="**SWE.2.BP3: 分析软件架构。** 就相关技术设计方面分析软件架构。",
        section="53",
    )
    assert noisy["canonical_title"] == "SWE.2 基本实践"
    assert noisy["canonical_process_code"] == "SWE.2"
    assert "layout_title_noise" in noisy["quality_flags"]
    assert "canonical_title_from_process_code" in noisy["quality_flags"]

    table = _normalize_unit_metadata(
        unit_type="table_requirement",
        title="Base Practices",
        table_title="表 A.7 交流充电控制时序表（续）",
        content="",
        headers=["时序", "状态", "条件", "时间"],
    )
    assert table["canonical_title"] == "表 A.7 交流充电控制时序表（续）"
    assert table["canonical_table_title"] == "表 A.7 交流充电控制时序表（续）"
    assert table["content_role"] == "timing_table"

    clean = _normalize_unit_metadata(
        unit_type="procedure",
        title="4.4.2. SWE.2 软件架构设计",
        content="**SWE.2.BP3: 分析软件架构。**",
    )
    assert clean["canonical_title"] == "4.4.2. SWE.2 软件架构设计"

    leading_punctuation = _normalize_unit_metadata(
        unit_type="procedure",
        title=". SWE.2 软件架构设计",
        content="**SWE.2.BP3: 分析软件架构。**",
    )
    assert leading_punctuation["canonical_title"] == "SWE.2 软件架构设计"


def test_knowledge_unit_factory_preserves_raw_title_and_adds_canonical_metadata() -> None:
    unit = _knowledge_unit(
        id="DOC-X_procedure_1_1",
        type="procedure",
        title="53\nPUBLIC",
        content="**SWE.2.BP3: 分析软件架构。** 就相关技术设计方面分析软件架构。",
        section="53",
        page=1,
    )

    assert unit.title == "53\nPUBLIC"
    assert unit.canonical_title == "SWE.2 基本实践"
    assert unit.canonical_process_code == "SWE.2"
    assert unit.content_role == "process_practice"
    assert "layout_title_noise" in (unit.quality_flags or [])


def test_text_llm_uses_minimax_before_astron(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://minimax.example/anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "minimax-key")
    monkeypatch.setenv("LLM_MODEL", "MiniMax-M2.7")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://astron.example/anthropic")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "astron-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "astron-code-latest")
    calls: list[dict[str, object]] = []

    def fake_post(url: str, **kwargs: object) -> _FakeLLMResponse:
        calls.append({"url": url, "json": kwargs.get("json")})
        return _FakeLLMResponse(_text_llm_payload('{"ok": true}'))

    monkeypatch.setattr(query_semantic_parser.httpx, "post", fake_post)
    result = query_semantic_parser._call_astron_text("ping")

    assert result == '{"ok": true}'
    assert len(calls) == 1
    assert str(calls[0]["url"]).startswith("https://minimax.example/anthropic")
    assert dict(calls[0]["json"] or {})["model"] == "MiniMax-M2.7"


def test_text_llm_falls_back_to_astron_after_minimax_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://minimax.example/anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "minimax-key")
    monkeypatch.setenv("LLM_MODEL", "MiniMax-M2.7")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://astron.example/anthropic")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "astron-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "astron-code-latest")
    calls: list[str] = []

    def fake_post(url: str, **kwargs: object) -> _FakeLLMResponse:
        calls.append(url)
        if "minimax.example" in url:
            raise TimeoutError("primary timeout")
        return _FakeLLMResponse(_text_llm_payload('{"fallback": true}'))

    monkeypatch.setattr(query_semantic_parser.httpx, "post", fake_post)
    result = query_semantic_parser._call_astron_text("ping")

    assert result == '{"fallback": true}'
    assert len(calls) == 2
    assert calls[0].startswith("https://minimax.example/anthropic")
    assert calls[1].startswith("https://astron.example/anthropic")


def test_rewrite_preserves_cc_resistance_anchor_for_meaning_query() -> None:
    rewritten = rewrite_query("CC阻值代表什么意思")
    assert rewritten.query_type == "parameter_lookup"
    assert rewritten.normalized_query == "CC阻值"
    assert rewritten.target_topic == "CC阻值"


def test_rewrite_treats_signal_state_value_definition_as_parameter_lookup() -> None:
    rewritten = rewrite_query("cp 9V PWM是什么意思")

    assert rewritten.query_type == "parameter_lookup"
    assert "CP" in rewritten.must_terms
    assert "9V" in rewritten.must_terms
    assert "PWM" in rewritten.must_terms


def test_rewrite_canonicalizes_cc_resistance_definition_query() -> None:
    rewritten = rewrite_query("CC电阻有哪些定义")
    assert rewritten.query_type == "parameter_lookup"
    assert rewritten.normalized_query == "CC阻值"
    assert rewritten.target_topic == "CC阻值"
    assert "CC阻值" in rewritten.must_terms
    assert "电阻" not in rewritten.must_terms
    assert "CC阻值" in rewritten.protected_anchor_terms


def test_rewrite_preserves_cp_duty_cycle_anchor_for_meaning_query() -> None:
    rewritten = rewrite_query("CP占空比是什么意思")
    assert rewritten.query_type == "parameter_lookup"
    assert rewritten.normalized_query == "CP占空比"
    assert rewritten.target_topic == "CP占空比"
    assert "CP占空比" in rewritten.must_terms
    assert "CP占空比" in rewritten.protected_anchor_terms


def test_rewrite_maps_v2v_definition_to_definition_query() -> None:
    rewritten = rewrite_query("V2V的定义是什么")
    assert rewritten.query_type == "definition"
    assert rewritten.normalized_query == "V2V"
    assert rewritten.target_topic == "V2V"


def test_rewrite_maps_measurement_query_to_test_method_lookup() -> None:
    rewritten = rewrite_query("OBC输入过压怎么测")
    assert rewritten.query_type == "test_method_lookup"
    assert rewritten.normalized_query == "OBC输入过压"
    assert "OBC" in rewritten.must_terms
    assert "输入过压" in rewritten.must_terms
    assert "车载充电机" in rewritten.aliases


def test_rewrite_maps_short_acronym_meaning_query_to_definition() -> None:
    rewritten = rewrite_query("CC是什么意思")
    assert rewritten.query_type == "definition"
    assert rewritten.normalized_query == "CC"
    assert rewritten.target_topic == "CC"
    assert "CC" in rewritten.protected_anchor_terms


def test_detects_ambiguous_short_acronym_definition_query() -> None:
    ambiguity = detect_query_ambiguity("CC是什么意思")
    assert ambiguity is not None
    assert ambiguity.anchor == "CC"
    labels = [item.label for item in ambiguity.options]
    assert any("连接确认" in label for label in labels)
    assert any("恒流" in label for label in labels)
    assert detect_query_ambiguity("充电接口里的CC是什么意思") is None
    assert detect_query_ambiguity("CC阻值代表什么意思") is None


def test_detects_ambiguous_cp_short_acronym_definition_query() -> None:
    ambiguity = detect_query_ambiguity("CP是什么意思")
    assert ambiguity is not None
    assert ambiguity.anchor == "CP"
    labels = [item.label for item in ambiguity.options]
    assert any("控制导引功能" in label for label in labels)
    assert any("控制导引电路" in label for label in labels)
    assert detect_query_ambiguity("充电接口里的CP是什么意思") is None
    assert detect_query_ambiguity("CP占空比是什么意思") is None


def test_rewrite_keeps_timing_intent_for_cp_sequence_query() -> None:
    rewritten = rewrite_query("CP的时序是什么样的")
    assert rewritten.query_type == "timing_lookup"
    assert rewritten.normalized_query == "CP"
    assert rewritten.target_topic == "CP"


@pytest.mark.integration
def test_answer_query_keeps_context_for_cp_timing_alias_anchor(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_query_llms(monkeypatch)
    answer = answer_query(WORKSPACE, "CP的时序是什么样的", limit=8)

    assert answer["answer_mode"] == "timing_lookup"
    assert "表 A.7" in json.dumps(answer, ensure_ascii=False)
    assert answer["context"]["retrieval_plan"]["query_type"] == "timing_lookup"
    assert answer["context"]["hits"]


def test_rewrite_treats_contextual_cp_meaning_as_definition() -> None:
    rewritten = rewrite_query("充电接口里的 CP 控制导引功能是什么意思")
    assert rewritten.query_type == "definition"
    assert rewritten.normalized_query == "CP"
    assert "CP" in rewritten.protected_anchor_terms

    parameter_rewritten = rewrite_query("CP占空比是什么意思")
    assert parameter_rewritten.query_type in {"definition", "parameter_lookup"}
    assert parameter_rewritten.normalized_query == "CP占空比"


def test_parameter_meaning_queries_use_parameter_meaning_policy() -> None:
    rewritten = rewrite_query("CC阻值代表什么意思")
    assert select_answer_policy(rewritten.query_type, "CC阻值代表什么意思", rewritten.to_dict()) == "parameter_meaning"

    rewritten = rewrite_query("CP占空比是什么意思")
    assert select_answer_policy(rewritten.query_type, "CP占空比是什么意思", rewritten.to_dict()) == "parameter_meaning"

    rewritten = rewrite_query("cp 9V PWM是什么意思")
    assert select_answer_policy(rewritten.query_type, "cp 9V PWM是什么意思", rewritten.to_dict()) == "parameter_meaning"


@pytest.mark.integration
def test_query_context_uses_obc_test_method_shape_for_input_overvoltage(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_query_llms(monkeypatch)
    context = build_query_context(WORKSPACE, "OBC输入过压怎么测", limit=8)

    assert context["rewrite"]["query_type"] == "test_method_lookup"
    assert context["hits"][0]["doc_id"] == "DOC-000009"
    judgement = context["evidence_judgement"]
    assert judgement["sufficient"] is True
    assert judgement["evidence_shape"] == "test_method"
    assert judgement["shape_diagnostics"]["shape_contract"]["allowed_shapes"] == ["test_method"]
    assert judgement["shape_diagnostics"]["shape_contract"]["matched"] is True
    assert judgement["shape_diagnostics"]["shape_contract_diagnosis"]["reason"] == "contract_matched"
    assert context["hits"][0]["result_id"] in judgement["best_fact_ids"]
    assert "5.4.1 交流输入过、欠压保护试验" in json.dumps(context["hits"][:3], ensure_ascii=False)
    assert "逐步调节交流输入电压至过压保护值或欠压保护值" in json.dumps(context["hits"][:5], ensure_ascii=False)
    assert "车载充电机" in judgement["matched_anchors"]
    assert "OBC" not in judgement["missing_anchors"]


@pytest.mark.integration
def test_answer_query_answers_obc_input_overvoltage_test_method(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_query_llms(monkeypatch)
    answer = answer_query(WORKSPACE, "OBC输入过压怎么测", limit=8)

    assert answer["answer_mode"] == "test_method_lookup"
    assert answer["supporting_facts"][0]["doc_id"] == "DOC-000009"
    assert answer["supporting_facts"][0]["fact_id"] in answer["context"]["evidence_judgement"]["best_fact_ids"]
    assert answer["context"]["evidence_judgement"]["shape_diagnostics"]["shape_contract"]["matched"] is True
    assert "5.4.1 交流输入过、欠压保护试验" in answer["direct_answer"]
    assert "逐步调节交流输入电压至过压保护值或欠压保护值" in answer["direct_answer"]
    assert "&nbsp;" not in answer["direct_answer"]
    assert "$" not in answer["direct_answer"]
    assert "\n" not in answer["direct_answer"]
    assert "；；" not in answer["direct_answer"]
    assert "。。" not in answer["direct_answer"]
    assert "输出负载突然断开" not in answer["direct_answer"]


def test_answer_query_asks_for_clarification_on_ambiguous_cc() -> None:
    answer = answer_query(WORKSPACE, "CC是什么意思", limit=6)
    assert answer["answer_mode"] == "clarification"
    assert answer["clarification_required"] is True
    assert "CC 有多个可能含义" in answer["direct_answer"]
    labels = [item["label"] for item in answer["clarification"]["options"]]
    assert any("连接确认" in label for label in labels)
    assert any("恒流" in label for label in labels)


def test_answer_query_asks_for_clarification_on_ambiguous_cp() -> None:
    answer = answer_query(WORKSPACE, "CP是什么意思", limit=6)
    assert answer["answer_mode"] == "clarification"
    assert answer["clarification_required"] is True
    assert "CP 有多个可能含义" in answer["direct_answer"]
    labels = [item["label"] for item in answer["clarification"]["options"]]
    assert any("控制导引功能" in label for label in labels)
    assert any("控制导引电路" in label for label in labels)


def test_answer_query_defines_contextual_cp_acronym(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_query_llms(monkeypatch)
    answer = answer_query(WORKSPACE, "充电接口里的 CP 控制导引功能是什么意思", limit=6)
    assert answer["answer_mode"] == "definition"
    assert "控制导引功能 control pilot function; CP" in answer["direct_answer"]
    assert "用于监控电动汽车和供电设备之间交互的功能" in answer["direct_answer"]
    assert "输出占空比公差" not in answer["direct_answer"]


def test_query_expansion_rejects_domain_drift_for_cp_pwm(monkeypatch: pytest.MonkeyPatch) -> None:
    query_expansion.expand_query.cache_clear()

    def fake_llm_response(*args, **kwargs) -> str:
        return """
        {
          "intent_candidates": ["generic electronics"],
          "preserved_anchors": ["CP", "9V", "PWM"],
          "expanded_terms": ["Control Pin", "Charge Pump", "DC-DC Converter"],
          "expanded_queries": [
            {"query": "standard definition of CP pin with 9V PWM", "purpose": "semantic_recall"}
          ],
          "must_not_change": ["CP", "9V", "PWM"],
          "possible_answer_shape": "definition",
          "confidence": 0.9,
          "risk_notes": []
        }
        """

    monkeypatch.setattr(query_expansion, "_call_astron_text", fake_llm_response)
    expansion = query_expansion.expand_query("cp 9V PWM是什么意思")
    assert expansion.used_llm is False
    assert "signal_state_explanation" in expansion.intent_candidates
    assert "表 A.4" in expansion.expanded_terms
    assert any("检测点1" in item.query for item in expansion.expanded_queries)


def test_query_expansion_rejects_domain_drift_for_cp_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    query_expansion.expand_query.cache_clear()

    def fake_llm_response(*args, **kwargs) -> str:
        return """
        {
          "intent_candidates": ["generic electronics timing"],
          "preserved_anchors": ["CP"],
          "expanded_terms": ["CP timing", "Charge Pump timing", "Control Pin waveform"],
          "expanded_queries": [
            {"query": "Charge Pump timing waveform", "purpose": "semantic_recall"}
          ],
          "must_not_change": ["CP"],
          "possible_answer_shape": "timing",
          "confidence": 0.9,
          "risk_notes": []
        }
        """

    monkeypatch.setattr(query_expansion, "_call_astron_text", fake_llm_response)
    expansion = query_expansion.expand_query("CP的时序是什么样的")
    assert expansion.used_llm is False
    assert "timing_lookup" in expansion.intent_candidates
    assert "表 A.7" in expansion.expanded_terms
    assert not any("Charge Pump" in item.query for item in expansion.expanded_queries)


def test_advanced_query_planner_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EAKB_ENABLE_ADVANCED_QUERY_PLANNER", raising=False)
    advanced_query_planner.plan_advanced_query.cache_clear()
    plan = advanced_query_planner.plan_advanced_query("CP的时序是什么样的")
    assert plan.enabled is False
    assert plan.used_llm is False
    assert plan.skip_reason == "disabled_by_env"


def test_advanced_query_planner_synthesizes_structured_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EAKB_ENABLE_ADVANCED_QUERY_PLANNER", "1")
    advanced_query_planner.plan_advanced_query.cache_clear()

    def fake_llm_response(prompt: str, system_prompt: str = "") -> str:
        if "查询规划综合器" in system_prompt:
            return """
            {
              "query_intent": "timing_lookup",
              "target_object": "CP",
              "hard_anchors": ["CP"],
              "must_terms": ["CP", "控制导引", "时序"],
              "should_terms": ["表 A.7", "交流充电控制时序表", "状态转换", "检测点1", "PWM"],
              "negative_terms": ["前言", "目录"],
              "retrieval_queries": [
                "CP 控制导引 时序 状态转换 表 A.7",
                "交流充电控制时序表 检测点1 PWM 状态"
              ],
              "answer_shape": "process_or_timing",
              "confidence": 0.88,
              "risk_notes": ["不要把 CP 扩写为 Charge Pump"]
            }
            """
        return """
        {
          "intent": "timing_lookup",
          "target_object": "CP",
          "must_terms": ["CP", "控制导引"],
          "should_terms": ["时序", "表 A.7"],
          "negative_terms": ["前言"],
          "retrieval_queries": ["CP 控制导引 时序 表 A.7"],
          "answer_shape": "process_or_timing",
          "confidence": 0.8,
          "risk_notes": []
        }
        """

    monkeypatch.setattr(advanced_query_planner, "_call_astron_text", fake_llm_response)
    plan = advanced_query_planner.plan_advanced_query("CP的时序是什么样的")
    assert plan.enabled is True
    assert plan.used_llm is True
    assert plan.query_intent == "timing_lookup"
    assert "CP" in plan.hard_anchors
    assert "表 A.7" in plan.should_terms
    terms = advanced_query_planner.advanced_terms_for_retrieval(plan)
    assert "CP 控制导引 时序 状态转换 表 A.7" in terms


def test_final_retrieval_rewrite_filters_cp_domain_drift_terms() -> None:
    rewritten = rewrite_query("CP的时序是什么样的")
    retrieval_rewrite = _rewrite_with_expansion(
        rewritten,
        ["Control Pilot", "Charge Pump", "Control Pin", "Clock Pulse", "Charging Protocol", "表 A.7"],
    )
    merged = " ".join([
        *retrieval_rewrite.must_terms,
        *retrieval_rewrite.should_terms,
        *retrieval_rewrite.aliases,
    ])
    assert "表 A.7" in merged
    assert "Charge Pump" not in merged
    assert "Control Pin" not in merged
    assert "Clock Pulse" not in merged
    assert "Charging Protocol" not in merged


def test_evidence_judge_llm_keeps_ids_inside_candidate_set(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_llm_response(*args, **kwargs) -> str:
        return """
        {
          "sufficient": true,
          "confidence": 0.91,
          "best_fact_ids": ["FACT-OK", "FACT-HALLUCINATED"],
          "best_evidence_ids": ["EV-OK"],
          "rejected_reasons": ["FACT-OTHER lacks the 9V PWM state row"],
          "suggested_followup_queries": [],
          "reason": "候选证据 FACT-OK 覆盖 9V、PWM 和状态。"
        }
        """

    monkeypatch.setattr(evidence_judge, "_call_astron_text", fake_llm_response)
    judgement = evidence_judge.judge_evidence(
        "cp 9V PWM是什么意思",
        {
            "facts": [
                {
                    "fact_id": "FACT-OK",
                    "evidence_id": "EV-OK",
                    "fact_type": "table_requirement",
                    "object": {"text": "9V 输出 PWM 对应 状态 2"},
                },
                {"fact_id": "FACT-OTHER", "object": {"text": "CP 占空比公差"}},
            ],
            "evidence": [{"evidence_id": "EV-OK", "text": "检测点1 9V PWM 状态"}],
        },
        {"preserved_anchors": ["CP", "9V", "PWM"]},
        force_llm=True,
    )
    assert judgement.used_llm is True
    assert judgement.judge_source == "llm"
    assert judgement.sufficient is True
    assert judgement.best_fact_ids == ["FACT-OK"]
    assert judgement.best_evidence_ids == ["EV-OK"]


def test_evidence_judge_accepts_process_activity_fact_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_query_llms(monkeypatch)

    judgement = evidence_judge.judge_evidence(
        "系统集成测试过程域有哪些活动",
        {
            "facts": [
                {
                    "fact_id": "FACT-SYS4-BP1",
                    "fact_type": "process_fact",
                    "doc_id": "DOC-ASPICE",
                    "object": {
                        "title": "4.3.4. SYS.4 系统集成与集成验证",
                        "process_name": "4.3.4. SYS.4 系统集成与集成验证",
                        "step_text": "SYS.4.BP1: 制定系统集成和集成验证策略。",
                    },
                    "graph_relation": "has_process",
                    "graph_trust_tier": "strong",
                },
                {
                    "fact_id": "FACT-SYS4-BP2",
                    "fact_type": "process_fact",
                    "doc_id": "DOC-ASPICE",
                    "object": {
                        "title": "4.3.4. SYS.4 系统集成与集成验证",
                        "process_name": "4.3.4. SYS.4 系统集成与集成验证",
                        "step_text": "SYS.4.BP2: 开发系统集成测试规范。",
                    },
                    "graph_relation": "has_process",
                    "graph_trust_tier": "strong",
                },
            ],
            "evidence": [],
        },
        {},
        use_llm=False,
    )

    assert judgement.sufficient is True
    assert judgement.best_fact_ids[:2] == ["FACT-SYS4-BP1", "FACT-SYS4-BP2"]
    assert judgement.evidence_shape == "process_activity"
    assert judgement.shape_diagnostics["active_shapes"] == ["process_activity"]
    assert "SYS.4.BP1" in judgement.shape_diagnostics["matched_bp_codes"]
    assert "SYS.4.BP2" in judgement.shape_diagnostics["matched_bp_codes"]
    assert judgement.reason == "top evidence covers process activity facts with process/BP anchors"


def test_evidence_judge_accepts_any_allowed_contract_shape_for_parameter_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_query_llms(monkeypatch)

    judgement = evidence_judge.judge_evidence(
        "R4电阻有哪些定义",
        {
            "rewrite": {"query_type": "parameter_lookup"},
            "facts": [
                {
                    "fact_id": "FACT-R4-TABLE",
                    "fact_type": "table_requirement",
                    "doc_id": "DOC-PARAM",
                    "object": {
                        "table_title": "控制导引电路参数",
                        "headers": ["参数", "符号", "单位", "标称值", "最大值", "最小值"],
                        "rows": [["R4 等效电阻", "R4", "Ω", "1 300", "1 313", "1 287"]],
                    },
                    "graph_relation": "has_parameter_topic",
                    "graph_trust_tier": "strong",
                }
            ],
            "evidence": [],
        },
        {"preserved_anchors": ["R4"]},
        use_llm=False,
    )

    assert judgement.sufficient is True
    assert judgement.evidence_shape == "parameter_definition"
    assert judgement.reason == "top evidence covers parameter definition facts with parameter anchors"
    assert judgement.shape_diagnostics["shape_sufficiency"]["mode"] == "any_allowed_shape"
    assert judgement.shape_diagnostics["shape_sufficiency"]["per_shape"]["parameter_definition"] is True
    assert judgement.shape_diagnostics["shape_sufficiency"]["per_shape"]["signal_state_table"] is False


def test_evidence_judge_rejects_process_title_without_activity_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_query_llms(monkeypatch)

    judgement = evidence_judge.judge_evidence(
        "系统集成测试过程域有哪些活动",
        {
            "facts": [
                {
                    "fact_id": "FACT-SYS4-TITLE",
                    "fact_type": "process_fact",
                    "doc_id": "DOC-ASPICE",
                    "object": {
                        "title": "4.3.4. SYS.4 系统集成与集成验证",
                        "process_name": "4.3.4. SYS.4 系统集成与集成验证",
                    },
                    "graph_relation": "has_process",
                    "graph_trust_tier": "strong",
                }
            ],
            "evidence": [],
        },
        {},
        use_llm=False,
    )

    assert judgement.sufficient is False
    assert judgement.evidence_shape is None
    assert judgement.shape_diagnostics["active_shapes"] == ["process_activity"]
    assert judgement.shape_diagnostics["matched_bp_codes"] == []
    assert judgement.reason == "top evidence does not cover enough required anchors or expected evidence shape"


@pytest.mark.integration
def test_query_context_prefers_parameter_topic_for_cc_resistance() -> None:
    context = build_query_context(WORKSPACE, "CC阻值代表什么意思", limit=6)
    candidates = context["topic_resolution"]["candidate_entities"]
    assert candidates
    assert candidates[0]["canonical_name"] == "CC阻值"
    assert candidates[0]["entity_type"] == "parameter_topic"


@pytest.mark.integration
def test_query_context_uses_graph_as_candidate_channel_for_cc_resistance(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_query_llms(monkeypatch)
    context = build_query_context(WORKSPACE, "CC电阻有哪些定义", limit=8)

    assert context["retrieval_plan"]["graph_candidate_count"] > 0
    assert "graph" in context["retrieval_plan"]["channels"]

    graph_candidates = context["graph_candidates"]
    assert graph_candidates
    assert any(item["relation"] == "has_parameter_topic" for item in graph_candidates)
    assert all(item["relation"] != "relates_to_term" or item["trust_tier"] == "weak" for item in graph_candidates)

    graph_facts = [item for item in context["facts"] if item.get("graph_path")]
    assert graph_facts
    assert graph_facts[0]["graph_relation"] == "has_parameter_topic"
    assert any(step.get("relation") == "supports_fact" for step in graph_facts[0]["graph_path"])
    assert context["evidence_judgement"]["sufficient"] is True
    assert context["evidence_judgement"]["evidence_shape"] == "parameter_definition"
    assert context["evidence_judgement"]["reason"] == "top evidence covers parameter definition facts with parameter anchors"


@pytest.mark.integration
def test_query_context_prefers_parameter_topic_for_cp_duty_cycle() -> None:
    context = build_query_context(WORKSPACE, "CP占空比是什么意思", limit=6)
    candidates = context["topic_resolution"]["candidate_entities"]
    assert candidates
    assert candidates[0]["canonical_name"] == "CP占空比"
    assert candidates[0]["entity_type"] == "parameter_topic"


@pytest.mark.integration
def test_query_context_prefers_parameter_topic_for_detection_point_voltage() -> None:
    context = build_query_context(WORKSPACE, "检测点1电压表示什么", limit=6)
    candidates = context["topic_resolution"]["candidate_entities"]
    assert candidates
    assert candidates[0]["canonical_name"] == "检测点1电压"
    assert candidates[0]["entity_type"] == "parameter_topic"


@pytest.mark.integration
def test_topic_resolution_keeps_software_architecture_activity_in_aspice_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_query_llms(monkeypatch)
    context = build_query_context(WORKSPACE, "软件架构设计有哪些活动要做", limit=8)

    candidates = context["topic_resolution"]["candidate_entities"]
    assert candidates
    assert candidates[0]["canonical_name"] == "4.4.2. SWE.2 软件架构设计"
    assert candidates[0]["entity_type"] == "process"
    candidate_blob = " ".join(str(item["canonical_name"]) for item in candidates)
    assert "能量传输阶段" not in candidate_blob
    assert "充电控制过程" not in candidate_blob

    graph_candidates = context["graph_candidates"]
    assert graph_candidates
    assert all(item["doc_id"] == "DOC-000005" for item in graph_candidates[:5])


@pytest.mark.integration
def test_answer_query_uses_process_facts_for_software_architecture_activities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_query_llms(monkeypatch)
    answer = answer_query(WORKSPACE, "软件架构设计有哪些活动要做", limit=8)

    assert answer["answer_mode"] == "lifecycle_lookup"
    assert "4.4.2. SWE.2 软件架构设计" in answer["direct_answer"]
    assert "SWE.2.BP" in answer["direct_answer"]
    assert "标准号是" not in answer["direct_answer"]


@pytest.mark.integration
def test_topic_resolution_uses_process_activity_alias_for_software_architecture_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_query_llms(monkeypatch)
    context = build_query_context(WORKSPACE, "软件架构分析有哪些活动", limit=8)

    assert context["rewrite"]["query_type"] == "lifecycle_lookup"
    assert context["topic_resolution"]["candidate_entities"][0]["canonical_name"] == "4.4.2. SWE.2 软件架构设计"
    assert context["retrieval_plan"]["graph_candidate_count"] > 0
    assert "graph" in context["retrieval_plan"]["channels"]
    assert all(item["doc_id"] == "DOC-000005" for item in context["hits"][:8])
    top_blob = json.dumps(context["hits"][:8], ensure_ascii=False)
    assert "SWE.2.BP3" in top_blob
    assert "Analyze software architecture" in top_blob or "分析软件架构" in top_blob


@pytest.mark.integration
def test_answer_query_uses_swe2_for_software_architecture_analysis_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_query_llms(monkeypatch)
    answer = answer_query(WORKSPACE, "软件架构分析有哪些活动", limit=8)

    assert answer["answer_mode"] == "lifecycle_lookup"
    assert "SWE.2.BP3" in answer["direct_answer"]
    assert "分析软件架构" in answer["direct_answer"]
    assert answer["context"]["retrieval_plan"]["graph_candidate_count"] > 0


@pytest.mark.integration
def test_process_aliases_are_sanitized_and_do_not_reuse_stale_reference_model_entities() -> None:
    connection = sqlite3.connect(WORKSPACE / "db" / "knowledge.db")
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT entity_id, canonical_name, alias_json
            FROM entities
            WHERE entity_type = 'process'
              AND entity_status = 'ready'
              AND alias_json IS NOT NULL
              AND alias_json != ''
              AND alias_json != '[]'
            """
        ).fetchall()
        disallowed = {
            "Process name",
            "Process purpose",
            "Process outcomes",
            "Base Practices",
            "Output Information Items",
            "过程名称",
            "过程目的",
            "过程成果",
            "基本实践",
            "输出信息项",
            "通用实践",
        }
        bad_aliases: list[tuple[str, str, str]] = []
        for row in rows:
            aliases = json.loads(row["alias_json"] or "[]")
            for alias in aliases:
                text = str(alias).strip()
                if (
                    text in disallowed
                    or re.fullmatch(r"[A-Z]{2,4}", text)
                    or "PUBLIC" in text
                    or "Process reference model" in text
                    or "过程参考模型" in text
                    or re.match(r"^\d+\)", text)
                    or re.match(r"^\d{2}-\d{2}\b", text)
                    or len(text) > 90
                ):
                    bad_aliases.append((row["entity_id"], row["canonical_name"], text))
        assert bad_aliases == []

        noisy_process_entities = []
        for row in connection.execute(
            """
            SELECT entity_id, canonical_name
            FROM entities
            WHERE entity_type = 'process'
              AND entity_status = 'ready'
            """
        ):
            name = str(row["canonical_name"] or "")
            compact = re.sub(r"\s+", "", name).upper()
            if (
                compact in {
                    "PUBLIC",
                    "BASEPRACTICES",
                    "BASICPRACTICES",
                    "OUTPUTINFORMATIONITEMS",
                    "TABLEREQUIREMENT",
                    "TABLE_REQUIREMENT",
                    "VDAQMC",
                }
                or re.fullmatch(r"\d+PUBLIC", compact or "")
                or name in {"Base Practices", "基本实践", "Output Information Items", "输出信息项", "过程名称", "table_requirement"}
                or name.startswith("--- Page")
                or len(name) > 160
                or "过程参考模型" in name
            ):
                noisy_process_entities.append((row["entity_id"], name))
        assert noisy_process_entities == []

        swe2 = connection.execute(
            """
            SELECT alias_json
            FROM entities
            WHERE entity_type = 'process'
              AND entity_status = 'ready'
              AND canonical_name = '4.4.2. SWE.2 软件架构设计'
            """
        ).fetchone()
        assert swe2 is not None
        swe2_aliases = json.loads(swe2["alias_json"] or "[]")
        assert "软件架构分析" in swe2_aliases
        assert "软件需求分析" not in swe2_aliases

        stale_reference_entities = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM entities
            WHERE entity_type = 'process'
              AND entity_status = 'ready'
              AND canonical_name LIKE '%过程参考模型%'
            """
        ).fetchone()
        assert stale_reference_entities["count"] == 0

        fts_wiki_count = connection.execute("SELECT COUNT(*) AS count FROM wiki_fts").fetchone()["count"]
        eligible_wiki_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM wiki_pages w
            LEFT JOIN entities e ON e.entity_id = w.entity_id
            WHERE COALESCE(w.trust_status, '') != 'stale'
              AND (w.entity_id IS NULL OR e.entity_status = 'ready')
            """
        ).fetchone()["count"]
        assert fts_wiki_count == eligible_wiki_count
    finally:
        connection.close()


@pytest.mark.integration
def test_query_context_uses_process_fact_fallback_for_system_integration_activities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_query_llms(monkeypatch)
    context = build_query_context(WORKSPACE, "系统集成测试过程域有哪些活动", limit=8)

    assert context["rewrite"]["query_type"] == "lifecycle_lookup"
    assert context["topic_resolution"]["candidate_entities"][0]["canonical_name"] == "4.3.4. SYS.4 系统集成与集成验证"
    assert context["retrieval_plan"]["graph_candidate_count"] > 0
    assert any(item["relation"] == "has_process" for item in context["graph_candidates"])
    top_blob = json.dumps(context["hits"][:12], ensure_ascii=False)
    for bp_code in ("SYS.4.BP1", "SYS.4.BP2", "SYS.4.BP3", "SYS.4.BP4", "SYS.4.BP5"):
        assert bp_code in top_blob
    assert all(item["doc_id"] == "DOC-000005" for item in context["hits"][:8])


@pytest.mark.integration
def test_answer_query_treats_process_domain_definition_as_lifecycle_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_query_llms(monkeypatch)
    answer = answer_query(WORKSPACE, "系统集成测试过程域是什么", limit=8)

    assert answer["answer_mode"] == "lifecycle_lookup"
    assert "SYS.4.BP1" in answer["direct_answer"]
    assert "SYS.4.BP2" in answer["direct_answer"]
    assert "SYS.4.BP3" in answer["direct_answer"]
    assert "SYS.4.BP4" in answer["direct_answer"]
    assert "SYS.4.BP5" in answer["direct_answer"]
    assert "VDA QMC" not in answer["direct_answer"]


@pytest.mark.integration
def test_query_context_prefers_term_for_short_cc_definition() -> None:
    context = build_query_context(WORKSPACE, "CC是什么意思", limit=6)
    candidates = context["topic_resolution"]["candidate_entities"]
    assert candidates
    names = [item["canonical_name"] for item in candidates[:3]]
    assert "连接确认功能 connection confirm function; CC" in names
    assert all(not str(item["canonical_name"]).startswith("--- Page") for item in candidates[:3])
    wiki_titles = [item["title"] for item in context["topic_resolution"]["candidate_wiki_pages"][:3]]
    assert wiki_titles[0] == "连接确认功能 connection confirm function; CC"
    assert context["evidence_judgement"]["evidence_shape"] == "term_definition"


@pytest.mark.integration
def test_contextual_cc_definition_uses_term_definition_shape() -> None:
    context = build_query_context(WORKSPACE, "充电接口里的CC是什么意思", limit=6)

    judgement = context["evidence_judgement"]
    assert judgement["sufficient"] is True
    assert judgement["evidence_shape"] == "term_definition"
    assert judgement["reason"] == "top evidence covers term definition facts with term anchors"


@pytest.mark.integration
def test_answer_query_uses_parameter_meaning_for_cc_resistance() -> None:
    answer = answer_query(WORKSPACE, "CC阻值代表什么意思", limit=6)
    assert answer["answer_mode"] == "parameter_meaning"
    assert "连接确认回路中的等效电阻参数" in answer["direct_answer"]
    assert answer["fallback_reason"] == ""


@pytest.mark.integration
def test_answer_query_uses_cc_resistance_for_cc_electric_resistance_definition(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_query_llms(monkeypatch)
    answer = answer_query(WORKSPACE, "CC电阻有哪些定义", limit=6)
    assert answer["answer_mode"] == "parameter_meaning"
    assert "CC阻值" in answer["direct_answer"]
    assert "连接确认回路中的等效电阻参数" in answer["direct_answer"]
    assert "GB：代替" not in answer["direct_answer"]
    assert "逆变器" not in answer["direct_answer"]
    assert answer["supporting_facts"][0]["doc_id"] == "DOC-000003"


@pytest.mark.integration
def test_answer_query_uses_parameter_meaning_for_cp_duty_cycle() -> None:
    answer = answer_query(WORKSPACE, "CP占空比是什么意思", limit=6)
    assert answer["answer_mode"] == "parameter_meaning"
    assert "控制导引 PWM 信号中的占空比参数" in answer["direct_answer"]
    assert answer["fallback_reason"] == ""


@pytest.mark.integration
def test_answer_query_defines_short_cc_acronym() -> None:
    answer = answer_query(WORKSPACE, "充电接口里的CC是什么意思", limit=6)
    assert answer["answer_mode"] == "definition"
    assert answer["preferred_doc_id"] is None
    assert "连接确认功能 connection confirm function; CC" in answer["direct_answer"]
    assert "反映车辆插头连接" in answer["direct_answer"]


@pytest.mark.integration
def test_answer_query_explains_cp_9v_pwm_state() -> None:
    answer = answer_query(WORKSPACE, "cp 9V PWM是什么意思", limit=8)
    assert answer["answer_mode"] == "parameter_meaning"
    assert "表 A.4" in answer["direct_answer"]
    assert "9V 且输出 PWM 对应 状态 2" in answer["direct_answer"]
    assert "供电设备准备就绪：是" in answer["direct_answer"]
    assert answer["supporting_facts"][0]["fact_type"] == "table_requirement"
    assert "表 A.4" in answer["supporting_facts"][0]["object"]["table_title"]
    expansion = answer["context"]["query_expansion"]
    assert "9V" in expansion["preserved_anchors"]
    assert "PWM" in expansion["preserved_anchors"]
    judgement = answer["context"]["evidence_judgement"]
    assert judgement["sufficient"] is True
    assert judgement["best_fact_ids"][0] == answer["supporting_facts"][0]["fact_id"]
    assert answer["context"]["retrieval_plan"]["routing_summary_hit_count"] > 0


@pytest.mark.integration
def test_answer_query_explains_cp_timing_from_a7() -> None:
    answer = answer_query(WORKSPACE, "CP的时序是什么样的", limit=8)
    assert answer["rewrite"]["query_type"] == "timing_lookup"
    assert "表 A.7" in answer["direct_answer"]
    assert "控制时序" in answer["direct_answer"] or "时序" in answer["direct_answer"]
    assert answer["supporting_facts"][0]["fact_type"] in {"table_requirement", "transition_fact", "process_fact"}
    assert "表 A.7" in str(answer["supporting_facts"][0]["object"])
    judgement = answer["context"]["evidence_judgement"]
    assert judgement["sufficient"] is True
    assert "timing" in judgement["reason"]


@pytest.mark.integration
def test_answer_query_returns_explainable_fallback_for_v2v() -> None:
    answer = answer_query(WORKSPACE, "什么是V2V", limit=6)
    assert answer["answer_mode"] == "definition"
    assert answer["fallback_reason"] == "fallback_to_related_concept"
    assert "未找到 V2V 的直接定义" in answer["direct_answer"]
    assert "V2X" in answer["direct_answer"]
    assert "近似解释" in answer["direct_answer"]
