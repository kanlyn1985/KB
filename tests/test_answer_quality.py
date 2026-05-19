from __future__ import annotations

from enterprise_agent_kb.answer_quality import evaluate_answer_quality
from enterprise_agent_kb.evidence_shapes import diagnose_shape_contract_failure


def test_answer_quality_passes_supported_answer() -> None:
    quality = evaluate_answer_quality(
        case={"must_include": "连接确认功能", "expected_answer_mode": "definition"},
        answer_text="CC 表示连接确认功能。依据来自 FACT-1。",
        retrieved_items=[{"result_type": "fact", "result_id": "FACT-1"}],
        expected_present=True,
        target_doc_present=True,
        negative_hits=[],
        answer_mode="definition",
        trace_metrics={"evidence_judge_sufficient": True},
    )

    assert quality["answer_pass"] is True
    assert quality["answer_mode_match"] is True
    assert quality["confidence_signal"] == "high"
    assert quality["failure_attribution"] == "ok"


def test_answer_quality_rejects_forbidden_content() -> None:
    quality = evaluate_answer_quality(
        case={"must_include": "CP", "negative_expected": ["Charge Pump"]},
        answer_text="CP 是 Charge Pump。",
        retrieved_items=[{"result_type": "wiki", "result_id": "WPAGE-X"}],
        expected_present=True,
        target_doc_present=True,
        negative_hits=[],
        answer_mode="definition",
        trace_metrics={"evidence_judge_sufficient": True},
    )

    assert quality["answer_pass"] is False
    assert quality["forbidden_hit_count"] == 1
    assert quality["failure_attribution"] == "forbidden_content"


def test_answer_quality_rejects_render_artifacts() -> None:
    quality = evaluate_answer_quality(
        case={"must_include": "试验方法及步骤"},
        answer_text="5.4.1：&nbsp;&nbsp;试验方法及步骤:\n观\n察车载充电机工作状态。；；$ \\pm15\\% $",
        retrieved_items=[{"result_type": "fact", "result_id": "FACT-056351"}],
        expected_present=True,
        target_doc_present=True,
        negative_hits=[],
        answer_mode="lifecycle_lookup",
        trace_metrics={
            "query_type": "test_method_lookup",
            "evidence_shape": "test_method",
            "evidence_judge_sufficient": True,
        },
    )

    assert quality["answer_pass"] is False
    assert quality["failure_attribution"] == "answer_render_artifact"
    assert quality["render_artifact_hit_count"] >= 3
    assert "html_entity_nbsp" in quality["render_artifact_hits"]
    assert "latex_math_delimiter" in quality["render_artifact_hits"]
    assert "hard_wrapped_cjk_line" in quality["render_artifact_hits"]


def test_answer_quality_hard_gates_test_method_shape() -> None:
    quality = evaluate_answer_quality(
        case={"must_include": "试验方法及步骤"},
        answer_text="5.4.1 交流输入过、欠压保护试验：试验方法及步骤：a) 按照图 1 接好试验电路。",
        retrieved_items=[{"result_type": "fact", "result_id": "FACT-056351"}],
        expected_present=True,
        target_doc_present=True,
        negative_hits=[],
        answer_mode="lifecycle_lookup",
        trace_metrics={
            "query_type": "test_method_lookup",
            "evidence_shape": "test_method",
            "evidence_judge_sufficient": False,
        },
    )

    assert quality["answer_pass"] is False
    assert quality["evidence_gate_applied"] is True
    assert quality["failure_attribution"] == "evidence_not_sufficient"


def test_answer_quality_attributes_wrong_answer_mode() -> None:
    quality = evaluate_answer_quality(
        case={"must_include": "表 A.7", "expected_answer_mode": "timing"},
        answer_text="表 A.7 给出控制时序。",
        retrieved_items=[{"result_type": "fact", "result_id": "FACT-1"}],
        expected_present=True,
        target_doc_present=True,
        negative_hits=[],
        answer_mode="definition",
        trace_metrics={"evidence_judge_sufficient": True},
    )

    assert quality["answer_pass"] is False
    assert quality["answer_mode_match"] is False
    assert quality["failure_attribution"] == "answer_mode_wrong"


def test_answer_quality_distinguishes_missing_answer_from_missing_doc() -> None:
    missing_answer = evaluate_answer_quality(
        case={"must_include": "SYS.4.BP1"},
        answer_text="",
        retrieved_items=[{"result_type": "fact", "result_id": "FACT-X"}],
        expected_present=False,
        target_doc_present=True,
        negative_hits=[],
        answer_mode="rich_answer",
        trace_metrics={},
    )
    missing_doc = evaluate_answer_quality(
        case={"must_include": "SYS.4.BP1"},
        answer_text="SYS.4.BP1",
        retrieved_items=[{"result_type": "fact", "result_id": "FACT-X"}],
        expected_present=True,
        target_doc_present=False,
        negative_hits=[],
        answer_mode="rich_answer",
        trace_metrics={},
    )

    assert missing_answer["failure_attribution"] == "expected_answer_missing"
    assert missing_doc["failure_attribution"] == "target_doc_missing"


def test_answer_quality_only_hard_gates_evidence_judge_when_applicable() -> None:
    lifecycle = evaluate_answer_quality(
        case={"must_include": "SWE.2.BP3"},
        answer_text="SWE.2.BP3 分析软件架构。",
        retrieved_items=[{"result_type": "fact", "result_id": "FACT-SWE2-BP3"}],
        expected_present=True,
        target_doc_present=True,
        negative_hits=[],
        answer_mode="lifecycle_lookup",
        trace_metrics={"query_type": "lifecycle_lookup", "evidence_judge_sufficient": False},
    )
    timing = evaluate_answer_quality(
        case={"must_include": "表 A.7"},
        answer_text="表 A.7 交流充电控制时序表。",
        retrieved_items=[{"result_type": "fact", "result_id": "FACT-A7"}],
        expected_present=True,
        target_doc_present=True,
        negative_hits=[],
        answer_mode="timing_lookup",
        trace_metrics={"query_type": "timing_lookup", "evidence_judge_sufficient": False},
    )

    assert lifecycle["answer_pass"] is False
    assert lifecycle["evidence_gate_applied"] is True
    assert lifecycle["expected_evidence_shape"] == "process_activity"
    assert lifecycle["failure_attribution"] == "evidence_shape_wrong"
    assert timing["answer_pass"] is False
    assert timing["evidence_gate_applied"] is True
    assert timing["expected_evidence_shape"] == "timing_table"
    assert timing["failure_attribution"] == "evidence_shape_wrong"


def test_answer_quality_hard_gates_lifecycle_when_process_activity_judge_applies() -> None:
    quality = evaluate_answer_quality(
        case={"must_include": "SWE.2.BP3"},
        answer_text="SWE.2.BP3 分析软件架构。",
        retrieved_items=[{"result_type": "fact", "result_id": "FACT-SWE2-BP3"}],
        expected_present=True,
        target_doc_present=True,
        negative_hits=[],
        answer_mode="lifecycle_lookup",
        trace_metrics={
            "query_type": "lifecycle_lookup",
            "evidence_shape": "process_activity",
            "evidence_judge_sufficient": True,
            "evidence_judge_reason": "top evidence covers process activity facts with process/BP anchors",
        },
    )

    assert quality["answer_pass"] is True
    assert quality["evidence_gate_applied"] is True


def test_answer_quality_rejects_wrong_evidence_shape() -> None:
    quality = evaluate_answer_quality(
        case={
            "must_include": "SWE.2.BP3",
            "expected_evidence_shape": "process_activity",
        },
        answer_text="SWE.2.BP3 分析软件架构。依据来自 FACT-SWE2-BP3。",
        retrieved_items=[{"result_type": "fact", "result_id": "FACT-SWE2-BP3"}],
        expected_present=True,
        target_doc_present=True,
        negative_hits=[],
        answer_mode="lifecycle_lookup",
        trace_metrics={
            "query_type": "lifecycle_lookup",
            "evidence_shape": "term_definition",
            "evidence_judge_sufficient": True,
        },
    )

    assert quality["answer_pass"] is False
    assert quality["evidence_shape_match"] is False
    assert quality["failure_attribution"] == "evidence_shape_wrong"


def test_shape_contract_diagnosis_attributes_wrong_query_type() -> None:
    diagnosis = diagnose_shape_contract_failure(
        query="OBC输入过压怎么测",
        query_type="definition",
        selected_shape="term_definition",
        candidate_shape_counts={"term_definition": 2},
        top_shape_counts={"term_definition": 2},
    )

    assert diagnosis["reason"] == "contract_query_type_wrong"
    assert "query rewrite" in diagnosis["action"]
    assert any("query_rewrite.py" in action for action in diagnosis["repair_actions"])


def test_constraint_contract_allows_requirement_shape() -> None:
    from enterprise_agent_kb.evidence_shapes import allowed_evidence_shapes

    assert "requirement" in allowed_evidence_shapes("constraint")
