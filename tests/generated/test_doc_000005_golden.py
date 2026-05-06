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
def test_doc_000005_golden_1() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是获取过程组（ACQ）？", "must_include": "获取过程组（ACQ）", "retrieval_must_hit": ["获取过程组（ACQ）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["获取过程组（ACQ）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_2() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中获取过程组（ACQ）的定义是什么？", "must_include": "获取过程组（ACQ）", "retrieval_must_hit": ["获取过程组（ACQ）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["获取过程组（ACQ）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_3() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是供应过程组（SPL）？", "must_include": "供应过程组（SPL）", "retrieval_must_hit": ["供应过程组（SPL）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["供应过程组（SPL）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_4() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中供应过程组（SPL）的定义是什么？", "must_include": "供应过程组（SPL）", "retrieval_must_hit": ["供应过程组（SPL）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["供应过程组（SPL）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_5() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是系统工程过程组（SYS）？", "must_include": "系统工程过程组（SYS）", "retrieval_must_hit": ["系统工程过程组（SYS）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["系统工程过程组（SYS）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_6() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中系统工程过程组（SYS）的定义是什么？", "must_include": "系统工程过程组（SYS）", "retrieval_must_hit": ["系统工程过程组（SYS）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["系统工程过程组（SYS）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_7() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是确认过程组（VAL）？", "must_include": "确认过程组（VAL）", "retrieval_must_hit": ["确认过程组（VAL）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["确认过程组（VAL）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_8() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中确认过程组（VAL）的定义是什么？", "must_include": "确认过程组（VAL）", "retrieval_must_hit": ["确认过程组（VAL）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["确认过程组（VAL）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_9() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是软件工程过程组（SWE）？", "must_include": "软件工程过程组（SWE）", "retrieval_must_hit": ["软件工程过程组（SWE）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["软件工程过程组（SWE）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_10() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中软件工程过程组（SWE）的定义是什么？", "must_include": "软件工程过程组（SWE）", "retrieval_must_hit": ["软件工程过程组（SWE）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["软件工程过程组（SWE）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_11() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是机器学习工程过程组（MLE）？", "must_include": "机器学习工程过程组（MLE）", "retrieval_must_hit": ["机器学习工程过程组（MLE）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["机器学习工程过程组（MLE）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_12() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中机器学习工程过程组（MLE）的定义是什么？", "must_include": "机器学习工程过程组（MLE）", "retrieval_must_hit": ["机器学习工程过程组（MLE）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["机器学习工程过程组（MLE）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_13() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是硬件工程过程组（HWE）？", "must_include": "硬件工程过程组（HWE）", "retrieval_must_hit": ["硬件工程过程组（HWE）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["硬件工程过程组（HWE）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_14() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中硬件工程过程组（HWE）的定义是什么？", "must_include": "硬件工程过程组（HWE）", "retrieval_must_hit": ["硬件工程过程组（HWE）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["硬件工程过程组（HWE）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_15() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是管理过程组（MAN）？", "must_include": "管理过程组（MAN）", "retrieval_must_hit": ["管理过程组（MAN）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["管理过程组（MAN）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_16() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中管理过程组（MAN）的定义是什么？", "must_include": "管理过程组（MAN）", "retrieval_must_hit": ["管理过程组（MAN）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["管理过程组（MAN）"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_17() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是过程实施过程属性？", "must_include": "过程实施过程属性", "retrieval_must_hit": ["过程实施过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过程实施过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_18() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中过程实施过程属性的定义是什么？", "must_include": "过程实施过程属性", "retrieval_must_hit": ["过程实施过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过程实施过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_19() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是实施管理过程属性？", "must_include": "实施管理过程属性", "retrieval_must_hit": ["实施管理过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["实施管理过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_20() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中实施管理过程属性的定义是什么？", "must_include": "实施管理过程属性", "retrieval_must_hit": ["实施管理过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["实施管理过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_21() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是工作产品管理过程属性？", "must_include": "工作产品管理过程属性", "retrieval_must_hit": ["工作产品管理过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["工作产品管理过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_22() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中工作产品管理过程属性的定义是什么？", "must_include": "工作产品管理过程属性", "retrieval_must_hit": ["工作产品管理过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["工作产品管理过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_23() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是过程定义过程属性？", "must_include": "过程定义过程属性", "retrieval_must_hit": ["过程定义过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过程定义过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_24() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中过程定义过程属性的定义是什么？", "must_include": "过程定义过程属性", "retrieval_must_hit": ["过程定义过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过程定义过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_25() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是过程部署过程属性？", "must_include": "过程部署过程属性", "retrieval_must_hit": ["过程部署过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过程部署过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_26() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中过程部署过程属性的定义是什么？", "must_include": "过程部署过程属性", "retrieval_must_hit": ["过程部署过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过程部署过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_27() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是定量控制过程属性？", "must_include": "定量控制过程属性", "retrieval_must_hit": ["定量控制过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["定量控制过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_28() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中定量控制过程属性的定义是什么？", "must_include": "定量控制过程属性", "retrieval_must_hit": ["定量控制过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["定量控制过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_29() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是过程创新过程的过程属性？", "must_include": "过程创新过程的过程属性", "retrieval_must_hit": ["过程创新过程的过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过程创新过程的过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_30() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中过程创新过程的过程属性的定义是什么？", "must_include": "过程创新过程的过程属性", "retrieval_must_hit": ["过程创新过程的过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过程创新过程的过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_31() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是过程创新实施过程属性？", "must_include": "过程创新实施过程属性", "retrieval_must_hit": ["过程创新实施过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过程创新实施过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_32() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中过程创新实施过程属性的定义是什么？", "must_include": "过程创新实施过程属性", "retrieval_must_hit": ["过程创新实施过程属性"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过程创新实施过程属性"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_33() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是机器学习工程过程组 * 硬件工程过程组？", "must_include": "机器学习工程过程组 * 硬件工程过程组", "retrieval_must_hit": ["机器学习工程过程组 * 硬件工程过程组"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["机器学习工程过程组 * 硬件工程过程组"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_34() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中机器学习工程过程组 * 硬件工程过程组的定义是什么？", "must_include": "机器学习工程过程组 * 硬件工程过程组", "retrieval_must_hit": ["机器学习工程过程组 * 硬件工程过程组"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["机器学习工程过程组 * 硬件工程过程组"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_35() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是过程名称 机器学习数据管理？", "must_include": "过程名称 机器学习数据管理", "retrieval_must_hit": ["过程名称 机器学习数据管理"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过程名称 机器学习数据管理"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_36() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中过程名称 机器学习数据管理的定义是什么？", "must_include": "过程名称 机器学习数据管理", "retrieval_must_hit": ["过程名称 机器学习数据管理"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过程名称 机器学习数据管理"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_37() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是过程属性范围？", "must_include": "过程属性范围", "retrieval_must_hit": ["过程属性范围"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过程属性范围"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_38() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中过程属性范围的定义是什么？", "must_include": "过程属性范围", "retrieval_must_hit": ["过程属性范围"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["过程属性范围"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_39() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是)提供、分配和维护实施已定义过程所需的资源？", "must_include": ")提供、分配和维护实施已定义过程所需的资源", "retrieval_must_hit": [")提供、分配和维护实施已定义过程所需的资源"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": [")提供、分配和维护实施已定义过程所需的资源"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_40() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中)提供、分配和维护实施已定义过程所需的资源的定义是什么？", "must_include": ")提供、分配和维护实施已定义过程所需的资源", "retrieval_must_hit": [")提供、分配和维护实施已定义过程所需的资源"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": [")提供、分配和维护实施已定义过程所需的资源"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_41() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是)识别了来自新技术和过程概念的创新机会？", "must_include": ")识别了来自新技术和过程概念的创新机会", "retrieval_must_hit": [")识别了来自新技术和过程概念的创新机会"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": [")识别了来自新技术和过程概念的创新机会"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_42() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中)识别了来自新技术和过程概念的创新机会的定义是什么？", "must_include": ")识别了来自新技术和过程概念的创新机会", "retrieval_must_hit": [")识别了来自新技术和过程概念的创新机会"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": [")识别了来自新技术和过程概念的创新机会"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_43() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是条款 6.3.2,“过程评估模型到过程参考模型的映射”？", "must_include": "条款 6.3.2,“过程评估模型到过程参考模型的映射”", "retrieval_must_hit": ["条款 6.3.2,“过程评估模型到过程参考模型的映射”"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["条款 6.3.2,“过程评估模型到过程参考模型的映射”"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_44() -> None:
    case = '{"kind": "retrieval_quality", "query": "IEC 33020中条款 6.3.2,“过程评估模型到过程参考模型的映射”的定义是什么？", "must_include": "条款 6.3.2,“过程评估模型到过程参考模型的映射”", "retrieval_must_hit": ["条款 6.3.2,“过程评估模型到过程参考模型的映射”"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["条款 6.3.2,“过程评估模型到过程参考模型的映射”"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_45() -> None:
    case = '{"kind": "retrieval_quality", "query": "·由承诺/协议的所有参与方签署·建立对什么的承诺·建立为满足承诺所需的资源,例如:·时间·人·预算·设备·设施的参数要求是什么？", "must_include": "·由承诺/协议的所有参与方签署·建立对什么的承诺·建立为满足承诺所需的资源,例如:·时间·人·预算·设备·设施", "retrieval_must_hit": ["·由承诺/协议的所有参与方签署·建立对什么的承诺·建立为满足承诺所需的资源,例如:·时间·人·预算·设备·设施"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [276], "expected_sections": ["VDA QMC"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_46() -> None:
    case = '{"kind": "retrieval_quality", "query": "承诺/协议代表什么参数？", "must_include": "·由承诺/协议的所有参与方签署·建立对什么的承诺·建立为满足承诺所需的资源,例如:·时间·人·预算·设备·设施", "retrieval_must_hit": ["·由承诺/协议的所有参与方签署·建立对什么的承诺·建立为满足承诺所需的资源,例如:·时间·人·预算·设备·设施"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [276], "expected_sections": ["VDA QMC"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_47() -> None:
    case = '{"kind": "retrieval_quality", "query": "·关于已定义的定量或定性的可度量指标的度量,与已定义的信息需要相匹配。·用于计算定量或定性的可度量指标的度量项·将过程实施与预期水平进行比较的数据·项目实施信息的示例:·依照已确立目标的资源使用·依照已确立目标的时间进度·活动或任务的完成准则得到满足·定义的输入以及输出工作产品是可用的·依照质量预期和/或准则的过程质量·依照质量预期和/或准则的产品质量·强调的产品性能问题、趋势·服务级别实施信息的示例:·引用所有已建立的目标·实时度量相关方面,例如:·能力·生产能力·运行性能·运行服务·服务中断时间·可服务时间·工作运行时间的参数要求是什么？", "must_include": "·关于已定义的定量或定性的可度量指标的度量,与已定义的信息需要相匹配。·用于计算定量或定性的可度量指标的度量项·将过程实施与预期水平进行比较的数据·项目实施信息的示例:·依照已确立目标的资源使用·依照已确立目标的时间进度·活动或任务的完成准则得到满足·定义的输入以及输出工作产品是可用的·依照质量预期和/或准则的过程质量·依照质量预期和/或准则的产品质量·强调的产品性能问题、趋势·服务级别实施信息的示例:·引用所有已建立的目标·实时度量相关方面,例如:·能力·生产能力·运行性能·运行服务·服务中断时间·可服务时间·工作运行时间", "retrieval_must_hit": ["·关于已定义的定量或定性的可度量指标的度量,与已定义的信息需要相匹配。·用于计算定量或定性的可度量指标的度量项·将过程实施与预期水平进行比较的数据·项目实施信息的示例:·依照已确立目标的资源使用·依照已确立目标的时间进度·活动或任务的完成准则得到满足·定义的输入以及输出工作产品是可用的·依照质量预期和/或准则的过程质量·依照质量预期和/或准则的产品质量·强调的产品性能问题、趋势·服务级别实施信息的示例:·引用所有已建立的目标·实时度量相关方面,例如:·能力·生产能力·运行性能·运行服务·服务中断时间·可服务时间·工作运行时间"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [276], "expected_sections": ["VDA QMC"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_48() -> None:
    case = '{"kind": "retrieval_quality", "query": "过程实施信息代表什么参数？", "must_include": "·关于已定义的定量或定性的可度量指标的度量,与已定义的信息需要相匹配。·用于计算定量或定性的可度量指标的度量项·将过程实施与预期水平进行比较的数据·项目实施信息的示例:·依照已确立目标的资源使用·依照已确立目标的时间进度·活动或任务的完成准则得到满足·定义的输入以及输出工作产品是可用的·依照质量预期和/或准则的过程质量·依照质量预期和/或准则的产品质量·强调的产品性能问题、趋势·服务级别实施信息的示例:·引用所有已建立的目标·实时度量相关方面,例如:·能力·生产能力·运行性能·运行服务·服务中断时间·可服务时间·工作运行时间", "retrieval_must_hit": ["·关于已定义的定量或定性的可度量指标的度量,与已定义的信息需要相匹配。·用于计算定量或定性的可度量指标的度量项·将过程实施与预期水平进行比较的数据·项目实施信息的示例:·依照已确立目标的资源使用·依照已确立目标的时间进度·活动或任务的完成准则得到满足·定义的输入以及输出工作产品是可用的·依照质量预期和/或准则的过程质量·依照质量预期和/或准则的产品质量·强调的产品性能问题、趋势·服务级别实施信息的示例:·引用所有已建立的目标·实时度量相关方面,例如:·能力·生产能力·运行性能·运行服务·服务中断时间·可服务时间·工作运行时间"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [276], "expected_sections": ["VDA QMC"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_49() -> None:
    case = '{"kind": "retrieval_quality", "query": "·软件详细设计的要素：-控制流定义-输入/输出数据格式-算法-定义的数据结构-合理的全局变量-解释性注释，例如，使用自然语言，用于单个要素或整个图表/模型。·表达式语言的示例，取决于软件单元的复杂性或关键性：-自然语言或非正式语言-半形式语言（例如，UML、SysML）-形式语言（例如，基于模型的方法）的参数要求是什么？", "must_include": "·软件详细设计的要素：-控制流定义-输入/输出数据格式-算法-定义的数据结构-合理的全局变量-解释性注释，例如，使用自然语言，用于单个要素或整个图表/模型。·表达式语言的示例，取决于软件单元的复杂性或关键性：-自然语言或非正式语言-半形式语言（例如，UML、SysML）-形式语言（例如，基于模型的方法）", "retrieval_must_hit": ["·软件详细设计的要素：-控制流定义-输入/输出数据格式-算法-定义的数据结构-合理的全局变量-解释性注释，例如，使用自然语言，用于单个要素或整个图表/模型。·表达式语言的示例，取决于软件单元的复杂性或关键性：-自然语言或非正式语言-半形式语言（例如，UML、SysML）-形式语言（例如，基于模型的方法）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [280], "expected_sections": ["VDA QMC"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_50() -> None:
    case = '{"kind": "retrieval_quality", "query": "软件详细设计代表什么参数？", "must_include": "·软件详细设计的要素：-控制流定义-输入/输出数据格式-算法-定义的数据结构-合理的全局变量-解释性注释，例如，使用自然语言，用于单个要素或整个图表/模型。·表达式语言的示例，取决于软件单元的复杂性或关键性：-自然语言或非正式语言-半形式语言（例如，UML、SysML）-形式语言（例如，基于模型的方法）", "retrieval_must_hit": ["·软件详细设计的要素：-控制流定义-输入/输出数据格式-算法-定义的数据结构-合理的全局变量-解释性注释，例如，使用自然语言，用于单个要素或整个图表/模型。·表达式语言的示例，取决于软件单元的复杂性或关键性：-自然语言或非正式语言-半形式语言（例如，UML、SysML）-形式语言（例如，基于模型的方法）"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [280], "expected_sections": ["VDA QMC"], "difficulty": "medium", "query_type": "parameter_lookup", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_51() -> None:
    case = '{"kind": "retrieval_quality", "query": "获取过程组（ACQ）和供应过程组（SPL）有什么区别？", "must_include": "获取过程组（ACQ）", "retrieval_must_hit": ["获取过程组（ACQ）", "供应过程组（SPL）"], "assert_mode": "rich_answer", "source": "local_rq", "difficulty": "hard", "query_type": "comparison", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_52() -> None:
    case = '{"kind": "retrieval_quality", "query": ". 主要生命周期过程类别有什么要求？", "must_include": ". 主要生命周期过程类别", "retrieval_must_hit": [". 主要生命周期过程类别"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [32], "expected_sections": ["3.1.1. 主要生命周期过程类别"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_53() -> None:
    case = '{"kind": "retrieval_quality", "query": ". 评定和聚合的方法有什么要求？", "must_include": ". 评定和聚合的方法", "retrieval_must_hit": [". 评定和聚合的方法"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [46], "expected_sections": ["3.2.3. 评定和聚合的方法"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_54() -> None:
    case = '{"kind": "retrieval_quality", "query": ". 过程能力等级模型有什么要求？", "must_include": ". 过程能力等级模型", "retrieval_must_hit": [". 过程能力等级模型"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [50], "expected_sections": ["3.2.4. 过程能力等级模型"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_55() -> None:
    case = '{"kind": "retrieval_quality", "query": ". 信息项与工作产品有什么要求？", "must_include": ". 信息项与工作产品", "retrieval_must_hit": [". 信息项与工作产品"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [56], "expected_sections": ["3.3.2.1. 信息项与工作产品"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_56() -> None:
    case = '{"kind": "retrieval_quality", "query": "Base Practices有什么要求？", "must_include": "Base Practices", "retrieval_must_hit": ["Base Practices"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [110], "expected_sections": ["requirement"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_57() -> None:
    case = '{"kind": "retrieval_quality", "query": "Annex C.1 “插件”的概念有什么要求？", "must_include": "Annex C.1 “插件”的概念", "retrieval_must_hit": ["Annex C.1 “插件”的概念"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [326], "expected_sections": ["Annex C.1 “插件”的概念"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_58() -> None:
    case = '{"kind": "retrieval_quality", "query": "Annex C.3 机器学习工程过程的整合有什么要求？", "must_include": "Annex C.3 机器学习工程过程的整合", "retrieval_must_hit": ["Annex C.3 机器学习工程过程的整合"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [330], "expected_sections": ["Annex C.3 机器学习工程过程的整合"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_59() -> None:
    case = '{"kind": "retrieval_quality", "query": "ACQ.4 基本实践的流程是什么？", "must_include": "ACQ.4 基本实践", "retrieval_must_hit": ["ACQ.4 基本实践"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [65], "expected_sections": ["32"], "difficulty": "medium", "query_type": "timing_lookup", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_60() -> None:
    case = '{"kind": "retrieval_quality", "query": "2.1. SPL.2 产品发布的流程是什么？", "must_include": "2.1. SPL.2 产品发布", "retrieval_must_hit": ["2.1. SPL.2 产品发布"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [69], "expected_sections": ["4.2.1"], "difficulty": "medium", "query_type": "timing_lookup", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_61() -> None:
    case = '{"kind": "retrieval_quality", "query": "SPL.2 基本实践的流程是什么？", "must_include": "SPL.2 基本实践", "retrieval_must_hit": ["SPL.2 基本实践"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [70], "expected_sections": ["35"], "difficulty": "medium", "query_type": "timing_lookup", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_62() -> None:
    case = '{"kind": "retrieval_quality", "query": "SYS.1 基本实践的流程是什么？", "must_include": "SYS.1 基本实践", "retrieval_must_hit": ["SYS.1 基本实践"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [75], "expected_sections": ["37"], "difficulty": "medium", "query_type": "timing_lookup", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_63() -> None:
    case = '{"kind": "retrieval_quality", "query": "3.2. SYS.2 系统需求分析的流程是什么？", "must_include": "3.2. SYS.2 系统需求分析", "retrieval_must_hit": ["3.2. SYS.2 系统需求分析"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [78], "expected_sections": ["4.3.2"], "difficulty": "medium", "query_type": "timing_lookup", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_64() -> None:
    case = '{"kind": "answer_quality", "query": "·由承诺/协议的所有参与方签署·建立对什么的承诺·建立为满足承诺所需的资源,例如:·时间·人·预算·设备·设施是多少", "must_include": "·由承诺/协议的所有参与方签署·建立对什么的承诺·建立为满足承诺所需的资源,例如:·时间·人·预算·设备·设施", "retrieval_must_hit": ["·由承诺/协议的所有参与方签署·建立对什么的承诺·建立为满足承诺所需的资源,例如:·时间·人·预算·设备·设施"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_65() -> None:
    case = '{"kind": "answer_quality", "query": "·关于已定义的定量或定性的可度量指标的度量,与已定义的信息需要相匹配。·用于计算定量或定性的可度量指标的度量项·将过程实施与预期水平进行比较的数据·项目实施信息的示例:·依照已确立目标的资源使用·依照已确立目标的时间进度·活动或任务的完成准则得到满足·定义的输入以及输出工作产品是可用的·依照质量预期和/或准则的过程质量·依照质量预期和/或准则的产品质量·强调的产品性能问题、趋势·服务级别实施信息的示例:·引用所有已建立的目标·实时度量相关方面,例如:·能力·生产能力·运行性能·运行服务·服务中断时间·可服务时间·工作运行时间是多少", "must_include": "·关于已定义的定量或定性的可度量指标的度量,与已定义的信息需要相匹配。·用于计算定量或定性的可度量指标的度量项·将过程实施与预期水平进行比较的数据·项目实施信息的示例:·依照已确立目标的资源使用·依照已确立目标的时间进度·活动或任务的完成准则得到满足·定义的输入以及输出工作产品是可用的·依照质量预期和/或准则的过程质量·依照质量预期和/或准则的产品质量·强调的产品性能问题、趋势·服务级别实施信息的示例:·引用所有已建立的目标·实时度量相关方面,例如:·能力·生产能力·运行性能·运行服务·服务中断时间·可服务时间·工作运行时间", "retrieval_must_hit": ["·关于已定义的定量或定性的可度量指标的度量,与已定义的信息需要相匹配。·用于计算定量或定性的可度量指标的度量项·将过程实施与预期水平进行比较的数据·项目实施信息的示例:·依照已确立目标的资源使用·依照已确立目标的时间进度·活动或任务的完成准则得到满足·定义的输入以及输出工作产品是可用的·依照质量预期和/或准则的过程质量·依照质量预期和/或准则的产品质量·强调的产品性能问题、趋势·服务级别实施信息的示例:·引用所有已建立的目标·实时度量相关方面,例如:·能力·生产能力·运行性能·运行服务·服务中断时间·可服务时间·工作运行时间"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_66() -> None:
    case = '{"kind": "answer_quality", "query": "·软件详细设计的要素：-控制流定义-输入/输出数据格式-算法-定义的数据结构-合理的全局变量-解释性注释，例如，使用自然语言，用于单个要素或整个图表/模型。·表达式语言的示例，取决于软件单元的复杂性或关键性：-自然语言或非正式语言-半形式语言（例如，UML、SysML）-形式语言（例如，基于模型的方法）是多少", "must_include": "·软件详细设计的要素：-控制流定义-输入/输出数据格式-算法-定义的数据结构-合理的全局变量-解释性注释，例如，使用自然语言，用于单个要素或整个图表/模型。·表达式语言的示例，取决于软件单元的复杂性或关键性：-自然语言或非正式语言-半形式语言（例如，UML、SysML）-形式语言（例如，基于模型的方法）", "retrieval_must_hit": ["·软件详细设计的要素：-控制流定义-输入/输出数据格式-算法-定义的数据结构-合理的全局变量-解释性注释，例如，使用自然语言，用于单个要素或整个图表/模型。·表达式语言的示例，取决于软件单元的复杂性或关键性：-自然语言或非正式语言-半形式语言（例如，UML、SysML）-形式语言（例如，基于模型的方法）"], "assert_mode": "rich_answer", "expected_answer_mode": "parameter_value", "forbidden_contains": ["没有找到足够的结构化结果。", "GB：代替"], "expected_evidence_shape": "parameter_value", "source": "local_aq", "query_type": "parameter_lookup", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_67() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第1页 Automotive SPICE® Process Reference Mo", "must_include": "Automotive SPICE® Process Reference Mo", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_68() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第2页 Automotive SPICE<sup>®</sup> 过程参考模型 过程", "must_include": "Automotive SPICE<sup>®</sup> 过程参考模型 过程", "source": "local", "assert_mode": "context_contains", "page_no": 2, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_69() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第3页 This document reproduces relevant mate", "must_include": "This document reproduces relevant mate", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_70() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第4页 悠牧砣信息科技（上海）有限公司 UMOVCOM 中国（上海）自由贸易试验区芳", "must_include": "悠牧砣信息科技（上海）有限公司 UMOVCOM 中国（上海）自由贸易试验区芳", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_71() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第6页 ### 衍生著作 未经 VDA 质量管理中心的事先同意，不得更改、转换或扩展", "must_include": "### 衍生著作 未经 VDA 质量管理中心的事先同意，不得更改、转换或扩展", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_72() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第7页 ### Document history | Version | Date", "must_include": "### Document history | Version | Date", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_73() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第13页 Process capability levels and process", "must_include": "Process capability levels and process", "source": "local", "assert_mode": "context_contains", "page_no": 13, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_74() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第15页 175 ### List of Figures Figure 1 – Pro", "must_include": "175 ### List of Figures Figure 1 – Pro", "source": "local", "assert_mode": "context_contains", "page_no": 15, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_75() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第17页 The Automotive SPICE process assessmen", "must_include": "The Automotive SPICE process assessmen", "source": "local", "assert_mode": "context_contains", "page_no": 17, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_76() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第18页 Automotive SPICE 有其本身的过程参考模型(PRM)，是基于", "must_include": "Automotive SPICE 有其本身的过程参考模型(PRM)，是基于", "source": "local", "assert_mode": "context_contains", "page_no": 18, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_77() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第19页 The notion of application parameter is", "must_include": "The notion of application parameter is", "source": "local", "assert_mode": "context_contains", "page_no": 19, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_78() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第20页 | | 基线 | Automotive SPICE V4.0 | 一组已定义", "must_include": "| | 基线 | Automotive SPICE V4.0 | 一组已定义", "source": "local", "assert_mode": "context_contains", "page_no": 20, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_79() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第24页 | | 确认措施 | Automotive SPICE V4.0 | 确认措", "must_include": "| | 确认措施 | Automotive SPICE V4.0 | 确认措", "source": "local", "assert_mode": "context_contains", "page_no": 24, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_80() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第26页 VDA QMC AUTOMOTIVE SPICE® ### 1.3.缩略语", "must_include": "VDA QMC AUTOMOTIVE SPICE® ### 1.3.缩略语", "source": "local", "assert_mode": "context_contains", "page_no": 26, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_81() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第28页 附录 A 提供过程评估模型及过程参考模型对于 ISO/IEC 33004:2", "must_include": "附录 A 提供过程评估模型及过程参考模型对于 ISO/IEC 33004:2", "source": "local", "assert_mode": "context_contains", "page_no": 28, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_82() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第29页 Process capability determination The c", "must_include": "Process capability determination The c", "source": "local", "assert_mode": "context_contains", "page_no": 29, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_83() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第30页 过程能力确定 使用过程评估模型来确定过程能力的概念是基于一个二维框架。第一个", "must_include": "过程能力确定 使用过程评估模型来确定过程能力的概念是基于一个二维框架。第一个", "source": "local", "assert_mode": "context_contains", "page_no": 30, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_84() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第31页 These process groups are organized int", "must_include": "These process groups are organized int", "source": "local", "assert_mode": "context_contains", "page_no": 31, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_85() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第32页 主要生命周期过程类别 主要生命周期过程类别是由适用于从供应商处获取产品的过程", "must_include": "主要生命周期过程类别 主要生命周期过程类别是由适用于从供应商处获取产品的过程", "source": "local", "assert_mode": "context_contains", "page_no": 32, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_86() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第33页 **SYS.1** Requirements Elicitation **S", "must_include": "**SYS.1** Requirements Elicitation **S", "source": "local", "assert_mode": "context_contains", "page_no": 33, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_87() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第35页 **MLE.1** Machine Learning Requirement", "must_include": "**MLE.1** Machine Learning Requirement", "source": "local", "assert_mode": "context_contains", "page_no": 35, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_88() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第36页 VDA QMC AUTOMOTIVE SPICE® SWE.6 软件验证 表", "must_include": "VDA QMC AUTOMOTIVE SPICE® SWE.6 软件验证 表", "source": "local", "assert_mode": "context_contains", "page_no": 36, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_89() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第38页 为了能够进行评定，度量框架提供了定义过程能力的有可度量特性的过程属性。每个过", "must_include": "为了能够进行评定，度量框架提供了定义过程能力的有可度量特性的过程属性。每个过", "source": "local", "assert_mode": "context_contains", "page_no": 38, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_90() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第39页 A capability level is characterized by", "must_include": "A capability level is characterized by", "source": "local", "assert_mode": "context_contains", "page_no": 39, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_91() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第40页 过程属性是通过提供过程能力的度量，对达成程度进行评估的过程特征。过程属性适用", "must_include": "过程属性是通过提供过程能力的度量，对达成程度进行评估的过程特征。过程属性适用", "source": "local", "assert_mode": "context_contains", "page_no": 40, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_92() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第41页 VDA QMC AUTOMOTIVE SPICE® | Level 2: M", "must_include": "VDA QMC AUTOMOTIVE SPICE® | Level 2: M", "source": "local", "assert_mode": "context_contains", "page_no": 41, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_93() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第42页 VDA QMC AUTOMOTIVE SPICE® | 等级 2 级:已管理", "must_include": "VDA QMC AUTOMOTIVE SPICE® | 等级 2 级:已管理", "source": "local", "assert_mode": "context_contains", "page_no": 42, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_94() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第43页 The corresponding percentages shall be", "must_include": "The corresponding percentages shall be", "source": "local", "assert_mode": "context_contains", "page_no": 43, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_95() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第44页 | 表 16—评定尺度 以上所定义的顺序尺度应以过程属性达成的百分比来理解", "must_include": "| 表 16—评定尺度 以上所定义的顺序尺度应以过程属性达成的百分比来理解", "source": "local", "assert_mode": "context_contains", "page_no": 44, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_96() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第45页 VDA QMC AUTOMOTIVE SPICE® The correspo", "must_include": "VDA QMC AUTOMOTIVE SPICE® The correspo", "source": "local", "assert_mode": "context_contains", "page_no": 45, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_97() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第46页 > > 评定方法的使用可根据评估的类型、范围和环境的不同而不同。主评估师应决", "must_include": "> > 评定方法的使用可根据评估的类型、范围和环境的不同而不同。主评估师应决", "source": "local", "assert_mode": "context_contains", "page_no": 46, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_98() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第47页 VDA QMC AUTOMOTIVE SPICE® *** *a) Each", "must_include": "VDA QMC AUTOMOTIVE SPICE® *** *a) Each", "source": "local", "assert_mode": "context_contains", "page_no": 47, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_99() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第48页 *** 原则上，ISO/IEC 33020 中定义的三种评定方法依赖于 a)", "must_include": "*** 原则上，ISO/IEC 33020 中定义的三种评定方法依赖于 a)", "source": "local", "assert_mode": "context_contains", "page_no": 48, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_100() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第49页 | Scale | Process attribute | Rating |", "must_include": "| Scale | Process attribute | Rating |", "source": "local", "assert_mode": "context_contains", "page_no": 49, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_101() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第51页 Assessment indicators According to ISO", "must_include": "Assessment indicators According to ISO", "source": "local", "assert_mode": "context_contains", "page_no": 51, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_102() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第52页 评估指标** 根据 ISO/IEC 33004，过程评估模型需要定义一套评估", "must_include": "评估指标** 根据 ISO/IEC 33004，过程评估模型需要定义一套评估", "source": "local", "assert_mode": "context_contains", "page_no": 52, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_103() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第53页 Therefore, information items including", "must_include": "Therefore, information items including", "source": "local", "assert_mode": "context_contains", "page_no": 53, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_104() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第54页 通用实践 ( GP ) 适用于能力等级 2 级到 5 级** 通用实践提供了", "must_include": "通用实践 ( GP ) 适用于能力等级 2 级到 5 级** 通用实践提供了", "source": "local", "assert_mode": "context_contains", "page_no": 54, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_105() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第55页 Information items versus work products", "must_include": "Information items versus work products", "source": "local", "assert_mode": "context_contains", "page_no": 55, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_106() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第56页 理解信息项和工作产品 为了判断过程成果和过程属性成就的存在或缺失，评估需要获", "must_include": "理解信息项和工作产品 为了判断过程成果和过程属性成就的存在或缺失，评估需要获", "source": "local", "assert_mode": "context_contains", "page_no": 56, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_107() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第57页 Context-sensitivity means that assesso", "must_include": "Context-sensitivity means that assesso", "source": "local", "assert_mode": "context_contains", "page_no": 57, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_108() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第59页 Why a PRM and PAM are not a lifecycle", "must_include": "Why a PRM and PAM are not a lifecycle", "source": "local", "assert_mode": "context_contains", "page_no": 59, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_109() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第60页 相反，符合 ISO/IEC 33004（以前的 ISO/IEC 15504-", "must_include": "相反，符合 ISO/IEC 33004（以前的 ISO/IEC 15504-", "source": "local", "assert_mode": "context_contains", "page_no": 60, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_110() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第62页 与过程维度中各个过程相关的表包含过程参考模型 ( 由红色栏表示 ) 和定义过", "must_include": "与过程维度中各个过程相关的表包含过程参考模型 ( 由红色栏表示 ) 和定义过", "source": "local", "assert_mode": "context_contains", "page_no": 62, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_111() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第63页 ACQ.4 Supplier Monitoring** | Process", "must_include": "ACQ.4 Supplier Monitoring** | Process", "source": "local", "assert_mode": "context_contains", "page_no": 63, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_112() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第65页 VDA QMC AUTOMOTIVE SPICE® --- **Base P", "must_include": "VDA QMC AUTOMOTIVE SPICE® --- **Base P", "source": "local", "assert_mode": "context_contains", "page_no": 65, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_113() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第66页 **ACQ.4.BP2: 交换所有约定的信息。** 使用客户和供应商之间定义", "must_include": "**ACQ.4.BP2: 交换所有约定的信息。** 使用客户和供应商之间定义", "source": "local", "assert_mode": "context_contains", "page_no": 66, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_114() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第67页 VDA QMC AUTOMOTIVE SPICE® | Base Pract", "must_include": "VDA QMC AUTOMOTIVE SPICE® | Base Pract", "source": "local", "assert_mode": "context_contains", "page_no": 67, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_115() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第69页 *Note 3: Unique identification may be", "must_include": "*Note 3: Unique identification may be", "source": "local", "assert_mode": "context_contains", "page_no": 69, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_116() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第73页 SYS.1 Requirements Elicitation** | Pro", "must_include": "SYS.1 Requirements Elicitation** | Pro", "source": "local", "assert_mode": "context_contains", "page_no": 73, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_117() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第75页 --- | SYS.1 Requirements Elicitation |", "must_include": "--- | SYS.1 Requirements Elicitation |", "source": "local", "assert_mode": "context_contains", "page_no": 75, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_118() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第77页 SYS.2 System Requirements Analysis | P", "must_include": "SYS.2 System Requirements Analysis | P", "source": "local", "assert_mode": "context_contains", "page_no": 77, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_119() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第79页 *Note 5: See MAN.3.BP3 for project fea", "must_include": "*Note 5: See MAN.3.BP3 for project fea", "source": "local", "assert_mode": "context_contains", "page_no": 79, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_120() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第85页 Note 5: Examples for methods being sui", "must_include": "Note 5: Examples for methods being sui", "source": "local", "assert_mode": "context_contains", "page_no": 85, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_121() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第86页 * 注 5: 适合分析技术方面方法的示例如，原型、仿真和定性分析(例如 FM", "must_include": "* 注 5: 适合分析技术方面方法的示例如，原型、仿真和定性分析(例如 FM", "source": "local", "assert_mode": "context_contains", "page_no": 86, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_122() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第87页 | | **Process outcomes** | 1) Verifica", "must_include": "| | **Process outcomes** | 1) Verifica", "source": "local", "assert_mode": "context_contains", "page_no": 87, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_123() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第89页 *Note 2: Examples for selection criter", "must_include": "*Note 2: Examples for selection criter", "source": "local", "assert_mode": "context_contains", "page_no": 89, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_124() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第90页 VDA QMC AUTOMOTIVE SPICE® **基本实践** **S", "must_include": "VDA QMC AUTOMOTIVE SPICE® **基本实践** **S", "source": "local", "assert_mode": "context_contains", "page_no": 90, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_125() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第91页 *Note 6: Providing all necessary infor", "must_include": "*Note 6: Providing all necessary infor", "source": "local", "assert_mode": "context_contains", "page_no": 91, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_126() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第92页 | SYS.4 系统集成与集成验证 | 成果 1 | 成果 2 | 成果 3", "must_include": "| SYS.4 系统集成与集成验证 | 成果 1 | 成果 2 | 成果 3", "source": "local", "assert_mode": "context_contains", "page_no": 92, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_127() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第93页 SYS.5 System Verification | Process ID", "must_include": "SYS.5 System Verification | Process ID", "source": "local", "assert_mode": "context_contains", "page_no": 93, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_128() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第95页 *Note 2: Examples for criteria for sel", "must_include": "*Note 2: Examples for criteria for sel", "source": "local", "assert_mode": "context_contains", "page_no": 95, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_129() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第97页 VDA QMC AUTOMOTIVE SPICE® | SYS.5 Syst", "must_include": "VDA QMC AUTOMOTIVE SPICE® | SYS.5 Syst", "source": "local", "assert_mode": "context_contains", "page_no": 97, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_130() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第98页 VDA QMC AUTOMOTIVE SPICE® | SYS.5 系统验证", "must_include": "VDA QMC AUTOMOTIVE SPICE® | SYS.5 系统验证", "source": "local", "assert_mode": "context_contains", "page_no": 98, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_131() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第99页 SWE.1 Software Requirements Analysis |", "must_include": "SWE.1 Software Requirements Analysis |", "source": "local", "assert_mode": "context_contains", "page_no": 99, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_132() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第101页 **SWE.1.BP3: Analyze software requirem", "must_include": "**SWE.1.BP3: Analyze software requirem", "source": "local", "assert_mode": "context_contains", "page_no": 101, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_133() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第104页 VDA QMC AUTOMOTIVE SPICE® | 13-52 沟通证据", "must_include": "VDA QMC AUTOMOTIVE SPICE® | 13-52 沟通证据", "source": "local", "assert_mode": "context_contains", "page_no": 104, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_134() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第105页 *Note 4: See MAN.3.BP3 for project fea", "must_include": "*Note 4: See MAN.3.BP3 for project fea", "source": "local", "assert_mode": "context_contains", "page_no": 105, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_135() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第107页 VDA QMC AUTOMOTIVE SPICE® | Base Pract", "must_include": "VDA QMC AUTOMOTIVE SPICE® | Base Pract", "source": "local", "assert_mode": "context_contains", "page_no": 107, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_136() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第108页 VDA QMC AUTOMOTIVE SPICE® | 基本实践 | | |", "must_include": "VDA QMC AUTOMOTIVE SPICE® | 基本实践 | | |", "source": "local", "assert_mode": "context_contains", "page_no": 108, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_137() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第109页 For mapping such application domain va", "must_include": "For mapping such application domain va", "source": "local", "assert_mode": "context_contains", "page_no": 109, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_138() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第110页 VDA QMC AUTOMOTIVE SPICE® *** **基本实践**", "must_include": "VDA QMC AUTOMOTIVE SPICE® *** **基本实践**", "source": "local", "assert_mode": "context_contains", "page_no": 110, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_139() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第111页 | SWE.3 Software Detailed Design and U", "must_include": "| SWE.3 Software Detailed Design and U", "source": "local", "assert_mode": "context_contains", "page_no": 111, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_140() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第112页 | SWE.3 软件详细设计和单元构建 | 成果 1 | 成果 2 | 成果", "must_include": "| SWE.3 软件详细设计和单元构建 | 成果 1 | 成果 2 | 成果", "source": "local", "assert_mode": "context_contains", "page_no": 112, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_141() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第117页 VDA QMC AUTOMOTIVE SPICE® *** **Proces", "must_include": "VDA QMC AUTOMOTIVE SPICE® *** **Proces", "source": "local", "assert_mode": "context_contains", "page_no": 117, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_142() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第118页 VDA QMC AUTOMOTIVE SPICE® --- **过程成果**", "must_include": "VDA QMC AUTOMOTIVE SPICE® --- **过程成果**", "source": "local", "assert_mode": "context_contains", "page_no": 118, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_143() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第119页 *Note 4: Examples for selection criter", "must_include": "*Note 4: Examples for selection criter", "source": "local", "assert_mode": "context_contains", "page_no": 119, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_144() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第121页 *Note 10: Providing all necessary info", "must_include": "*Note 10: Providing all necessary info", "source": "local", "assert_mode": "context_contains", "page_no": 121, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_145() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第122页 | SWE.5 软件组件验证与集成验证 | 成果 1 | 成果 2 | 成果", "must_include": "| SWE.5 软件组件验证与集成验证 | 成果 1 | 成果 2 | 成果", "source": "local", "assert_mode": "context_contains", "page_no": 122, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_146() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第123页 SWE.6 Software Verification | Process", "must_include": "SWE.6 Software Verification | Process", "source": "local", "assert_mode": "context_contains", "page_no": 123, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_147() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第125页 > Note 2: Examples for selection crite", "must_include": "> Note 2: Examples for selection crite", "source": "local", "assert_mode": "context_contains", "page_no": 125, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_148() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第126页 * *注 5: 在总结中提供来自测试用例执行的所有必要信息，以便其他方可以判", "must_include": "* *注 5: 在总结中提供来自测试用例执行的所有必要信息，以便其他方可以判", "source": "local", "assert_mode": "context_contains", "page_no": 126, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_149() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第129页 Further examples of sources of intende", "must_include": "Further examples of sources of intende", "source": "local", "assert_mode": "context_contains", "page_no": 129, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_150() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第130页 VDA QMC AUTOMOTIVE SPICE® --- **基本实践**", "must_include": "VDA QMC AUTOMOTIVE SPICE® --- **基本实践**", "source": "local", "assert_mode": "context_contains", "page_no": 130, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_151() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第131页 | VAL.1 Validation | Outcome 1 | Outco", "must_include": "| VAL.1 Validation | Outcome 1 | Outco", "source": "local", "assert_mode": "context_contains", "page_no": 131, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_152() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第132页 | VAL.1 确认 | 成果 1 | 成果 2 | 成果 3 | 成果 4", "must_include": "| VAL.1 确认 | 成果 1 | 成果 2 | 成果 3 | 成果 4", "source": "local", "assert_mode": "context_contains", "page_no": 132, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_153() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第133页 VDA QMC AUTOMOTIVE SPICE® 1) The ML re", "must_include": "VDA QMC AUTOMOTIVE SPICE® 1) The ML re", "source": "local", "assert_mode": "context_contains", "page_no": 133, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_154() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第134页 VDA QMC AUTOMOTIVE SPICE® --- **过程成果**", "must_include": "VDA QMC AUTOMOTIVE SPICE® --- **过程成果**", "source": "local", "assert_mode": "context_contains", "page_no": 134, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_155() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第135页 *Note 7: The ML operating environment", "must_include": "*Note 7: The ML operating environment", "source": "local", "assert_mode": "context_contains", "page_no": 135, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_156() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第139页 MLE.2 Machine Learning Architecture |", "must_include": "MLE.2 Machine Learning Architecture |", "source": "local", "assert_mode": "context_contains", "page_no": 139, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_157() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第141页 *** | MLE.2 Machine Learning Architect", "must_include": "*** | MLE.2 Machine Learning Architect", "source": "local", "assert_mode": "context_contains", "page_no": 141, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_158() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第145页 *Note 4: The ML training and validatio", "must_include": "*Note 4: The ML training and validatio", "source": "local", "assert_mode": "context_contains", "page_no": 145, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_159() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第146页 **MLE.3.BP3: 创建和优化 ML 模型。**根据 ML 架构创建", "must_include": "**MLE.3.BP3: 创建和优化 ML 模型。**根据 ML 架构创建", "source": "local", "assert_mode": "context_contains", "page_no": 146, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_160() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第147页 VDA QMC AUTOMOTIVE SPICE® | Base Pract", "must_include": "VDA QMC AUTOMOTIVE SPICE® | Base Pract", "source": "local", "assert_mode": "context_contains", "page_no": 147, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_161() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第148页 VDA QMC AUTOMOTIVE SPICE® | 基本实践 | | |", "must_include": "VDA QMC AUTOMOTIVE SPICE® | 基本实践 | | |", "source": "local", "assert_mode": "context_contains", "page_no": 148, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_162() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第149页 E.g., weather condition may contain ex", "must_include": "E.g., weather condition may contain ex", "source": "local", "assert_mode": "context_contains", "page_no": 149, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_163() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第150页 *注1：各测试数据点的预期结果可能需要对测试数据进行标注，以支持 ML 模型", "must_include": "*注1：各测试数据点的预期结果可能需要对测试数据进行标注，以支持 ML 模型", "source": "local", "assert_mode": "context_contains", "page_no": 150, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_164() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第151页 **MLE.4.BP6: Ensure consistency and es", "must_include": "**MLE.4.BP6: Ensure consistency and es", "source": "local", "assert_mode": "context_contains", "page_no": 151, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_165() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第155页 HWE.1 Hardware Requirements Analysis |", "must_include": "HWE.1 Hardware Requirements Analysis |", "source": "local", "assert_mode": "context_contains", "page_no": 155, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_166() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第156页 BP1: 定义硬件需求。** 根据已定义的需求特性，使用系统需求和系统架构(", "must_include": "BP1: 定义硬件需求。** 根据已定义的需求特性，使用系统需求和系统架构(", "source": "local", "assert_mode": "context_contains", "page_no": 156, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_167() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第157页 > *Note 7: See MAN.3.BP3 for project f", "must_include": "> *Note 7: See MAN.3.BP3 for project f", "source": "local", "assert_mode": "context_contains", "page_no": 157, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_168() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第158页 BP3: 分析硬件需求。分析已定义的硬件需求（包括它们的相互依赖性），以确保", "must_include": "BP3: 分析硬件需求。分析已定义的硬件需求（包括它们的相互依赖性），以确保", "source": "local", "assert_mode": "context_contains", "page_no": 158, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_169() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第159页 VDA QMC AUTOMOTIVE SPICE® | HWE.1 Hard", "must_include": "VDA QMC AUTOMOTIVE SPICE® | HWE.1 Hard", "source": "local", "assert_mode": "context_contains", "page_no": 159, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_170() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第160页 VDA QMC AUTOMOTIVE SPICE® | HWE.1 硬件需求", "must_include": "VDA QMC AUTOMOTIVE SPICE® | HWE.1 硬件需求", "source": "local", "assert_mode": "context_contains", "page_no": 160, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_171() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第161页 **Process outcomes** 1) A hardware arc", "must_include": "**Process outcomes** 1) A hardware arc", "source": "local", "assert_mode": "context_contains", "page_no": 161, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_172() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第162页 VDA QMC AUTOMOTIVE SPICE® 其目的是：提供已分析的（", "must_include": "VDA QMC AUTOMOTIVE SPICE® 其目的是：提供已分析的（", "source": "local", "assert_mode": "context_contains", "page_no": 162, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_173() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第163页 *Note 6: Examples for technical aspect", "must_include": "*Note 6: Examples for technical aspect", "source": "local", "assert_mode": "context_contains", "page_no": 163, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_174() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第165页 VDA QMC AUTOMOTIVE SPICE® | 04-56 Hard", "must_include": "VDA QMC AUTOMOTIVE SPICE® | 04-56 Hard", "source": "local", "assert_mode": "context_contains", "page_no": 165, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_175() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第167页 This includes<br>• techniques for the", "must_include": "This includes<br>• techniques for the", "source": "local", "assert_mode": "context_contains", "page_no": 167, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_176() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第168页 VDA QMC AUTOMOTIVE SPICE® --- **基本实践**", "must_include": "VDA QMC AUTOMOTIVE SPICE® --- **基本实践**", "source": "local", "assert_mode": "context_contains", "page_no": 168, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_177() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第169页 VDA QMC AUTOMOTIVE SPICE® | HWE.3 Veri", "must_include": "VDA QMC AUTOMOTIVE SPICE® | HWE.3 Veri", "source": "local", "assert_mode": "context_contains", "page_no": 169, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_178() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第170页 VDA QMC AUTOMOTIVE SPICE® | HWE.3 硬件设计", "must_include": "VDA QMC AUTOMOTIVE SPICE® | HWE.3 硬件设计", "source": "local", "assert_mode": "context_contains", "page_no": 170, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_179() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第171页 | | 3) Verification is performed, if a", "must_include": "| | 3) Verification is performed, if a", "source": "local", "assert_mode": "context_contains", "page_no": 171, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_180() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第172页 VDA QMC AUTOMOTIVE SPICE® **过程成果** 1)", "must_include": "VDA QMC AUTOMOTIVE SPICE® **过程成果** 1)", "source": "local", "assert_mode": "context_contains", "page_no": 172, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_181() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第173页 *Note 6: Providing all necessary infor", "must_include": "*Note 6: Providing all necessary infor", "source": "local", "assert_mode": "context_contains", "page_no": 173, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_182() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第174页 *注 6:在总结中提供来自测试用例执行的所有必要信息，以便其他方可以判断结果", "must_include": "*注 6:在总结中提供来自测试用例执行的所有必要信息，以便其他方可以判断结果", "source": "local", "assert_mode": "context_contains", "page_no": 174, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_183() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第175页 SUP.1 Quality Assurance | Process ID |", "must_include": "SUP.1 Quality Assurance | Process ID |", "source": "local", "assert_mode": "context_contains", "page_no": 175, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_184() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第177页 *NOTE 7: The decision whether to escal", "must_include": "*NOTE 7: The decision whether to escal", "source": "local", "assert_mode": "context_contains", "page_no": 177, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_185() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第178页 *注 7：决定是否需要升级不符合项可基于诸如解决延迟、紧急性及风险的准则。*", "must_include": "*注 7：决定是否需要升级不符合项可基于诸如解决延迟、紧急性及风险的准则。*", "source": "local", "assert_mode": "context_contains", "page_no": 178, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_186() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第181页 _NOTE 4: The configuration item proper", "must_include": "_NOTE 4: The configuration item proper", "source": "local", "assert_mode": "context_contains", "page_no": 181, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_187() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第182页 *注 4：可以为单个配置项或一组配置项定义配置项属性。* *注 5：配置项属", "must_include": "*注 4：可以为单个配置项或一组配置项定义配置项属性。* *注 5：配置项属", "source": "local", "assert_mode": "context_contains", "page_no": 182, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_188() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第183页 This may include references to corresp", "must_include": "This may include references to corresp", "source": "local", "assert_mode": "context_contains", "page_no": 183, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_189() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第184页 *注 11：备份和恢复机制可能由项目外的组织单位进行定义和实施。这可包括对相", "must_include": "*注 11：备份和恢复机制可能由项目外的组织单位进行定义和实施。这可包括对相", "source": "local", "assert_mode": "context_contains", "page_no": 184, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_190() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第185页 SUP.9 Problem Resolution Management |", "must_include": "SUP.9 Problem Resolution Management |", "source": "local", "assert_mode": "context_contains", "page_no": 185, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_191() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第188页 *注 6: 收集的数据可以包含的信息有：问题是在哪里发生的、是如何及时被发现", "must_include": "*注 6: 收集的数据可以包含的信息有：问题是在哪里发生的、是如何及时被发现", "source": "local", "assert_mode": "context_contains", "page_no": 188, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_192() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第189页 SUP.10 Change Request Management | Pro", "must_include": "SUP.10 Change Request Management | Pro", "source": "local", "assert_mode": "context_contains", "page_no": 189, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_193() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第191页 *NOTE 7: Examples for informing affect", "must_include": "*NOTE 7: Examples for informing affect", "source": "local", "assert_mode": "context_contains", "page_no": 191, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_194() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第192页 *注 7：通知受影响方的示例可以是每日站会或工具支持的工作流程。* ---", "must_include": "*注 7：通知受影响方的示例可以是每日站会或工具支持的工作流程。* ---", "source": "local", "assert_mode": "context_contains", "page_no": 192, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_195() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第193页 SUP.11 Machine Learning Data Managemen", "must_include": "SUP.11 Machine Learning Data Managemen", "source": "local", "assert_mode": "context_contains", "page_no": 193, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_196() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第194页 SUP.11 机器学习数据管理 过程 ID SUP.11 过程名称 机器学习", "must_include": "SUP.11 机器学习数据管理 过程 ID SUP.11 过程名称 机器学习", "source": "local", "assert_mode": "context_contains", "page_no": 194, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_197() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第197页 VDA QMC AUTOMOTIVE SPICE® | Base Pract", "must_include": "VDA QMC AUTOMOTIVE SPICE® | Base Pract", "source": "local", "assert_mode": "context_contains", "page_no": 197, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_198() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第198页 VDA QMC AUTOMOTIVE SPICE® | 基本实践 | | |", "must_include": "VDA QMC AUTOMOTIVE SPICE® | 基本实践 | | |", "source": "local", "assert_mode": "context_contains", "page_no": 198, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_199() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第199页 MAN.3 Project Management **Process ID*", "must_include": "MAN.3 Project Management **Process ID*", "source": "local", "assert_mode": "context_contains", "page_no": 199, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_200() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第201页 *Note 5: Examples of necessary resourc", "must_include": "*Note 5: Examples of necessary resourc", "source": "local", "assert_mode": "context_contains", "page_no": 201, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_201() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第203页 VDA QMC AUTOMOTIVE SPICE® | MAN.3 Proj", "must_include": "VDA QMC AUTOMOTIVE SPICE® | MAN.3 Proj", "source": "local", "assert_mode": "context_contains", "page_no": 203, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_202() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第204页 VDA QMC AUTOMOTIVE SPICE® | MAN.3 项目管理", "must_include": "VDA QMC AUTOMOTIVE SPICE® | MAN.3 项目管理", "source": "local", "assert_mode": "context_contains", "page_no": 204, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_203() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第205页 MAN.5 Risk Management | Process ID | |", "must_include": "MAN.5 Risk Management | Process ID | |", "source": "local", "assert_mode": "context_contains", "page_no": 205, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_204() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第206页 | | 4) 定义、应用和评估了风险应对措施，以确定风险的状态变化和风险处理", "must_include": "| | 4) 定义、应用和评估了风险应对措施，以确定风险的状态变化和风险处理", "source": "local", "assert_mode": "context_contains", "page_no": 206, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_205() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第207页 *Note 6: Corrective actions may involv", "must_include": "*Note 6: Corrective actions may involv", "source": "local", "assert_mode": "context_contains", "page_no": 207, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_206() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第208页 | MAN.5 风险管理 | 成果 1 | 成果 2 | 成果 3 | 成果", "must_include": "| MAN.5 风险管理 | 成果 1 | 成果 2 | 成果 3 | 成果", "source": "local", "assert_mode": "context_contains", "page_no": 208, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_207() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第209页 MAN.6 Measurement | Process ID | | :--", "must_include": "MAN.6 Measurement | Process ID | | :--", "source": "local", "assert_mode": "context_contains", "page_no": 209, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_208() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第211页 --- | MAN.6 Measurement | Outcome 1 |", "must_include": "--- | MAN.6 Measurement | Outcome 1 |", "source": "local", "assert_mode": "context_contains", "page_no": 211, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_209() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第213页 Process improvement process group (PIM", "must_include": "Process improvement process group (PIM", "source": "local", "assert_mode": "context_contains", "page_no": 213, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_210() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第215页 *Note 4: Analysis may include problem", "must_include": "*Note 4: Analysis may include problem", "source": "local", "assert_mode": "context_contains", "page_no": 215, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_211() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第216页 注 6：问题识别的来源可包括：过程评估结果、审核、客户满意度报告、组织有效性", "must_include": "注 6：问题识别的来源可包括：过程评估结果、审核、客户满意度报告、组织有效性", "source": "local", "assert_mode": "context_contains", "page_no": 216, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_212() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第219页 REU.2 Management of Products for Reuse", "must_include": "REU.2 Management of Products for Reuse", "source": "local", "assert_mode": "context_contains", "page_no": 219, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_213() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第221页 *Note 7: The communication with the pr", "must_include": "*Note 7: The communication with the pr", "source": "local", "assert_mode": "context_contains", "page_no": 221, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_214() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第222页 VDA QMC AUTOMOTIVE SPICE® REU 2.BP4: 确", "must_include": "VDA QMC AUTOMOTIVE SPICE® REU 2.BP4: 确", "source": "local", "assert_mode": "context_contains", "page_no": 222, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_215() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第223页 *Note: Due to lack of a defined proces", "must_include": "*Note: Due to lack of a defined proces", "source": "local", "assert_mode": "context_contains", "page_no": 223, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_216() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第225页 PA 1.1 Process performance process att", "must_include": "PA 1.1 Process performance process att", "source": "local", "assert_mode": "context_contains", "page_no": 225, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_217() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第227页 PA 2.1 Process performance management", "must_include": "PA 2.1 Process performance management", "source": "local", "assert_mode": "context_contains", "page_no": 227, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_218() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第229页 *Note 1: Budget targets and delivery d", "must_include": "*Note 1: Budget targets and delivery d", "source": "local", "assert_mode": "context_contains", "page_no": 229, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_219() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第230页 *注 3：过程实施策略不一定专门针对每个过程进行记录。适用于多个过程的要素可", "must_include": "*注 3：过程实施策略不一定专门针对每个过程进行记录。适用于多个过程的要素可", "source": "local", "assert_mode": "context_contains", "page_no": 230, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000005_golden_220() -> None:
    case = '{"kind": "page_coverage", "query": "AutomotiveSPICE_PAM_40_Chinese：第231页 *Note 7: Qualification of individuals", "must_include": "*Note 7: Qualification of individuals", "source": "local", "assert_mode": "context_contains", "page_no": 231, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))
