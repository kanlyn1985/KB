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
def test_doc_000012_golden_24() -> None:
    case = '{"kind": "evidence", "query": "# 中华人民共和国国家标准 GB/T 18487.5—2024 # 电动汽车传导充电", "must_include": "# 中华人民共和国国家标准 GB/T 18487.5—2024 # 电动汽车传导充电", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_25() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：## 前言 本文件按照 GB/T 1.1—2020《标准化工作导则 第1部分：标准化", "must_include": "## 前言 本文件按照 GB/T 1.1—2020《标准化工作导则 第1部分：标准化", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_26() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：本文件是 GB/T 18487《电动汽车传导充电系统》的第 5 部分。GB/T 18", "must_include": "本文件是 GB/T 18487《电动汽车传导充电系统》的第 5 部分。GB/T 18", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_27() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：——电动车辆传导充电系统 电动车辆交流/直流充电机（站）；", "must_include": "——电动车辆传导充电系统 电动车辆交流/直流充电机（站）；", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_28() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：——电动汽车传导充电系统 第5部分：用于GB/T20234.3的直流充电系统。", "must_include": "——电动汽车传导充电系统 第5部分：用于GB/T20234.3的直流充电系统。", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_29() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：请注意本文件的某些内容可能涉及专利。本文件的发布机构不承担识别专利的责任。", "must_include": "请注意本文件的某些内容可能涉及专利。本文件的发布机构不承担识别专利的责任。", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_30() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：本文件由中华人民共和国工业和信息化部提出。", "must_include": "本文件由中华人民共和国工业和信息化部提出。", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_31() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：## 引言 随着电动汽车相关产业与消费市场规模的快速扩大，行业迫切需求大功率充电、即", "must_include": "## 引言 随着电动汽车相关产业与消费市场规模的快速扩大，行业迫切需求大功率充电、即", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_32() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：GB/T 18487 拟由 5 个部分构成。", "must_include": "GB/T 18487 拟由 5 个部分构成。", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_33() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：——第1部分：通用要求。目的在于规范电动汽车与非车载传导式电能传输设备需要满足的安全", "must_include": "——第1部分：通用要求。目的在于规范电动汽车与非车载传导式电能传输设备需要满足的安全", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_34() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：——第2部分：非车载传导供电设备电磁兼容要求。目的在于规范电动汽车非车载传导供电设备", "must_include": "——第2部分：非车载传导供电设备电磁兼容要求。目的在于规范电动汽车非车载传导供电设备", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_35() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：——第3部分：电动车辆交流直流充电机（站）。目的在于规范电动汽车充电机（站）的具体要", "must_include": "——第3部分：电动车辆交流直流充电机（站）。目的在于规范电动汽车充电机（站）的具体要", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_36() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：——第4部分：车辆对外放电要求。目的在于规定电动汽车通过充电接口为车外负荷提供电能的", "must_include": "——第4部分：车辆对外放电要求。目的在于规定电动汽车通过充电接口为车外负荷提供电能的", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_37() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：# 电动汽车传导充电系统 第 5 部分: 用于 GB/T 20234.3 的直流 充", "must_include": "# 电动汽车传导充电系统 第 5 部分: 用于 GB/T 20234.3 的直流 充", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_38() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：本文件适用于数字通信协议符合 GB/T 27930.2 的电动汽车（简称“车辆”）和", "must_include": "本文件适用于数字通信协议符合 GB/T 27930.2 的电动汽车（简称“车辆”）和", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_39() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：本文件适用于采用隔离式系统的非车载传导式充电机，其供电网侧额定电压不超过AC1000", "must_include": "本文件适用于采用隔离式系统的非车载传导式充电机，其供电网侧额定电压不超过AC1000", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_40() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.5—2024：注 $ ^{1} $：非限制场所的非车载传导式充电机车辆接口处推荐直流工作电压范围为", "must_include": "注 $ ^{1} $：非限制场所的非车载传导式充电机车辆接口处推荐直流工作电压范围为", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_41() -> None:
    case = '{"kind": "standard", "query": "GB/T 18487.5—2024 的标准号和实施日期是什么？", "must_include": "GB/T 18487.5—2024", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_42() -> None:
    case = '{"kind": "standard", "query": "GB/T 18487.5—2024 对应的标准编号是什么？", "must_include": "GB/T 18487.5—2024", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_43() -> None:
    case = '{"kind": "standard", "query": "GB/T 18487.5—2024 的现行标准号是什么？", "must_include": "GB/T 18487.5—2024", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_44() -> None:
    case = '{"kind": "publication_date", "query": "GB/T 18487.5—2024 的发布日期是什么？", "must_include": "2024-12-31", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_45() -> None:
    case = '{"kind": "publication_date", "query": "GB/T 18487.5—2024 是哪一天发布的？", "must_include": "2024-12-31", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_46() -> None:
    case = '{"kind": "effective_date", "query": "GB/T 18487.5—2024 的实施日期是什么？", "must_include": "2024-12-31", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_47() -> None:
    case = '{"kind": "effective_date", "query": "GB/T 18487.5—2024 从哪一天开始实施？", "must_include": "2024-12-31", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_48() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.5—2024中，是否包含“中华人民共和国国家标准”这一章节？", "must_include": "中华人民共和国国家标准", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_49() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.5—2024中，是否包含“5.2 模式 4 提供的功能”这一章节？", "must_include": "5.2 模式 4 提供的功能", "source": "local", "assert_mode": "context_contains", "page_no": 8, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_50() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.5—2024中，是否包含“直流充电系统应提供附加防护，如按 A.5.5 的规定配置绝缘监测装置 (IMD) 等。”这一章节？", "must_include": "直流充电系统应提供附加防护，如按 A.5.5 的规定配置绝缘监测装置 (IMD) 等。", "source": "local", "assert_mode": "context_contains", "page_no": 9, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_51() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.5—2024中，是否包含“A.2 充电控制导引电路”这一章节？", "must_include": "A.2 充电控制导引电路", "source": "local", "assert_mode": "context_contains", "page_no": 11, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_52() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.5—2024中，是否包含“A.4 充电连接控制时序”这一章节？", "must_include": "A.4 充电连接控制时序", "source": "local", "assert_mode": "context_contains", "page_no": 27, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_53() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.5—2024中，是否包含“A.5.8 接触器检测”这一章节？", "must_include": "A.5.8 接触器检测", "source": "local", "assert_mode": "context_contains", "page_no": 38, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_54() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.5—2024中，是否包含“B.2.1 充电控制导引电路”这一章节？", "must_include": "B.2.1 充电控制导引电路", "source": "local", "assert_mode": "context_contains", "page_no": 42, "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000012_golden_55() -> None:
    case = '{"kind": "title", "query": "GB/T 18487.5—2024 这份文档的标题是什么？", "must_include": "# 电动汽车传导充电系统 第 5 部分: 用于 GB/T 20234.3 的直流 充电系统", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000012"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_56() -> None:
    case = '{"kind": "coverage_requirement", "query": "规范性引用文件有哪些要求？", "must_include": "规范性引用文件", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 7, "coverage_unit_id": "DOC-000012_requirement_7_11", "coverage_semantic_key": "规范性引用文件"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_57() -> None:
    case = '{"kind": "coverage_requirement", "query": "模式 4 充电接口锁止装置的应急解锁装置（若有）应具备防误操作措施有哪些要求？", "must_include": "模式 4 充电接口锁止装置的应急解锁装置（若有）应具备防误操作措施", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 9, "coverage_unit_id": "DOC-000012_requirement_9_20", "coverage_semantic_key": "模式 4 充电接口锁止装置的应急解锁装置（若有）应具备防误操作措施"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_58() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.3.3 参数配置阶段有哪些要求？", "must_include": "A.3.3 参数配置阶段", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 14, "coverage_unit_id": "DOC-000012_requirement_14_21", "coverage_semantic_key": "A.3.3 参数配置阶段"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_59() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.3.4 鉴权阶段有哪些要求？", "must_include": "A.3.4 鉴权阶段", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 15, "coverage_unit_id": "DOC-000012_requirement_15_10", "coverage_semantic_key": "A.3.4 鉴权阶段"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_60() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.3.5 预约充电有哪些要求？", "must_include": "A.3.5 预约充电", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 15, "coverage_unit_id": "DOC-000012_requirement_15_16", "coverage_semantic_key": "A.3.5 预约充电"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_61() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.3.6 输出回路检测阶段有哪些要求？", "must_include": "A.3.6 输出回路检测阶段", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 15, "coverage_unit_id": "DOC-000012_requirement_15_25", "coverage_semantic_key": "A.3.6 输出回路检测阶段"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_62() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.3.8 预充电有哪些要求？", "must_include": "A.3.8 预充电", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 17, "coverage_unit_id": "DOC-000012_requirement_17_14", "coverage_semantic_key": "A.3.8 预充电"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_63() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.3.10.3.2 充电机紧急停机有哪些要求？", "must_include": "A.3.10.3.2 充电机紧急停机", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 25, "coverage_unit_id": "DOC-000012_requirement_25_2", "coverage_semantic_key": "A.3.10.3.2 充电机紧急停机"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_64() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.5.6 充电机 Y 电容有哪些要求？", "must_include": "A.5.6 充电机 Y 电容", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 36, "coverage_unit_id": "DOC-000012_requirement_36_6", "coverage_semantic_key": "A.5.6 充电机 Y 电容"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_65() -> None:
    case = '{"kind": "coverage_requirement", "query": "B.2.2.4 充电准备就绪有哪些要求？", "must_include": "B.2.2.4 充电准备就绪", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 45, "coverage_unit_id": "DOC-000012_requirement_45_4", "coverage_semantic_key": "B.2.2.4 充电准备就绪"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_66() -> None:
    case = '{"kind": "coverage_requirement", "query": "B.2.2.5 充电阶段有哪些要求？", "must_include": "B.2.2.5 充电阶段", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 45, "coverage_unit_id": "DOC-000012_requirement_45_11", "coverage_semantic_key": "B.2.2.5 充电阶段"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_67() -> None:
    case = '{"kind": "coverage_requirement", "query": "B.2.2.7 非正常条件下充电中止有哪些要求？", "must_include": "B.2.2.7 非正常条件下充电中止", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 45, "coverage_unit_id": "DOC-000012_requirement_45_17", "coverage_semantic_key": "B.2.2.7 非正常条件下充电中止"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_68() -> None:
    case = '{"kind": "coverage_requirement", "query": "B.2.3 充电电路原理有哪些要求？", "must_include": "B.2.3 充电电路原理", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 46, "coverage_unit_id": "DOC-000012_requirement_46_14", "coverage_semantic_key": "B.2.3 充电电路原理"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_69() -> None:
    case = '{"kind": "coverage_requirement", "query": "B.3.2.4 充电准备就绪有哪些要求？", "must_include": "B.3.2.4 充电准备就绪", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 51, "coverage_unit_id": "DOC-000012_requirement_51_3", "coverage_semantic_key": "B.3.2.4 充电准备就绪"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_70() -> None:
    case = '{"kind": "coverage_requirement", "query": "B.3.2.7 非正常条件下充电中止有哪些要求？", "must_include": "B.3.2.7 非正常条件下充电中止", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 51, "coverage_unit_id": "DOC-000012_requirement_51_14", "coverage_semantic_key": "B.3.2.7 非正常条件下充电中止"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_71() -> None:
    case = '{"kind": "coverage_requirement", "query": "接触顺序有哪些要求？", "must_include": "接触顺序", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 9, "coverage_unit_id": "DOC-000012:requirement:9:5EC0DB18C963", "coverage_semantic_key": "接触顺序"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_72() -> None:
    case = '{"kind": "coverage_requirement", "query": "车辆接口功能性说明有哪些要求？", "must_include": "车辆接口功能性说明", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 9, "coverage_unit_id": "DOC-000012:requirement:9:8CB180ED9DF0", "coverage_semantic_key": "车辆接口功能性说明"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_73() -> None:
    case = '{"kind": "coverage_requirement", "query": "使用条件、维修、标识和说明有哪些要求？", "must_include": "使用条件、维修、标识和说明", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 10, "coverage_unit_id": "DOC-000012:requirement:10:5B035001E0D4", "coverage_semantic_key": "使用条件、维修、标识和说明"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_74() -> None:
    case = '{"kind": "coverage_requirement", "query": "过载保护、短路保护和急停有哪些要求？", "must_include": "过载保护、短路保护和急停", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 10, "coverage_unit_id": "DOC-000012:requirement:10:EC48275BE4A7", "coverage_semantic_key": "过载保护、短路保护和急停"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_75() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1 通则有哪些要求？", "must_include": "A.1 通则", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 11, "coverage_unit_id": "DOC-000012:requirement:11:12BA0127C9AD", "coverage_semantic_key": "A.1 通则"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_76() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.3.7 供电模式有哪些要求？", "must_include": "A.3.7 供电模式", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 16, "coverage_unit_id": "DOC-000012:requirement:16:398D03A819F9", "coverage_semantic_key": "A.3.7 供电模式"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_77() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.3.10.2.1 车辆故障停机有哪些要求？", "must_include": "A.3.10.2.1 车辆故障停机", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 21, "coverage_unit_id": "DOC-000012:requirement:21:A4CE093A6824", "coverage_semantic_key": "A.3.10.2.1 车辆故障停机"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_78() -> None:
    case = '{"kind": "coverage_requirement", "query": "i) 预充及能量传输失败有哪些要求？", "must_include": "i) 预充及能量传输失败", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 21, "coverage_unit_id": "DOC-000012:requirement:21:1F1BD8188FEB", "coverage_semantic_key": "i) 预充及能量传输失败"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_79() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.3.10.2.2 充电机故障停机有哪些要求？", "must_include": "A.3.10.2.2 充电机故障停机", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 22, "coverage_unit_id": "DOC-000012:requirement:22:D23236A25DC8", "coverage_semantic_key": "A.3.10.2.2 充电机故障停机"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_80() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.4.1 正常启动有哪些要求？", "must_include": "A.4.1 正常启动", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 27, "coverage_unit_id": "DOC-000012:requirement:27:986738871BC1", "coverage_semantic_key": "A.4.1 正常启动"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_81() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.4.2 正常结束、故障停机和紧急停机有哪些要求？", "must_include": "A.4.2 正常结束、故障停机和紧急停机", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 29, "coverage_unit_id": "DOC-000012:requirement:29:0A4E387D2CDB", "coverage_semantic_key": "A.4.2 正常结束、故障停机和紧急停机"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_82() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.5.5 绝缘监测装置有哪些要求？", "must_include": "A.5.5 绝缘监测装置", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 35, "coverage_unit_id": "DOC-000012:requirement:35:864FC4A8A9B4", "coverage_semantic_key": "A.5.5 绝缘监测装置"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_83() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.5.10 过载及短路保护有哪些要求？", "must_include": "A.5.10 过载及短路保护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 38, "coverage_unit_id": "DOC-000012:requirement:38:6201F4344A6C", "coverage_semantic_key": "A.5.10 过载及短路保护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_84() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.5.12 车辆供电回路电压切换有哪些要求？", "must_include": "A.5.12 车辆供电回路电压切换", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 38, "coverage_unit_id": "DOC-000012:requirement:38:689A5B7DC408", "coverage_semantic_key": "A.5.12 车辆供电回路电压切换"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_85() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.5.9 负载突降有哪些要求？", "must_include": "A.5.9 负载突降", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 38, "coverage_unit_id": "DOC-000012:requirement:38:221276937A5B", "coverage_semantic_key": "A.5.9 负载突降"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_86() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.5.13 充放电模式有哪些要求？", "must_include": "A.5.13 充放电模式", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 39, "coverage_unit_id": "DOC-000012:requirement:39:11AF2B767B8E", "coverage_semantic_key": "A.5.13 充放电模式"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_87() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.5.14 具备双车辆插座的车辆有哪些要求？", "must_include": "A.5.14 具备双车辆插座的车辆", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 39, "coverage_unit_id": "DOC-000012:requirement:39:A3D5161B36C9", "coverage_semantic_key": "A.5.14 具备双车辆插座的车辆"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_88() -> None:
    case = '{"kind": "coverage_requirement", "query": "B.1 总体要求有哪些要求？", "must_include": "B.1 总体要求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 42, "coverage_unit_id": "DOC-000012:requirement:42:29C1AE08269D", "coverage_semantic_key": "B.1 总体要求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_89() -> None:
    case = '{"kind": "coverage_requirement", "query": "B.2.2.6 正常条件下充电结束有哪些要求？", "must_include": "B.2.2.6 正常条件下充电结束", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 45, "coverage_unit_id": "DOC-000012:requirement:45:AC66682DDFF3", "coverage_semantic_key": "B.2.2.6 正常条件下充电结束"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_90() -> None:
    case = '{"kind": "coverage_requirement", "query": "B.3.1 充电控制导引电路有哪些要求？", "must_include": "B.3.1 充电控制导引电路", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 49, "coverage_unit_id": "DOC-000012:requirement:49:4AECC84B80BD", "coverage_semantic_key": "B.3.1 充电控制导引电路"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_91() -> None:
    case = '{"kind": "coverage_requirement", "query": "B.3.2.6 正常条件下充电结束有哪些要求？", "must_include": "B.3.2.6 正常条件下充电结束", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 51, "coverage_unit_id": "DOC-000012:requirement:51:C90D372D3BB3", "coverage_semantic_key": "B.3.2.6 正常条件下充电结束"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_92() -> None:
    case = '{"kind": "coverage_requirement", "query": "B.3.3 充电电路原理有哪些要求？", "must_include": "B.3.3 充电电路原理", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 52, "coverage_unit_id": "DOC-000012:requirement:52:BE1205987932", "coverage_semantic_key": "B.3.3 充电电路原理"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000012_golden_93() -> None:
    case = '{"kind": "coverage_requirement", "query": "B.3.4 充电连接控制时序有哪些要求？", "must_include": "B.3.4 充电连接控制时序", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000012", "page_no": 52, "coverage_unit_id": "DOC-000012:requirement:52:A7862323392E", "coverage_semantic_key": "B.3.4 充电连接控制时序"}'
    _assert_case(json.loads(case))
