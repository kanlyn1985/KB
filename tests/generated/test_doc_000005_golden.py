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
def test_doc_000005_golden_67() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：Automotive SPICE® Process Reference Model", "must_include": "Automotive SPICE® Process Reference Model", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_68() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：Automotive SPICE<sup>®</sup> 过程参考模型 过程评估模型", "must_include": "Automotive SPICE<sup>®</sup> 过程参考模型 过程评估模型", "source": "local", "assert_mode": "context_contains", "page_no": 2, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_69() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：VDA QMC AUTOMOTIVE SPICE® *** ### Copyrigh", "must_include": "VDA QMC AUTOMOTIVE SPICE® *** ### Copyrigh", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_70() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：This document reproduces relevant material", "must_include": "This document reproduces relevant material", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_71() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：### Acknowledgement The VDA, the VDA QMC a", "must_include": "### Acknowledgement The VDA, the VDA QMC a", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_72() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：We would like to thank all involved people", "must_include": "We would like to thank all involved people", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_73() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：### Derivative works You may not alter, tr", "must_include": "### Derivative works You may not alter, tr", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_74() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：Such consent may be given provided ISO cop", "must_include": "Such consent may be given provided ISO cop", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_75() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：本文的中文翻译是由以下公司提供支持 实施。", "must_include": "本文的中文翻译是由以下公司提供支持 实施。", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_76() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：悠牧砣信息科技（上海）有限公司 UMOVCOM 中国（上海）自由贸易试验区芳春路 4", "must_include": "悠牧砣信息科技（上海）有限公司 UMOVCOM 中国（上海）自由贸易试验区芳春路 4", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_77() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：VDA QMC VDA QMC 德国汽车工业协会 SWQ AB China VDA-", "must_include": "VDA QMC VDA QMC 德国汽车工业协会 SWQ AB China VDA-", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_78() -> None:
    case = '{"kind": "evidence", "query": "本文复制的相关资料来自于： * **ISO/IEC 33020:2019** 信息技", "must_include": "本文复制的相关资料来自于： * **ISO/IEC 33020:2019** 信息技", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_79() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：VDA QMC AUTOMOTIVE SPICE® --- ‘ISO/IEC 155", "must_include": "VDA QMC AUTOMOTIVE SPICE® --- ‘ISO/IEC 155", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_80() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：### 致谢 VDA、VDA QMC 及第 13 工作组诚挚感谢 intacs®工作", "must_include": "### 致谢 VDA、VDA QMC 及第 13 工作组诚挚感谢 intacs®工作", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_81() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：### 衍生著作 未经 VDA 质量管理中心的事先同意，不得更改、转换或扩展本文。在", "must_include": "### 衍生著作 未经 VDA 质量管理中心的事先同意，不得更改、转换或扩展本文。在", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_82() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：本文中所含的详细描述可作为任意工具或其他资料的一部分，以支持过程评估的实施，使过程评", "must_include": "本文中所含的详细描述可作为任意工具或其他资料的一部分，以支持过程评估的实施，使过程评", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_83() -> None:
    case = '{"kind": "evidence", "query": "IEC 33020：所有衍生著作的分发均应免费提供给接收方。", "must_include": "所有衍生著作的分发均应免费提供给接收方。", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_84() -> None:
    case = '{"kind": "definition", "query": "在IEC 33020中，什么是获取过程组（ACQ）？", "must_include": "获取过程组（ACQ）", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_85() -> None:
    case = '{"kind": "definition_detail", "query": "在IEC 33020中，获取过程组（ACQ） 的定义是什么？", "must_include": "获取过程组(ACQ)包括客户执行的过程,或者当供应商为了获取产品或服务而作为其供应商", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_86() -> None:
    case = '{"kind": "definition", "query": "在IEC 33020中，什么是供应过程组（SPL）？", "must_include": "供应过程组（SPL）", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_87() -> None:
    case = '{"kind": "definition_detail", "query": "在IEC 33020中，供应过程组（SPL） 的定义是什么？", "must_include": "供应过程组(SPL)包括供应商为了供应产品和/或服务所执行的过程。", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_88() -> None:
    case = '{"kind": "definition", "query": "在IEC 33020中，什么是系统工程过程组（SYS）？", "must_include": "系统工程过程组（SYS）", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_89() -> None:
    case = '{"kind": "definition_detail", "query": "在IEC 33020中，系统工程过程组（SYS） 的定义是什么？", "must_include": "系统工程过程组(SYS)由多个过程组成,这些过程用于管理客户和内部需求的挖掘和管理、", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_90() -> None:
    case = '{"kind": "definition", "query": "在IEC 33020中，什么是确认过程组（VAL）？", "must_include": "确认过程组（VAL）", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_91() -> None:
    case = '{"kind": "definition_detail", "query": "在IEC 33020中，确认过程组（VAL） 的定义是什么？", "must_include": "确认过程组(VAL)由一个过程组成,执行该过程提供证据,来证明待交付产品满足其预期用", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_92() -> None:
    case = '{"kind": "definition", "query": "在IEC 33020中，什么是软件工程过程组（SWE）？", "must_include": "软件工程过程组（SWE）", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_93() -> None:
    case = '{"kind": "definition_detail", "query": "在IEC 33020中，软件工程过程组（SWE） 的定义是什么？", "must_include": "软件工程过程组(SWE)由多个过程组成,这些过程用于管理源自系统需求的软件需求的管理", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_94() -> None:
    case = '{"kind": "definition", "query": "在IEC 33020中，什么是机器学习工程过程组（MLE）？", "must_include": "机器学习工程过程组（MLE）", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_95() -> None:
    case = '{"kind": "definition_detail", "query": "在IEC 33020中，机器学习工程过程组（MLE） 的定义是什么？", "must_include": "机器学习工程过程组(MLE)由多个过程组成,这些过程用于管理源自软件需求的 ML 需", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_96() -> None:
    case = '{"kind": "definition", "query": "在IEC 33020中，什么是硬件工程过程组（HWE）？", "must_include": "硬件工程过程组（HWE）", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_97() -> None:
    case = '{"kind": "definition_detail", "query": "在IEC 33020中，硬件工程过程组（HWE） 的定义是什么？", "must_include": "硬件工程过程组(HWE)由多个过程组成,这些过程用于管理从系统需求中衍生出来的硬件需", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_98() -> None:
    case = '{"kind": "definition", "query": "在IEC 33020中，什么是管理过程组（MAN）？", "must_include": "管理过程组（MAN）", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_99() -> None:
    case = '{"kind": "definition_detail", "query": "在IEC 33020中，管理过程组（MAN） 的定义是什么？", "must_include": "管理过程组(MAN)是由在生命周期内管理任何类型的项目或过程的任何人可使用的过程所组", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_100() -> None:
    case = '{"kind": "standard", "query": "IEC 33020 的标准号和实施日期是什么？", "must_include": "IEC 33020", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_101() -> None:
    case = '{"kind": "standard", "query": "IEC 33020 对应的标准编号是什么？", "must_include": "IEC 33020", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_102() -> None:
    case = '{"kind": "standard", "query": "IEC 33020 的现行标准号是什么？", "must_include": "IEC 33020", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_103() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“Copyright notice”这一章节？", "must_include": "Copyright notice", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_104() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“3. Process capability determination”这一章节？", "must_include": "3. Process capability determination", "source": "local", "assert_mode": "context_contains", "page_no": 29, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_105() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“3.2.3. 评定和聚合的方法”这一章节？", "must_include": "3.2.3. 评定和聚合的方法", "source": "local", "assert_mode": "context_contains", "page_no": 46, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_106() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“4. 过程参考模型和实施指标 ( 等级 1 级 )”这一章节？", "must_include": "4. 过程参考模型和实施指标 ( 等级 1 级 )", "source": "local", "assert_mode": "context_contains", "page_no": 62, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_107() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“4.5.1. VAL.1 Validation”这一章节？", "must_include": "4.5.1. VAL.1 Validation", "source": "local", "assert_mode": "context_contains", "page_no": 127, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_108() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“GP 4.1.6 Collect product and process measurement results through performing the defined process”这一章节？", "must_include": "GP 4.1.6 Collect product and process measurement results through performing the defined process", "source": "local", "assert_mode": "context_contains", "page_no": 251, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000005_golden_109() -> None:
    case = '{"kind": "section", "query": "在IEC 33020中，是否包含“GP 5.2.3 评估过程变更的有效性。”这一章节？", "must_include": "GP 5.2.3 评估过程变更的有效性。", "source": "local", "assert_mode": "context_contains", "page_no": 264, "target_doc_id": "DOC-000005"}'
    _assert_case(json.loads(case))
