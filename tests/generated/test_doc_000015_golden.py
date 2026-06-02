from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from enterprise_agent_kb.answer_api import answer_query
from enterprise_agent_kb.query_api import build_query_context

os.environ.setdefault("EAKB_ENABLE_LLM_EVIDENCE_JUDGE", "0")

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
def test_doc_000015_golden_1() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是Overview？", "must_include": "Overview", "retrieval_must_hit": ["Overview"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["Overview"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_2() -> None:
    case = '{"kind": "retrieval_quality", "query": "DOC-000015中Overview的定义是什么？", "must_include": "Overview", "retrieval_must_hit": ["Overview"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["Overview"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_3() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是在受损车辆或单一控制器刷写的场景中,如果用于刷新前置条件判断的信号(如车速或整车主？", "must_include": "在受损车辆或单一控制器刷写的场景中,如果用于刷新前置条件判断的信号(如车速或整车主", "retrieval_must_hit": ["在受损车辆或单一控制器刷写的场景中,如果用于刷新前置条件判断的信号(如车速或整车主"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["在受损车辆或单一控制器刷写的场景中,如果用于刷新前置条件判断的信号(如车速或整车主"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_4() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是过OBCAcUActL1、OBCAcUActL2、OBCAcUActL3 发送交流电压有效？", "must_include": "过OBCAcUActL1、OBCAcUActL2、OBCAcUActL3 发送交流电压有效", "retrieval_must_hit": ["过OBCAcUActL1、OBCAcUActL2、OBCAcUActL3 发送交流电压有效"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过OBCAcUActL1、OBCAcUActL2、OBCAcUActL3 发送交流电压有效"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_5() -> None:
    case = '{"kind": "retrieval_quality", "query": "DOC-000015中过OBCAcUActL1、OBCAcUActL2、OBCAcUActL3 发送交流电压有效的定义是什么？", "must_include": "过OBCAcUActL1、OBCAcUActL2、OBCAcUActL3 发送交流电压有效", "retrieval_must_hit": ["过OBCAcUActL1、OBCAcUActL2、OBCAcUActL3 发送交流电压有效"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过OBCAcUActL1、OBCAcUActL2、OBCAcUActL3 发送交流电压有效"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_6() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是DrtOBCHvdcUAbnorm=True？", "must_include": "DrtOBCHvdcUAbnorm=True", "retrieval_must_hit": ["DrtOBCHvdcUAbnorm=True"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["DrtOBCHvdcUAbnorm=True"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_7() -> None:
    case = '{"kind": "retrieval_quality", "query": "DOC-000015中DrtOBCHvdcUAbnorm=True的定义是什么？", "must_include": "DrtOBCHvdcUAbnorm=True", "retrieval_must_hit": ["DrtOBCHvdcUAbnorm=True"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["DrtOBCHvdcUAbnorm=True"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_8() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是OBCAcU3Frq 当前L3 交流电压频率？", "must_include": "OBCAcU3Frq 当前L3 交流电压频率", "retrieval_must_hit": ["OBCAcU3Frq 当前L3 交流电压频率"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["OBCAcU3Frq 当前L3 交流电压频率"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_9() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是首次插枪时(Disconnect->!Disconnect),CCU 同时基于？", "must_include": "首次插枪时(Disconnect->!Disconnect),CCU 同时基于", "retrieval_must_hit": ["首次插枪时(Disconnect->!Disconnect),CCU 同时基于"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["首次插枪时(Disconnect->!Disconnect),CCU 同时基于"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_10() -> None:
    case = '{"kind": "retrieval_quality", "query": "DOC-000015中首次插枪时(Disconnect->!Disconnect),CCU 同时基于的定义是什么？", "must_include": "首次插枪时(Disconnect->!Disconnect),CCU 同时基于", "retrieval_must_hit": ["首次插枪时(Disconnect->!Disconnect),CCU 同时基于"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["首次插枪时(Disconnect->!Disconnect),CCU 同时基于"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_11() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是类别逻辑功能？", "must_include": "类别逻辑功能", "retrieval_must_hit": ["类别逻辑功能"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["类别逻辑功能"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_12() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是OBCAcUFrq 当前交流电压频率？", "must_include": "OBCAcUFrq 当前交流电压频率", "retrieval_must_hit": ["OBCAcUFrq 当前交流电压频率"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["OBCAcUFrq 当前交流电压频率"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_13() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是连接的是交流充电桩,则CCU 接收到VCUOBCModReq=Discharge？", "must_include": "连接的是交流充电桩,则CCU 接收到VCUOBCModReq=Discharge", "retrieval_must_hit": ["连接的是交流充电桩,则CCU 接收到VCUOBCModReq=Discharge"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["连接的是交流充电桩,则CCU 接收到VCUOBCModReq=Discharge"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_14() -> None:
    case = '{"kind": "retrieval_quality", "query": "DOC-000015中连接的是交流充电桩,则CCU 接收到VCUOBCModReq=Discharge的定义是什么？", "must_include": "连接的是交流充电桩,则CCU 接收到VCUOBCModReq=Discharge", "retrieval_must_hit": ["连接的是交流充电桩,则CCU 接收到VCUOBCModReq=Discharge"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["连接的是交流充电桩,则CCU 接收到VCUOBCModReq=Discharge"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_15() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是放电车辆S4 默认为检测状态,当整车判断为V2V 场景,放电车辆？", "must_include": "放电车辆S4 默认为检测状态,当整车判断为V2V 场景,放电车辆", "retrieval_must_hit": ["放电车辆S4 默认为检测状态,当整车判断为V2V 场景,放电车辆"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["放电车辆S4 默认为检测状态,当整车判断为V2V 场景,放电车辆"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_16() -> None:
    case = '{"kind": "retrieval_quality", "query": "DOC-000015中放电车辆S4 默认为检测状态,当整车判断为V2V 场景,放电车辆的定义是什么？", "must_include": "放电车辆S4 默认为检测状态,当整车判断为V2V 场景,放电车辆", "retrieval_must_hit": ["放电车辆S4 默认为检测状态,当整车判断为V2V 场景,放电车辆"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["放电车辆S4 默认为检测状态,当整车判断为V2V 场景,放电车辆"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_17() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是E4U1 需求？", "must_include": "E4U1 需求", "retrieval_must_hit": ["E4U1 需求"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["E4U1 需求"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_18() -> None:
    case = '{"kind": "retrieval_quality", "query": "DOC-000015中E4U1 需求的定义是什么？", "must_include": "E4U1 需求", "retrieval_must_hit": ["E4U1 需求"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["E4U1 需求"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_19() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是内容当系统唤醒后,INIT 为默认的初始状态？", "must_include": "内容当系统唤醒后,INIT 为默认的初始状态", "retrieval_must_hit": ["内容当系统唤醒后,INIT 为默认的初始状态"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["内容当系统唤醒后,INIT 为默认的初始状态"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_20() -> None:
    case = '{"kind": "retrieval_quality", "query": "DOC-000015中内容当系统唤醒后,INIT 为默认的初始状态的定义是什么？", "must_include": "内容当系统唤醒后,INIT 为默认的初始状态", "retrieval_must_hit": ["内容当系统唤醒后,INIT 为默认的初始状态"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["内容当系统唤醒后,INIT 为默认的初始状态"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_21() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是如果在standby 状态下,收到VCUDCDCModReq=Boost 且DCDC 无？", "must_include": "如果在standby 状态下,收到VCUDCDCModReq=Boost 且DCDC 无", "retrieval_must_hit": ["如果在standby 状态下,收到VCUDCDCModReq=Boost 且DCDC 无"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["如果在standby 状态下,收到VCUDCDCModReq=Boost 且DCDC 无"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_22() -> None:
    case = '{"kind": "retrieval_quality", "query": "DOC-000015中如果在standby 状态下,收到VCUDCDCModReq=Boost 且DCDC 无的定义是什么？", "must_include": "如果在standby 状态下,收到VCUDCDCModReq=Boost 且DCDC 无", "retrieval_must_hit": ["如果在standby 状态下,收到VCUDCDCModReq=Boost 且DCDC 无"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["如果在standby 状态下,收到VCUDCDCModReq=Boost 且DCDC 无"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_23() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是故障发生且DCDCUActHv<60V,则DCDC 在一定时间内(具体参考？", "must_include": "故障发生且DCDCUActHv<60V,则DCDC 在一定时间内(具体参考", "retrieval_must_hit": ["故障发生且DCDCUActHv<60V,则DCDC 在一定时间内(具体参考"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["故障发生且DCDCUActHv<60V,则DCDC 在一定时间内(具体参考"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_24() -> None:
    case = '{"kind": "retrieval_quality", "query": "DOC-000015中故障发生且DCDCUActHv<60V,则DCDC 在一定时间内(具体参考的定义是什么？", "must_include": "故障发生且DCDCUActHv<60V,则DCDC 在一定时间内(具体参考", "retrieval_must_hit": ["故障发生且DCDCUActHv<60V,则DCDC 在一定时间内(具体参考"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["故障发生且DCDCUActHv<60V,则DCDC 在一定时间内(具体参考"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_25() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是无故障发生且DCDCUActHV>400V(tbc),则DCDC 在一定时间内？", "must_include": "无故障发生且DCDCUActHV>400V(tbc),则DCDC 在一定时间内", "retrieval_must_hit": ["无故障发生且DCDCUActHV>400V(tbc),则DCDC 在一定时间内"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["无故障发生且DCDCUActHV>400V(tbc),则DCDC 在一定时间内"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_26() -> None:
    case = '{"kind": "retrieval_quality", "query": "DOC-000015中无故障发生且DCDCUActHV>400V(tbc),则DCDC 在一定时间内的定义是什么？", "must_include": "无故障发生且DCDCUActHV>400V(tbc),则DCDC 在一定时间内", "retrieval_must_hit": ["无故障发生且DCDCUActHV>400V(tbc),则DCDC 在一定时间内"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["无故障发生且DCDCUActHV>400V(tbc),则DCDC 在一定时间内"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_27() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是VCUDCDCModReq!=Buck,则DCDC 在一定时间内(具体参考状？", "must_include": "VCUDCDCModReq!=Buck,则DCDC 在一定时间内(具体参考状", "retrieval_must_hit": ["VCUDCDCModReq!=Buck,则DCDC 在一定时间内(具体参考状"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["VCUDCDCModReq!=Buck,则DCDC 在一定时间内(具体参考状"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_28() -> None:
    case = '{"kind": "retrieval_quality", "query": "DOC-000015中VCUDCDCModReq!=Buck,则DCDC 在一定时间内(具体参考状的定义是什么？", "must_include": "VCUDCDCModReq!=Buck,则DCDC 在一定时间内(具体参考状", "retrieval_must_hit": ["VCUDCDCModReq!=Buck,则DCDC 在一定时间内(具体参考状"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["VCUDCDCModReq!=Buck,则DCDC 在一定时间内(具体参考状"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_29() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是如果在Ready 状态下,检测到DCDCUActHv<60V 且无故障发生,？", "must_include": "如果在Ready 状态下,检测到DCDCUActHv<60V 且无故障发生,", "retrieval_must_hit": ["如果在Ready 状态下,检测到DCDCUActHv<60V 且无故障发生,"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["如果在Ready 状态下,检测到DCDCUActHv<60V 且无故障发生,"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_30() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是DCDCUActHV>400V(tbc,cal)且VCUDCDCModReq!=Active？", "must_include": "DCDCUActHV>400V(tbc,cal)且VCUDCDCModReq!=Active", "retrieval_must_hit": ["DCDCUActHV>400V(tbc,cal)且VCUDCDCModReq!=Active"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["DCDCUActHV>400V(tbc,cal)且VCUDCDCModReq!=Active"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_31() -> None:
    case = '{"kind": "retrieval_quality", "query": "DOC-000015中DCDCUActHV>400V(tbc,cal)且VCUDCDCModReq!=Active的定义是什么？", "must_include": "DCDCUActHV>400V(tbc,cal)且VCUDCDCModReq!=Active", "retrieval_must_hit": ["DCDCUActHV>400V(tbc,cal)且VCUDCDCModReq!=Active"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["DCDCUActHV>400V(tbc,cal)且VCUDCDCModReq!=Active"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_32() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是tbc)且VCUDCDCModReq!=Active discharge,则DCDC 一定时间？", "must_include": "tbc)且VCUDCDCModReq!=Active discharge,则DCDC 一定时间", "retrieval_must_hit": ["tbc)且VCUDCDCModReq!=Active discharge,则DCDC 一定时间"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["tbc)且VCUDCDCModReq!=Active discharge,则DCDC 一定时间"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_33() -> None:
    case = '{"kind": "retrieval_quality", "query": "DOC-000015中tbc)且VCUDCDCModReq!=Active discharge,则DCDC 一定时间的定义是什么？", "must_include": "tbc)且VCUDCDCModReq!=Active discharge,则DCDC 一定时间", "retrieval_must_hit": ["tbc)且VCUDCDCModReq!=Active discharge,则DCDC 一定时间"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["tbc)且VCUDCDCModReq!=Active discharge,则DCDC 一定时间"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_34() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是类别800V,逻辑功能？", "must_include": "类别800V,逻辑功能", "retrieval_must_hit": ["类别800V,逻辑功能"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["类别800V,逻辑功能"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_35() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是a.在Boost 模式下收到Buck 指令,需要直接根据指令做状态切？", "must_include": "a.在Boost 模式下收到Buck 指令,需要直接根据指令做状态切", "retrieval_must_hit": ["a.在Boost 模式下收到Buck 指令,需要直接根据指令做状态切"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["a.在Boost 模式下收到Buck 指令,需要直接根据指令做状态切"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_36() -> None:
    case = '{"kind": "evidence", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：VAVE CCU 项目:CCU 软件功能开发需求规格书", "must_include": "VAVE CCU 项目:CCU 软件功能开发需求规格书", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_37() -> None:
    case = '{"kind": "evidence", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：1.本文件为《Appendix T2_Software Development Re", "must_include": "1.本文件为《Appendix T2_Software Development Re", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_38() -> None:
    case = '{"kind": "evidence", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：规范》的补充,说明软件功能开发需求细节,会随着项目开发的实际需要进行适时调整。", "must_include": "规范》的补充,说明软件功能开发需求细节,会随着项目开发的实际需要进行适时调整。", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_39() -> None:
    case = '{"kind": "evidence", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：2.本文中涉及的信号表述为参考表述,具体信号名称以小米释放的DBC 文件为准。", "must_include": "2.本文中涉及的信号表述为参考表述,具体信号名称以小米释放的DBC 文件为准。", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_40() -> None:
    case = '{"kind": "evidence", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：3.本文中描述的功能安全需求,需要结合《Appendix T2_Software D", "must_include": "3.本文中描述的功能安全需求,需要结合《Appendix T2_Software D", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_41() -> None:
    case = '{"kind": "evidence", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：Requirement Specification 软件开发需求规范》一起实施,实际", "must_include": "Requirement Specification 软件开发需求规范》一起实施,实际", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_42() -> None:
    case = '{"kind": "evidence", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：2/148 Change History 版本 日期 描述 作者 V1.0 2023", "must_include": "2/148 Change History 版本 日期 描述 作者 V1.0 2023", "source": "local", "assert_mode": "context_contains", "page_no": 2, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_43() -> None:
    case = '{"kind": "evidence", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：薛鹏 V1.1 2024.1.4 智能诊断ECUs 相关需求升版V2-V3,更新描述", "must_include": "薛鹏 V1.1 2024.1.4 智能诊断ECUs 相关需求升版V2-V3,更新描述", "source": "local", "assert_mode": "context_contains", "page_no": 2, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_44() -> None:
    case = '{"kind": "evidence", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：薛鹏 V1,2 2024.1.5 添加附A 需求章节2、更新3.2.2.1 Note", "must_include": "薛鹏 V1,2 2024.1.5 添加附A 需求章节2、更新3.2.2.1 Note", "source": "local", "assert_mode": "context_contains", "page_no": 2, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_45() -> None:
    case = '{"kind": "evidence", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：修改SC40001 电子锁解锁执行电子锁解锁时间 描述。", "must_include": "修改SC40001 电子锁解锁执行电子锁解锁时间 描述。", "source": "local", "assert_mode": "context_contains", "page_no": 2, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_46() -> None:
    case = '{"kind": "evidence", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：薛鹏 V1.4//V1.0.0 2024.3.25 添加10 添加高压互锁需求 薛鹏", "must_include": "薛鹏 V1.4//V1.0.0 2024.3.25 添加10 添加高压互锁需求 薛鹏", "source": "local", "assert_mode": "context_contains", "page_no": 2, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_47() -> None:
    case = '{"kind": "evidence", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：Note:SC40029,SC4400074 明确需要实现", "must_include": "Note:SC40029,SC4400074 明确需要实现", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_48() -> None:
    case = '{"kind": "evidence", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：SC40061&SC41039 :暂时沿用MX11 的偏离申", "must_include": "SC40061&SC41039 :暂时沿用MX11 的偏离申", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_49() -> None:
    case = '{"kind": "evidence", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：SC40010:暂时沿用的MX11 的策略,该语句中", "must_include": "SC40010:暂时沿用的MX11 的策略,该语句中", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_50() -> None:
    case = '{"kind": "definition", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：什么是Overview？", "must_include": "Overview", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_51() -> None:
    case = '{"kind": "definition_detail", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：Overview 的定义是什么？", "must_include": "基础技术定义了全局诊断快照数据,用于所有支持存储DTC 的ECU 记录故障发生时的整", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_52() -> None:
    case = '{"kind": "definition_detail", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：Overview 的定义是什么？", "must_include": "控制器刷写前置条件判定是控制器从非编程会话向编程会话跳转的必要步骤。当刷写前置条件", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_53() -> None:
    case = '{"kind": "definition", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：什么是在受损车辆或单一控制器刷写的场景中,如果用于刷新前置条件判断的信号(如车速或整车主？", "must_include": "在受损车辆或单一控制器刷写的场景中,如果用于刷新前置条件判断的信号(如车速或整车主", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_54() -> None:
    case = '{"kind": "definition", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：什么是C. CP 信号由常电平变更为PWM 信号？", "must_include": "C. CP 信号由常电平变更为PWM 信号", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_55() -> None:
    case = '{"kind": "definition", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：什么是过OBCAcUActL1、OBCAcUActL2、OBCAcUActL3 发送交流电压有效？", "must_include": "过OBCAcUActL1、OBCAcUActL2、OBCAcUActL3 发送交流电压有效", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_56() -> None:
    case = '{"kind": "definition_detail", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：过OBCAcUActL1、OBCAcUActL2、OBCAcUActL3 发送交流电压有效 的定义是什么？", "must_include": "值,并参考下表通过OBCACVoltSts 反馈桩端交流电压类型。", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_57() -> None:
    case = '{"kind": "definition", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：什么是DrtOBCHvdcUAbnorm=True？", "must_include": "DrtOBCHvdcUAbnorm=True", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_58() -> None:
    case = '{"kind": "definition_detail", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：DrtOBCHvdcUAbnorm=True 的定义是什么？", "must_include": "当因为是冷却液温度导致的充电降额时:DrtOBCCooltTAbnorm=True", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_59() -> None:
    case = '{"kind": "definition", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：什么是OBCAcU3Frq 当前L3 交流电压频率？", "must_include": "OBCAcU3Frq 当前L3 交流电压频率", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_60() -> None:
    case = '{"kind": "definition_detail", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：OBCAcU3Frq 当前L3 交流电压频率 的定义是什么？", "must_include": "OBCPFCoutCurAct PFC 输出电流(用于售后故障排查)", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_61() -> None:
    case = '{"kind": "section", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：在该文档中，是否包含“逻辑功能需求”这一章节？", "must_include": "逻辑功能需求", "source": "local", "assert_mode": "context_contains", "page_no": 14, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_62() -> None:
    case = '{"kind": "section", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：在该文档中，是否包含“SC03-网络管理”这一章节？", "must_include": "SC03-网络管理", "source": "local", "assert_mode": "context_contains", "page_no": 15, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_63() -> None:
    case = '{"kind": "section", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：在该文档中，是否包含“信号收发汇总”这一章节？", "must_include": "信号收发汇总", "source": "local", "assert_mode": "context_contains", "page_no": 62, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_64() -> None:
    case = '{"kind": "section", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：在该文档中，是否包含“ms 断开交流放电回路,然后将开关S1 切换到+12V 连接状态,”这一章节？", "must_include": "ms 断开交流放电回路,然后将开关S1 切换到+12V 连接状态,", "source": "local", "assert_mode": "context_contains", "page_no": 90, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000015_golden_65() -> None:
    case = '{"kind": "section", "query": "CCU软件功能开发需求规格书-VAVE项目_V3.0_20251125：在该文档中，是否包含“SC44033 V1 网络管理需求”这一章节？", "must_include": "SC44033 V1 网络管理需求", "source": "local", "assert_mode": "context_contains", "page_no": 110, "target_doc_id": "DOC-000015"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_66() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是平,当检测1 电压为9V,放电车辆将S1 切换为PWM 模式,检点1？", "must_include": "平,当检测1 电压为9V,放电车辆将S1 切换为PWM 模式,检点1", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "term_definition", "page_no": 86, "coverage_unit_id": "DOC-000015_definition_86_11", "coverage_semantic_key": "平,当检测1 电压为9V,放电车辆将S1 切换为PWM 模式,检点1"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_67() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是增加预充电压的校验和调整？", "must_include": "增加预充电压的校验和调整", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "term_definition", "page_no": 114, "coverage_unit_id": "DOC-000015_definition_114_9", "coverage_semantic_key": "增加预充电压的校验和调整"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_68() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是压,则系统停止预充,并进入standby 模式,并将预充超时故障置？", "must_include": "压,则系统停止预充,并进入standby 模式,并将预充超时故障置", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "term_definition", "page_no": 115, "coverage_unit_id": "DOC-000015_definition_115_7", "coverage_semantic_key": "压,则系统停止预充,并进入standby 模式,并将预充超时故障置"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_69() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是VCUDCDCModReq=Buck mode request,DCDC 接收到该请求后,并？", "must_include": "VCUDCDCModReq=Buck mode request,DCDC 接收到该请求后,并", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "term_definition", "page_no": 117, "coverage_unit_id": "DOC-000015_definition_117_7", "coverage_semantic_key": "VCUDCDCModReq=Buck mode request,DCDC 接收到该请求后,并"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_70() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是当前流量、入水口温度信息,实时计算并请求所需的最低流量请求值？", "must_include": "当前流量、入水口温度信息,实时计算并请求所需的最低流量请求值", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "term_definition", "page_no": 123, "coverage_unit_id": "DOC-000015_definition_123_16", "coverage_semantic_key": "当前流量、入水口温度信息,实时计算并请求所需的最低流量请求值"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_71() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是内容因为温度或者电压或其他客观条件超过运行范围而导致主动进行保护？", "must_include": "内容因为温度或者电压或其他客观条件超过运行范围而导致主动进行保护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "term_definition", "page_no": 130, "coverage_unit_id": "DOC-000015_definition_130_21", "coverage_semantic_key": "内容因为温度或者电压或其他客观条件超过运行范围而导致主动进行保护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_72() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是DTC 码实时上报？", "must_include": "DTC 码实时上报", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "term_definition", "page_no": 133, "coverage_unit_id": "DOC-000015_definition_133_55", "coverage_semantic_key": "DTC 码实时上报"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_73() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是流端的电压值？", "must_include": "流端的电压值", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "term_definition", "page_no": 139, "coverage_unit_id": "DOC-000015_definition_139_11", "coverage_semantic_key": "流端的电压值"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_74() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是电流符号\\"-\\",表示电流从低压电池流出进入系统？", "must_include": "电流符号\\"-\\",表示电流从低压电池流出进入系统", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "term_definition", "page_no": 139, "coverage_unit_id": "DOC-000015_definition_139_15", "coverage_semantic_key": "电流符号\\"-\\",表示电流从低压电池流出进入系统"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_75() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是电流符号\\"-\\",表示电流从系统流出进入电池？", "must_include": "电流符号\\"-\\",表示电流从系统流出进入电池", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "term_definition", "page_no": 139, "coverage_unit_id": "DOC-000015_definition_139_9", "coverage_semantic_key": "电流符号\\"-\\",表示电流从系统流出进入电池"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_76() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是CM-KES-04]为了保证整车密钥的安全性以及满足整车业务要求,车端需集成小米汽车提供的？", "must_include": "CM-KES-04]为了保证整车密钥的安全性以及满足整车业务要求,车端需集成小米汽车提供的", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "term_definition", "page_no": 143, "coverage_unit_id": "DOC-000015_definition_143_20", "coverage_semantic_key": "CM-KES-04]为了保证整车密钥的安全性以及满足整车业务要求,车端需集成小米汽车提供的"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_77() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是用户体验项描述时间指标？", "must_include": "用户体验项描述时间指标", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "term_definition", "page_no": 147, "coverage_unit_id": "DOC-000015_definition_147_15", "coverage_semantic_key": "用户体验项描述时间指标"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_78() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是OBC 停机,电流输出<1A ,然后发出驱动电子锁解锁,此过程[S3 按？", "must_include": "OBC 停机,电流输出<1A ,然后发出驱动电子锁解锁,此过程[S3 按", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "term_definition", "page_no": 148, "coverage_unit_id": "DOC-000015_definition_148_8", "coverage_semantic_key": "OBC 停机,电流输出<1A ,然后发出驱动电子锁解锁,此过程[S3 按"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_79() -> None:
    case = '{"kind": "coverage_requirement", "query": "E2E 故障诊断与响应有哪些要求？", "must_include": "E2E 故障诊断与响应", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 9, "coverage_unit_id": "DOC-000015:requirement:9:362585E5EEB3", "coverage_semantic_key": "E2E 故障诊断与响应"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_80() -> None:
    case = '{"kind": "coverage_requirement", "query": "架构哨兵功耗优化- CCU 需求有哪些要求？", "must_include": "架构哨兵功耗优化- CCU 需求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 16, "coverage_unit_id": "DOC-000015_requirement_16_14", "coverage_semantic_key": "架构哨兵功耗优化- CCU 需求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_81() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC03002 V3 Overview有哪些要求？", "must_include": "SC03002 V3 Overview", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 17, "coverage_unit_id": "DOC-000015:requirement:17:A6950D766B8F", "coverage_semantic_key": "SC03002 V3 Overview"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_82() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC03003 REQ001 V2 主动唤醒网络和休眠有哪些要求？", "must_include": "SC03003 REQ001 V2 主动唤醒网络和休眠", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 17, "coverage_unit_id": "DOC-000015_requirement_17_26", "coverage_semantic_key": "SC03003 REQ001 V2 主动唤醒网络和休眠"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_83() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC03014 REQ003 V2 sAUTOSAR CAN 网络管理配置有哪些要求？", "must_include": "SC03014 REQ003 V2 sAUTOSAR CAN 网络管理配置", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 20, "coverage_unit_id": "DOC-000015_requirement_20_13", "coverage_semantic_key": "SC03014 REQ003 V2 sAUTOSAR CAN 网络管理配置"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_84() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC03005 REQ004 V2 输出保持唤醒原因有哪些要求？", "must_include": "SC03005 REQ004 V2 输出保持唤醒原因", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 21, "coverage_unit_id": "DOC-000015_requirement_21_18", "coverage_semantic_key": "SC03005 REQ004 V2 输出保持唤醒原因"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_85() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC03015 REQ005 V3 进入OFF 后一段时间停止请求CAN 网络有哪些要求？", "must_include": "SC03015 REQ005 V3 进入OFF 后一段时间停止请求CAN 网络", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 22, "coverage_unit_id": "DOC-000015_requirement_22_19", "coverage_semantic_key": "SC03015 REQ005 V3 进入OFF 后一段时间停止请求CAN 网络"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_86() -> None:
    case = '{"kind": "coverage_requirement", "query": "进制数据发出有哪些要求？", "must_include": "进制数据发出", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 22, "coverage_unit_id": "DOC-000015_requirement_22_10", "coverage_semantic_key": "进制数据发出"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_87() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC40021 V6 OBC 插枪唤醒有哪些要求？", "must_include": "SC40021 V6 OBC 插枪唤醒", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 27, "coverage_unit_id": "DOC-000015_requirement_27_20", "coverage_semantic_key": "SC40021 V6 OBC 插枪唤醒"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_88() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC40024 V3 反馈桩端电压有哪些要求？", "must_include": "SC40024 V3 反馈桩端电压", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 30, "coverage_unit_id": "DOC-000015_requirement_30_10", "coverage_semantic_key": "SC40024 V3 反馈桩端电压"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_89() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC40029 V5 反馈OBC 功率能力有哪些要求？", "must_include": "SC40029 V5 反馈OBC 功率能力", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 32, "coverage_unit_id": "DOC-000015_requirement_32_23", "coverage_semantic_key": "SC40029 V5 反馈OBC 功率能力"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_90() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC40026 V5 OBC 输出功率有哪些要求？", "must_include": "SC40026 V5 OBC 输出功率", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 36, "coverage_unit_id": "DOC-000015_requirement_36_3", "coverage_semantic_key": "SC40026 V5 OBC 输出功率"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_91() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC40034 V2 故障等级信息上报有哪些要求？", "must_include": "SC40034 V2 故障等级信息上报", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 46, "coverage_unit_id": "DOC-000015_requirement_46_10", "coverage_semantic_key": "SC40034 V2 故障等级信息上报"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_92() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC40025 V3 故障详细信息上报有哪些要求？", "must_include": "SC40025 V3 故障详细信息上报", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 47, "coverage_unit_id": "DOC-000015_requirement_47_10", "coverage_semantic_key": "SC40025 V3 故障详细信息上报"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_93() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC40053 V4 PT-CAN 通讯故障响应(E4 更新)有哪些要求？", "must_include": "SC40053 V4 PT-CAN 通讯故障响应(E4 更新)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 47, "coverage_unit_id": "DOC-000015_requirement_47_20", "coverage_semantic_key": "SC40053 V4 PT-CAN 通讯故障响应(E4 更新)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_94() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC40003 V4 OBC 停止充电有哪些要求？", "must_include": "SC40003 V4 OBC 停止充电", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 49, "coverage_unit_id": "DOC-000015:requirement:49:4D3854E8FF73", "coverage_semantic_key": "SC40003 V4 OBC 停止充电"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_95() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC40062 FSR06 V1 OBC 应正确响应VCCD 的停止功率输出请求有哪些要求？", "must_include": "SC40062 FSR06 V1 OBC 应正确响应VCCD 的停止功率输出请求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 51, "coverage_unit_id": "DOC-000015_requirement_51_13", "coverage_semantic_key": "SC40062 FSR06 V1 OBC 应正确响应VCCD 的停止功率输出请求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_96() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC40022 V8 sCC 和CP 信号检测有哪些要求？", "must_include": "SC40022 V8 sCC 和CP 信号检测", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 55, "coverage_unit_id": "DOC-000015_requirement_55_20", "coverage_semantic_key": "SC40022 V8 sCC 和CP 信号检测"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_97() -> None:
    case = '{"kind": "coverage_requirement", "query": "表A.3 判断接口连接状态和电缆容量有哪些要求？", "must_include": "表A.3 判断接口连接状态和电缆容量", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 57, "coverage_unit_id": "DOC-000015:requirement:57:EBAEA4E9E472", "coverage_semantic_key": "表A.3 判断接口连接状态和电缆容量"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_98() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC4000065 V1 充、放电线缆电流能力识别及上报(E3)有哪些要求？", "must_include": "SC4000065 V1 充、放电线缆电流能力识别及上报(E3)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 59, "coverage_unit_id": "DOC-000015_requirement_59_4", "coverage_semantic_key": "SC4000065 V1 充、放电线缆电流能力识别及上报(E3)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_99() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC40001 V6 电子锁解锁执行有哪些要求？", "must_include": "SC40001 V6 电子锁解锁执行", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 61, "coverage_unit_id": "DOC-000015_requirement_61_13", "coverage_semantic_key": "SC40001 V6 电子锁解锁执行"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_100() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC40036 V2 S 紧急碰撞下的交流充电(E3)有哪些要求？", "must_include": "SC40036 V2 S 紧急碰撞下的交流充电(E3)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 61, "coverage_unit_id": "DOC-000015_requirement_61_30", "coverage_semantic_key": "SC40036 V2 S 紧急碰撞下的交流充电(E3)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_101() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC40045 V7 S 执行电子锁上锁有哪些要求？", "must_include": "SC40045 V7 S 执行电子锁上锁", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 65, "coverage_unit_id": "DOC-000015_requirement_65_25", "coverage_semantic_key": "SC40045 V7 S 执行电子锁上锁"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_102() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC41001 V3 OBC 插枪唤醒(CCU)有哪些要求？", "must_include": "SC41001 V3 OBC 插枪唤醒(CCU)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 67, "coverage_unit_id": "DOC-000015_requirement_67_11", "coverage_semantic_key": "SC41001 V3 OBC 插枪唤醒(CCU)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_103() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC41015 V3 执行电子锁上锁(CCU)有哪些要求？", "must_include": "SC41015 V3 执行电子锁上锁(CCU)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 70, "coverage_unit_id": "DOC-000015_requirement_70_13", "coverage_semantic_key": "SC41015 V3 执行电子锁上锁(CCU)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_104() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC41024 V1 SS 放电中OBC 反馈信息(CCU)有哪些要求？", "must_include": "SC41024 V1 SS 放电中OBC 反馈信息(CCU)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 74, "coverage_unit_id": "DOC-000015_requirement_74_20", "coverage_semantic_key": "SC41024 V1 SS 放电中OBC 反馈信息(CCU)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_105() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC41025 V1 故障等级信息上报有哪些要求？", "must_include": "SC41025 V1 故障等级信息上报", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 75, "coverage_unit_id": "DOC-000015_requirement_75_13", "coverage_semantic_key": "SC41025 V1 故障等级信息上报"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_106() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC41026 V2 故障详细信息上报有哪些要求？", "must_include": "SC41026 V2 故障详细信息上报", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 76, "coverage_unit_id": "DOC-000015_requirement_76_10", "coverage_semantic_key": "SC41026 V2 故障详细信息上报"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_107() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC41027 V3 PT-CAN 通讯故障响应(E4 更新)有哪些要求？", "must_include": "SC41027 V3 PT-CAN 通讯故障响应(E4 更新)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 76, "coverage_unit_id": "DOC-000015_requirement_76_18", "coverage_semantic_key": "SC41027 V3 PT-CAN 通讯故障响应(E4 更新)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_108() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC41035 V1 绝缘检测故障有哪些要求？", "must_include": "SC41035 V1 绝缘检测故障", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 77, "coverage_unit_id": "DOC-000015_requirement_77_19", "coverage_semantic_key": "SC41035 V1 绝缘检测故障"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_109() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC41003 V4 CC 和CP 信号检测(E4)有哪些要求？", "must_include": "SC41003 V4 CC 和CP 信号检测(E4)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 79, "coverage_unit_id": "DOC-000015:requirement:79:258748C9BC81", "coverage_semantic_key": "SC41003 V4 CC 和CP 信号检测(E4)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_110() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC41030 V5 OBC 停止放电(CCU,E4 更新)有哪些要求？", "must_include": "SC41030 V5 OBC 停止放电(CCU,E4 更新)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 89, "coverage_unit_id": "DOC-000015_requirement_89_20", "coverage_semantic_key": "SC41030 V5 OBC 停止放电(CCU,E4 更新)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_111() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC41032 V3 电子锁解锁执行(CCU)有哪些要求？", "must_include": "SC41032 V3 电子锁解锁执行(CCU)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 92, "coverage_unit_id": "DOC-000015_requirement_92_5", "coverage_semantic_key": "SC41032 V3 电子锁解锁执行(CCU)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_112() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC41033 V2 紧急碰撞下的交流放电有哪些要求？", "must_include": "SC41033 V2 紧急碰撞下的交流放电", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 92, "coverage_unit_id": "DOC-000015_requirement_92_22", "coverage_semantic_key": "SC41033 V2 紧急碰撞下的交流放电"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_113() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC41011 V5 V2L/V2V 能力上报(CCU)有哪些要求？", "must_include": "SC41011 V5 V2L/V2V 能力上报(CCU)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 96, "coverage_unit_id": "DOC-000015:requirement:96:A435D8F79FE1", "coverage_semantic_key": "SC41011 V5 V2L/V2V 能力上报(CCU)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_114() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44020 V1 模式请求管理有哪些要求？", "must_include": "SC44020 V1 模式请求管理", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 105, "coverage_unit_id": "DOC-000015_requirement_105_12", "coverage_semantic_key": "SC44020 V1 模式请求管理"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_115() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44009 V1 INIT 模式默认状态有哪些要求？", "must_include": "SC44009 V1 INIT 模式默认状态", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 106, "coverage_unit_id": "DOC-000015_requirement_106_12", "coverage_semantic_key": "SC44009 V1 INIT 模式默认状态"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_116() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44024 V2 Standby 模式管理有哪些要求？", "must_include": "SC44024 V2 Standby 模式管理", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 106, "coverage_unit_id": "DOC-000015_requirement_106_23", "coverage_semantic_key": "SC44024 V2 Standby 模式管理"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_117() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44019 V1 Boost 模式管理(E3)有哪些要求？", "must_include": "SC44019 V1 Boost 模式管理(E3)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 107, "coverage_unit_id": "DOC-000015_requirement_107_16", "coverage_semantic_key": "SC44019 V1 Boost 模式管理(E3)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_118() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44004 V3 Buck 模式管理有哪些要求？", "must_include": "SC44004 V3 Buck 模式管理", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 108, "coverage_unit_id": "DOC-000015_requirement_108_11", "coverage_semantic_key": "SC44004 V3 Buck 模式管理"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_119() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44017 V1 Ready 模式管理有哪些要求？", "must_include": "SC44017 V1 Ready 模式管理", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 109, "coverage_unit_id": "DOC-000015_requirement_109_4", "coverage_semantic_key": "SC44017 V1 Ready 模式管理"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_120() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44034 V2 Active discharge 模式管理有哪些要求？", "must_include": "SC44034 V2 Active discharge 模式管理", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 109, "coverage_unit_id": "DOC-000015_requirement_109_19", "coverage_semantic_key": "SC44034 V2 Active discharge 模式管理"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_121() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44010 V3 Boost mode management有哪些要求？", "must_include": "SC44010 V3 Boost mode management", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 112, "coverage_unit_id": "DOC-000015_requirement_112_23", "coverage_semantic_key": "SC44010 V3 Boost mode management"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_122() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44006 V3 Boost control有哪些要求？", "must_include": "SC44006 V3 Boost control", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 113, "coverage_unit_id": "DOC-000015:requirement:113:90FA5E8DB5FA", "coverage_semantic_key": "SC44006 V3 Boost control"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_123() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44002 V2 Buck control management有哪些要求？", "must_include": "SC44002 V2 Buck control management", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 117, "coverage_unit_id": "DOC-000015_requirement_117_19", "coverage_semantic_key": "SC44002 V2 Buck control management"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_124() -> None:
    case = '{"kind": "coverage_requirement", "query": "年12 月基于原需求补充逻辑有哪些要求？", "must_include": "年12 月基于原需求补充逻辑", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 123, "coverage_unit_id": "DOC-000015_requirement_123_15", "coverage_semantic_key": "年12 月基于原需求补充逻辑"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_125() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44021 V1 故障等级信息上报有哪些要求？", "must_include": "SC44021 V1 故障等级信息上报", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 129, "coverage_unit_id": "DOC-000015_requirement_129_36", "coverage_semantic_key": "SC44021 V1 故障等级信息上报"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_126() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44018 V2 降额运行反馈有哪些要求？", "must_include": "SC44018 V2 降额运行反馈", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 130, "coverage_unit_id": "DOC-000015_requirement_130_23", "coverage_semantic_key": "SC44018 V2 降额运行反馈"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_127() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44003 V2 故障详细信息上报有哪些要求？", "must_include": "SC44003 V2 故障详细信息上报", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 131, "coverage_unit_id": "DOC-000015_requirement_131_13", "coverage_semantic_key": "SC44003 V2 故障详细信息上报"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_128() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44039 V3 PT-CAN 通讯故障响应有哪些要求？", "must_include": "SC44039 V3 PT-CAN 通讯故障响应", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 131, "coverage_unit_id": "DOC-000015_requirement_131_19", "coverage_semantic_key": "SC44039 V3 PT-CAN 通讯故障响应"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_129() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44005 V1 DTC 码实时上报有哪些要求？", "must_include": "SC44005 V1 DTC 码实时上报", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 134, "coverage_unit_id": "DOC-000015_requirement_134_3", "coverage_semantic_key": "SC44005 V1 DTC 码实时上报"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_130() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44023 V3 碰撞保护下电流程(E3)有哪些要求？", "must_include": "SC44023 V3 碰撞保护下电流程(E3)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 134, "coverage_unit_id": "DOC-000015_requirement_134_20", "coverage_semantic_key": "SC44023 V3 碰撞保护下电流程(E3)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_131() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44040 V2 DCDC 主动放电有哪些要求？", "must_include": "SC44040 V2 DCDC 主动放电", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 135, "coverage_unit_id": "DOC-000015_requirement_135_17", "coverage_semantic_key": "SC44040 V2 DCDC 主动放电"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_132() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44001 V2 输出电流能力上报有哪些要求？", "must_include": "SC44001 V2 输出电流能力上报", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 138, "coverage_unit_id": "DOC-000015_requirement_138_17", "coverage_semantic_key": "SC44001 V2 输出电流能力上报"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_133() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC44011 V2 云上大数据上传有哪些要求？", "must_include": "SC44011 V2 云上大数据上传", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 140, "coverage_unit_id": "DOC-000015:requirement:140:27DE6C836F21", "coverage_semantic_key": "SC44011 V2 云上大数据上传"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_134() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC7000006 V1 硬件安全[CM-HWS-03]有哪些要求？", "must_include": "SC7000006 V1 硬件安全[CM-HWS-03]", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 142, "coverage_unit_id": "DOC-000015:requirement:142:70A4D2512DD1", "coverage_semantic_key": "SC7000006 V1 硬件安全[CM-HWS-03]"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_135() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC7000007 V1 硬件安全[CM-HWS-04]有哪些要求？", "must_include": "SC7000007 V1 硬件安全[CM-HWS-04]", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 142, "coverage_unit_id": "DOC-000015_requirement_142_18", "coverage_semantic_key": "SC7000007 V1 硬件安全[CM-HWS-04]"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_136() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC7000020 V1 非托管代码安全[CM-NCS-01]有哪些要求？", "must_include": "SC7000020 V1 非托管代码安全[CM-NCS-01]", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 145, "coverage_unit_id": "DOC-000015_requirement_145_27", "coverage_semantic_key": "SC7000020 V1 非托管代码安全[CM-NCS-01]"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_137() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC7000023 V1 漏洞升级[CM-VUS-01]有哪些要求？", "must_include": "SC7000023 V1 漏洞升级[CM-VUS-01]", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 146, "coverage_unit_id": "DOC-000015_requirement_146_22", "coverage_semantic_key": "SC7000023 V1 漏洞升级[CM-VUS-01]"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_138() -> None:
    case = '{"kind": "coverage_requirement", "query": "SC7000024 V1 漏洞升级[CM-VUS-02]有哪些要求？", "must_include": "SC7000024 V1 漏洞升级[CM-VUS-02]", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "requirement", "page_no": 147, "coverage_unit_id": "DOC-000015:requirement:147:46E3F766625B", "coverage_semantic_key": "SC7000024 V1 漏洞升级[CM-VUS-02]"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_139() -> None:
    case = '{"kind": "coverage_gap", "query": "SC41002 V1 整车网络唤醒有哪些活动？", "must_include": "SC41002 V1 整车网络唤醒", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "expected_evidence_shape": "process_activity", "page_no": 69, "coverage_unit_id": "DOC-000015_procedure_69_5", "coverage_semantic_key": "SC41002 V1 整车网络唤醒"}'
    _assert_case(json.loads(case))
