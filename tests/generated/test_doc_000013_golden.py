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
def test_doc_000013_golden_1() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是山博轩,杨郁？", "must_include": "山博轩,杨郁", "retrieval_must_hit": ["山博轩,杨郁"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["山博轩,杨郁"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_2() -> None:
    case = '{"kind": "retrieval_quality", "query": "ISO 15118中山博轩,杨郁的定义是什么？", "must_include": "山博轩,杨郁", "retrieval_must_hit": ["山博轩,杨郁"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["山博轩,杨郁"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_3() -> None:
    case = '{"kind": "retrieval_quality", "query": ". 充电与逆变技术有什么要求？", "must_include": ". 充电与逆变技术", "retrieval_must_hit": [". 充电与逆变技术"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [2], "expected_sections": ["2.1. 充电与逆变技术"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_4() -> None:
    case = '{"kind": "retrieval_quality", "query": ". 地区性综合示范实践有什么要求？", "must_include": ". 地区性综合示范实践", "retrieval_must_hit": [". 地区性综合示范实践"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [6], "expected_sections": ["3.3.4. 地区性综合示范实践"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_5() -> None:
    case = '{"kind": "retrieval_quality", "query": ". 问题与限制有什么要求？", "must_include": ". 问题与限制", "retrieval_must_hit": [". 问题与限制"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [7], "expected_sections": ["3.4. 问题与限制"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_6() -> None:
    case = '{"kind": "retrieval_quality", "query": ". 商业模式不成熟有什么要求？", "must_include": ". 商业模式不成熟", "retrieval_must_hit": [". 商业模式不成熟"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [7], "expected_sections": ["3.4.1. 商业模式不成熟"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000013_golden_7() -> None:
    case = '{"kind": "page_coverage", "query": "V2G相关：第1页 https://www.hanspub.org/journal/sg htt", "must_include": "https://www.hanspub.org/journal/sg htt", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000013_golden_8() -> None:
    case = '{"kind": "page_coverage", "query": "V2G相关：第2页 http://creativecommons.org/licenses/by", "must_include": "http://creativecommons.org/licenses/by", "source": "local", "assert_mode": "context_contains", "page_no": 2, "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000013_golden_9() -> None:
    case = '{"kind": "page_coverage", "query": "V2G相关：第3页 通信协议标准化** 电动汽车与充电桩之间的通信(V2C—Vehicle-to", "must_include": "通信协议标准化** 电动汽车与充电桩之间的通信(V2C—Vehicle-to", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000013_golden_10() -> None:
    case = '{"kind": "page_coverage", "query": "V2G相关：第4页 随着 EV 数量的增长及分布式能源接入的不断增加，分布式光伏和 EV 的互补", "must_include": "随着 EV 数量的增长及分布式能源接入的不断增加，分布式光伏和 EV 的互补", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000013_golden_11() -> None:
    case = '{"kind": "page_coverage", "query": "V2G相关：第5页 国外试点概况** 全球范围内的车网协同示范实践非常活跃。试点示范项目主要分为", "must_include": "国外试点概况** 全球范围内的车网协同示范实践非常活跃。试点示范项目主要分为", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000013_golden_12() -> None:
    case = '{"kind": "page_coverage", "query": "V2G相关：第6页 个人 V2H 文献[12]中，北京中再大厦 V2G 试点项目是全国第一座 V", "must_include": "个人 V2H 文献[12]中，北京中再大厦 V2G 试点项目是全国第一座 V", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000013_golden_13() -> None:
    case = '{"kind": "page_coverage", "query": "V2G相关：第7页 问题与限制 从以上试点内容中可以看出，当前大部分充电设施参与市场的运营模式仍", "must_include": "问题与限制 从以上试点内容中可以看出，当前大部分充电设施参与市场的运营模式仍", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000013_golden_14() -> None:
    case = '{"kind": "page_coverage", "query": "V2G相关：第8页 发挥聚合商的作用** 在 V2G 体系中，聚合商扮演着极其重要的角色。他们主", "must_include": "发挥聚合商的作用** 在 V2G 体系中，聚合商扮演着极其重要的角色。他们主", "source": "local", "assert_mode": "context_contains", "page_no": 8, "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000013_golden_15() -> None:
    case = '{"kind": "page_coverage", "query": "V2G相关：第9页 结语 打造气候弹性强、安全韧性强、调节柔性强、保障能力强的数智化坚强电网，在", "must_include": "结语 打造气候弹性强、安全韧性强、调节柔性强、保障能力强的数智化坚强电网，在", "source": "local", "assert_mode": "context_contains", "page_no": 9, "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000013_golden_16() -> None:
    case = '{"kind": "page_coverage", "query": "V2G相关：第10页 http://kns.cnki.net/kcms/detail/32.118", "must_include": "http://kns.cnki.net/kcms/detail/32.118", "source": "local", "assert_mode": "context_contains", "page_no": 10, "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_17() -> None:
    case = '{"kind": "evidence", "query": "V2G相关：Smart Grid 智能电网, 2024, 14(2), 11-20 Publis", "must_include": "Smart Grid 智能电网, 2024, 14(2), 11-20 Publis", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_18() -> None:
    case = '{"kind": "evidence", "query": "V2G相关：https://www.hanspub.org/journal/sg https:/", "must_include": "https://www.hanspub.org/journal/sg https:/", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_19() -> None:
    case = '{"kind": "evidence", "query": "V2G相关：### 关键词 V2G，需求响应，新能源消纳，新型电力系统 # From Pilot", "must_include": "### 关键词 V2G，需求响应，新能源消纳，新型电力系统 # From Pilot", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000013_golden_20() -> None:
    case = '{"kind": "evidence", "query": "V2G相关：18ᵗʰ, 2024; published: Jun.", "must_include": "18ᵗʰ, 2024; published: Jun.", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000013"}'
    _assert_case(json.loads(case))
