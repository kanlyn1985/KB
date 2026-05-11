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
def test_doc_000003_golden_1() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是充电 charging？", "must_include": "充电 charging", "retrieval_must_hit": ["充电 charging"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["充电 charging"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_2() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中充电 charging的定义是什么？", "must_include": "充电 charging", "retrieval_must_hit": ["充电 charging"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["充电 charging"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_3() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是充放电 bi-directional charging？", "must_include": "充放电 bi-directional charging", "retrieval_must_hit": ["充放电 bi-directional charging"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["充放电 bi-directional charging"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_4() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中充放电 bi-directional charging的定义是什么？", "must_include": "充放电 bi-directional charging", "retrieval_must_hit": ["充放电 bi-directional charging"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["充放电 bi-directional charging"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_5() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是传导充电 conductive charge？", "must_include": "传导充电 conductive charge", "retrieval_must_hit": ["传导充电 conductive charge"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["传导充电 conductive charge"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_6() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中传导充电 conductive charge的定义是什么？", "must_include": "传导充电 conductive charge", "retrieval_must_hit": ["传导充电 conductive charge"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["传导充电 conductive charge"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_7() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是充电模式 charging modes？", "must_include": "充电模式 charging modes", "retrieval_must_hit": ["充电模式 charging modes"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["充电模式 charging modes"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_8() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中充电模式 charging modes的定义是什么？", "must_include": "充电模式 charging modes", "retrieval_must_hit": ["充电模式 charging modes"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["充电模式 charging modes"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_9() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是模式 1 mode 1？", "must_include": "模式 1 mode 1", "retrieval_must_hit": ["模式 1 mode 1"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["模式 1 mode 1"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_10() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中模式 1 mode 1的定义是什么？", "must_include": "模式 1 mode 1", "retrieval_must_hit": ["模式 1 mode 1"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["模式 1 mode 1"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_11() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是电动汽车电能传输设备 EV energy transfer equipment？", "must_include": "电动汽车电能传输设备 EV energy transfer equipment", "retrieval_must_hit": ["电动汽车电能传输设备 EV energy transfer equipment"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["电动汽车电能传输设备 EV energy transfer equipment"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_12() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中电动汽车电能传输设备 EV energy transfer equipment的定义是什么？", "must_include": "电动汽车电能传输设备 EV energy transfer equipment", "retrieval_must_hit": ["电动汽车电能传输设备 EV energy transfer equipment"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["电动汽车电能传输设备 EV energy transfer equipment"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_13() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是充电设备 charging equipment？", "must_include": "充电设备 charging equipment", "retrieval_must_hit": ["充电设备 charging equipment"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["充电设备 charging equipment"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_14() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中充电设备 charging equipment的定义是什么？", "must_include": "充电设备 charging equipment", "retrieval_must_hit": ["充电设备 charging equipment"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["充电设备 charging equipment"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_15() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是充放电设备 charging and discharging equipment？", "must_include": "充放电设备 charging and discharging equipment", "retrieval_must_hit": ["充放电设备 charging and discharging equipment"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["充放电设备 charging and discharging equipment"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_16() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中充放电设备 charging and discharging equipment的定义是什么？", "must_include": "充放电设备 charging and discharging equipment", "retrieval_must_hit": ["充放电设备 charging and discharging equipment"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["充放电设备 charging and discharging equipment"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_17() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是绝缘[性能] insulation？", "must_include": "绝缘[性能] insulation", "retrieval_must_hit": ["绝缘[性能] insulation"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["绝缘[性能] insulation"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_18() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中绝缘[性能] insulation的定义是什么？", "must_include": "绝缘[性能] insulation", "retrieval_must_hit": ["绝缘[性能] insulation"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["绝缘[性能] insulation"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_19() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是基本绝缘 basic insulation？", "must_include": "基本绝缘 basic insulation", "retrieval_must_hit": ["基本绝缘 basic insulation"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["基本绝缘 basic insulation"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_20() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中基本绝缘 basic insulation的定义是什么？", "must_include": "基本绝缘 basic insulation", "retrieval_must_hit": ["基本绝缘 basic insulation"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["基本绝缘 basic insulation"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_21() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是附加绝缘 supplementary insulation？", "must_include": "附加绝缘 supplementary insulation", "retrieval_must_hit": ["附加绝缘 supplementary insulation"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["附加绝缘 supplementary insulation"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_22() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中附加绝缘 supplementary insulation的定义是什么？", "must_include": "附加绝缘 supplementary insulation", "retrieval_must_hit": ["附加绝缘 supplementary insulation"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["附加绝缘 supplementary insulation"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_23() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是保护导体 protective conductor(identification: PE)？", "must_include": "保护导体 protective conductor(identification: PE)", "retrieval_must_hit": ["保护导体 protective conductor(identification: PE)"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["保护导体 protective conductor(identification: PE)"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_24() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中保护导体 protective conductor(identification: PE)的定义是什么？", "must_include": "保护导体 protective conductor(identification: PE)", "retrieval_must_hit": ["保护导体 protective conductor(identification: PE)"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["保护导体 protective conductor(identification: PE)"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_25() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是保护联结导体 protective bonding conductor？", "must_include": "保护联结导体 protective bonding conductor", "retrieval_must_hit": ["保护联结导体 protective bonding conductor"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["保护联结导体 protective bonding conductor"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_26() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中保护联结导体 protective bonding conductor的定义是什么？", "must_include": "保护联结导体 protective bonding conductor", "retrieval_must_hit": ["保护联结导体 protective bonding conductor"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["保护联结导体 protective bonding conductor"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_27() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是接地端子 earthing terminal？", "must_include": "接地端子 earthing terminal", "retrieval_must_hit": ["接地端子 earthing terminal"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["接地端子 earthing terminal"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_28() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中接地端子 earthing terminal的定义是什么？", "must_include": "接地端子 earthing terminal", "retrieval_must_hit": ["接地端子 earthing terminal"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["接地端子 earthing terminal"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_29() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是电气隔离 galvanic separation？", "must_include": "电气隔离 galvanic separation", "retrieval_must_hit": ["电气隔离 galvanic separation"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["电气隔离 galvanic separation"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_30() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中电气隔离 galvanic separation的定义是什么？", "must_include": "电气隔离 galvanic separation", "retrieval_must_hit": ["电气隔离 galvanic separation"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["电气隔离 galvanic separation"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_31() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是保护接地 protective earthing？", "must_include": "保护接地 protective earthing", "retrieval_must_hit": ["保护接地 protective earthing"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["保护接地 protective earthing"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_32() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中保护接地 protective earthing的定义是什么？", "must_include": "保护接地 protective earthing", "retrieval_must_hit": ["保护接地 protective earthing"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["保护接地 protective earthing"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_33() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是电涌保护器 surge protective device; SPD？", "must_include": "电涌保护器 surge protective device; SPD", "retrieval_must_hit": ["电涌保护器 surge protective device; SPD"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["电涌保护器 surge protective device; SPD"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_34() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中电涌保护器 surge protective device; SPD的定义是什么？", "must_include": "电涌保护器 surge protective device; SPD", "retrieval_must_hit": ["电涌保护器 surge protective device; SPD"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["电涌保护器 surge protective device; SPD"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_35() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是感知阈 threshold of perception？", "must_include": "感知阈 threshold of perception", "retrieval_must_hit": ["感知阈 threshold of perception"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["感知阈 threshold of perception"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_36() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中感知阈 threshold of perception的定义是什么？", "must_include": "感知阈 threshold of perception", "retrieval_must_hit": ["感知阈 threshold of perception"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["感知阈 threshold of perception"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_37() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是控制导引电路 control pilot circuit？", "must_include": "控制导引电路 control pilot circuit", "retrieval_must_hit": ["控制导引电路 control pilot circuit"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["控制导引电路 control pilot circuit"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_38() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中控制导引电路 control pilot circuit的定义是什么？", "must_include": "控制导引电路 control pilot circuit", "retrieval_must_hit": ["控制导引电路 control pilot circuit"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["控制导引电路 control pilot circuit"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_39() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是控制导引功能 control pilot function; CP？", "must_include": "控制导引功能 control pilot function; CP", "retrieval_must_hit": ["控制导引功能 control pilot function; CP"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["控制导引功能 control pilot function; CP"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_40() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中控制导引功能 control pilot function; CP的定义是什么？", "must_include": "控制导引功能 control pilot function; CP", "retrieval_must_hit": ["控制导引功能 control pilot function; CP"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["控制导引功能 control pilot function; CP"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_41() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是连接确认功能 connection confirm function; CC？", "must_include": "连接确认功能 connection confirm function; CC", "retrieval_must_hit": ["连接确认功能 connection confirm function; CC"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["连接确认功能 connection confirm function; CC"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_42() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中连接确认功能 connection confirm function; CC的定义是什么？", "must_include": "连接确认功能 connection confirm function; CC", "retrieval_must_hit": ["连接确认功能 connection confirm function; CC"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["连接确认功能 connection confirm function; CC"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_43() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV？", "must_include": "燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV", "retrieval_must_hit": ["燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_44() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV的定义是什么？", "must_include": "燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV", "retrieval_must_hit": ["燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_45() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是车辆断开装置 EV disconnection device？", "must_include": "车辆断开装置 EV disconnection device", "retrieval_must_hit": ["车辆断开装置 EV disconnection device"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["车辆断开装置 EV disconnection device"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_46() -> None:
    case = '{"kind": "retrieval_quality", "query": "GB/T 18487.1—2023中车辆断开装置 EV disconnection device的定义是什么？", "must_include": "车辆断开装置 EV disconnection device", "retrieval_must_hit": ["车辆断开装置 EV disconnection device"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["车辆断开装置 EV disconnection device"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_47() -> None:
    case = '{"kind": "answer_quality", "query": "输出占空比公差是多少", "must_include": "输出占空比公差", "retrieval_must_hit": ["输出占空比公差", "—"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_48() -> None:
    case = '{"kind": "answer_quality", "query": "R1 等效电阻^d是多少", "must_include": "R1 等效电阻^d", "retrieval_must_hit": ["R1 等效电阻^d", "Ω"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_49() -> None:
    case = '{"kind": "answer_quality", "query": "R2 等效电阻^d是多少", "must_include": "R2 等效电阻^d", "retrieval_must_hit": ["R2 等效电阻^d", "Ω"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_50() -> None:
    case = '{"kind": "answer_quality", "query": "R3 等效电阻^d是多少", "must_include": "R3 等效电阻^d", "retrieval_must_hit": ["R3 等效电阻^d", "Ω"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_51() -> None:
    case = '{"kind": "answer_quality", "query": "输入占空比公差是多少", "must_include": "输入占空比公差", "retrieval_must_hit": ["输入占空比公差", "—"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_52() -> None:
    case = '{"kind": "answer_quality", "query": "R1 等效电阻是多少", "must_include": "R1 等效电阻", "retrieval_must_hit": ["R1 等效电阻", "Ω"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_53() -> None:
    case = '{"kind": "answer_quality", "query": "检测点 1 电压是多少", "must_include": "检测点 1 电压", "retrieval_must_hit": ["检测点 1 电压", "V"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_54() -> None:
    case = '{"kind": "answer_quality", "query": "R2 等效电阻是多少", "must_include": "R2 等效电阻", "retrieval_must_hit": ["R2 等效电阻", "Ω"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_55() -> None:
    case = '{"kind": "answer_quality", "query": "R3 等效电阻是多少", "must_include": "R3 等效电阻", "retrieval_must_hit": ["R3 等效电阻", "Ω"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_56() -> None:
    case = '{"kind": "answer_quality", "query": "R4 等效电阻是多少", "must_include": "R4 等效电阻", "retrieval_must_hit": ["R4 等效电阻", "Ω"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_57() -> None:
    case = '{"kind": "answer_quality", "query": "R5 等效电阻是多少", "must_include": "R5 等效电阻", "retrieval_must_hit": ["R5 等效电阻", "Ω"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_58() -> None:
    case = '{"kind": "answer_quality", "query": "检测点 2 电压是多少", "must_include": "检测点 2 电压", "retrieval_must_hit": ["检测点 2 电压", "V"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_59() -> None:
    case = '{"kind": "answer_quality", "query": "R1\' 等效电阻是多少", "must_include": "R1\' 等效电阻", "retrieval_must_hit": ["R1\' 等效电阻", "Ω"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_60() -> None:
    case = '{"kind": "answer_quality", "query": "S0 开关^c是多少", "must_include": "S0 开关^c", "retrieval_must_hit": ["S0 开关^c", "—"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_61() -> None:
    case = '{"kind": "answer_quality", "query": "Rc 等效电阻是多少", "must_include": "Rc 等效电阻", "retrieval_must_hit": ["Rc 等效电阻", "Ω"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_62() -> None:
    case = '{"kind": "answer_quality", "query": "R3\'等效电阻是多少", "must_include": "R3\'等效电阻", "retrieval_must_hit": ["R3\'等效电阻", "Ω"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_63() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023：ICS 43.040.99 CCS T 35 # GB # 中华人民共和国国家标准", "must_include": "ICS 43.040.99 CCS T 35 # GB # 中华人民共和国国家标准", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_64() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023 # 前 言 本文件按照 GB/T 1.1—202", "must_include": "GB/T 18487.1—2023 # 前 言 本文件按照 GB/T 1.1—202", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_65() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023：本文件是 GB/T 18487 的第 1 部分。GB/T 18487 已经发布了以下", "must_include": "本文件是 GB/T 18487 的第 1 部分。GB/T 18487 已经发布了以下", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_66() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023：——电动汽车传导充电系统 第 2 部分：非车载传导供电设备电磁兼容要求（GB/T 1", "must_include": "——电动汽车传导充电系统 第 2 部分：非车载传导供电设备电磁兼容要求（GB/T 1", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_67() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023：——电动车辆传导充电系统 第 3 部分：电动车辆交流/直流充电机(站)(GB/T 1", "must_include": "——电动车辆传导充电系统 第 3 部分：电动车辆交流/直流充电机(站)(GB/T 1", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_68() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023：本文件代替 GB/T 18487.1—2015《电动汽车传导充电系统 第 1 部分：", "must_include": "本文件代替 GB/T 18487.1—2015《电动汽车传导充电系统 第 1 部分：", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_69() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023 电要求(见 8.1); z) 更改了连接方式 B", "must_include": "GB/T 18487.1—2023 电要求(见 8.1); z) 更改了连接方式 B", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_70() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023 “采用 GB/T 20234.4 规定的充电连接", "must_include": "GB/T 18487.1—2023 “采用 GB/T 20234.4 规定的充电连接", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_71() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023：本文件由中国电力企业联合会提出并归口。", "must_include": "本文件由中国电力企业联合会提出并归口。", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_72() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023：本文件起草单位:国网电力科学研究院有限公司、中国电力企业联合会、国家电网有限公司、南", "must_include": "本文件起草单位:国网电力科学研究院有限公司、中国电力企业联合会、国家电网有限公司、南", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_73() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023：本文件主要起草人:张萱、倪峰、刘永东、栗文涛、董新生、李志刚、梁晓芳、武亨、郑隽一、", "must_include": "本文件主要起草人:张萱、倪峰、刘永东、栗文涛、董新生、李志刚、梁晓芳、武亨、郑隽一、", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_74() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023：本文件及其所代替文件的历次版本发布情况为: ——2001 年首次发布为 GB/T 1", "must_include": "本文件及其所代替文件的历次版本发布情况为: ——2001 年首次发布为 GB/T 1", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_75() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023 # 引 言 GB/T 18487 旨在确立电动汽", "must_include": "GB/T 18487.1—2023 # 引 言 GB/T 18487 旨在确立电动汽", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_76() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023：——第 1 部分:通用要求。目的在于规范电动汽车与非车载传导式电能传输设备需要满足的", "must_include": "——第 1 部分:通用要求。目的在于规范电动汽车与非车载传导式电能传输设备需要满足的", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_77() -> None:
    case = '{"kind": "evidence", "query": "GB/T 18487.1—2023：——第 2 部分:非车载传导供电设备电磁兼容要求。目的在于规范电动汽车非车载传导式供", "must_include": "——第 2 部分:非车载传导供电设备电磁兼容要求。目的在于规范电动汽车非车载传导式供", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_78() -> None:
    case = '{"kind": "definition", "query": "在GB/T 18487.1—2023中，什么是充电 charging？", "must_include": "充电 charging", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_79() -> None:
    case = '{"kind": "definition_detail", "query": "在GB/T 18487.1—2023中，充电 charging 的定义是什么？", "must_include": "将交流或直流供电网(电源)调整为适当的电压/电流,为电动汽车可充电储能系统提供电能。", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_80() -> None:
    case = '{"kind": "definition", "query": "在GB/T 18487.1—2023中，什么是充放电 bi-directional charging？", "must_include": "充放电 bi-directional charging", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_81() -> None:
    case = '{"kind": "definition_detail", "query": "在GB/T 18487.1—2023中，充放电 bi-directional charging 的定义是什么？", "must_include": "将交流或直流供电网(电源)调整为适当的电压/电流,为电动汽车可充电储能系统提供电能", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_82() -> None:
    case = '{"kind": "definition", "query": "在GB/T 18487.1—2023中，什么是传导充电 conductive charge？", "must_include": "传导充电 conductive charge", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_83() -> None:
    case = '{"kind": "definition_detail", "query": "在GB/T 18487.1—2023中，传导充电 conductive charge 的定义是什么？", "must_include": "利用电传导给蓄电池进行充电的方式。 [来源:GB/T 19596—2017,3.4.", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_84() -> None:
    case = '{"kind": "definition", "query": "在GB/T 18487.1—2023中，什么是充电模式 charging modes？", "must_include": "充电模式 charging modes", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_85() -> None:
    case = '{"kind": "definition_detail", "query": "在GB/T 18487.1—2023中，充电模式 charging modes 的定义是什么？", "must_include": "连接电动汽车到供电网(电源)给电动汽车供电的方法。 注:模式 1、模式 2、模式 3", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_86() -> None:
    case = '{"kind": "definition", "query": "在GB/T 18487.1—2023中，什么是模式 1 mode 1？", "must_include": "模式 1 mode 1", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_87() -> None:
    case = '{"kind": "definition_detail", "query": "在GB/T 18487.1—2023中，模式 1 mode 1 的定义是什么？", "must_include": "将电动汽车连接到供电网(电源)时,在电源侧使用了符合 GB/T 2099.1 和 G", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_88() -> None:
    case = '{"kind": "definition", "query": "在GB/T 18487.1—2023中，什么是电动汽车电能传输设备 EV energy transfer equipment？", "must_include": "电动汽车电能传输设备 EV energy transfer equipment", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_89() -> None:
    case = '{"kind": "definition_detail", "query": "在GB/T 18487.1—2023中，电动汽车电能传输设备 EV energy transfer equipment 的定义是什么？", "must_include": "连接于电动汽车与供电网(电源)之间,可实现能量流动的设备。 注 1:电动汽车电能传输", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_90() -> None:
    case = '{"kind": "definition", "query": "在GB/T 18487.1—2023中，什么是充电设备 charging equipment？", "must_include": "充电设备 charging equipment", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_91() -> None:
    case = '{"kind": "definition_detail", "query": "在GB/T 18487.1—2023中，充电设备 charging equipment 的定义是什么？", "must_include": "以传导或无线方式与电动汽车或动力蓄电池连接,为其提供电能的设备。 注:根据电动汽车与", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_92() -> None:
    case = '{"kind": "definition", "query": "在GB/T 18487.1—2023中，什么是充放电设备 charging and discharging equipment？", "must_include": "充放电设备 charging and discharging equipment", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_93() -> None:
    case = '{"kind": "definition_detail", "query": "在GB/T 18487.1—2023中，充放电设备 charging and discharging equipment 的定义是什么？", "must_include": "连接于电动汽车或动力蓄电池与电网(或负荷)之间,可实现能量双向流动的设备。 注:根据", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_94() -> None:
    case = '{"kind": "standard", "query": "GB/T 18487.1—2023 的标准号和实施日期是什么？", "must_include": "GB/T 18487.1—2023", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_95() -> None:
    case = '{"kind": "standard", "query": "GB/T 18487.1—2023 对应的标准编号是什么？", "must_include": "GB/T 18487.1—2023", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_96() -> None:
    case = '{"kind": "standard", "query": "GB/T 18487.1—2023 的现行标准号是什么？", "must_include": "GB/T 18487.1—2023", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_97() -> None:
    case = '{"kind": "publication_date", "query": "GB/T 18487.1—2023 的发布日期是什么？", "must_include": "2023-09-07", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_98() -> None:
    case = '{"kind": "publication_date", "query": "GB/T 18487.1—2023 是哪一天发布的？", "must_include": "2023-09-07", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_99() -> None:
    case = '{"kind": "effective_date", "query": "GB/T 18487.1—2023 的实施日期是什么？", "must_include": "2024-04-01", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_100() -> None:
    case = '{"kind": "effective_date", "query": "GB/T 18487.1—2023 从哪一天开始实施？", "must_include": "2024-04-01", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_101() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.1—2023中，是否包含“功能 function”这一章节？", "must_include": "功能 function", "source": "local", "assert_mode": "context_contains", "page_no": 20, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_102() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.1—2023中，是否包含“模式 2、模式 3 和模式 4 提供的功能”这一章节？", "must_include": "模式 2、模式 3 和模式 4 提供的功能", "source": "local", "assert_mode": "context_contains", "page_no": 31, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_103() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.1—2023中，是否包含“7.1.4 感知阈和惊跳反应”这一章节？", "must_include": "7.1.4 感知阈和惊跳反应", "source": "local", "assert_mode": "context_contains", "page_no": 34, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_104() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.1—2023中，是否包含“10.4 IP 防护等级”这一章节？", "must_include": "10.4 IP 防护等级", "source": "local", "assert_mode": "context_contains", "page_no": 39, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_105() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.1—2023中，是否包含“10.3 分断能力”这一章节？", "must_include": "10.3 分断能力", "source": "local", "assert_mode": "context_contains", "page_no": 39, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_106() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.1—2023中，是否包含“接触电流限值超过 3.5 mA 的特殊情况”这一章节？", "must_include": "接触电流限值超过 3.5 mA 的特殊情况", "source": "local", "assert_mode": "context_contains", "page_no": 45, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_107() -> None:
    case = '{"kind": "section", "query": "在GB/T 18487.1—2023中，是否包含“A.5 控制导引电路状态转换图和控制时序列表”这一章节？", "must_include": "A.5 控制导引电路状态转换图和控制时序列表", "source": "local", "assert_mode": "context_contains", "page_no": 65, "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_108() -> None:
    case = '{"kind": "title", "query": "GB/T 18487.1—2023 这份文档的标题是什么？", "must_include": "# 电动汽车传导充电系统", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000003"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_109() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是电缆组件 供电插头 供电插座？", "must_include": "电缆组件 供电插头 供电插座", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 11, "coverage_unit_id": "DOC-000003_definition_11_4", "coverage_semantic_key": "电缆组件 供电插头 供电插座"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_110() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是车辆插座 车辆插头 电缆组件 车辆接口？", "must_include": "车辆插座 车辆插头 电缆组件 车辆接口", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 12, "coverage_unit_id": "DOC-000003_definition_12_7", "coverage_semantic_key": "车辆插座 车辆插头 电缆组件 车辆接口"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_111() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "等效二极管压降 (2.75~10 mA, -40 ℃~+85 ℃)是多少？", "must_include": "等效二极管压降 (2.75~10 mA, -40 ℃~+85 ℃)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 53, "coverage_unit_id": "DOC-000003_table_53_3:row:12", "coverage_semantic_key": "等效二极管压降 (2.75~10 mA, -40 ℃~+85 ℃)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_112() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "输出低电压是多少？", "must_include": "输出低电压", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 53, "coverage_unit_id": "DOC-000003_table_53_3:row:2", "coverage_semantic_key": "输出低电压"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_113() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "上拉电压是多少？", "must_include": "上拉电压", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 76, "coverage_unit_id": "DOC-000003_table_76_7:row:10", "coverage_semantic_key": "上拉电压"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_114() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "Sv 开关 f是多少？", "must_include": "Sv 开关 f", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 86, "coverage_unit_id": "DOC-000003_table_86_3:row:8", "coverage_semantic_key": "Sv 开关 f"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_115() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "上拉电压 d是多少？", "must_include": "上拉电压 d", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 86, "coverage_unit_id": "DOC-000003_table_86_3:row:5", "coverage_semantic_key": "上拉电压 d"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_116() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "等效二极管压降 g (2.75 mA~10 mA, -40 ℃~+85 ℃)是多少？", "must_include": "等效二极管压降 g (2.75 mA~10 mA, -40 ℃~+85 ℃)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 86, "coverage_unit_id": "DOC-000003_table_86_3:row:9", "coverage_semantic_key": "等效二极管压降 g (2.75 mA~10 mA, -40 ℃~+85 ℃)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_117() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "开关 1是多少？", "must_include": "开关 1", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 98, "coverage_unit_id": "DOC-000003_table_98_2:row:6", "coverage_semantic_key": "开关 1"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_118() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "开关 2是多少？", "must_include": "开关 2", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 98, "coverage_unit_id": "DOC-000003_table_98_2:row:8", "coverage_semantic_key": "开关 2"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_119() -> None:
    case = '{"kind": "coverage_requirement", "query": "规范性引用文件有哪些要求？", "must_include": "规范性引用文件", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 8, "coverage_unit_id": "DOC-000003_requirement_8_7", "coverage_semantic_key": "规范性引用文件"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_120() -> None:
    case = '{"kind": "coverage_requirement", "query": "电动汽车交流充电系统 AC electric vehicle charging system 为电动汽车车载充电机提供交流电源的充电系统有哪些要求？", "must_include": "电动汽车交流充电系统 AC electric vehicle charging system 为电动汽车车载充电机提供交流电源的充电系统", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 16, "coverage_unit_id": "DOC-000003_requirement_16_4", "coverage_semantic_key": "电动汽车交流充电系统 AC electric vehicle charging system 为电动汽车车载充电机提供交流电源的充电系统"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_121() -> None:
    case = '{"kind": "coverage_requirement", "query": "测试负载 test load 特定测试条件下模拟电动汽车动力蓄电池的装置有哪些要求？", "must_include": "测试负载 test load 特定测试条件下模拟电动汽车动力蓄电池的装置", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 22, "coverage_unit_id": "DOC-000003_requirement_22_10", "coverage_semantic_key": "测试负载 test load 特定测试条件下模拟电动汽车动力蓄电池的装置"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_122() -> None:
    case = '{"kind": "coverage_requirement", "query": "供电设备输出有哪些要求？", "must_include": "供电设备输出", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 30, "coverage_unit_id": "DOC-000003_requirement_30_12", "coverage_semantic_key": "供电设备输出"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_123() -> None:
    case = '{"kind": "coverage_requirement", "query": "保护接地导体连续性的持续监测有哪些要求？", "must_include": "保护接地导体连续性的持续监测", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 31, "coverage_unit_id": "DOC-000003_requirement_31_12", "coverage_semantic_key": "保护接地导体连续性的持续监测"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_124() -> None:
    case = '{"kind": "coverage_requirement", "query": "车辆供电回路电压适应性切换功能有哪些要求？", "must_include": "车辆供电回路电压适应性切换功能", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 33, "coverage_unit_id": "DOC-000003_requirement_33_8", "coverage_semantic_key": "车辆供电回路电压适应性切换功能"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_125() -> None:
    case = '{"kind": "coverage_requirement", "query": "接触电流或接触电压的限值有哪些要求？", "must_include": "接触电流或接触电压的限值", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 34, "coverage_unit_id": "DOC-000003_requirement_34_4", "coverage_semantic_key": "接触电流或接触电压的限值"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_126() -> None:
    case = '{"kind": "coverage_requirement", "query": "限制电压防护有哪些要求？", "must_include": "限制电压防护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 35, "coverage_unit_id": "DOC-000003_requirement_35_7", "coverage_semantic_key": "限制电压防护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_127() -> None:
    case = '{"kind": "coverage_requirement", "query": "中性线有哪些要求？", "must_include": "中性线", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 38, "coverage_unit_id": "DOC-000003_requirement_38_15", "coverage_semantic_key": "中性线"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_128() -> None:
    case = '{"kind": "coverage_requirement", "query": "供电网断电有哪些要求？", "must_include": "供电网断电", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 38, "coverage_unit_id": "DOC-000003:requirement:38:930DC0BC451B", "coverage_semantic_key": "供电网断电"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_129() -> None:
    case = '{"kind": "coverage_requirement", "query": "接触器粘连有哪些要求？", "must_include": "接触器粘连", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 38, "coverage_unit_id": "DOC-000003_requirement_38_8", "coverage_semantic_key": "接触器粘连"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_130() -> None:
    case = '{"kind": "coverage_requirement", "query": "接触顺序有哪些要求？", "must_include": "接触顺序", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 38, "coverage_unit_id": "DOC-000003:requirement:38:622CC1362C2D", "coverage_semantic_key": "接触顺序"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_131() -> None:
    case = '{"kind": "coverage_requirement", "query": "模式 1 和模式 2 供电接口和车辆接口功能性说明有哪些要求？", "must_include": "模式 1 和模式 2 供电接口和车辆接口功能性说明", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 38, "coverage_unit_id": "DOC-000003:requirement:38:E84F35635D44", "coverage_semantic_key": "模式 1 和模式 2 供电接口和车辆接口功能性说明"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_132() -> None:
    case = '{"kind": "coverage_requirement", "query": "模式 3 供电接口和车辆接口的功能性说明有哪些要求？", "must_include": "模式 3 供电接口和车辆接口的功能性说明", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 38, "coverage_unit_id": "DOC-000003:requirement:38:67CA1FD62E13", "coverage_semantic_key": "模式 3 供电接口和车辆接口的功能性说明"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_133() -> None:
    case = '{"kind": "coverage_requirement", "query": "电动汽车供电设备和电动汽车之间信号电路的安全要求有哪些要求？", "must_include": "电动汽车供电设备和电动汽车之间信号电路的安全要求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 38, "coverage_unit_id": "DOC-000003_requirement_38_6", "coverage_semantic_key": "电动汽车供电设备和电动汽车之间信号电路的安全要求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_134() -> None:
    case = '{"kind": "coverage_requirement", "query": "插拔力有哪些要求？", "must_include": "插拔力", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 39, "coverage_unit_id": "DOC-000003:requirement:39:9EE1863FD08A", "coverage_semantic_key": "插拔力"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_135() -> None:
    case = '{"kind": "coverage_requirement", "query": "模式 4 车辆接口的功能性说明有哪些要求？", "must_include": "模式 4 车辆接口的功能性说明", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 39, "coverage_unit_id": "DOC-000003:requirement:39:E795A192730F", "coverage_semantic_key": "模式 4 车辆接口的功能性说明"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_136() -> None:
    case = '{"kind": "coverage_requirement", "query": "电缆加长组件有哪些要求？", "must_include": "电缆加长组件", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 39, "coverage_unit_id": "DOC-000003_requirement_39_11", "coverage_semantic_key": "电缆加长组件"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_137() -> None:
    case = '{"kind": "coverage_requirement", "query": "模式 2 和模式 3 充电接口的锁止装置有哪些要求？", "must_include": "模式 2 和模式 3 充电接口的锁止装置", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 40, "coverage_unit_id": "DOC-000003:requirement:40:2B1E187FFA38", "coverage_semantic_key": "模式 2 和模式 3 充电接口的锁止装置"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_138() -> None:
    case = '{"kind": "coverage_requirement", "query": "模式 4 充电接口的锁止装置有哪些要求？", "must_include": "模式 4 充电接口的锁止装置", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 40, "coverage_unit_id": "DOC-000003:requirement:40:46F7BD6341F8", "coverage_semantic_key": "模式 4 充电接口的锁止装置"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_139() -> None:
    case = '{"kind": "coverage_requirement", "query": "模式 4 的冲击电流有哪些要求？", "must_include": "模式 4 的冲击电流", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 40, "coverage_unit_id": "DOC-000003_requirement_40_13", "coverage_semantic_key": "模式 4 的冲击电流"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_140() -> None:
    case = '{"kind": "coverage_requirement", "query": "交流供电设备的剩余电流保护器有哪些要求？", "must_include": "交流供电设备的剩余电流保护器", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 41, "coverage_unit_id": "DOC-000003:requirement:41:224C370A116C", "coverage_semantic_key": "交流供电设备的剩余电流保护器"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_141() -> None:
    case = '{"kind": "coverage_requirement", "query": "开关和隔离开关有哪些要求？", "must_include": "开关和隔离开关", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 41, "coverage_unit_id": "DOC-000003:requirement:41:AA1E4F3EC8BB", "coverage_semantic_key": "开关和隔离开关"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_142() -> None:
    case = '{"kind": "coverage_requirement", "query": "断路器有哪些要求？", "must_include": "断路器", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 41, "coverage_unit_id": "DOC-000003:requirement:41:2B046242DCB3", "coverage_semantic_key": "断路器"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_143() -> None:
    case = '{"kind": "coverage_requirement", "query": "继电器有哪些要求？", "must_include": "继电器", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 41, "coverage_unit_id": "DOC-000003:requirement:41:6FDB21A93AEF", "coverage_semantic_key": "继电器"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_144() -> None:
    case = '{"kind": "coverage_requirement", "query": "模式 2 的防护等级有哪些要求？", "must_include": "模式 2 的防护等级", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 42, "coverage_unit_id": "DOC-000003:requirement:42:19545B9DC5F8", "coverage_semantic_key": "模式 2 的防护等级"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_145() -> None:
    case = '{"kind": "coverage_requirement", "query": "模式 3 和模式 4 的防护等级有哪些要求？", "must_include": "模式 3 和模式 4 的防护等级", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 42, "coverage_unit_id": "DOC-000003_requirement_42_11", "coverage_semantic_key": "模式 3 和模式 4 的防护等级"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_146() -> None:
    case = '{"kind": "coverage_requirement", "query": "电气间隙和爬电距离有哪些要求？", "must_include": "电气间隙和爬电距离", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 42, "coverage_unit_id": "DOC-000003_requirement_42_6", "coverage_semantic_key": "电气间隙和爬电距离"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_147() -> None:
    case = '{"kind": "coverage_requirement", "query": "电缆管理及贮存方式有哪些要求？", "must_include": "电缆管理及贮存方式", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 42, "coverage_unit_id": "DOC-000003:requirement:42:22F9523EA058", "coverage_semantic_key": "电缆管理及贮存方式"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_148() -> None:
    case = '{"kind": "coverage_requirement", "query": "输入端瞬态过压有哪些要求？", "must_include": "输入端瞬态过压", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 44, "coverage_unit_id": "DOC-000003:requirement:44:E3EAEE4B257B", "coverage_semantic_key": "输入端瞬态过压"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_149() -> None:
    case = '{"kind": "coverage_requirement", "query": "防止大气源或开关引起的瞬态过压有哪些要求？", "must_include": "防止大气源或开关引起的瞬态过压", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 44, "coverage_unit_id": "DOC-000003:requirement:44:F013D5F5D8F3", "coverage_semantic_key": "防止大气源或开关引起的瞬态过压"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_150() -> None:
    case = '{"kind": "coverage_requirement", "query": "测试网络选择有哪些要求？", "must_include": "测试网络选择", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 45, "coverage_unit_id": "DOC-000003:requirement:45:358D6E582A54", "coverage_semantic_key": "测试网络选择"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_151() -> None:
    case = '{"kind": "coverage_requirement", "query": "介电强度有哪些要求？", "must_include": "介电强度", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 46, "coverage_unit_id": "DOC-000003_requirement_46_10", "coverage_semantic_key": "介电强度"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_152() -> None:
    case = '{"kind": "coverage_requirement", "query": "绝缘电阻有哪些要求？", "must_include": "绝缘电阻", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 46, "coverage_unit_id": "DOC-000003:requirement:46:058F3DB24424", "coverage_semantic_key": "绝缘电阻"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_153() -> None:
    case = '{"kind": "coverage_requirement", "query": "冲击耐压有哪些要求？", "must_include": "冲击耐压", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 47, "coverage_unit_id": "DOC-000003:requirement:47:14F21DE2DFDE", "coverage_semantic_key": "冲击耐压"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_154() -> None:
    case = '{"kind": "coverage_requirement", "query": "极限温升有哪些要求？", "must_include": "极限温升", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 47, "coverage_unit_id": "DOC-000003_requirement_47_12", "coverage_semantic_key": "极限温升"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_155() -> None:
    case = '{"kind": "coverage_requirement", "query": "允许表面温度有哪些要求？", "must_include": "允许表面温度", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 48, "coverage_unit_id": "DOC-000003:requirement:48:0DF22737CC52", "coverage_semantic_key": "允许表面温度"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_156() -> None:
    case = '{"kind": "coverage_requirement", "query": "充电电缆的过载保护有哪些要求？", "must_include": "充电电缆的过载保护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 48, "coverage_unit_id": "DOC-000003_requirement_48_9", "coverage_semantic_key": "充电电缆的过载保护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_157() -> None:
    case = '{"kind": "coverage_requirement", "query": "雷电防护有哪些要求？", "must_include": "雷电防护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 48, "coverage_unit_id": "DOC-000003:requirement:48:ED4363708503", "coverage_semantic_key": "雷电防护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_158() -> None:
    case = '{"kind": "coverage_requirement", "query": "周围空气温度有哪些要求？", "must_include": "周围空气温度", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 49, "coverage_unit_id": "DOC-000003:requirement:49:9CFA04610DA1", "coverage_semantic_key": "周围空气温度"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_159() -> None:
    case = '{"kind": "coverage_requirement", "query": "室内设备的湿度条件有哪些要求？", "must_include": "室内设备的湿度条件", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 49, "coverage_unit_id": "DOC-000003:requirement:49:8561F8E9AA8E", "coverage_semantic_key": "室内设备的湿度条件"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_160() -> None:
    case = '{"kind": "coverage_requirement", "query": "特殊使用条件有哪些要求？", "must_include": "特殊使用条件", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 49, "coverage_unit_id": "DOC-000003_requirement_49_17", "coverage_semantic_key": "特殊使用条件"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_161() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.1.1 模式 3有哪些要求？", "must_include": "A.1.1 模式 3", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 51, "coverage_unit_id": "DOC-000003:requirement:51:DD13A175E1A6", "coverage_semantic_key": "A.1.1 模式 3"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_162() -> None:
    case = '{"kind": "coverage_requirement", "query": "附 录 B 采用 GB/T 20234.3 规定的充电连接装置的直流充电控制导引电路与控制原理有哪些要求？", "must_include": "附 录 B 采用 GB/T 20234.3 规定的充电连接装置的直流充电控制导引电路与控制原理", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 75, "coverage_unit_id": "DOC-000003:requirement:75:3D314E282B12", "coverage_semantic_key": "附 录 B 采用 GB/T 20234.3 规定的充电连接装置的直流充电控制导引电路与控制原理"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_163() -> None:
    case = '{"kind": "coverage_requirement", "query": "C.1 通则有哪些要求？", "must_include": "C.1 通则", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 84, "coverage_unit_id": "DOC-000003:requirement:84:3AAE40E6E360", "coverage_semantic_key": "C.1 通则"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_164() -> None:
    case = '{"kind": "coverage_requirement", "query": "C.2 直流充电安全保护系统有哪些要求？", "must_include": "C.2 直流充电安全保护系统", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 84, "coverage_unit_id": "DOC-000003:requirement:84:0FE870DB088C", "coverage_semantic_key": "C.2 直流充电安全保护系统"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_165() -> None:
    case = '{"kind": "coverage_requirement", "query": "C.4.3 充电连接就绪有哪些要求？", "must_include": "C.4.3 充电连接就绪", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 87, "coverage_unit_id": "DOC-000003_requirement_87_6", "coverage_semantic_key": "C.4.3 充电连接就绪"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_166() -> None:
    case = '{"kind": "coverage_requirement", "query": "C.4.5 自检阶段有哪些要求？", "must_include": "C.4.5 自检阶段", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 87, "coverage_unit_id": "DOC-000003:requirement:87:20964D810A76", "coverage_semantic_key": "C.4.5 自检阶段"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_167() -> None:
    case = '{"kind": "coverage_requirement", "query": "C.4.6 供电模式(可选功能)有哪些要求？", "must_include": "C.4.6 供电模式(可选功能)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 88, "coverage_unit_id": "DOC-000003:requirement:88:C6261DBB6542", "coverage_semantic_key": "C.4.6 供电模式(可选功能)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_168() -> None:
    case = '{"kind": "coverage_requirement", "query": "D.2 充电控制过程有哪些要求？", "must_include": "D.2 充电控制过程", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 115, "coverage_unit_id": "DOC-000003_requirement_115_7", "coverage_semantic_key": "D.2 充电控制过程"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_169() -> None:
    case = '{"kind": "coverage_requirement", "query": "D.3 电压适应性切换电路原理有哪些要求？", "must_include": "D.3 电压适应性切换电路原理", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 115, "coverage_unit_id": "DOC-000003_requirement_115_10", "coverage_semantic_key": "D.3 电压适应性切换电路原理"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_170() -> None:
    case = '{"kind": "coverage_requirement", "query": "F.2.3 系统用例有哪些要求？", "must_include": "F.2.3 系统用例", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 123, "coverage_unit_id": "DOC-000003:requirement:123:80494967FE19", "coverage_semantic_key": "F.2.3 系统用例"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_171() -> None:
    case = '{"kind": "coverage_requirement", "query": "附录B 充电桩 车辆插头 GB 车辆适配器 车辆插座 附录D 电动汽车 二选一 RCD 电流测量 C1 FUSE DC+ DC+ C5 FUSE 泄放电路 电压测量 Rload C 可充电储能系统 C2 DC有哪些要求？", "must_include": "附录B 充电桩 车辆插头 GB 车辆适配器 车辆插座 附录D 电动汽车 二选一 RCD 电流测量 C1 FUSE DC+ DC+ C5 FUSE 泄放电路 电压测量 Rload C 可充电储能系统 C2 DC", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 129, "coverage_unit_id": "DOC-000003_requirement_129_7", "coverage_semantic_key": "附录B 充电桩 车辆插头 GB 车辆适配器 车辆插座 附录D 电动汽车 二选一 RCD 电流测量 C1 FUSE DC+ DC+ C5 FUSE 泄放电路 电压测量 Rload C 可充电储能系统 C2 DC"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_172() -> None:
    case = '{"kind": "coverage_requirement", "query": "附录B 充电机 未连接 连接车辆适配器 完全连接 检测点1为 4V? 否 是 开始附录B对应的数字通信 绝缘自检 附录B规定的充电控制过程有哪些要求？", "must_include": "附录B 充电机 未连接 连接车辆适配器 完全连接 检测点1为 4V? 否 是 开始附录B对应的数字通信 绝缘自检 附录B规定的充电控制过程", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 131, "coverage_unit_id": "DOC-000003_requirement_131_3", "coverage_semantic_key": "附录B 充电机 未连接 连接车辆适配器 完全连接 检测点1为 4V? 否 是 开始附录B对应的数字通信 绝缘自检 附录B规定的充电控制过程"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_173() -> None:
    case = '{"kind": "coverage_requirement", "query": "G.3.3.1 车辆插座与车辆适配器和/或车辆插头插合有哪些要求？", "must_include": "G.3.3.1 车辆插座与车辆适配器和/或车辆插头插合", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 132, "coverage_unit_id": "DOC-000003_requirement_132_8", "coverage_semantic_key": "G.3.3.1 车辆插座与车辆适配器和/或车辆插头插合"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_174() -> None:
    case = '{"kind": "coverage_requirement", "query": "附录B充电机 车辆插头 GB车辆适配器 车辆插座 全球通用版本电动汽车 PE PE PE 车身地 U1, 12.0V S R1, 1.0kΩ R2, 1.0kΩ R3, 1.0kΩ Rc\', 1.0kΩ CC1 CC有哪些要求？", "must_include": "附录B充电机 车辆插头 GB车辆适配器 车辆插座 全球通用版本电动汽车 PE PE PE 车身地 U1, 12.0V S R1, 1.0kΩ R2, 1.0kΩ R3, 1.0kΩ Rc\', 1.0kΩ CC1 CC", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 140, "coverage_unit_id": "DOC-000003_requirement_140_5", "coverage_semantic_key": "附录B充电机 车辆插头 GB车辆适配器 车辆插座 全球通用版本电动汽车 PE PE PE 车身地 U1, 12.0V S R1, 1.0kΩ R2, 1.0kΩ R3, 1.0kΩ Rc\', 1.0kΩ CC1 CC"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_175() -> None:
    case = '{"kind": "coverage_requirement", "query": "I.2.1 结构 直流充电时,车辆接口应具有锁止装置有哪些要求？", "must_include": "I.2.1 结构 直流充电时,车辆接口应具有锁止装置", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 146, "coverage_unit_id": "DOC-000003:requirement:146:23920755CE2B", "coverage_semantic_key": "I.2.1 结构 直流充电时,车辆接口应具有锁止装置"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_176() -> None:
    case = '{"kind": "coverage_requirement", "query": "J.4.2 故障停机有哪些要求？", "must_include": "J.4.2 故障停机", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 153, "coverage_unit_id": "DOC-000003_requirement_153_9", "coverage_semantic_key": "J.4.2 故障停机"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_177() -> None:
    case = '{"kind": "coverage_requirement", "query": "J.4.3 紧急停机有哪些要求？", "must_include": "J.4.3 紧急停机", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 154, "coverage_unit_id": "DOC-000003_requirement_154_7", "coverage_semantic_key": "J.4.3 紧急停机"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_178() -> None:
    case = '{"kind": "coverage_requirement", "query": "附 录 B (规范性) 采用 GB/T 20234.3 规定的充电连接装置的直流充电控制导引电路与控制原理有哪些要求？", "must_include": "附 录 B (规范性) 采用 GB/T 20234.3 规定的充电连接装置的直流充电控制导引电路与控制原理", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 76, "coverage_unit_id": "DOC-000003:requirement:76:807AB5F188AF", "coverage_semantic_key": "附 录 B (规范性) 采用 GB/T 20234.3 规定的充电连接装置的直流充电控制导引电路与控制原理"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_179() -> None:
    case = '{"kind": "coverage_requirement", "query": "附录B 充电桩 车辆插头 GB 车辆适配器 车辆插座 附录D 电动汽车 二选一 RCD 电流测量 C1 FUSE DC+ DC+ C5 FUSE 泄放电路 电压测量 Rload C 可充电储能系统 C2 DC- DC- C6 Rload IMD 设备地 PE PE 车身地 RCD 控制电源 设备控制器 S+ S+ 车辆控制器 S- S- U1 S R3 Re\' R4\' R4c R4 U2 R1 检测点1 R2 CC1 CC1 R3\' 检测点2 S2 Rv CC2 Re\'\' C有哪些要求？", "must_include": "附录B 充电桩 车辆插头 GB 车辆适配器 车辆插座 附录D 电动汽车 二选一 RCD 电流测量 C1 FUSE DC+ DC+ C5 FUSE 泄放电路 电压测量 Rload C 可充电储能系统 C2 DC- DC- C6 Rload IMD 设备地 PE PE 车身地 RCD 控制电源 设备控制器 S+ S+ 车辆控制器 S- S- U1 S R3 Re\' R4\' R4c R4 U2 R1 检测点1 R2 CC1 CC1 R3\' 检测点2 S2 Rv CC2 Re\'\' C", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 129, "coverage_unit_id": "DOC-000003:requirement:129:88AA13DBBCAD", "coverage_semantic_key": "附录B 充电桩 车辆插头 GB 车辆适配器 车辆插座 附录D 电动汽车 二选一 RCD 电流测量 C1 FUSE DC+ DC+ C5 FUSE 泄放电路 电压测量 Rload C 可充电储能系统 C2 DC- DC- C6 Rload IMD 设备地 PE PE 车身地 RCD 控制电源 设备控制器 S+ S+ 车辆控制器 S- S- U1 S R3 Re\' R4\' R4c R4 U2 R1 检测点1 R2 CC1 CC1 R3\' 检测点2 S2 Rv CC2 Re\'\' C"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_180() -> None:
    case = '{"kind": "coverage_requirement", "query": "G.3.3.1 车辆插座与车辆适配器和/或车辆插头插合:使车辆处于不可行驶状态有哪些要求？", "must_include": "G.3.3.1 车辆插座与车辆适配器和/或车辆插头插合:使车辆处于不可行驶状态", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 134, "coverage_unit_id": "DOC-000003:requirement:134:9C65DCDA213D", "coverage_semantic_key": "G.3.3.1 车辆插座与车辆适配器和/或车辆插头插合:使车辆处于不可行驶状态"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_181() -> None:
    case = '{"kind": "coverage_requirement", "query": "附录B充电机 车辆插头 GB车辆适配器 车辆插座 全球通用版本电动汽车 PE PE PE 车身地 U1, 12.0V S R1, 1.0kΩ R2, 1.0kΩ R3, 1.0kΩ Rc\', 1.0kΩ CC1 CC1 D1 检测点1 CC2 Rc\'\', 1.5kΩ CC2 检测点2 检测点3 R3\', 100kΩ S2\' R4\', 2.74kΩ R4c\', 830Ω R4c, 130Ω R4, 1.3kΩ U2, 12V S2 3 2 1 0 Rv\', 1.59kΩ Sv有哪些要求？", "must_include": "附录B充电机 车辆插头 GB车辆适配器 车辆插座 全球通用版本电动汽车 PE PE PE 车身地 U1, 12.0V S R1, 1.0kΩ R2, 1.0kΩ R3, 1.0kΩ Rc\', 1.0kΩ CC1 CC1 D1 检测点1 CC2 Rc\'\', 1.5kΩ CC2 检测点2 检测点3 R3\', 100kΩ S2\' R4\', 2.74kΩ R4c\', 830Ω R4c, 130Ω R4, 1.3kΩ U2, 12V S2 3 2 1 0 Rv\', 1.59kΩ Sv", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 140, "coverage_unit_id": "DOC-000003:requirement:140:A3A6CC8723AC", "coverage_semantic_key": "附录B充电机 车辆插头 GB车辆适配器 车辆插座 全球通用版本电动汽车 PE PE PE 车身地 U1, 12.0V S R1, 1.0kΩ R2, 1.0kΩ R3, 1.0kΩ Rc\', 1.0kΩ CC1 CC1 D1 检测点1 CC2 Rc\'\', 1.5kΩ CC2 检测点2 检测点3 R3\', 100kΩ S2\' R4\', 2.74kΩ R4c\', 830Ω R4c, 130Ω R4, 1.3kΩ U2, 12V S2 3 2 1 0 Rv\', 1.59kΩ Sv"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_182() -> None:
    case = '{"kind": "coverage_gap", "query": "模式 2 和模式 3 充电接口的锁止功能有哪些活动？", "must_include": "模式 2 和模式 3 充电接口的锁止功能", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 33, "coverage_unit_id": "DOC-000003_procedure_33_6", "coverage_semantic_key": "模式 2 和模式 3 充电接口的锁止功能"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_183() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是保护接地导体 protective earthing conductor？", "must_include": "保护接地导体 protective earthing conductor", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 19, "coverage_unit_id": "DOC-000003:definition:19:FD71A78C1B8C", "coverage_semantic_key": "保护接地导体 protective earthing conductor"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_184() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是电动汽车模拟器 EV simulator？", "must_include": "电动汽车模拟器 EV simulator", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 21, "coverage_unit_id": "DOC-000003:definition:21:E34105BE7B70", "coverage_semantic_key": "电动汽车模拟器 EV simulator"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_185() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是充电自动耦合器主动端 automated connection device; ACD？", "must_include": "充电自动耦合器主动端 automated connection device; ACD", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 23, "coverage_unit_id": "DOC-000003:definition:23:5EDD53673352", "coverage_semantic_key": "充电自动耦合器主动端 automated connection device; ACD"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_186() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是机械锁 mechanical lock？", "must_include": "机械锁 mechanical lock", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 23, "coverage_unit_id": "DOC-000003:definition:23:4E3705960626", "coverage_semantic_key": "机械锁 mechanical lock"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_187() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是电子锁 electronic lock？", "must_include": "电子锁 electronic lock", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 23, "coverage_unit_id": "DOC-000003:definition:23:8E3C0737D5C5", "coverage_semantic_key": "电子锁 electronic lock"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_188() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是车辆插座 vehicle inlet？", "must_include": "车辆插座 vehicle inlet", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 23, "coverage_unit_id": "DOC-000003:definition:23:06B5F8BC163D", "coverage_semantic_key": "车辆插座 vehicle inlet"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_189() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是车辆适配器 vehicle adaptor？", "must_include": "车辆适配器 vehicle adaptor", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 23, "coverage_unit_id": "DOC-000003:definition:23:A9C6E4E4EC38", "coverage_semantic_key": "车辆适配器 vehicle adaptor"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_190() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是连接点 connecting point？", "must_include": "连接点 connecting point", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 23, "coverage_unit_id": "DOC-000003:definition:23:5CFDEEAA402F", "coverage_semantic_key": "连接点 connecting point"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_191() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是便携式设备 portable equipment？", "must_include": "便携式设备 portable equipment", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 24, "coverage_unit_id": "DOC-000003:definition:24:A5989DCA721A", "coverage_semantic_key": "便携式设备 portable equipment"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_192() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是受过培训的[电气]人员 (electrically)instructed person？", "must_include": "受过培训的[电气]人员 (electrically)instructed person", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 24, "coverage_unit_id": "DOC-000003:definition:24:5DD6210D8D2C", "coverage_semantic_key": "受过培训的[电气]人员 (electrically)instructed person"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_193() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是固定设备 fixed equipment？", "must_include": "固定设备 fixed equipment", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 24, "coverage_unit_id": "DOC-000003:definition:24:F215FEF13FB3", "coverage_semantic_key": "固定设备 fixed equipment"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_194() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是室外使用 outdoor use？", "must_include": "室外使用 outdoor use", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 24, "coverage_unit_id": "DOC-000003:definition:24:21B29FBA1818", "coverage_semantic_key": "室外使用 outdoor use"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_195() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是一般人员 ordinary person？", "must_include": "一般人员 ordinary person", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 25, "coverage_unit_id": "DOC-000003:definition:25:B51FB1EBD34B", "coverage_semantic_key": "一般人员 ordinary person"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_196() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是可用最大电流 applicable maximum current？", "must_include": "可用最大电流 applicable maximum current", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 25, "coverage_unit_id": "DOC-000003:definition:25:B649F6125EDA", "coverage_semantic_key": "可用最大电流 applicable maximum current"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_197() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是工作电压范围 operating voltage range？", "must_include": "工作电压范围 operating voltage range", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 25, "coverage_unit_id": "DOC-000003:definition:25:2E150219E79F", "coverage_semantic_key": "工作电压范围 operating voltage range"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_198() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是当前电压测量值 present measured voltage？", "must_include": "当前电压测量值 present measured voltage", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 25, "coverage_unit_id": "DOC-000003:definition:25:033017733A95", "coverage_semantic_key": "当前电压测量值 present measured voltage"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_199() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是当前电流测量值 present measured current？", "must_include": "当前电流测量值 present measured current", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 25, "coverage_unit_id": "DOC-000003:definition:25:C7B20549FAE3", "coverage_semantic_key": "当前电流测量值 present measured current"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_200() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是额定持续电流 rated continuous current？", "must_include": "额定持续电流 rated continuous current", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 25, "coverage_unit_id": "DOC-000003:definition:25:0E626670FE53", "coverage_semantic_key": "额定持续电流 rated continuous current"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_201() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是电流需求值(电动汽车) target current (EV)？", "must_include": "电流需求值(电动汽车) target current (EV)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 26, "coverage_unit_id": "DOC-000003:definition:26:C05A5804C23E", "coverage_semantic_key": "电流需求值(电动汽车) target current (EV)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_202() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是额定最大功率 rated maximum power？", "must_include": "额定最大功率 rated maximum power", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 26, "coverage_unit_id": "DOC-000003:definition:26:FD53DA38A5E9", "coverage_semantic_key": "额定最大功率 rated maximum power"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_203() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是额定最大电压 rated maximum voltage？", "must_include": "额定最大电压 rated maximum voltage", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 26, "coverage_unit_id": "DOC-000003:definition:26:4754EBC18DBD", "coverage_semantic_key": "额定最大电压 rated maximum voltage"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_204() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是额定最小电压 rated minimum voltage？", "must_include": "额定最小电压 rated minimum voltage", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 26, "coverage_unit_id": "DOC-000003:definition:26:261E8FBB100E", "coverage_semantic_key": "额定最小电压 rated minimum voltage"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_205() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是额定最小电流 rated minimum current？", "must_include": "额定最小电流 rated minimum current", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 26, "coverage_unit_id": "DOC-000003:definition:26:3ED153D9F093", "coverage_semantic_key": "额定最小电流 rated minimum current"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_206() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是电压需求值(电动汽车) target voltage (EV)？", "must_include": "电压需求值(电动汽车) target voltage (EV)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 27, "coverage_unit_id": "DOC-000003:definition:27:F50DF9BB858F", "coverage_semantic_key": "电压需求值(电动汽车) target voltage (EV)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_207() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是脉冲加热 pulse heating？", "must_include": "脉冲加热 pulse heating", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 27, "coverage_unit_id": "DOC-000003:definition:27:6FC98C44B12D", "coverage_semantic_key": "脉冲加热 pulse heating"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_208() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是电动汽车与电网充放电双向互动 vehicle to grid; V2G？", "must_include": "电动汽车与电网充放电双向互动 vehicle to grid; V2G", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 28, "coverage_unit_id": "DOC-000003:definition:28:95EE8C400CBD", "coverage_semantic_key": "电动汽车与电网充放电双向互动 vehicle to grid; V2G"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_209() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是电动汽车充放电双向互动 vehicle to X; V2X？", "must_include": "电动汽车充放电双向互动 vehicle to X; V2X", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 28, "coverage_unit_id": "DOC-000003:definition:28:A9BE7F047070", "coverage_semantic_key": "电动汽车充放电双向互动 vehicle to X; V2X"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_210() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "等效二极管压降 (2.75 mA~10 mA, -40 °C ~+85 °C)是多少？", "must_include": "等效二极管压降 (2.75 mA~10 mA, -40 °C ~+85 °C)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 140, "coverage_unit_id": "DOC-000003:parameter-row:140:380CD1F0221F", "coverage_semantic_key": "等效二极管压降 (2.75 mA~10 mA, -40 °C ~+85 °C)"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_211() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "检测点1/检测点2 Udp1=Udp2 无二极管是多少？", "must_include": "检测点1/检测点2 Udp1=Udp2 无二极管", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 148, "coverage_unit_id": "DOC-000003:parameter-row:148:B6F4381ACF96", "coverage_semantic_key": "检测点1/检测点2 Udp1=Udp2 无二极管"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_212() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "检测点1/检测点2 Udp1=Udp2+ 0.7V 有二极管是多少？", "must_include": "检测点1/检测点2 Udp1=Udp2+ 0.7V 有二极管", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 148, "coverage_unit_id": "DOC-000003:parameter-row:148:561BEBF830D0", "coverage_semantic_key": "检测点1/检测点2 Udp1=Udp2+ 0.7V 有二极管"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_213() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "充电机接触器是多少？", "must_include": "充电机接触器", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 150, "coverage_unit_id": "DOC-000003:parameter-row:150:EDC05D5A9388", "coverage_semantic_key": "充电机接触器"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_214() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "开关Sv是多少？", "must_include": "开关Sv", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 150, "coverage_unit_id": "DOC-000003_table_150_2:row:12", "coverage_semantic_key": "开关Sv"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_215() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "控制引导是多少？", "must_include": "控制引导", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 150, "coverage_unit_id": "DOC-000003:parameter-row:150:1AD7642912BC", "coverage_semantic_key": "控制引导"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_216() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "绝缘监测是多少？", "must_include": "绝缘监测", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 150, "coverage_unit_id": "DOC-000003:parameter-row:150:3B6034D24802", "coverage_semantic_key": "绝缘监测"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_217() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "检测点1/检测点2 U_{\\\\text{dp1}}=U_{\\\\text{dp2}}+0.7\\\\text{V} 有二极管是多少？", "must_include": "检测点1/检测点2 U_{\\\\text{dp1}}=U_{\\\\text{dp2}}+0.7\\\\text{V} 有二极管", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 152, "coverage_unit_id": "DOC-000003:parameter-row:152:08771E0BFC12", "coverage_semantic_key": "检测点1/检测点2 U_{\\\\text{dp1}}=U_{\\\\text{dp2}}+0.7\\\\text{V} 有二极管"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_218() -> None:
    case = '{"kind": "coverage_requirement", "query": "电动汽车供电设备可用负载电流实时调节有哪些要求？", "must_include": "电动汽车供电设备可用负载电流实时调节", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 33, "coverage_unit_id": "DOC-000003:requirement:33:0B036D651CEE", "coverage_semantic_key": "电动汽车供电设备可用负载电流实时调节"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_219() -> None:
    case = '{"kind": "coverage_requirement", "query": "预期使用和合理可预见的误用有哪些要求？", "must_include": "预期使用和合理可预见的误用", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 33, "coverage_unit_id": "DOC-000003:requirement:33:2F5192AD054A", "coverage_semantic_key": "预期使用和合理可预见的误用"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_220() -> None:
    case = '{"kind": "coverage_requirement", "query": "带电部分基本绝缘进行防护有哪些要求？", "must_include": "带电部分基本绝缘进行防护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 35, "coverage_unit_id": "DOC-000003:requirement:35:0EBFA2C3E43F", "coverage_semantic_key": "带电部分基本绝缘进行防护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_221() -> None:
    case = '{"kind": "coverage_requirement", "query": "用外壳或屏障进行防护有哪些要求？", "must_include": "用外壳或屏障进行防护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 35, "coverage_unit_id": "DOC-000003:requirement:35:5C778101335C", "coverage_semantic_key": "用外壳或屏障进行防护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_222() -> None:
    case = '{"kind": "coverage_requirement", "query": "故障防护有哪些要求？", "must_include": "故障防护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 36, "coverage_unit_id": "DOC-000003:requirement:36:AE26DCB7E879", "coverage_semantic_key": "故障防护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000003_golden_223() -> None:
    case = '{"kind": "coverage_requirement", "query": "稳态接触电流的限值保护有哪些要求？", "must_include": "稳态接触电流的限值保护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000003", "page_no": 36, "coverage_unit_id": "DOC-000003:requirement:36:AD8777BCE685", "coverage_semantic_key": "稳态接触电流的限值保护"}'
    _assert_case(json.loads(case))
