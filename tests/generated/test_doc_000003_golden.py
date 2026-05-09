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
def test_doc_000003_golden_1() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是充电 charging？\", \"must_include\": \"充电 charging\", \"retrieval_must_hit\": [\"充电 charging\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"充电 charging\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_2() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中充电 charging的定义是什么？\", \"must_include\": \"充电 charging\", \"retrieval_must_hit\": [\"充电 charging\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"充电 charging\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_3() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是充放电 bi-directional charging？\", \"must_include\": \"充放电 bi-directional charging\", \"retrieval_must_hit\": [\"充放电 bi-directional charging\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"充放电 bi-directional charging\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_4() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中充放电 bi-directional charging的定义是什么？\", \"must_include\": \"充放电 bi-directional charging\", \"retrieval_must_hit\": [\"充放电 bi-directional charging\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"充放电 bi-directional charging\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_5() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是传导充电 conductive charge？\", \"must_include\": \"传导充电 conductive charge\", \"retrieval_must_hit\": [\"传导充电 conductive charge\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"传导充电 conductive charge\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_6() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中传导充电 conductive charge的定义是什么？\", \"must_include\": \"传导充电 conductive charge\", \"retrieval_must_hit\": [\"传导充电 conductive charge\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"传导充电 conductive charge\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_7() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是充电模式 charging modes？\", \"must_include\": \"充电模式 charging modes\", \"retrieval_must_hit\": [\"充电模式 charging modes\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"充电模式 charging modes\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_8() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中充电模式 charging modes的定义是什么？\", \"must_include\": \"充电模式 charging modes\", \"retrieval_must_hit\": [\"充电模式 charging modes\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"充电模式 charging modes\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_9() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是模式 1 mode 1？\", \"must_include\": \"模式 1 mode 1\", \"retrieval_must_hit\": [\"模式 1 mode 1\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"模式 1 mode 1\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_10() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中模式 1 mode 1的定义是什么？\", \"must_include\": \"模式 1 mode 1\", \"retrieval_must_hit\": [\"模式 1 mode 1\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"模式 1 mode 1\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_11() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是电动汽车电能传输设备 EV energy transfer equipment？\", \"must_include\": \"电动汽车电能传输设备 EV energy transfer equipment\", \"retrieval_must_hit\": [\"电动汽车电能传输设备 EV energy transfer equipment\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"电动汽车电能传输设备 EV energy transfer equipment\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_12() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中电动汽车电能传输设备 EV energy transfer equipment的定义是什么？\", \"must_include\": \"电动汽车电能传输设备 EV energy transfer equipment\", \"retrieval_must_hit\": [\"电动汽车电能传输设备 EV energy transfer equipment\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"电动汽车电能传输设备 EV energy transfer equipment\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_13() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是充电设备 charging equipment？\", \"must_include\": \"充电设备 charging equipment\", \"retrieval_must_hit\": [\"充电设备 charging equipment\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"充电设备 charging equipment\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_14() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中充电设备 charging equipment的定义是什么？\", \"must_include\": \"充电设备 charging equipment\", \"retrieval_must_hit\": [\"充电设备 charging equipment\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"充电设备 charging equipment\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_15() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是充放电设备 charging and discharging equipment？\", \"must_include\": \"充放电设备 charging and discharging equipment\", \"retrieval_must_hit\": [\"充放电设备 charging and discharging equipment\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"充放电设备 charging and discharging equipment\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_16() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中充放电设备 charging and discharging equipment的定义是什么？\", \"must_include\": \"充放电设备 charging and discharging equipment\", \"retrieval_must_hit\": [\"充放电设备 charging and discharging equipment\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"充放电设备 charging and discharging equipment\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_17() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是绝缘[性能] insulation？\", \"must_include\": \"绝缘[性能] insulation\", \"retrieval_must_hit\": [\"绝缘[性能] insulation\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"绝缘[性能] insulation\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_18() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中绝缘[性能] insulation的定义是什么？\", \"must_include\": \"绝缘[性能] insulation\", \"retrieval_must_hit\": [\"绝缘[性能] insulation\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"绝缘[性能] insulation\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_19() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是基本绝缘 basic insulation？\", \"must_include\": \"基本绝缘 basic insulation\", \"retrieval_must_hit\": [\"基本绝缘 basic insulation\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"基本绝缘 basic insulation\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_20() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中基本绝缘 basic insulation的定义是什么？\", \"must_include\": \"基本绝缘 basic insulation\", \"retrieval_must_hit\": [\"基本绝缘 basic insulation\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"基本绝缘 basic insulation\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_21() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是附加绝缘 supplementary insulation？\", \"must_include\": \"附加绝缘 supplementary insulation\", \"retrieval_must_hit\": [\"附加绝缘 supplementary insulation\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"附加绝缘 supplementary insulation\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_22() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中附加绝缘 supplementary insulation的定义是什么？\", \"must_include\": \"附加绝缘 supplementary insulation\", \"retrieval_must_hit\": [\"附加绝缘 supplementary insulation\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"附加绝缘 supplementary insulation\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_23() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是保护导体 protective conductor(identification: PE)？\", \"must_include\": \"保护导体 protective conductor(identification: PE)\", \"retrieval_must_hit\": [\"保护导体 protective conductor(identification: PE)\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"保护导体 protective conductor(identification: PE)\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_24() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中保护导体 protective conductor(identification: PE)的定义是什么？\", \"must_include\": \"保护导体 protective conductor(identification: PE)\", \"retrieval_must_hit\": [\"保护导体 protective conductor(identification: PE)\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"保护导体 protective conductor(identification: PE)\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_25() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是保护联结导体 protective bonding conductor？\", \"must_include\": \"保护联结导体 protective bonding conductor\", \"retrieval_must_hit\": [\"保护联结导体 protective bonding conductor\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"保护联结导体 protective bonding conductor\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_26() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中保护联结导体 protective bonding conductor的定义是什么？\", \"must_include\": \"保护联结导体 protective bonding conductor\", \"retrieval_must_hit\": [\"保护联结导体 protective bonding conductor\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"保护联结导体 protective bonding conductor\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_27() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是接地端子 earthing terminal？\", \"must_include\": \"接地端子 earthing terminal\", \"retrieval_must_hit\": [\"接地端子 earthing terminal\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"接地端子 earthing terminal\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_28() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中接地端子 earthing terminal的定义是什么？\", \"must_include\": \"接地端子 earthing terminal\", \"retrieval_must_hit\": [\"接地端子 earthing terminal\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"接地端子 earthing terminal\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_29() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是电气隔离 galvanic separation？\", \"must_include\": \"电气隔离 galvanic separation\", \"retrieval_must_hit\": [\"电气隔离 galvanic separation\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"电气隔离 galvanic separation\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_30() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中电气隔离 galvanic separation的定义是什么？\", \"must_include\": \"电气隔离 galvanic separation\", \"retrieval_must_hit\": [\"电气隔离 galvanic separation\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"电气隔离 galvanic separation\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_31() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是保护接地 protective earthing？\", \"must_include\": \"保护接地 protective earthing\", \"retrieval_must_hit\": [\"保护接地 protective earthing\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"保护接地 protective earthing\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_32() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中保护接地 protective earthing的定义是什么？\", \"must_include\": \"保护接地 protective earthing\", \"retrieval_must_hit\": [\"保护接地 protective earthing\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"保护接地 protective earthing\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_33() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是电涌保护器 surge protective device; SPD？\", \"must_include\": \"电涌保护器 surge protective device; SPD\", \"retrieval_must_hit\": [\"电涌保护器 surge protective device; SPD\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"电涌保护器 surge protective device; SPD\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_34() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中电涌保护器 surge protective device; SPD的定义是什么？\", \"must_include\": \"电涌保护器 surge protective device; SPD\", \"retrieval_must_hit\": [\"电涌保护器 surge protective device; SPD\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"电涌保护器 surge protective device; SPD\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_35() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是感知阈 threshold of perception？\", \"must_include\": \"感知阈 threshold of perception\", \"retrieval_must_hit\": [\"感知阈 threshold of perception\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"感知阈 threshold of perception\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_36() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中感知阈 threshold of perception的定义是什么？\", \"must_include\": \"感知阈 threshold of perception\", \"retrieval_must_hit\": [\"感知阈 threshold of perception\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"感知阈 threshold of perception\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_37() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是控制导引电路 control pilot circuit？\", \"must_include\": \"控制导引电路 control pilot circuit\", \"retrieval_must_hit\": [\"控制导引电路 control pilot circuit\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"控制导引电路 control pilot circuit\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_38() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中控制导引电路 control pilot circuit的定义是什么？\", \"must_include\": \"控制导引电路 control pilot circuit\", \"retrieval_must_hit\": [\"控制导引电路 control pilot circuit\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"控制导引电路 control pilot circuit\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_39() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是控制导引功能 control pilot function; CP？\", \"must_include\": \"控制导引功能 control pilot function; CP\", \"retrieval_must_hit\": [\"控制导引功能 control pilot function; CP\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"控制导引功能 control pilot function; CP\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_40() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中控制导引功能 control pilot function; CP的定义是什么？\", \"must_include\": \"控制导引功能 control pilot function; CP\", \"retrieval_must_hit\": [\"控制导引功能 control pilot function; CP\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"控制导引功能 control pilot function; CP\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_41() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是连接确认功能 connection confirm function; CC？\", \"must_include\": \"连接确认功能 connection confirm function; CC\", \"retrieval_must_hit\": [\"连接确认功能 connection confirm function; CC\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"连接确认功能 connection confirm function; CC\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_42() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中连接确认功能 connection confirm function; CC的定义是什么？\", \"must_include\": \"连接确认功能 connection confirm function; CC\", \"retrieval_must_hit\": [\"连接确认功能 connection confirm function; CC\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"连接确认功能 connection confirm function; CC\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_43() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV？\", \"must_include\": \"燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV\", \"retrieval_must_hit\": [\"燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_44() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV的定义是什么？\", \"must_include\": \"燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV\", \"retrieval_must_hit\": [\"燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"燃料电池混合动力电动汽车 fuel cell hybrid electric vehicle; FCHEV\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_45() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"什么是车辆断开装置 EV disconnection device？\", \"must_include\": \"车辆断开装置 EV disconnection device\", \"retrieval_must_hit\": [\"车辆断开装置 EV disconnection device\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"车辆断开装置 EV disconnection device\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_46() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \"GB/T 18487.1—2023中车辆断开装置 EV disconnection device的定义是什么？\", \"must_include\": \"车辆断开装置 EV disconnection device\", \"retrieval_must_hit\": [\"车辆断开装置 EV disconnection device\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_sections\": [\"车辆断开装置 EV disconnection device\"], \"difficulty\": \"medium\", \"query_type\": \"definition\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_47() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"输出占空比公差是多少\", \"must_include\": \"输出占空比公差\", \"retrieval_must_hit\": [\"输出占空比公差\", \"—\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_48() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"R1 等效电阻^d是多少\", \"must_include\": \"R1 等效电阻^d\", \"retrieval_must_hit\": [\"R1 等效电阻^d\", \"Ω\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_49() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"R2 等效电阻^d是多少\", \"must_include\": \"R2 等效电阻^d\", \"retrieval_must_hit\": [\"R2 等效电阻^d\", \"Ω\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_50() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"R3 等效电阻^d是多少\", \"must_include\": \"R3 等效电阻^d\", \"retrieval_must_hit\": [\"R3 等效电阻^d\", \"Ω\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_51() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"输入占空比公差是多少\", \"must_include\": \"输入占空比公差\", \"retrieval_must_hit\": [\"输入占空比公差\", \"—\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_52() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"R1 等效电阻是多少\", \"must_include\": \"R1 等效电阻\", \"retrieval_must_hit\": [\"R1 等效电阻\", \"Ω\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_53() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"检测点 1 电压是多少\", \"must_include\": \"检测点 1 电压\", \"retrieval_must_hit\": [\"检测点 1 电压\", \"V\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_54() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"R2 等效电阻是多少\", \"must_include\": \"R2 等效电阻\", \"retrieval_must_hit\": [\"R2 等效电阻\", \"Ω\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_55() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"R3 等效电阻是多少\", \"must_include\": \"R3 等效电阻\", \"retrieval_must_hit\": [\"R3 等效电阻\", \"Ω\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_56() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"R4 等效电阻是多少\", \"must_include\": \"R4 等效电阻\", \"retrieval_must_hit\": [\"R4 等效电阻\", \"Ω\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_57() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"R5 等效电阻是多少\", \"must_include\": \"R5 等效电阻\", \"retrieval_must_hit\": [\"R5 等效电阻\", \"Ω\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_58() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"检测点 2 电压是多少\", \"must_include\": \"检测点 2 电压\", \"retrieval_must_hit\": [\"检测点 2 电压\", \"V\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_59() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"R1' 等效电阻是多少\", \"must_include\": \"R1' 等效电阻\", \"retrieval_must_hit\": [\"R1' 等效电阻\", \"Ω\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_60() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"S0 开关^c是多少\", \"must_include\": \"S0 开关^c\", \"retrieval_must_hit\": [\"S0 开关^c\", \"—\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_61() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"Rc 等效电阻是多少\", \"must_include\": \"Rc 等效电阻\", \"retrieval_must_hit\": [\"Rc 等效电阻\", \"Ω\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_62() -> None:
    case = json.loads("{\"kind\": \"answer_quality\", \"query\": \"R3'等效电阻是多少\", \"must_include\": \"R3'等效电阻\", \"retrieval_must_hit\": [\"R3'等效电阻\", \"Ω\"], \"assert_mode\": \"rich_answer\", \"expected_answer_mode\": \"parameter_value\", \"forbidden_contains\": [\"没有找到足够的结构化结果。\", \"GB：代替\"], \"expected_evidence_shape\": \"parameter_value\", \"source\": \"local_aq\", \"query_type\": \"parameter_lookup\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_63() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023：ICS 43.040.99 CCS T 35 # GB # 中华人民共和国国家标准\", \"must_include\": \"ICS 43.040.99 CCS T 35 # GB # 中华人民共和国国家标准\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 1, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_64() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023 # 前 言 本文件按照 GB/T 1.1—202\", \"must_include\": \"GB/T 18487.1—2023 # 前 言 本文件按照 GB/T 1.1—202\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 3, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_65() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023：本文件是 GB/T 18487 的第 1 部分。GB/T 18487 已经发布了以下\", \"must_include\": \"本文件是 GB/T 18487 的第 1 部分。GB/T 18487 已经发布了以下\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 3, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_66() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023：——电动汽车传导充电系统 第 2 部分：非车载传导供电设备电磁兼容要求（GB/T 1\", \"must_include\": \"——电动汽车传导充电系统 第 2 部分：非车载传导供电设备电磁兼容要求（GB/T 1\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 3, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_67() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023：——电动车辆传导充电系统 第 3 部分：电动车辆交流/直流充电机(站)(GB/T 1\", \"must_include\": \"——电动车辆传导充电系统 第 3 部分：电动车辆交流/直流充电机(站)(GB/T 1\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 3, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_68() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023：本文件代替 GB/T 18487.1—2015《电动汽车传导充电系统 第 1 部分：\", \"must_include\": \"本文件代替 GB/T 18487.1—2015《电动汽车传导充电系统 第 1 部分：\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 3, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_69() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023 电要求(见 8.1); z) 更改了连接方式 B\", \"must_include\": \"GB/T 18487.1—2023 电要求(见 8.1); z) 更改了连接方式 B\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 5, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_70() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023 “采用 GB/T 20234.4 规定的充电连接\", \"must_include\": \"GB/T 18487.1—2023 “采用 GB/T 20234.4 规定的充电连接\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 6, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_71() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023：本文件由中国电力企业联合会提出并归口。\", \"must_include\": \"本文件由中国电力企业联合会提出并归口。\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 6, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_72() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023：本文件起草单位:国网电力科学研究院有限公司、中国电力企业联合会、国家电网有限公司、南\", \"must_include\": \"本文件起草单位:国网电力科学研究院有限公司、中国电力企业联合会、国家电网有限公司、南\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 6, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_73() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023：本文件主要起草人:张萱、倪峰、刘永东、栗文涛、董新生、李志刚、梁晓芳、武亨、郑隽一、\", \"must_include\": \"本文件主要起草人:张萱、倪峰、刘永东、栗文涛、董新生、李志刚、梁晓芳、武亨、郑隽一、\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 6, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_74() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023：本文件及其所代替文件的历次版本发布情况为: ——2001 年首次发布为 GB/T 1\", \"must_include\": \"本文件及其所代替文件的历次版本发布情况为: ——2001 年首次发布为 GB/T 1\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 6, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_75() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023 # 引 言 GB/T 18487 旨在确立电动汽\", \"must_include\": \"GB/T 18487.1—2023 # 引 言 GB/T 18487 旨在确立电动汽\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 7, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_76() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023：——第 1 部分:通用要求。目的在于规范电动汽车与非车载传导式电能传输设备需要满足的\", \"must_include\": \"——第 1 部分:通用要求。目的在于规范电动汽车与非车载传导式电能传输设备需要满足的\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 7, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_77() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"GB/T 18487.1—2023：——第 2 部分:非车载传导供电设备电磁兼容要求。目的在于规范电动汽车非车载传导式供\", \"must_include\": \"——第 2 部分:非车载传导供电设备电磁兼容要求。目的在于规范电动汽车非车载传导式供\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 7, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_78() -> None:
    case = json.loads("{\"kind\": \"definition\", \"query\": \"在GB/T 18487.1—2023中，什么是充电 charging？\", \"must_include\": \"充电 charging\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_79() -> None:
    case = json.loads("{\"kind\": \"definition_detail\", \"query\": \"在GB/T 18487.1—2023中，充电 charging 的定义是什么？\", \"must_include\": \"将交流或直流供电网(电源)调整为适当的电压/电流,为电动汽车可充电储能系统提供电能。\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_80() -> None:
    case = json.loads("{\"kind\": \"definition\", \"query\": \"在GB/T 18487.1—2023中，什么是充放电 bi-directional charging？\", \"must_include\": \"充放电 bi-directional charging\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_81() -> None:
    case = json.loads("{\"kind\": \"definition_detail\", \"query\": \"在GB/T 18487.1—2023中，充放电 bi-directional charging 的定义是什么？\", \"must_include\": \"将交流或直流供电网(电源)调整为适当的电压/电流,为电动汽车可充电储能系统提供电能\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_82() -> None:
    case = json.loads("{\"kind\": \"definition\", \"query\": \"在GB/T 18487.1—2023中，什么是传导充电 conductive charge？\", \"must_include\": \"传导充电 conductive charge\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_83() -> None:
    case = json.loads("{\"kind\": \"definition_detail\", \"query\": \"在GB/T 18487.1—2023中，传导充电 conductive charge 的定义是什么？\", \"must_include\": \"利用电传导给蓄电池进行充电的方式。 [来源:GB/T 19596—2017,3.4.\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_84() -> None:
    case = json.loads("{\"kind\": \"definition\", \"query\": \"在GB/T 18487.1—2023中，什么是充电模式 charging modes？\", \"must_include\": \"充电模式 charging modes\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_85() -> None:
    case = json.loads("{\"kind\": \"definition_detail\", \"query\": \"在GB/T 18487.1—2023中，充电模式 charging modes 的定义是什么？\", \"must_include\": \"连接电动汽车到供电网(电源)给电动汽车供电的方法。 注:模式 1、模式 2、模式 3\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_86() -> None:
    case = json.loads("{\"kind\": \"definition\", \"query\": \"在GB/T 18487.1—2023中，什么是模式 1 mode 1？\", \"must_include\": \"模式 1 mode 1\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_87() -> None:
    case = json.loads("{\"kind\": \"definition_detail\", \"query\": \"在GB/T 18487.1—2023中，模式 1 mode 1 的定义是什么？\", \"must_include\": \"将电动汽车连接到供电网(电源)时,在电源侧使用了符合 GB/T 2099.1 和 G\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_88() -> None:
    case = json.loads("{\"kind\": \"definition\", \"query\": \"在GB/T 18487.1—2023中，什么是电动汽车电能传输设备 EV energy transfer equipment？\", \"must_include\": \"电动汽车电能传输设备 EV energy transfer equipment\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_89() -> None:
    case = json.loads("{\"kind\": \"definition_detail\", \"query\": \"在GB/T 18487.1—2023中，电动汽车电能传输设备 EV energy transfer equipment 的定义是什么？\", \"must_include\": \"连接于电动汽车与供电网(电源)之间,可实现能量流动的设备。 注 1:电动汽车电能传输\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_90() -> None:
    case = json.loads("{\"kind\": \"definition\", \"query\": \"在GB/T 18487.1—2023中，什么是充电设备 charging equipment？\", \"must_include\": \"充电设备 charging equipment\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_91() -> None:
    case = json.loads("{\"kind\": \"definition_detail\", \"query\": \"在GB/T 18487.1—2023中，充电设备 charging equipment 的定义是什么？\", \"must_include\": \"以传导或无线方式与电动汽车或动力蓄电池连接,为其提供电能的设备。 注:根据电动汽车与\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_92() -> None:
    case = json.loads("{\"kind\": \"definition\", \"query\": \"在GB/T 18487.1—2023中，什么是充放电设备 charging and discharging equipment？\", \"must_include\": \"充放电设备 charging and discharging equipment\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_93() -> None:
    case = json.loads("{\"kind\": \"definition_detail\", \"query\": \"在GB/T 18487.1—2023中，充放电设备 charging and discharging equipment 的定义是什么？\", \"must_include\": \"连接于电动汽车或动力蓄电池与电网(或负荷)之间,可实现能量双向流动的设备。 注:根据\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_94() -> None:
    case = json.loads("{\"kind\": \"standard\", \"query\": \"GB/T 18487.1—2023 的标准号和实施日期是什么？\", \"must_include\": \"GB/T 18487.1—2023\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_95() -> None:
    case = json.loads("{\"kind\": \"standard\", \"query\": \"GB/T 18487.1—2023 对应的标准编号是什么？\", \"must_include\": \"GB/T 18487.1—2023\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_96() -> None:
    case = json.loads("{\"kind\": \"standard\", \"query\": \"GB/T 18487.1—2023 的现行标准号是什么？\", \"must_include\": \"GB/T 18487.1—2023\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_97() -> None:
    case = json.loads("{\"kind\": \"publication_date\", \"query\": \"GB/T 18487.1—2023 的发布日期是什么？\", \"must_include\": \"2023-09-07\", \"source\": \"local\", \"assert_mode\": \"rich_answer\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_98() -> None:
    case = json.loads("{\"kind\": \"publication_date\", \"query\": \"GB/T 18487.1—2023 是哪一天发布的？\", \"must_include\": \"2023-09-07\", \"source\": \"local\", \"assert_mode\": \"rich_answer\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_99() -> None:
    case = json.loads("{\"kind\": \"effective_date\", \"query\": \"GB/T 18487.1—2023 的实施日期是什么？\", \"must_include\": \"2024-04-01\", \"source\": \"local\", \"assert_mode\": \"rich_answer\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_100() -> None:
    case = json.loads("{\"kind\": \"effective_date\", \"query\": \"GB/T 18487.1—2023 从哪一天开始实施？\", \"must_include\": \"2024-04-01\", \"source\": \"local\", \"assert_mode\": \"rich_answer\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_101() -> None:
    case = json.loads("{\"kind\": \"section\", \"query\": \"在GB/T 18487.1—2023中，是否包含“功能 function”这一章节？\", \"must_include\": \"功能 function\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 20, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_102() -> None:
    case = json.loads("{\"kind\": \"section\", \"query\": \"在GB/T 18487.1—2023中，是否包含“模式 2、模式 3 和模式 4 提供的功能”这一章节？\", \"must_include\": \"模式 2、模式 3 和模式 4 提供的功能\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 31, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_103() -> None:
    case = json.loads("{\"kind\": \"section\", \"query\": \"在GB/T 18487.1—2023中，是否包含“7.1.4 感知阈和惊跳反应”这一章节？\", \"must_include\": \"7.1.4 感知阈和惊跳反应\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 34, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_104() -> None:
    case = json.loads("{\"kind\": \"section\", \"query\": \"在GB/T 18487.1—2023中，是否包含“10.4 IP 防护等级”这一章节？\", \"must_include\": \"10.4 IP 防护等级\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 39, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_105() -> None:
    case = json.loads("{\"kind\": \"section\", \"query\": \"在GB/T 18487.1—2023中，是否包含“10.3 分断能力”这一章节？\", \"must_include\": \"10.3 分断能力\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 39, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_106() -> None:
    case = json.loads("{\"kind\": \"section\", \"query\": \"在GB/T 18487.1—2023中，是否包含“接触电流限值超过 3.5 mA 的特殊情况”这一章节？\", \"must_include\": \"接触电流限值超过 3.5 mA 的特殊情况\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 45, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_107() -> None:
    case = json.loads("{\"kind\": \"section\", \"query\": \"在GB/T 18487.1—2023中，是否包含“A.5 控制导引电路状态转换图和控制时序列表”这一章节？\", \"must_include\": \"A.5 控制导引电路状态转换图和控制时序列表\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 65, \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000003_golden_108() -> None:
    case = json.loads("{\"kind\": \"title\", \"query\": \"GB/T 18487.1—2023 这份文档的标题是什么？\", \"must_include\": \"# 电动汽车传导充电系统\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"target_doc_id\": \"DOC-000003\"}")
    _assert_case(case)
