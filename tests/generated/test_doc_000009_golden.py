from __future__ import annotations

import json
from pathlib import Path

import pytest

from enterprise_agent_kb.answer_api import answer_query
from enterprise_agent_kb.query_api import build_query_context

WORKSPACE = Path("knowledge_base")


def _normalize(value: str) -> str:
    text = value.lower().replace("—", "-").replace("／", "/")
    return "".join(text.split())


def _assert_case(case: dict[str, str]) -> None:
    expected = _normalize(case["must_include"])
    target_doc_id = str(case.get("target_doc_id") or "") or None
    if case.get("assert_mode") == "context_contains":
        context = build_query_context(WORKSPACE, case["query"], limit=10, preferred_doc_id=target_doc_id)
        blob = json.dumps(context, ensure_ascii=False)
    else:
        answer = answer_query(WORKSPACE, case["query"], limit=10, preferred_doc_id=target_doc_id)
        blob = "\n".join(
            [
                str(answer.get("direct_answer", "")),
                *[str(item) for item in answer.get("summary", [])],
                *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_facts", [])],
                *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_evidence", [])],
                *[json.dumps(item, ensure_ascii=False) for item in answer.get("related_wiki_pages", [])],
            ]
        )
    if target_doc_id:
        assert _normalize(target_doc_id) in _normalize(blob)
    assert expected in _normalize(blob)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_1() -> None:
    case = '{"kind": "retrieval_quality", "query": "规范性引用文件有什么要求？", "must_include": "规范性引用文件", "retrieval_must_hit": ["规范性引用文件"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [4], "expected_sections": ["2 规范性引用文件"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_2() -> None:
    case = '{"kind": "retrieval_quality", "query": "启动输入冲击电流有什么要求？", "must_include": "启动输入冲击电流", "retrieval_must_hit": ["启动输入冲击电流"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [5], "expected_sections": ["4.2.2 启动输入冲击电流"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_3() -> None:
    case = '{"kind": "retrieval_quality", "query": "直流输出限压特性有什么要求？", "must_include": "直流输出限压特性", "retrieval_must_hit": ["直流输出限压特性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [6], "expected_sections": ["4.2.3 直流输出限压特性"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_4() -> None:
    case = '{"kind": "retrieval_quality", "query": "直流输出限流特性有什么要求？", "must_include": "直流输出限流特性", "retrieval_must_hit": ["直流输出限流特性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [6], "expected_sections": ["4.2.4 直流输出限流特性"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_5() -> None:
    case = '{"kind": "retrieval_quality", "query": "直流输出电压误差有什么要求？", "must_include": "直流输出电压误差", "retrieval_must_hit": ["直流输出电压误差"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [6], "expected_sections": ["4.2.6 直流输出电压误差"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_6() -> None:
    case = '{"kind": "retrieval_quality", "query": "直流输出电流误差有什么要求？", "must_include": "直流输出电流误差", "retrieval_must_hit": ["直流输出电流误差"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [6], "expected_sections": ["4.2.7 直流输出电流误差"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_7() -> None:
    case = '{"kind": "retrieval_quality", "query": "输出电压纹波因数有什么要求？", "must_include": "输出电压纹波因数", "retrieval_must_hit": ["输出电压纹波因数"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [6], "expected_sections": ["4.2.8 输出电压纹波因数"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_8() -> None:
    case = '{"kind": "retrieval_quality", "query": "输出抛载要求有什么要求？", "must_include": "输出抛载要求", "retrieval_must_hit": ["输出抛载要求"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [6], "expected_sections": ["4.2.10 输出抛载要求"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_9() -> None:
    case = '{"kind": "retrieval_quality", "query": "交流输入过压、欠压保护有什么要求？", "must_include": "交流输入过压、欠压保护", "retrieval_must_hit": ["交流输入过压、欠压保护"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [7], "expected_sections": ["4.3.1 交流输入过压、欠压保护"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_10() -> None:
    case = '{"kind": "retrieval_quality", "query": "直流输出过压、欠压保护有什么要求？", "must_include": "直流输出过压、欠压保护", "retrieval_must_hit": ["直流输出过压、欠压保护"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [7], "expected_sections": ["4.3.3 直流输出过压、欠压保护"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_11() -> None:
    case = '{"kind": "retrieval_quality", "query": "输出短路保护有什么要求？", "must_include": "输出短路保护", "retrieval_must_hit": ["输出短路保护"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [7], "expected_sections": ["4.3.4 输出短路保护"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_12() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021：ICS 43.040 CCS T 35 # GB # 中华人民共和国国家标准 GB/", "must_include": "ICS 43.040 CCS T 35 # GB # 中华人民共和国国家标准 GB/", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_13() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021 # 前 言 本文件按照GB/T 1.1—2020《标", "must_include": "GB/T 40432—2021 # 前 言 本文件按照GB/T 1.1—2020《标", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_14() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021：请注意本文件的某些内容可能涉及专利。本文件的发布机构不承担识别专利的责任。", "must_include": "请注意本文件的某些内容可能涉及专利。本文件的发布机构不承担识别专利的责任。", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_15() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021：本文件由中华人民共和国工业和信息化部提出。", "must_include": "本文件由中华人民共和国工业和信息化部提出。", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_16() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021：本文件由全国汽车标准化技术委员会(SAC/TC 114)归口。", "must_include": "本文件由全国汽车标准化技术委员会(SAC/TC 114)归口。", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_17() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021：本文件起草单位:北京新能源汽车股份有限公司、苏州汇川联合动力系统有限公司、华为技术有", "must_include": "本文件起草单位:北京新能源汽车股份有限公司、苏州汇川联合动力系统有限公司、华为技术有", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_18() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021：本文件主要起草人:赵春阳、符志辉、许晓、曹冬冬、叶铱塬、闫亚江、赵凌霄、徐枭、张晓彬", "must_include": "本文件主要起草人:赵春阳、符志辉、许晓、曹冬冬、叶铱塬、闫亚江、赵凌霄、徐枭、张晓彬", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_19() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021 # 电动汽车用传导式车载充电机 ### 1 范围 本", "must_include": "GB/T 40432—2021 # 电动汽车用传导式车载充电机 ### 1 范围 本", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_20() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021：本文件适用于标称输入电压为 220 V(AC)(单相)或 380 V(AC)(三相)", "must_include": "本文件适用于标称输入电压为 220 V(AC)(单相)或 380 V(AC)(三相)", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_21() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021：### 2 规范性引用文件 下列文件中的内容通过文中的规范性引用而构成本文件必不可少", "must_include": "### 2 规范性引用文件 下列文件中的内容通过文中的规范性引用而构成本文件必不可少", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_22() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021：GB 4824—2019 工业、科学和医疗设备 射频骚扰特性 限值和测量方法 GB/", "must_include": "GB 4824—2019 工业、科学和医疗设备 射频骚扰特性 限值和测量方法 GB/", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_23() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021 3.1 **车载充电机 on-board charg", "must_include": "GB/T 40432—2021 3.1 **车载充电机 on-board charg", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_24() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021：3.3 **充电效率 charging efficiency** 输出功率与输入有功", "must_include": "3.3 **充电效率 charging efficiency** 输出功率与输入有功", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_25() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021：3.4 **输出电压误差 output voltage tolerance** 实际", "must_include": "3.4 **输出电压误差 output voltage tolerance** 实际", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_26() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021：3.5 **输出电流误差 output current tolerance** 实际", "must_include": "3.5 **输出电流误差 output current tolerance** 实际", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_27() -> None:
    case = '{"kind": "evidence", "query": "GB/T 40432—2021：3.6 **电压纹波因数 voltage ripple factor** 车载充电机", "must_include": "3.6 **电压纹波因数 voltage ripple factor** 车载充电机", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_28() -> None:
    case = '{"kind": "standard", "query": "GB/T 40432—2021 的标准号和实施日期是什么？", "must_include": "GB/T 40432—2021", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_29() -> None:
    case = '{"kind": "standard", "query": "GB/T 40432—2021 对应的标准编号是什么？", "must_include": "GB/T 40432—2021", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_30() -> None:
    case = '{"kind": "standard", "query": "GB/T 40432—2021 的现行标准号是什么？", "must_include": "GB/T 40432—2021", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_31() -> None:
    case = '{"kind": "publication_date", "query": "GB/T 40432—2021 的发布日期是什么？", "must_include": "2021-08-20", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_32() -> None:
    case = '{"kind": "publication_date", "query": "GB/T 40432—2021 是哪一天发布的？", "must_include": "2021-08-20", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_33() -> None:
    case = '{"kind": "effective_date", "query": "GB/T 40432—2021 的实施日期是什么？", "must_include": "2022-03-01", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_34() -> None:
    case = '{"kind": "effective_date", "query": "GB/T 40432—2021 从哪一天开始实施？", "must_include": "2022-03-01", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_35() -> None:
    case = '{"kind": "coverage_requirement", "query": "输出反接保护有哪些要求？", "must_include": "输出反接保护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 7, "coverage_unit_id": "DOC-000009_requirement_7_23", "coverage_semantic_key": "输出反接保护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_36() -> None:
    case = '{"kind": "coverage_requirement", "query": "功能特性状态有哪些要求？", "must_include": "功能特性状态", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 8, "coverage_unit_id": "DOC-000009_requirement_8_13", "coverage_semantic_key": "功能特性状态"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_37() -> None:
    case = '{"kind": "coverage_requirement", "query": "电快速瞬变脉冲群抗扰度有哪些要求？", "must_include": "电快速瞬变脉冲群抗扰度", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 9, "coverage_unit_id": "DOC-000009_requirement_9_10", "coverage_semantic_key": "电快速瞬变脉冲群抗扰度"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_38() -> None:
    case = '{"kind": "coverage_requirement", "query": "电波暗室法抗扰度有哪些要求？", "must_include": "电波暗室法抗扰度", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 9, "coverage_unit_id": "DOC-000009_requirement_9_24", "coverage_semantic_key": "电波暗室法抗扰度"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_39() -> None:
    case = '{"kind": "coverage_requirement", "query": "静电放电(ESD)抗扰度有哪些要求？", "must_include": "静电放电(ESD)抗扰度", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 9, "coverage_unit_id": "DOC-000009_requirement_9_20", "coverage_semantic_key": "静电放电(ESD)抗扰度"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_40() -> None:
    case = '{"kind": "coverage_requirement", "query": "电压波动和闪烁要求有哪些要求？", "must_include": "电压波动和闪烁要求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 10, "coverage_unit_id": "DOC-000009_requirement_10_16", "coverage_semantic_key": "电压波动和闪烁要求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_41() -> None:
    case = '{"kind": "coverage_requirement", "query": "湿热循环有哪些要求？", "must_include": "湿热循环", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 11, "coverage_unit_id": "DOC-000009_requirement_11_16", "coverage_semantic_key": "湿热循环"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_42() -> None:
    case = '{"kind": "coverage_requirement", "query": "稳态湿热有哪些要求？", "must_include": "稳态湿热", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 11, "coverage_unit_id": "DOC-000009_requirement_11_18", "coverage_semantic_key": "稳态湿热"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_43() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐振动性能有哪些要求？", "must_include": "耐振动性能", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 11, "coverage_unit_id": "DOC-000009_requirement_11_22", "coverage_semantic_key": "耐振动性能"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_44() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐机械冲击性能有哪些要求？", "must_include": "耐机械冲击性能", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 11, "coverage_unit_id": "DOC-000009_requirement_11_24", "coverage_semantic_key": "耐机械冲击性能"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_45() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐盐雾性能有哪些要求？", "must_include": "耐盐雾性能", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 11, "coverage_unit_id": "DOC-000009_requirement_11_20", "coverage_semantic_key": "耐盐雾性能"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_46() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐高、低温性能有哪些要求？", "must_include": "耐高、低温性能", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 11, "coverage_unit_id": "DOC-000009_requirement_11_13", "coverage_semantic_key": "耐高、低温性能"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_47() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.1.3 交流输出频率有哪些要求？", "must_include": "A.1.1.3 交流输出频率", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 21, "coverage_unit_id": "DOC-000009_requirement_21_35", "coverage_semantic_key": "A.1.1.3 交流输出频率"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_48() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.2.1 直流输入过、欠压保护有哪些要求？", "must_include": "A.1.2.1 直流输入过、欠压保护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 22, "coverage_unit_id": "DOC-000009_requirement_22_36", "coverage_semantic_key": "A.1.2.1 直流输入过、欠压保护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_49() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.2.2 交流输出短路保护有哪些要求？", "must_include": "A.1.2.2 交流输出短路保护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 22, "coverage_unit_id": "DOC-000009_requirement_22_38", "coverage_semantic_key": "A.1.2.2 交流输出短路保护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_50() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.2.3 交流输出过流保护有哪些要求？", "must_include": "A.1.2.3 交流输出过流保护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 22, "coverage_unit_id": "DOC-000009_requirement_22_40", "coverage_semantic_key": "A.1.2.3 交流输出过流保护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_51() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.2.1 试验条件有哪些要求？", "must_include": "A.2.1 试验条件", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 23, "coverage_unit_id": "DOC-000009_requirement_23_10", "coverage_semantic_key": "A.2.1 试验条件"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_52() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.2.3.3 交流输出过流保护试验有哪些要求？", "must_include": "A.2.3.3 交流输出过流保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 25, "coverage_unit_id": "DOC-000009_requirement_25_10", "coverage_semantic_key": "A.2.3.3 交流输出过流保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_53() -> None:
    case = '{"kind": "coverage_gap", "query": "外观试验有哪些活动？", "must_include": "外观试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 12, "coverage_unit_id": "DOC-000009_procedure_12_15", "coverage_semantic_key": "外观试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_54() -> None:
    case = '{"kind": "coverage_gap", "query": "三相交流电压相位偏差试验有哪些活动？", "must_include": "三相交流电压相位偏差试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 13, "coverage_unit_id": "DOC-000009_procedure_13_10", "coverage_semantic_key": "三相交流电压相位偏差试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_55() -> None:
    case = '{"kind": "coverage_gap", "query": "交流电压频率试验有哪些活动？", "must_include": "交流电压频率试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 13, "coverage_unit_id": "DOC-000009_procedure_13_26", "coverage_semantic_key": "交流电压频率试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_56() -> None:
    case = '{"kind": "coverage_gap", "query": "交流输入电压试验有哪些活动？", "must_include": "交流输入电压试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 13, "coverage_unit_id": "DOC-000009_procedure_13_20", "coverage_semantic_key": "交流输入电压试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_57() -> None:
    case = '{"kind": "coverage_gap", "query": "启动输入冲击电流试验有哪些活动？", "must_include": "启动输入冲击电流试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 13, "coverage_unit_id": "DOC-000009_procedure_13_12", "coverage_semantic_key": "启动输入冲击电流试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_58() -> None:
    case = '{"kind": "coverage_gap", "query": "直流输出电压误差试验有哪些活动？", "must_include": "直流输出电压误差试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 14, "coverage_unit_id": "DOC-000009_procedure_14_10", "coverage_semantic_key": "直流输出电压误差试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_59() -> None:
    case = '{"kind": "coverage_gap", "query": "直流输出电流误差试验有哪些活动？", "must_include": "直流输出电流误差试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 14, "coverage_unit_id": "DOC-000009_procedure_14_15", "coverage_semantic_key": "直流输出电流误差试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_60() -> None:
    case = '{"kind": "coverage_gap", "query": "直流输出限功率特性试验有哪些活动？", "must_include": "直流输出限功率特性试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 14, "coverage_unit_id": "DOC-000009_procedure_14_30", "coverage_semantic_key": "直流输出限功率特性试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_61() -> None:
    case = '{"kind": "coverage_gap", "query": "直流输出限压特性试验有哪些活动？", "must_include": "直流输出限压特性试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 14, "coverage_unit_id": "DOC-000009_procedure_14_20", "coverage_semantic_key": "直流输出限压特性试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_62() -> None:
    case = '{"kind": "coverage_gap", "query": "直流输出限流特性试验有哪些活动？", "must_include": "直流输出限流特性试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 14, "coverage_unit_id": "DOC-000009_procedure_14_25", "coverage_semantic_key": "直流输出限流特性试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_63() -> None:
    case = '{"kind": "coverage_gap", "query": "恒压模式下启动输出过冲试验有哪些活动？", "must_include": "恒压模式下启动输出过冲试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 15, "coverage_unit_id": "DOC-000009_procedure_15_35", "coverage_semantic_key": "恒压模式下启动输出过冲试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_64() -> None:
    case = '{"kind": "coverage_gap", "query": "恒流模式下启动输出过冲试验有哪些活动？", "must_include": "恒流模式下启动输出过冲试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 15, "coverage_unit_id": "DOC-000009_procedure_15_39", "coverage_semantic_key": "恒流模式下启动输出过冲试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_65() -> None:
    case = '{"kind": "coverage_gap", "query": "输出抛载试验有哪些活动？", "must_include": "输出抛载试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 15, "coverage_unit_id": "DOC-000009_procedure_15_11", "coverage_semantic_key": "输出抛载试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_66() -> None:
    case = '{"kind": "coverage_gap", "query": "输出电压纹波因数试验有哪些活动？", "must_include": "输出电压纹波因数试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 15, "coverage_unit_id": "DOC-000009_procedure_15_23", "coverage_semantic_key": "输出电压纹波因数试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_67() -> None:
    case = '{"kind": "coverage_gap", "query": "交流输入过、欠压保护试验有哪些活动？", "must_include": "交流输入过、欠压保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 16, "coverage_unit_id": "DOC-000009_procedure_16_34", "coverage_semantic_key": "交流输入过、欠压保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_68() -> None:
    case = '{"kind": "coverage_gap", "query": "充电效率试验有哪些活动？", "must_include": "充电效率试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 16, "coverage_unit_id": "DOC-000009_procedure_16_26", "coverage_semantic_key": "充电效率试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_69() -> None:
    case = '{"kind": "coverage_gap", "query": "功率因数试验有哪些活动？", "must_include": "功率因数试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 16, "coverage_unit_id": "DOC-000009_procedure_16_21", "coverage_semantic_key": "功率因数试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_70() -> None:
    case = '{"kind": "coverage_gap", "query": "直流输出过压保护试验有哪些活动？", "must_include": "直流输出过压保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 16, "coverage_unit_id": "DOC-000009_procedure_16_14", "coverage_semantic_key": "直流输出过压保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_71() -> None:
    case = '{"kind": "coverage_gap", "query": "缺相保护试验有哪些活动？", "must_include": "缺相保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 16, "coverage_unit_id": "DOC-000009_procedure_16_11", "coverage_semantic_key": "缺相保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_72() -> None:
    case = '{"kind": "coverage_gap", "query": "启动前的短路保护试验有哪些活动？", "must_include": "启动前的短路保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 17, "coverage_unit_id": "DOC-000009_procedure_17_29", "coverage_semantic_key": "启动前的短路保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_73() -> None:
    case = '{"kind": "coverage_gap", "query": "工作过程中的短路保护试验有哪些活动？", "must_include": "工作过程中的短路保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 17, "coverage_unit_id": "DOC-000009_procedure_17_34", "coverage_semantic_key": "工作过程中的短路保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_74() -> None:
    case = '{"kind": "coverage_gap", "query": "直流输出欠压保护试验有哪些活动？", "must_include": "直流输出欠压保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 17, "coverage_unit_id": "DOC-000009_procedure_17_22", "coverage_semantic_key": "直流输出欠压保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_75() -> None:
    case = '{"kind": "coverage_gap", "query": "绝缘电阻试验有哪些活动？", "must_include": "绝缘电阻试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 17, "coverage_unit_id": "DOC-000009_procedure_17_16", "coverage_semantic_key": "绝缘电阻试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_76() -> None:
    case = '{"kind": "coverage_gap", "query": "输出反接保护试验有哪些活动？", "must_include": "输出反接保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 17, "coverage_unit_id": "DOC-000009_procedure_17_13", "coverage_semantic_key": "输出反接保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_77() -> None:
    case = '{"kind": "coverage_gap", "query": "交流端口传导发射骚扰试验有哪些活动？", "must_include": "交流端口传导发射骚扰试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 18, "coverage_unit_id": "DOC-000009_procedure_18_23", "coverage_semantic_key": "交流端口传导发射骚扰试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_78() -> None:
    case = '{"kind": "coverage_gap", "query": "接触电流试验有哪些活动？", "must_include": "接触电流试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 18, "coverage_unit_id": "DOC-000009_procedure_18_34", "coverage_semantic_key": "接触电流试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_79() -> None:
    case = '{"kind": "coverage_gap", "query": "浪涌(冲击)抗扰度试验有哪些活动？", "must_include": "浪涌(冲击)抗扰度试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 18, "coverage_unit_id": "DOC-000009_procedure_18_18", "coverage_semantic_key": "浪涌(冲击)抗扰度试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_80() -> None:
    case = '{"kind": "coverage_gap", "query": "电压暂降和短时中断抗扰度试验有哪些活动？", "must_include": "电压暂降和短时中断抗扰度试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 18, "coverage_unit_id": "DOC-000009_procedure_18_20", "coverage_semantic_key": "电压暂降和短时中断抗扰度试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_81() -> None:
    case = '{"kind": "coverage_gap", "query": "电快速瞬变脉冲群抗扰度试验有哪些活动？", "must_include": "电快速瞬变脉冲群抗扰度试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 18, "coverage_unit_id": "DOC-000009_procedure_18_16", "coverage_semantic_key": "电快速瞬变脉冲群抗扰度试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_82() -> None:
    case = '{"kind": "coverage_gap", "query": "电波暗室法抗扰度试验有哪些活动？", "must_include": "电波暗室法抗扰度试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 18, "coverage_unit_id": "DOC-000009_procedure_18_14", "coverage_semantic_key": "电波暗室法抗扰度试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_83() -> None:
    case = '{"kind": "coverage_gap", "query": "耐电压性试验有哪些活动？", "must_include": "耐电压性试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 18, "coverage_unit_id": "DOC-000009_procedure_18_32", "coverage_semantic_key": "耐电压性试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_84() -> None:
    case = '{"kind": "coverage_gap", "query": "静电放电抗扰度试验有哪些活动？", "must_include": "静电放电抗扰度试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 18, "coverage_unit_id": "DOC-000009_procedure_18_12", "coverage_semantic_key": "静电放电抗扰度试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_85() -> None:
    case = '{"kind": "coverage_gap", "query": "高压直流端口传导发射骚扰限值试验有哪些活动？", "must_include": "高压直流端口传导发射骚扰限值试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 18, "coverage_unit_id": "DOC-000009_procedure_18_25", "coverage_semantic_key": "高压直流端口传导发射骚扰限值试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_86() -> None:
    case = '{"kind": "coverage_gap", "query": "低温储存试验有哪些活动？", "must_include": "低温储存试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 19, "coverage_unit_id": "DOC-000009_procedure_19_11", "coverage_semantic_key": "低温储存试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_87() -> None:
    case = '{"kind": "coverage_gap", "query": "低温工作试验有哪些活动？", "must_include": "低温工作试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 19, "coverage_unit_id": "DOC-000009_procedure_19_13", "coverage_semantic_key": "低温工作试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_88() -> None:
    case = '{"kind": "coverage_gap", "query": "辐射发射骚扰试验有哪些活动？", "must_include": "辐射发射骚扰试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 19, "coverage_unit_id": "DOC-000009_procedure_19_25", "coverage_semantic_key": "辐射发射骚扰试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_89() -> None:
    case = '{"kind": "coverage_gap", "query": "高温储存试验有哪些活动？", "must_include": "高温储存试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 19, "coverage_unit_id": "DOC-000009_procedure_19_15", "coverage_semantic_key": "高温储存试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_90() -> None:
    case = '{"kind": "coverage_gap", "query": "高温工作试验有哪些活动？", "must_include": "高温工作试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 19, "coverage_unit_id": "DOC-000009_procedure_19_17", "coverage_semantic_key": "高温工作试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_91() -> None:
    case = '{"kind": "coverage_gap", "query": "噪声试验有哪些活动？", "must_include": "噪声试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 20, "coverage_unit_id": "DOC-000009_procedure_20_22", "coverage_semantic_key": "噪声试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_92() -> None:
    case = '{"kind": "coverage_gap", "query": "A.2.2.2 交流输出电压精度及输出频率试验有哪些活动？", "must_include": "A.2.2.2 交流输出电压精度及输出频率试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 23, "coverage_unit_id": "DOC-000009_procedure_23_22", "coverage_semantic_key": "A.2.2.2 交流输出电压精度及输出频率试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_93() -> None:
    case = '{"kind": "coverage_gap", "query": "A.2.2.3 交流输出负载动态响应试验有哪些活动？", "must_include": "A.2.2.3 交流输出负载动态响应试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 23, "coverage_unit_id": "DOC-000009_procedure_23_32", "coverage_semantic_key": "A.2.2.3 交流输出负载动态响应试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_94() -> None:
    case = '{"kind": "coverage_gap", "query": "A.2.2.4 交流输出电压波形畸变率及直流分量试验有哪些活动？", "must_include": "A.2.2.4 交流输出电压波形畸变率及直流分量试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 23, "coverage_unit_id": "DOC-000009_procedure_23_37", "coverage_semantic_key": "A.2.2.4 交流输出电压波形畸变率及直流分量试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_95() -> None:
    case = '{"kind": "coverage_gap", "query": "A.2.2.5 逆变效率及空载损耗试验有哪些活动？", "must_include": "A.2.2.5 逆变效率及空载损耗试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 24, "coverage_unit_id": "DOC-000009_procedure_24_24", "coverage_semantic_key": "A.2.2.5 逆变效率及空载损耗试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_96() -> None:
    case = '{"kind": "coverage_gap", "query": "A.2.2.6 逆变输出带非阻性负载试验有哪些活动？", "must_include": "A.2.2.6 逆变输出带非阻性负载试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 24, "coverage_unit_id": "DOC-000009_procedure_24_30", "coverage_semantic_key": "A.2.2.6 逆变输出带非阻性负载试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_97() -> None:
    case = '{"kind": "coverage_gap", "query": "A.2.2.7 逆变输出过载能力试验有哪些活动？", "must_include": "A.2.2.7 逆变输出过载能力试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 24, "coverage_unit_id": "DOC-000009_procedure_24_34", "coverage_semantic_key": "A.2.2.7 逆变输出过载能力试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_98() -> None:
    case = '{"kind": "coverage_gap", "query": "A.2.3.1 直流输入过、欠压保护试验有哪些活动？", "must_include": "A.2.3.1 直流输入过、欠压保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 24, "coverage_unit_id": "DOC-000009_procedure_24_39", "coverage_semantic_key": "A.2.3.1 直流输入过、欠压保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_99() -> None:
    case = '{"kind": "coverage_gap", "query": "A.2.3.2.1 启动前的短路保护试验有哪些活动？", "must_include": "A.2.3.2.1 启动前的短路保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 24, "coverage_unit_id": "DOC-000009_procedure_24_45", "coverage_semantic_key": "A.2.3.2.1 启动前的短路保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_100() -> None:
    case = '{"kind": "coverage_gap", "query": "A.2.3.2.2 工作过程中的短路保护试验有哪些活动？", "must_include": "A.2.3.2.2 工作过程中的短路保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 24, "coverage_unit_id": "DOC-000009_procedure_24_49", "coverage_semantic_key": "A.2.3.2.2 工作过程中的短路保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_101() -> None:
    case = '{"kind": "coverage_gap", "query": "A.2.3.4 并网相关保护试验有哪些活动？", "must_include": "A.2.3.4 并网相关保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 25, "coverage_unit_id": "DOC-000009_procedure_25_12", "coverage_semantic_key": "A.2.3.4 并网相关保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_102() -> None:
    case = '{"kind": "coverage_requirement", "query": "过温保护有哪些要求？", "must_include": "过温保护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 7, "coverage_unit_id": "DOC-000009:requirement:7:DC4577DEE61E", "coverage_semantic_key": "过温保护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_103() -> None:
    case = '{"kind": "coverage_requirement", "query": "交流端口传导发射骚扰要求有哪些要求？", "must_include": "交流端口传导发射骚扰要求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 10, "coverage_unit_id": "DOC-000009:requirement:10:5575C556C9EB", "coverage_semantic_key": "交流端口传导发射骚扰要求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_104() -> None:
    case = '{"kind": "coverage_requirement", "query": "沿电源线的电瞬态传导骚扰有哪些要求？", "must_include": "沿电源线的电瞬态传导骚扰", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 10, "coverage_unit_id": "DOC-000009:requirement:10:3802ED9149C0", "coverage_semantic_key": "沿电源线的电瞬态传导骚扰"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_105() -> None:
    case = '{"kind": "coverage_requirement", "query": "谐波电流发射要求有哪些要求？", "must_include": "谐波电流发射要求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 10, "coverage_unit_id": "DOC-000009:requirement:10:9D6E643C7047", "coverage_semantic_key": "谐波电流发射要求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_106() -> None:
    case = '{"kind": "coverage_requirement", "query": "辐射发射骚扰要求有哪些要求？", "must_include": "辐射发射骚扰要求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 10, "coverage_unit_id": "DOC-000009:requirement:10:1775479256A0", "coverage_semantic_key": "辐射发射骚扰要求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_107() -> None:
    case = '{"kind": "coverage_requirement", "query": "高压直流端口的传导发射骚扰要求有哪些要求？", "must_include": "高压直流端口的传导发射骚扰要求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 10, "coverage_unit_id": "DOC-000009:requirement:10:630DC45C1B94", "coverage_semantic_key": "高压直流端口的传导发射骚扰要求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_108() -> None:
    case = '{"kind": "coverage_requirement", "query": "环境温度有哪些要求？", "must_include": "环境温度", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 11, "coverage_unit_id": "DOC-000009:requirement:11:D9D92C231E57", "coverage_semantic_key": "环境温度"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_109() -> None:
    case = '{"kind": "coverage_requirement", "query": "仪器设备要求有哪些要求？", "must_include": "仪器设备要求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 12, "coverage_unit_id": "DOC-000009:requirement:12:22DC164EBFF9", "coverage_semantic_key": "仪器设备要求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_110() -> None:
    case = '{"kind": "coverage_requirement", "query": "环境条件有哪些要求？", "must_include": "环境条件", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 12, "coverage_unit_id": "DOC-000009:requirement:12:3D8302A17C80", "coverage_semantic_key": "环境条件"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_111() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐久性有哪些要求？", "must_include": "耐久性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 12, "coverage_unit_id": "DOC-000009:requirement:12:1AD83C5657BD", "coverage_semantic_key": "耐久性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_112() -> None:
    case = '{"kind": "coverage_requirement", "query": "逆变输出功能要求有哪些要求？", "must_include": "逆变输出功能要求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 12, "coverage_unit_id": "DOC-000009:requirement:12:66B2CA7418C8", "coverage_semantic_key": "逆变输出功能要求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_113() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.1.2 交流输出电压精度有哪些要求？", "must_include": "A.1.1.2 交流输出电压精度", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 21, "coverage_unit_id": "DOC-000009:requirement:21:13F605808EA1", "coverage_semantic_key": "A.1.1.2 交流输出电压精度"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_114() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.1.4 交流输出负载动态响应有哪些要求？", "must_include": "A.1.1.4 交流输出负载动态响应", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 21, "coverage_unit_id": "DOC-000009:requirement:21:655A3B43030C", "coverage_semantic_key": "A.1.1.4 交流输出负载动态响应"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_115() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.1.5 交流输出电压波形畸变率有哪些要求？", "must_include": "A.1.1.5 交流输出电压波形畸变率", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 21, "coverage_unit_id": "DOC-000009:requirement:21:6DC681E12930", "coverage_semantic_key": "A.1.1.5 交流输出电压波形畸变率"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_116() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.1.6 交流输出直流分量有哪些要求？", "must_include": "A.1.1.6 交流输出直流分量", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 21, "coverage_unit_id": "DOC-000009:requirement:21:8C62A73DC021", "coverage_semantic_key": "A.1.1.6 交流输出直流分量"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_117() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.1.7 逆变效率要求有哪些要求？", "must_include": "A.1.1.7 逆变效率要求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 21, "coverage_unit_id": "DOC-000009:requirement:21:7569AAE8D3A5", "coverage_semantic_key": "A.1.1.7 逆变效率要求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_118() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.1.8 空载损耗有哪些要求？", "must_include": "A.1.1.8 空载损耗", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 21, "coverage_unit_id": "DOC-000009:requirement:21:9F7C75C1C403", "coverage_semantic_key": "A.1.1.8 空载损耗"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_119() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐久性试验有哪些要求？", "must_include": "耐久性试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 21, "coverage_unit_id": "DOC-000009:requirement:21:1CA022045D24", "coverage_semantic_key": "耐久性试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_120() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.1.9 交流输出带非阻性负载能力有哪些要求？", "must_include": "A.1.1.9 交流输出带非阻性负载能力", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 22, "coverage_unit_id": "DOC-000009:requirement:22:2E3E7A850749", "coverage_semantic_key": "A.1.1.9 交流输出带非阻性负载能力"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_121() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.2.4 并网相关保护有哪些要求？", "must_include": "A.1.2.4 并网相关保护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 22, "coverage_unit_id": "DOC-000009:requirement:22:5D4AACB83149", "coverage_semantic_key": "A.1.2.4 并网相关保护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_122() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.4.1 逆变工作状态下的电磁抗扰性要求有哪些要求？", "must_include": "A.1.4.1 逆变工作状态下的电磁抗扰性要求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 22, "coverage_unit_id": "DOC-000009:requirement:22:F8F249255377", "coverage_semantic_key": "A.1.4.1 逆变工作状态下的电磁抗扰性要求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_123() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.4.2 逆变工作状态下的电磁发射骚扰要求有哪些要求？", "must_include": "A.1.4.2 逆变工作状态下的电磁发射骚扰要求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 22, "coverage_unit_id": "DOC-000009:requirement:22:13BBB2CCDFB8", "coverage_semantic_key": "A.1.4.2 逆变工作状态下的电磁发射骚扰要求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_124() -> None:
    case = '{"kind": "coverage_requirement", "query": "车载充电机的交流输入额定电压和频率要求应符合表 1 的规定有哪些要求？", "must_include": "车载充电机的交流输入额定电压和频率要求应符合表 1 的规定", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 5, "coverage_unit_id": "DOC-000009:requirement:5:844AA63D05DF", "coverage_semantic_key": "车载充电机的交流输入额定电压和频率要求应符合表 1 的规定"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_125() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.1.1 交流输出额定电压及额定频率有哪些要求？", "must_include": "A.1.1.1 交流输出额定电压及额定频率", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 21, "coverage_unit_id": "DOC-000009:requirement:21:16DE3FA85859", "coverage_semantic_key": "A.1.1.1 交流输出额定电压及额定频率"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000009_golden_126() -> None:
    case = '{"kind": "coverage_gap", "query": "沿电源线的电瞬态传导骚扰有哪些活动？", "must_include": "沿电源线的电瞬态传导骚扰", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000009", "page_no": 18, "coverage_unit_id": "DOC-000009_procedure_18_27", "coverage_semantic_key": "沿电源线的电瞬态传导骚扰"}'
    _assert_case(json.loads(case))
