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
def test_doc_000012_golden_1() -> None:
    case = '{"kind": "retrieval_quality", "query": "R1代表什么参数？", "must_include": "R1等效电阻", "retrieval_must_hit": ["R1等效电阻"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [12], "expected_sections": ["A.2 充电控制导引电路"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_2() -> None:
    case = '{"kind": "retrieval_quality", "query": "R2等效电阻的参数要求是什么？", "must_include": "R2等效电阻", "retrieval_must_hit": ["R2等效电阻"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [12], "expected_sections": ["A.2 充电控制导引电路"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_3() -> None:
    case = '{"kind": "retrieval_quality", "query": "检测点1电压的参数要求是什么？", "must_include": "检测点1电压", "retrieval_must_hit": ["检测点1电压"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [12], "expected_sections": ["A.2 充电控制导引电路"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_4() -> None:
    case = '{"kind": "retrieval_quality", "query": "R3代表什么参数？", "must_include": "R3等效电阻", "retrieval_must_hit": ["R3等效电阻"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [12], "expected_sections": ["A.2 充电控制导引电路"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_5() -> None:
    case = '{"kind": "retrieval_quality", "query": "R4代表什么参数？", "must_include": "R4等效电阻", "retrieval_must_hit": ["R4等效电阻"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [13], "expected_sections": ["A.2 充电控制导引电路"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_6() -> None:
    case = '{"kind": "retrieval_quality", "query": "R6等效电阻的参数要求是什么？", "must_include": "R6等效电阻", "retrieval_must_hit": ["R6等效电阻"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [13], "expected_sections": ["A.2 充电控制导引电路"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_7() -> None:
    case = '{"kind": "retrieval_quality", "query": "检测点3电压的参数要求是什么？", "must_include": "检测点3电压", "retrieval_must_hit": ["检测点3电压"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [13], "expected_sections": ["A.2 充电控制导引电路"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_8() -> None:
    case = '{"kind": "retrieval_quality", "query": "R5等效电阻的参数要求是什么？", "must_include": "R5等效电阻", "retrieval_must_hit": ["R5等效电阻"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [13], "expected_sections": ["A.2 充电控制导引电路"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_9() -> None:
    case = '{"kind": "retrieval_quality", "query": "检测点2电压的参数要求是什么？", "must_include": "检测点2电压", "retrieval_must_hit": ["检测点2电压"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [13], "expected_sections": ["A.2 充电控制导引电路"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_10() -> None:
    case = '{"kind": "retrieval_quality", "query": "停止数据交互c的参数要求是什么？", "must_include": "停止数据交互c", "retrieval_must_hit": ["停止数据交互c"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [20], "expected_sections": ["A.3.9 能量传输阶段"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_11() -> None:
    case = '{"kind": "retrieval_quality", "query": "停止数据交互c代表什么参数？", "must_include": "停止数据交互c", "retrieval_must_hit": ["停止数据交互c"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [20], "expected_sections": ["A.3.9 能量传输阶段"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_12() -> None:
    case = '{"kind": "retrieval_quality", "query": "停止数据交互b的参数要求是什么？", "must_include": "停止数据交互b", "retrieval_must_hit": ["停止数据交互b"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [24], "expected_sections": ["h）预充及能量传输失败："], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_13() -> None:
    case = '{"kind": "retrieval_quality", "query": "停止数据交互b代表什么参数？", "must_include": "停止数据交互b", "retrieval_must_hit": ["停止数据交互b"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [24], "expected_sections": ["h）预充及能量传输失败："], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_14() -> None:
    case = '{"kind": "retrieval_quality", "query": "DC+对PE总电阻R系统+的参数要求是什么？", "must_include": "DC+对PE总电阻R系统+", "retrieval_must_hit": ["DC+对PE总电阻R系统+"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [37], "expected_sections": ["A.5.7 附加防护措施"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_15() -> None:
    case = '{"kind": "retrieval_quality", "query": "R系统+=1/(1/R充电机++1/R车辆++1/RIMD++1/R人体)代表什么参数？", "must_include": "DC+对PE总电阻R系统+", "retrieval_must_hit": ["DC+对PE总电阻R系统+"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [37], "expected_sections": ["A.5.7 附加防护措施"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_16() -> None:
    case = '{"kind": "retrieval_quality", "query": "DC-对PE总电阻R系统-的参数要求是什么？", "must_include": "DC-对PE总电阻R系统-", "retrieval_must_hit": ["DC-对PE总电阻R系统-"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [37], "expected_sections": ["A.5.7 附加防护措施"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_17() -> None:
    case = '{"kind": "retrieval_quality", "query": "R系统-=1/(1/R充电机-+1/R车辆-+1/RIMD-+1/R漏电-)代表什么参数？", "must_include": "DC-对PE总电阻R系统-", "retrieval_must_hit": ["DC-对PE总电阻R系统-"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [37], "expected_sections": ["A.5.7 附加防护措施"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_18() -> None:
    case = '{"kind": "answer_quality", "query": "R1等效电阻是多少", "must_include": "R1等效电阻", "retrieval_must_hit": ["R1等效电阻", "Ω"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_19() -> None:
    case = '{"kind": "answer_quality", "query": "R3等效电阻是多少", "must_include": "R3等效电阻", "retrieval_must_hit": ["R3等效电阻", "Ω"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_20() -> None:
    case = '{"kind": "answer_quality", "query": "R4等效电阻是多少", "must_include": "R4等效电阻", "retrieval_must_hit": ["R4等效电阻", "Ω"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_21() -> None:
    case = '{"kind": "answer_quality", "query": "停止数据交互c是多少", "must_include": "停止数据交互c", "retrieval_must_hit": ["停止数据交互c"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_22() -> None:
    case = '{"kind": "answer_quality", "query": "停止数据交互b是多少", "must_include": "停止数据交互b", "retrieval_must_hit": ["停止数据交互b"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_23() -> None:
    case = '{"kind": "answer_quality", "query": "DC+对PE总电阻R系统+是多少", "must_include": "DC+对PE总电阻R系统+", "retrieval_must_hit": ["DC+对PE总电阻R系统+"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_24() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第1页 # 中华人民共和国国家标准 GB/T 18487.5—2024 # 电动汽车", "must_include": "# 中华人民共和国国家标准 GB/T 18487.5—2024 # 电动汽车", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_25() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第5页 本文件是 GB/T 18487《电动汽车传导充电系统》的第 5 部分。GB/", "must_include": "本文件是 GB/T 18487《电动汽车传导充电系统》的第 5 部分。GB/", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_26() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第6页 ## 引言 随着电动汽车相关产业与消费市场规模的快速扩大，行业迫切需求大功率", "must_include": "## 引言 随着电动汽车相关产业与消费市场规模的快速扩大，行业迫切需求大功率", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_27() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第7页 # 电动汽车传导充电系统 第 5 部分: 用于 GB/T 20234.3 的", "must_include": "# 电动汽车传导充电系统 第 5 部分: 用于 GB/T 20234.3 的", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_28() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第8页 ## 3 术语和定义 GB/T 18487.1—2023、GB/T 1959", "must_include": "## 3 术语和定义 GB/T 18487.1—2023、GB/T 1959", "source": "local", "assert_mode": "context_contains", "page_no": 8, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_29() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第9页 ## 8 电动汽车和供电设备之间的连接 ### 8.1 通用要求 8.1.1", "must_include": "## 8 电动汽车和供电设备之间的连接 ### 8.1 通用要求 8.1.1", "source": "local", "assert_mode": "context_contains", "page_no": 9, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_30() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第10页 ## 11 过载保护、短路保护和急停 直流供电设备的过载保护、短路保护和急停", "must_include": "## 11 过载保护、短路保护和急停 直流供电设备的过载保护、短路保护和急停", "source": "local", "assert_mode": "context_contains", "page_no": 10, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_31() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第11页 ### A.2 充电控制导引电路 A.2.1 直流充电控制导引电路的基本方案", "must_include": "### A.2 充电控制导引电路 A.2.1 直流充电控制导引电路的基本方案", "source": "local", "assert_mode": "context_contains", "page_no": 11, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_32() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第12页 非车载充电机中电流测量、泄放电路与短路保护装置（如熔断器 FUSE）位置仅供", "must_include": "非车载充电机中电流测量、泄放电路与短路保护装置（如熔断器 FUSE）位置仅供", "source": "local", "assert_mode": "context_contains", "page_no": 12, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_33() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第14页 A.3.2.4 从车辆接口未连接到检测点1电压值变为4 V之前，非车载充电机", "must_include": "A.3.2.4 从车辆接口未连接到检测点1电压值变为4 V之前，非车载充电机", "source": "local", "assert_mode": "context_contains", "page_no": 14, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_34() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第15页 注：车辆控制器发送的车辆最大允许充电电流、车辆最高允许充电总电压等需求值和测", "must_include": "注：车辆控制器发送的车辆最大允许充电电流、车辆最高允许充电总电压等需求值和测", "source": "local", "assert_mode": "context_contains", "page_no": 15, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_35() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第16页 A.3.6.5 充电机应检测直流充电回路 DC+ 与 PE 之间、DC- 与", "must_include": "A.3.6.5 充电机应检测直流充电回路 DC+ 与 PE 之间、DC- 与", "source": "local", "assert_mode": "context_contains", "page_no": 16, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_36() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第17页 A.3.7.8 供电模式中，当充电机需要降低输出功率，应先更新充电机当前最大", "must_include": "A.3.7.8 供电模式中，当充电机需要降低输出功率，应先更新充电机当前最大", "source": "local", "assert_mode": "context_contains", "page_no": 17, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_37() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第18页 A.3.9.4 在恒压充电模式下，充电机的输出电压应满足车辆电压需求值，输出", "must_include": "A.3.9.4 在恒压充电模式下，充电机的输出电压应满足车辆电压需求值，输出", "source": "local", "assert_mode": "context_contains", "page_no": 18, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_38() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第19页 A.3.9.9 能量传输阶段完成后，充电机停止输出、断开接触器 K1、K2", "must_include": "A.3.9.9 能量传输阶段完成后，充电机停止输出、断开接触器 K1、K2", "source": "local", "assert_mode": "context_contains", "page_no": 19, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_39() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第20页 A.3.10.1.2.2 充电机正常结束时，应停止输出并断开接触器 K1、K", "must_include": "A.3.10.1.2.2 充电机正常结束时，应停止输出并断开接触器 K1、K", "source": "local", "assert_mode": "context_contains", "page_no": 20, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_40() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第22页 造厂规定的限值，故障检测时间由制造厂自定义。", "must_include": "造厂规定的限值，故障检测时间由制造厂自定义。", "source": "local", "assert_mode": "context_contains", "page_no": 22, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_41() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第23页 ## h）预充及能量传输失败： 1）预充电压不匹配：充电机检测的接触器K1、", "must_include": "## h）预充及能量传输失败： 1）预充电压不匹配：充电机检测的接触器K1、", "source": "local", "assert_mode": "context_contains", "page_no": 23, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_42() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第24页 f) 放电电压过低：在放电模式，车辆输出电压低于车辆制造厂规定的欠压保护值", "must_include": "f) 放电电压过低：在放电模式，车辆输出电压低于车辆制造厂规定的欠压保护值", "source": "local", "assert_mode": "context_contains", "page_no": 24, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_43() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第25页 f) 电压过高：在供电模式、预充电或能量传输阶段，充电机输出电压高于表 A.", "must_include": "f) 电压过高：在供电模式、预充电或能量传输阶段，充电机输出电压高于表 A.", "source": "local", "assert_mode": "context_contains", "page_no": 25, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_44() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第28页 3电压均变为4V", "must_include": "3电压均变为4V", "source": "local", "assert_mode": "context_contains", "page_no": 28, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_45() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第29页 注2：时序图中网格填充区域状态由制造厂自定义，网格填充区域粗实线为推荐值。", "must_include": "注2：时序图中网格填充区域状态由制造厂自定义，网格填充区域粗实线为推荐值。", "source": "local", "assert_mode": "context_contains", "page_no": 29, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_46() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第30页 2电压变为6V（U2为12V时）", "must_include": "2电压变为6V（U2为12V时）", "source": "local", "assert_mode": "context_contains", "page_no": 30, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_47() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第31页 注2：时序图中网格填充区域状态由制造厂自定义，网格填充区域粗实线为推荐值。", "must_include": "注2：时序图中网格填充区域状态由制造厂自定义，网格填充区域粗实线为推荐值。", "source": "local", "assert_mode": "context_contains", "page_no": 31, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_48() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第32页 3电压变为10V", "must_include": "3电压变为10V", "source": "local", "assert_mode": "context_contains", "page_no": 32, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_49() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第33页 注2：时序图中网格填充区域状态由制造厂自定义，网格填充区域粗实线为推荐值。", "must_include": "注2：时序图中网格填充区域状态由制造厂自定义，网格填充区域粗实线为推荐值。", "source": "local", "assert_mode": "context_contains", "page_no": 33, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_50() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第34页 #### A.5.4 手动应急解锁装置 若车辆插头配备手动应急解锁装置，则可", "must_include": "#### A.5.4 手动应急解锁装置 若车辆插头配备手动应急解锁装置，则可", "source": "local", "assert_mode": "context_contains", "page_no": 34, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_51() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第36页 注：充电机绝缘监测装置在输出回路检测阶段完成前进行自诊断可避免功能冲突。车辆", "must_include": "注：充电机绝缘监测装置在输出回路检测阶段完成前进行自诊断可避免功能冲突。车辆", "source": "local", "assert_mode": "context_contains", "page_no": 36, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_52() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第38页 #### A.5.9 负载突降 在能量传输阶段，由于故障出现负载突降的情况时", "must_include": "#### A.5.9 负载突降 在能量传输阶段，由于故障出现负载突降的情况时", "source": "local", "assert_mode": "context_contains", "page_no": 38, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_53() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第40页 A.5.14.3 若仅使用一个车辆插座进行充电，另一个车辆插座的 B 级电压", "must_include": "A.5.14.3 若仅使用一个车辆插座进行充电，另一个车辆插座的 B 级电压", "source": "local", "assert_mode": "context_contains", "page_no": 40, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_54() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第41页 A.5.14.9 可双车辆插座充电的车辆，每个车辆插座绝缘监测应符合 A.5", "must_include": "A.5.14.9 可双车辆插座充电的车辆，每个车辆插座绝缘监测应符合 A.5", "source": "local", "assert_mode": "context_contains", "page_no": 41, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000012_golden_55() -> None:
    case = '{"kind": "page_coverage", "query": "GB_T 18487.5-2024 电动汽车传导充电系统 第5部分：用于GB_T 20234.3直流充电系统：第43页 非车载充电机中电流测量、泄放电路与短路保护装置（如熔断器 FUSE）位置仅供", "must_include": "非车载充电机中电流测量、泄放电路与短路保护装置（如熔断器 FUSE）位置仅供", "source": "local", "assert_mode": "context_contains", "page_no": 43, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))
