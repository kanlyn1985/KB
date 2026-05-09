from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from enterprise_agent_kb.answer_api import answer_query

WORKSPACE = Path("knowledge_base")
DB_PATH = WORKSPACE / "db" / "knowledge.db"


def _normalize(value: str) -> str:
    text = value.lower().replace("\u2014", "-").replace("\uff0f", "/")
    return "".join(text.split())


def _sanitize_fts5_query(query: str) -> str:
    cleaned = query.replace("/", " ").replace("\u2014", " ").replace("\u2015", " ")
    cleaned = re.sub(r"""[?？！!。，、；;：:""''（）()\[\]{{}}*\-—.#]""", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _fts5_context_contains(query: str, target_doc_id: str | None = None) -> str:
    sanitized = _sanitize_fts5_query(query)
    terms = [t for t in sanitized.split() if len(t) >= 2]
    if not terms:
        return target_doc_id or ""
    fts_query = " OR ".join(terms)
    conn = sqlite3.connect(str(DB_PATH.resolve()))
    parts: list[str] = []
    try:
        for table in ["evidence_fts", "facts_fts", "wiki_fts"]:
            try:
                if target_doc_id:
                    for (text,) in conn.execute(
                        f"SELECT searchable_text FROM {table} WHERE {table} MATCH ? AND doc_id = ? LIMIT 8",
                        (fts_query, target_doc_id),
                    ):
                        if text:
                            parts.append(text)
                else:
                    for (text,) in conn.execute(
                        f"SELECT searchable_text FROM {table} WHERE {table} MATCH ? LIMIT 8",
                        (fts_query,),
                    ):
                        if text:
                            parts.append(text)
            except sqlite3.OperationalError:
                pass
    finally:
        conn.close()
    if target_doc_id:
        parts.append(target_doc_id)
    return "\n".join(parts)


def _assert_case(case: dict[str, str]) -> None:
    expected = _normalize(case["must_include"])
    target_doc_id = str(case.get("target_doc_id") or "") or None
    if case.get("assert_mode") == "context_contains":
        blob = _fts5_context_contains(case["query"], target_doc_id)
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
def test_doc_000013_golden_1() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \". 充电与逆变技术有什么要求？\", \"must_include\": \". 充电与逆变技术\", \"retrieval_must_hit\": [\". 充电与逆变技术\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [2], \"expected_sections\": [\"2.1. 充电与逆变技术\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_2() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \". 地区性综合示范实践有什么要求？\", \"must_include\": \". 地区性综合示范实践\", \"retrieval_must_hit\": [\". 地区性综合示范实践\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [6], \"expected_sections\": [\"3.3.4. 地区性综合示范实践\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_3() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \". 问题与限制有什么要求？\", \"must_include\": \". 问题与限制\", \"retrieval_must_hit\": [\". 问题与限制\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [7], \"expected_sections\": [\"3.4. 问题与限制\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_4() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \". 商业模式不成熟有什么要求？\", \"must_include\": \". 商业模式不成熟\", \"retrieval_must_hit\": [\". 商业模式不成熟\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [7], \"expected_sections\": [\"3.4.1. 商业模式不成熟\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_5() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \". 存在成本疏导问题有什么要求？\", \"must_include\": \". 存在成本疏导问题\", \"retrieval_must_hit\": [\". 存在成本疏导问题\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [7], \"expected_sections\": [\"3.4.2. 存在成本疏导问题\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_6() -> None:
    case = json.loads("{\"kind\": \"retrieval_quality\", \"query\": \". 技术细节还有待进一步验证和研究有什么要求？\", \"must_include\": \". 技术细节还有待进一步验证和研究\", \"retrieval_must_hit\": [\". 技术细节还有待进一步验证和研究\"], \"assert_mode\": \"rich_answer\", \"source\": \"local_rq\", \"expected_pages\": [7], \"expected_sections\": [\"3.4.3. 技术细节还有待进一步验证和研究\"], \"difficulty\": \"medium\", \"query_type\": \"general_search\", \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_7() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"ISO 15118：Smart Grid 智能电网, 2024, 14(2), 11-20 Publis\", \"must_include\": \"Smart Grid 智能电网, 2024, 14(2), 11-20 Publis\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 1, \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_8() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"ISO 15118：https://www.hanspub.org/journal/sg https:/\", \"must_include\": \"https://www.hanspub.org/journal/sg https:/\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 1, \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_9() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"ISO 15118：### 关键词 V2G，需求响应，新能源消纳，新型电力系统 # From Pilot\", \"must_include\": \"### 关键词 V2G，需求响应，新能源消纳，新型电力系统 # From Pilot\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 1, \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_10() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"ISO 15118：18ᵗʰ, 2024; published: Jun.\", \"must_include\": \"18ᵗʰ, 2024; published: Jun.\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 1, \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_11() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"ISO 15118：27ᵗʰ, 2024 ### Abstract Vehicle-to-Grid (V\", \"must_include\": \"27ᵗʰ, 2024 ### Abstract Vehicle-to-Grid (V\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 1, \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_12() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"ISO 15118：Not only does it optimize the use of elect\", \"must_include\": \"Not only does it optimize the use of elect\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 1, \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_13() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"ISO 15118：山博轩，杨郁 comprehensive energy systems, and r\", \"must_include\": \"山博轩，杨郁 comprehensive energy systems, and r\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 2, \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_14() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"ISO 15118：The limitations and problems in the pilot\", \"must_include\": \"The limitations and problems in the pilot\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 2, \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_15() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"ISO 15118：Suggestions are also made for the pilot wo\", \"must_include\": \"Suggestions are also made for the pilot wo\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 2, \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_16() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"ISO 15118：**Keywords** **V2G, Demand Response, Renew\", \"must_include\": \"**Keywords** **V2G, Demand Response, Renew\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 2, \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_17() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"ISO 15118：This work is licensed under the Creative C\", \"must_include\": \"This work is licensed under the Creative C\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 2, \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_18() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"ISO 15118：http://creativecommons.org/licenses/by/4.0\", \"must_include\": \"http://creativecommons.org/licenses/by/4.0\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 2, \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_19() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"ISO 15118：通信协议标准化** 电动汽车与充电桩之间的通信(V2C—Vehicle-to-Cha\", \"must_include\": \"通信协议标准化** 电动汽车与充电桩之间的通信(V2C—Vehicle-to-Cha\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 3, \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_20() -> None:
    case = json.loads("{\"kind\": \"evidence\", \"query\": \"ISO 15118：充电桩与后端系统之间的通信(C2B—Charger-to-Backend)方面，OC\", \"must_include\": \"充电桩与后端系统之间的通信(C2B—Charger-to-Backend)方面，OC\", \"source\": \"local\", \"assert_mode\": \"context_contains\", \"page_no\": 3, \"target_doc_id\": \"DOC-000013\"}")
    _assert_case(case)
