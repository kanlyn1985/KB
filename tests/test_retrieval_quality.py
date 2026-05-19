from __future__ import annotations

from enterprise_agent_kb.retrieval_quality import evaluate_retrieval_quality
from enterprise_agent_kb.user_query_retrieval_eval import _case_contract_result, _clarification_retrieval_quality


def test_retrieval_quality_scores_rank_and_recall() -> None:
    quality = evaluate_retrieval_quality(
        case={"must_include": ["SWE.2.BP3", "SWE.2.BP4"], "negative_expected": ["SYS.3"]},
        retrieved_items=[
            {"result_type": "fact", "result_id": "FACT-1", "snippet": "SWE.2.BP2 定义软件架构动态方面"},
            {"result_type": "fact", "result_id": "FACT-2", "snippet": "SWE.2.BP3 分析软件架构"},
            {"result_type": "fact", "result_id": "FACT-3", "snippet": "SWE.2.BP4 确保一致性"},
        ],
        trace_metrics={"query_type": "lifecycle_lookup", "retrieval_channels": ["graph", "facts"], "graph_candidate_count": 4},
    )

    assert quality["must_hit_found"] == 2
    assert quality["must_hit_best_rank"] == 2
    assert quality["recall_at_5"] == 1.0
    assert quality["mrr"] == 0.5
    assert quality["negative_hit_rate"] == 0.0
    assert quality["failure_attribution"] == "ok"


def test_retrieval_quality_attributes_graph_not_engaged() -> None:
    quality = evaluate_retrieval_quality(
        case={"must_include": "SYS.4.BP1"},
        retrieved_items=[{"result_type": "fact", "result_id": "FACT-X", "snippet": "unrelated"}],
        trace_metrics={
            "query_type": "lifecycle_lookup",
            "retrieval_channels": ["graph", "facts"],
            "graph_candidate_count": 0,
            "topic_resolution_confidence": 0.8,
            "top_hit_ids": ["FACT-X"],
        },
    )

    assert quality["must_hit_found"] == 0
    assert quality["recall_at_5"] == 0.0
    assert quality["mrr"] == 0.0
    assert quality["failure_attribution"] == "graph_not_engaged"


def test_retrieval_quality_detects_negative_hits() -> None:
    quality = evaluate_retrieval_quality(
        case={"must_include": "CP", "negative_expected": ["Charge Pump"]},
        retrieved_items=[{"result_type": "wiki", "result_id": "WPAGE-X", "snippet": "Charge Pump definition"}],
        trace_metrics={"query_type": "definition", "retrieval_channels": ["wiki"]},
    )

    assert quality["negative_hit_count"] == 1
    assert quality["negative_hit_rate"] == 1.0
    assert quality["failure_attribution"] == "negative_hit"


def test_retrieval_quality_ignores_internal_retrieval_type_labels_for_negative_hits() -> None:
    quality = evaluate_retrieval_quality(
        case={"must_include": "SWE.2.BP1", "negative_expected": ["table_requirement"]},
        retrieved_items=[
            {
                "result_type": "fact",
                "result_id": "FACT-BP1",
                "snippet": 'graph_fact table_requirement: {"rows": [["SWE.2.BP1: Specify static aspects."]]}',
            }
        ],
        trace_metrics={"query_type": "lifecycle_lookup", "retrieval_channels": ["graph"], "graph_candidate_count": 1},
    )

    assert quality["must_hit_found"] == 1
    assert quality["negative_hit_count"] == 0
    assert quality["failure_attribution"] == "ok"


def test_retrieval_quality_flags_partial_must_hit_recall_below_threshold() -> None:
    quality = evaluate_retrieval_quality(
        case={"retrieval_must_hit": ["SWE.2.BP1", "SWE.2.BP2", "SWE.2.BP3"]},
        retrieved_items=[
            {"result_type": "fact", "result_id": "FACT-2", "snippet": "SWE.2.BP2 定义软件架构动态方面"},
            {"result_type": "fact", "result_id": "FACT-3", "snippet": "SWE.2.BP3 分析软件架构"},
        ],
        trace_metrics={"query_type": "lifecycle_lookup", "retrieval_channels": ["graph"], "graph_candidate_count": 3},
    )

    assert quality["recall_at_5"] == 0.666667
    assert quality["failure_attribution"] == "recall_at_5_below_threshold"


def test_retrieval_quality_allows_case_specific_min_recall_threshold() -> None:
    quality = evaluate_retrieval_quality(
        case={"retrieval_must_hit": ["Alpha", "Beta", "Gamma"], "min_recall_at_5": 0.66},
        retrieved_items=[
            {"result_type": "fact", "result_id": "FACT-A", "snippet": "Alpha"},
            {"result_type": "fact", "result_id": "FACT-B", "snippet": "Beta"},
        ],
        trace_metrics={"query_type": "general_search", "retrieval_channels": ["facts"]},
    )

    assert quality["recall_at_5"] == 0.666667
    assert quality["failure_attribution"] == "ok"


def test_retrieval_quality_matches_composite_table_conditions() -> None:
    quality = evaluate_retrieval_quality(
        case={"must_include": "9V 且输出 PWM"},
        retrieved_items=[
            {
                "result_type": "fact",
                "result_id": "FACT-CP-STATE",
                "snippet": "检测点 1 电压值 / V | 最小值 8 | 标称值 9 | 最大值 10 | 是否输出 PWM | 是 | 状态 2'",
            }
        ],
        trace_metrics={"query_type": "parameter_lookup", "retrieval_channels": ["facts"]},
    )

    assert quality["must_hit_found"] == 1
    assert quality["recall_at_5"] == 1.0
    assert quality["failure_attribution"] == "ok"


def test_retrieval_quality_prefers_retrieval_specific_anchors() -> None:
    quality = evaluate_retrieval_quality(
        case={"must_include": "CC阻值", "retrieval_must_hit": ["CC", "等效电阻"]},
        retrieved_items=[
            {
                "result_type": "fact",
                "result_id": "FACT-CC-R",
                "snippet": "CC1 CC2 R4c'等效电阻 标称值 1000 Ω",
            }
        ],
        trace_metrics={"query_type": "parameter_lookup", "retrieval_channels": ["facts"]},
    )

    assert quality["must_hit_total"] == 2
    assert quality["must_hit_found"] == 2
    assert quality["recall_at_5"] == 1.0
    assert quality["failure_attribution"] == "ok"


def test_retrieval_quality_does_not_overmatch_process_code_tokens() -> None:
    quality = evaluate_retrieval_quality(
        case={"must_include": "SWE.2.BP3", "negative_expected": ["SYS.3"]},
        retrieved_items=[
            {"result_type": "fact", "result_id": "FACT-1", "snippet": "SWE.2.BP3 Analyze software architecture"},
            {"result_type": "fact", "result_id": "FACT-2", "snippet": "SYS.1.BP3 分析利益相关方需求变更"},
        ],
        trace_metrics={"query_type": "lifecycle_lookup", "retrieval_channels": ["graph"], "graph_candidate_count": 2},
    )

    assert quality["negative_hit_count"] == 0
    assert quality["failure_attribution"] == "ok"


def test_user_query_eval_treats_clarification_as_non_retrieval_contract() -> None:
    context = {
        "clarification_required": True,
        "rewrite": {"query_type": "clarification"},
        "retrieval_plan": {"channels": ["clarification"], "graph_candidate_count": 0},
        "topic_resolution": {"confidence": 0.0, "candidate_entities": []},
        "hits": [],
        "clarification": {
            "options": [
                {"option_id": "connection_confirm", "label": "连接确认功能 / connection confirm"},
                {"option_id": "constant_current", "label": "恒流 / constant current"},
            ]
        },
    }
    trace_metrics = {
        "query_type": "clarification",
        "retrieval_channels": ["clarification"],
        "graph_candidate_count": 0,
        "topic_resolution_confidence": 0.0,
        "topic_candidate_names": [],
        "top_hit_ids": [],
    }
    case = {
        "expected_query_type": "clarification",
        "expected_clarification_required": True,
        "expected_clarification_options": ["连接确认功能", "恒流"],
        "retrieval_must_hit": ["连接确认功能"],
    }

    contract = _case_contract_result(case, context, trace_metrics, [])
    quality = _clarification_retrieval_quality()

    assert contract["passed"] is True
    assert quality["failure_attribution"] == "ok"
    assert quality["recall_at_5"] is None
