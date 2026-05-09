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
        context = build_query_context(WORKSPACE, case["query"], limit=8, preferred_doc_id=target_doc_id)
        blob = json.dumps(context, ensure_ascii=False)
    else:
        answer = answer_query(WORKSPACE, case["query"], limit=8, preferred_doc_id=target_doc_id)
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
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"规范性引用文件有什么要求？\", \"must_include\": \"规范性引用文件\", \"retrieval_must_hit\": [\"规范性引用文件\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [4], \"expected_sections\": [\"2 规范性引用文件\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_2() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"启动输入冲击电流有什么要求？\", \"must_include\": \"启动输入冲击电流\", \"retrieval_must_hit\": [\"启动输入冲击电流\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [5], \"expected_sections\": [\"4.2.2 启动输入冲击电流\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_3() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"直流输出限压特性有什么要求？\", \"must_include\": \"直流输出限压特性\", \"retrieval_must_hit\": [\"直流输出限压特性\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [6], \"expected_sections\": [\"4.2.3 直流输出限压特性\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_4() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"直流输出限流特性有什么要求？\", \"must_include\": \"直流输出限流特性\", \"retrieval_must_hit\": [\"直流输出限流特性\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [6], \"expected_sections\": [\"4.2.4 直流输出限流特性\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_5() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"直流输出电压误差有什么要求？\", \"must_include\": \"直流输出电压误差\", \"retrieval_must_hit\": [\"直流输出电压误差\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [6], \"expected_sections\": [\"4.2.6 直流输出电压误差\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_6() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"直流输出电流误差有什么要求？\", \"must_include\": \"直流输出电流误差\", \"retrieval_must_hit\": [\"直流输出电流误差\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [6], \"expected_sections\": [\"4.2.7 直流输出电流误差\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_7() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"输出电压纹波因数有什么要求？\", \"must_include\": \"输出电压纹波因数\", \"retrieval_must_hit\": [\"输出电压纹波因数\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [6], \"expected_sections\": [\"4.2.8 输出电压纹波因数\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_8() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"输出抛载要求有什么要求？\", \"must_include\": \"输出抛载要求\", \"retrieval_must_hit\": [\"输出抛载要求\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [6], \"expected_sections\": [\"4.2.10 输出抛载要求\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_9() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"交流输入过压、欠压保护有什么要求？\", \"must_include\": \"交流输入过压、欠压保护\", \"retrieval_must_hit\": [\"交流输入过压、欠压保护\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [7], \"expected_sections\": [\"4.3.1 交流输入过压、欠压保护\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_10() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"直流输出过压、欠压保护有什么要求？\", \"must_include\": \"直流输出过压、欠压保护\", \"retrieval_must_hit\": [\"直流输出过压、欠压保护\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [7], \"expected_sections\": [\"4.3.3 直流输出过压、欠压保护\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_11() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"输出短路保护有什么要求？\", \"must_include\": \"输出短路保护\", \"retrieval_must_hit\": [\"输出短路保护\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [7], \"expected_sections\": [\"4.3.4 输出短路保护\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_12() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021：ICS 43.040 CCS T 35 # GB # 中华人民共和国国家标准 GB/\", \"must_include\": \"ICS 43.040 CCS T 35 # GB # 中华人民共和国国家标准 GB/\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 1, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_13() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021 # 前 言 本文件按照GB/T 1.1—2020《标\", \"must_include\": \"GB/T 40432—2021 # 前 言 本文件按照GB/T 1.1—2020《标\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 3, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_14() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021：请注意本文件的某些内容可能涉及专利。本文件的发布机构不承担识别专利的责任。\", \"must_include\": \"请注意本文件的某些内容可能涉及专利。本文件的发布机构不承担识别专利的责任。\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 3, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_15() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021：本文件由中华人民共和国工业和信息化部提出。\", \"must_include\": \"本文件由中华人民共和国工业和信息化部提出。\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 3, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_16() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021：本文件由全国汽车标准化技术委员会(SAC/TC 114)归口。\", \"must_include\": \"本文件由全国汽车标准化技术委员会(SAC/TC 114)归口。\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 3, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_17() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021：本文件起草单位:北京新能源汽车股份有限公司、苏州汇川联合动力系统有限公司、华为技术有\", \"must_include\": \"本文件起草单位:北京新能源汽车股份有限公司、苏州汇川联合动力系统有限公司、华为技术有\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 3, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_18() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021：本文件主要起草人:赵春阳、符志辉、许晓、曹冬冬、叶铱塬、闫亚江、赵凌霄、徐枭、张晓彬\", \"must_include\": \"本文件主要起草人:赵春阳、符志辉、许晓、曹冬冬、叶铱塬、闫亚江、赵凌霄、徐枭、张晓彬\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 3, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_19() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021 # 电动汽车用传导式车载充电机 ### 1 范围 本\", \"must_include\": \"GB/T 40432—2021 # 电动汽车用传导式车载充电机 ### 1 范围 本\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 4, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_20() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021：本文件适用于标称输入电压为 220 V(AC)(单相)或 380 V(AC)(三相)\", \"must_include\": \"本文件适用于标称输入电压为 220 V(AC)(单相)或 380 V(AC)(三相)\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 4, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_21() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021：### 2 规范性引用文件 下列文件中的内容通过文中的规范性引用而构成本文件必不可少\", \"must_include\": \"### 2 规范性引用文件 下列文件中的内容通过文中的规范性引用而构成本文件必不可少\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 4, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_22() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021：GB 4824—2019 工业、科学和医疗设备 射频骚扰特性 限值和测量方法 GB/\", \"must_include\": \"GB 4824—2019 工业、科学和医疗设备 射频骚扰特性 限值和测量方法 GB/\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 4, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_23() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021 3.1 **车载充电机 on-board charg\", \"must_include\": \"GB/T 40432—2021 3.1 **车载充电机 on-board charg\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 5, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_24() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021：3.3 **充电效率 charging efficiency** 输出功率与输入有功\", \"must_include\": \"3.3 **充电效率 charging efficiency** 输出功率与输入有功\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 5, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_25() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021：3.4 **输出电压误差 output voltage tolerance** 实际\", \"must_include\": \"3.4 **输出电压误差 output voltage tolerance** 实际\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 5, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_26() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021：3.5 **输出电流误差 output current tolerance** 实际\", \"must_include\": \"3.5 **输出电流误差 output current tolerance** 实际\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 5, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_27() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 40432—2021：3.6 **电压纹波因数 voltage ripple factor** 车载充电机\", \"must_include\": \"3.6 **电压纹波因数 voltage ripple factor** 车载充电机\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 5, \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_28() -> None:
    case = json.loads("{\"kind\": \"standard\", \"query\": \"GB/T 40432—2021 的标准号和实施日期是什么？\", \"must_include\": \"GB/T 40432—2021\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_29() -> None:
    case = json.loads("{\"kind\": \"standard\", \"query\": \"GB/T 40432—2021 对应的标准编号是什么？\", \"must_include\": \"GB/T 40432—2021\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_30() -> None:
    case = json.loads("{\"kind\": \"standard\", \"query\": \"GB/T 40432—2021 的现行标准号是什么？\", \"must_include\": \"GB/T 40432—2021\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_31() -> None:
    case = json.loads("{\"kind\": \"publication_date\", \"query\": \"GB/T 40432—2021 的发布日期是什么？\", \"must_include\": \"2021-08-20\", \"source\": \"local\", \"assert_mode\": \"rich_answer\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_32() -> None:
    case = json.loads("{\"kind\": \"publication_date\", \"query\": \"GB/T 40432—2021 是哪一天发布的？\", \"must_include\": \"2021-08-20\", \"source\": \"local\", \"assert_mode\": \"rich_answer\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_33() -> None:
    case = json.loads("{\"kind\": \"effective_date\", \"query\": \"GB/T 40432—2021 的实施日期是什么？\", \"must_include\": \"2022-03-01\", \"source\": \"local\", \"assert_mode\": \"rich_answer\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_34() -> None:
    case = json.loads("{\"kind\": \"effective_date\", \"query\": \"GB/T 40432—2021 从哪一天开始实施？\", \"must_include\": \"2022-03-01\", \"source\": \"local\", \"assert_mode\": \"rich_answer\", \"target_doc_id\": \"DOC-000009\"}")
    _assert_case(case)
