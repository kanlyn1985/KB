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
def test_doc_000014_golden_1() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是boot manager？", "must_include": "boot manager", "retrieval_must_hit": ["boot manager"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["boot manager"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_2() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中boot manager的定义是什么？", "must_include": "boot manager", "retrieval_must_hit": ["boot manager"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["boot manager"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_3() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是boot memory partition？", "must_include": "boot memory partition", "retrieval_must_hit": ["boot memory partition"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["boot memory partition"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_4() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中boot memory partition的定义是什么？", "must_include": "boot memory partition", "retrieval_must_hit": ["boot memory partition"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["boot memory partition"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_5() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是boot software？", "must_include": "boot software", "retrieval_must_hit": ["boot software"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["boot software"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_6() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中boot software的定义是什么？", "must_include": "boot software", "retrieval_must_hit": ["boot software"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["boot software"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_7() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是client？", "must_include": "client", "retrieval_must_hit": ["client"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["client"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_8() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中client的定义是什么？", "must_include": "client", "retrieval_must_hit": ["client"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["client"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_9() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是diagnostic data？", "must_include": "diagnostic data", "retrieval_must_hit": ["diagnostic data"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["diagnostic data"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_10() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中diagnostic data的定义是什么？", "must_include": "diagnostic data", "retrieval_must_hit": ["diagnostic data"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["diagnostic data"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_11() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是diagnostic routine？", "must_include": "diagnostic routine", "retrieval_must_hit": ["diagnostic routine"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["diagnostic routine"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_12() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中diagnostic routine的定义是什么？", "must_include": "diagnostic routine", "retrieval_must_hit": ["diagnostic routine"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["diagnostic routine"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_13() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是diagnostic service？", "must_include": "diagnostic service", "retrieval_must_hit": ["diagnostic service"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["diagnostic service"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_14() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中diagnostic service的定义是什么？", "must_include": "diagnostic service", "retrieval_must_hit": ["diagnostic service"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["diagnostic service"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_15() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是diagnostic session？", "must_include": "diagnostic session", "retrieval_must_hit": ["diagnostic session"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["diagnostic session"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_16() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中diagnostic session的定义是什么？", "must_include": "diagnostic session", "retrieval_must_hit": ["diagnostic session"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["diagnostic session"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_17() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是diagnostic trouble code？", "must_include": "diagnostic trouble code", "retrieval_must_hit": ["diagnostic trouble code"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["diagnostic trouble code"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_18() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中diagnostic trouble code的定义是什么？", "must_include": "diagnostic trouble code", "retrieval_must_hit": ["diagnostic trouble code"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["diagnostic trouble code"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_19() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是functional unit？", "must_include": "functional unit", "retrieval_must_hit": ["functional unit"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["functional unit"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_20() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中functional unit的定义是什么？", "must_include": "functional unit", "retrieval_must_hit": ["functional unit"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["functional unit"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_21() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是integer type？", "must_include": "integer type", "retrieval_must_hit": ["integer type"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["integer type"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_22() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中integer type的定义是什么？", "must_include": "integer type", "retrieval_must_hit": ["integer type"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["integer type"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_23() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是local client？", "must_include": "local client", "retrieval_must_hit": ["local client"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["local client"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_24() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中local client的定义是什么？", "must_include": "local client", "retrieval_must_hit": ["local client"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["local client"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_25() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是local server？", "must_include": "local server", "retrieval_must_hit": ["local server"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["local server"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_26() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中local server的定义是什么？", "must_include": "local server", "retrieval_must_hit": ["local server"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["local server"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_27() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是record？", "must_include": "record", "retrieval_must_hit": ["record"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["record"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_28() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中record的定义是什么？", "must_include": "record", "retrieval_must_hit": ["record"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["record"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_29() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是remote server？", "must_include": "remote server", "retrieval_must_hit": ["remote server"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["remote server"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_30() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中remote server的定义是什么？", "must_include": "remote server", "retrieval_must_hit": ["remote server"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["remote server"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_31() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是reprogramming software？", "must_include": "reprogramming software", "retrieval_must_hit": ["reprogramming software"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["reprogramming software"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_32() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中reprogramming software的定义是什么？", "must_include": "reprogramming software", "retrieval_must_hit": ["reprogramming software"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["reprogramming software"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_33() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是Service？", "must_include": "Service", "retrieval_must_hit": ["Service"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["Service"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_34() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中Service的定义是什么？", "must_include": "Service", "retrieval_must_hit": ["Service"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["Service"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_35() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是Software？", "must_include": "Software", "retrieval_must_hit": ["Software"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["Software"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_36() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 14229-1—2013中Software的定义是什么？", "must_include": "Software", "retrieval_must_hit": ["Software"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["Software"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_37() -> None:
    case = '{"kind": "retrieval_quality", "query": "boot manager和boot memory partition有什么区别？", "must_include": "boot manager", "retrieval_must_hit": ["boot manager", "boot memory partition"], "assert_mode": "rich_answer", "source": "local_rq", "difficulty": "hard", "query_type": "comparison", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_38() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：# Road vehicles — Unified diagnostic servi", "must_include": "# Road vehicles — Unified diagnostic servi", "source": "local", "assert_mode": "context_contains", "page_no": 9, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_39() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：connected to a serial data link embedded i", "must_include": "connected to a serial data link embedded i", "source": "local", "assert_mode": "context_contains", "page_no": 9, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_40() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：It specifies generic services, which allow", "must_include": "It specifies generic services, which allow", "source": "local", "assert_mode": "context_contains", "page_no": 9, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_41() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：This part of ISO 14229 does not apply to n", "must_include": "This part of ISO 14229 does not apply to n", "source": "local", "assert_mode": "context_contains", "page_no": 9, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_42() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：However, this part of ISO 14229 does not r", "must_include": "However, this part of ISO 14229 does not r", "source": "local", "assert_mode": "context_contains", "page_no": 9, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_43() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：This part of ISO 14229 does not specify an", "must_include": "This part of ISO 14229 does not specify an", "source": "local", "assert_mode": "context_contains", "page_no": 9, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_44() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：#### 3.1.3 ## boot software software which", "must_include": "#### 3.1.3 ## boot software software which", "source": "local", "assert_mode": "context_contains", "page_no": 10, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_45() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：NOTE 2 See also 3.1.1 and 3.1.17.", "must_include": "NOTE 2 See also 3.1.1 and 3.1.17.", "source": "local", "assert_mode": "context_contains", "page_no": 10, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_46() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：#### 3.1.4 ## client function that is part", "must_include": "#### 3.1.4 ## client function that is part", "source": "local", "assert_mode": "context_contains", "page_no": 10, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_47() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：#### 3.1.5 ## diagnostic data data that is", "must_include": "#### 3.1.5 ## diagnostic data data that is", "source": "local", "assert_mode": "context_contains", "page_no": 10, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_48() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：NOTE 2 Examples of diagnostic data are veh", "must_include": "NOTE 2 Examples of diagnostic data are veh", "source": "local", "assert_mode": "context_contains", "page_no": 10, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_49() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：Three types of values are defined for diag", "must_include": "Three types of values are defined for diag", "source": "local", "assert_mode": "context_contains", "page_no": 10, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_50() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：#### 3.1.9 ## diagnostic trouble code DTC", "must_include": "#### 3.1.9 ## diagnostic trouble code DTC", "source": "local", "assert_mode": "context_contains", "page_no": 11, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_51() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：#### 3.1.11 ## functional unit set of func", "must_include": "#### 3.1.11 ## functional unit set of func", "source": "local", "assert_mode": "context_contains", "page_no": 11, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_52() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：#### 3.1.13 ## local client client that is", "must_include": "#### 3.1.13 ## local client client that is", "source": "local", "assert_mode": "context_contains", "page_no": 11, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_53() -> None:
    case = '{"kind": "evidence", "query": "ISO 14229-1—2013：the appropriate monitors for each DTC have", "must_include": "the appropriate monitors for each DTC have", "source": "local", "assert_mode": "context_contains", "page_no": 11, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_54() -> None:
    case = '{"kind": "definition", "query": "在ISO 14229-1—2013中，什么是boot manager？", "must_include": "boot manager", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_55() -> None:
    case = '{"kind": "definition_detail", "query": "在ISO 14229-1—2013中，boot manager 的定义是什么？", "must_include": "part of the boot software that executes im", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_56() -> None:
    case = '{"kind": "definition", "query": "在ISO 14229-1—2013中，什么是boot memory partition？", "must_include": "boot memory partition", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_57() -> None:
    case = '{"kind": "definition_detail", "query": "在ISO 14229-1—2013中，boot memory partition 的定义是什么？", "must_include": "area of the server memory in which the boo", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_58() -> None:
    case = '{"kind": "definition", "query": "在ISO 14229-1—2013中，什么是boot software？", "must_include": "boot software", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_59() -> None:
    case = '{"kind": "definition_detail", "query": "在ISO 14229-1—2013中，boot software 的定义是什么？", "must_include": "software which is executed in a special pa", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_60() -> None:
    case = '{"kind": "definition", "query": "在ISO 14229-1—2013中，什么是client？", "must_include": "client", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_61() -> None:
    case = '{"kind": "definition_detail", "query": "在ISO 14229-1—2013中，client 的定义是什么？", "must_include": "function that is part of the tester and th", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_62() -> None:
    case = '{"kind": "definition", "query": "在ISO 14229-1—2013中，什么是diagnostic data？", "must_include": "diagnostic data", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_63() -> None:
    case = '{"kind": "definition_detail", "query": "在ISO 14229-1—2013中，diagnostic data 的定义是什么？", "must_include": "data that is located in the memory of an e", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_64() -> None:
    case = '{"kind": "definition", "query": "在ISO 14229-1—2013中，什么是diagnostic routine？", "must_include": "diagnostic routine", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_65() -> None:
    case = '{"kind": "definition_detail", "query": "在ISO 14229-1—2013中，diagnostic routine 的定义是什么？", "must_include": "routine that is embedded in an electronic", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_66() -> None:
    case = '{"kind": "definition", "query": "在ISO 14229-1—2013中，什么是diagnostic service？", "must_include": "diagnostic service", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_67() -> None:
    case = '{"kind": "definition_detail", "query": "在ISO 14229-1—2013中，diagnostic service 的定义是什么？", "must_include": "information exchange initiated by a client", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_68() -> None:
    case = '{"kind": "definition", "query": "在ISO 14229-1—2013中，什么是diagnostic session？", "must_include": "diagnostic session", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_69() -> None:
    case = '{"kind": "definition_detail", "query": "在ISO 14229-1—2013中，diagnostic session 的定义是什么？", "must_include": "state within the server in which a specifi", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "term_definition", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_70() -> None:
    case = '{"kind": "standard", "query": "ISO 14229-1—2013 的标准号和实施日期是什么？", "must_include": "ISO 14229-1—2013", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "standard_metadata", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_71() -> None:
    case = '{"kind": "standard", "query": "ISO 14229-1—2013 对应的标准编号是什么？", "must_include": "ISO 14229-1—2013", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "standard_metadata", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_72() -> None:
    case = '{"kind": "standard", "query": "ISO 14229-1—2013 的现行标准号是什么？", "must_include": "ISO 14229-1—2013", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "standard_metadata", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_73() -> None:
    case = '{"kind": "section", "query": "在ISO 14229-1—2013中，是否包含“7.1 General definition”这一章节？", "must_include": "7.1 General definition", "source": "local", "assert_mode": "context_contains", "page_no": 23, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_74() -> None:
    case = '{"kind": "section", "query": "在ISO 14229-1—2013中，是否包含“9.2.2.1 Request message definition”这一章节？", "must_include": "9.2.2.1 Request message definition", "source": "local", "assert_mode": "context_contains", "page_no": 47, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_75() -> None:
    case = '{"kind": "section", "query": "在ISO 14229-1—2013中，是否包含“9.9.3.2 Positive response message data-parameter definition”这一章节？", "must_include": "9.9.3.2 Positive response message data-parameter definition", "source": "local", "assert_mode": "context_contains", "page_no": 81, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_76() -> None:
    case = '{"kind": "section", "query": "在ISO 14229-1—2013中，是否包含“9.9.4 Supported negative response codes (NRC_)”这一章节？", "must_include": "9.9.4 Supported negative response codes (NRC_)", "source": "local", "assert_mode": "context_contains", "page_no": 81, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_77() -> None:
    case = '{"kind": "section", "query": "在ISO 14229-1—2013中，是否包含“Example #14 assumptions”这一章节？", "must_include": "Example #14 assumptions", "source": "local", "assert_mode": "context_contains", "page_no": 244, "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000014_golden_78() -> None:
    case = '{"kind": "title", "query": "ISO 14229-1—2013 这份文档的标题是什么？", "must_include": "Road vehicles — Unified diagnostic services (UDS) —", "source": "local", "assert_mode": "context_contains", "expected_evidence_shape": "standard_metadata", "target_doc_id": "DOC-000014"}'
    _assert_case(json.loads(case))
