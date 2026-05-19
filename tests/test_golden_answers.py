from __future__ import annotations

from pathlib import Path

import pytest

from enterprise_agent_kb.answer_api import answer_query
from enterprise_agent_kb.agent_tools import run_agent_query


WORKSPACE = Path("knowledge_base")


@pytest.mark.integration
@pytest.mark.benchmark
def test_standard_answer_for_doc3() -> None:
    answer = answer_query(WORKSPACE, "GBT 18487.1-2023 的标准号和实施日期是什么？", limit=6)
    assert "GB/T 18487.1—2023" in answer["direct_answer"]
    assert "2024-04-01" in answer["direct_answer"]


@pytest.mark.integration
@pytest.mark.benchmark
def test_definition_answer_for_control_pilot() -> None:
    answer = answer_query(WORKSPACE, "什么是控制导引电路？", limit=6)
    assert "控制导引电路 control pilot circuit" in answer["direct_answer"]
    assert "信号传输或通信的电路" in answer["direct_answer"]


@pytest.mark.integration
@pytest.mark.benchmark
def test_standard_answer_for_doc4() -> None:
    answer = answer_query(WORKSPACE, "GB/T 18487.5—2024", limit=6)
    assert "GB/T 18487.5—2024" in answer["direct_answer"]
    assert "2024-12-31" in answer["direct_answer"]


@pytest.mark.integration
@pytest.mark.benchmark
def test_standard_answer_for_doc5() -> None:
    answer = answer_query(WORKSPACE, "GB/T 40432-2021 的标准号和实施日期是什么？", limit=6)
    assert "GB/T 40432—2021" in answer["direct_answer"]
    assert "2021-08-20" in answer["direct_answer"]
    assert "2022-03-01" in answer["direct_answer"]


@pytest.mark.integration
@pytest.mark.benchmark
def test_agent_query_prefers_term_definition() -> None:
    result = run_agent_query(WORKSPACE, "什么是控制导引电路？", limit=6)
    final_answer = result.final_answer
    assert "控制导引电路 control pilot circuit" in final_answer["direct_answer"]
    assert any(item["fact_type"] == "term_definition" for item in final_answer["supporting_facts"])


@pytest.mark.integration
@pytest.mark.benchmark
def test_answer_query_for_v2g_definition() -> None:
    answer = answer_query(WORKSPACE, "什么是V2G？", limit=6)
    assert "V2G" in answer["direct_answer"]
    assert "双向能量交换" in answer["direct_answer"]


@pytest.mark.integration
@pytest.mark.benchmark
def test_agent_query_for_v2g_definition() -> None:
    result = run_agent_query(WORKSPACE, "什么是V2G？", limit=6)
    final_answer = result.final_answer
    assert "V2G" in final_answer["direct_answer"]
    assert any(item["fact_type"] in {"concept_definition", "term_definition"} for item in final_answer["supporting_facts"])


@pytest.mark.integration
@pytest.mark.benchmark
def test_answer_query_for_v2x_types() -> None:
    answer = answer_query(WORKSPACE, "V2X有哪些类型？", limit=8)
    assert "V2X" in answer["direct_answer"]
    assert any(token in answer["direct_answer"] for token in ("公共电网", "楼宇供配电系统", "住宅供配电系统", "用电负荷"))
