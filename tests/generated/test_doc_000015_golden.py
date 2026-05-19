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
@pytest.mark.coverage
def test_doc_000015_golden_1() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是vehicle connector？", "must_include": "vehicle connector", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "page_no": 25, "coverage_unit_id": "DOC-000015:definition:25:EAD7093805EC", "coverage_semantic_key": "vehicle connector", "expected_evidence_shape": "term_definition"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_2() -> None:
    case = '{"kind": "coverage_definition", "query": "什么是vehicle inlet？", "must_include": "vehicle inlet", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "page_no": 25, "coverage_unit_id": "DOC-000015:definition:25:5D5FB4A87209", "coverage_semantic_key": "vehicle inlet", "expected_evidence_shape": "term_definition"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_3() -> None:
    case = '{"kind": "coverage_requirement", "query": "Switch and switch-disconnector有哪些要求？", "must_include": "Switch and switch-disconnector", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "page_no": 46, "coverage_unit_id": "DOC-000015:requirement:46:D3854AD9B945", "coverage_semantic_key": "Switch and switch-disconnector", "expected_evidence_shape": "requirement"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_4() -> None:
    case = '{"kind": "coverage_requirement", "query": "A.3 Requirements for parameters and system behaviour有哪些要求？", "must_include": "A.3 Requirements for parameters and system behaviour", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "page_no": 57, "coverage_unit_id": "DOC-000015:requirement:57:C4504A88E550", "coverage_semantic_key": "A.3 Requirements for parameters and system behaviour", "expected_evidence_shape": "requirement"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_5() -> None:
    case = '{"kind": "coverage_requirement", "query": "Table A.6: Sequence 1.2 Plug-in (w/o S2 or S2 always in close position)有哪些要求？", "must_include": "Table A.6: Sequence 1.2 Plug-in (w/o S2 or S2 always in close position)", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "page_no": 64, "coverage_unit_id": "DOC-000015:requirement:64:B4D4F58736AF", "coverage_semantic_key": "Table A.6: Sequence 1.2 Plug-in (w/o S2 or S2 always in close position)", "expected_evidence_shape": "requirement"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000015_golden_6() -> None:
    case = '{"kind": "coverage_requirement", "query": "Table A.8 - Maximum current to be drawn by vehicle有哪些要求？", "must_include": "Table A.8 - Maximum current to be drawn by vehicle", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000015", "page_no": 73, "coverage_unit_id": "DOC-000015:requirement:73:B2AC41092BF1", "coverage_semantic_key": "Table A.8 - Maximum current to be drawn by vehicle", "expected_evidence_shape": "requirement"}'
    _assert_case(json.loads(case))
