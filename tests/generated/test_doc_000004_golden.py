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
def test_doc_000004_golden_1() -> None:
    case = '{"kind": "retrieval_quality", "query": "什么是保护门 shutter？", "must_include": "保护门 shutter", "retrieval_must_hit": ["保护门 shutter"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["保护门 shutter"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_2() -> None:
    case = '{"kind": "retrieval_quality", "query": "QC/T 1036—2016中保护门 shutter的定义是什么？", "must_include": "保护门 shutter", "retrieval_must_hit": ["保护门 shutter"], "assert_mode": "rich_answer", "source": "local_rq", "expected_sections": ["保护门 shutter"], "difficulty": "medium", "query_type": "definition", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_3() -> None:
    case = '{"kind": "retrieval_quality", "query": "规范性引用文件有什么要求？", "must_include": "规范性引用文件", "retrieval_must_hit": ["规范性引用文件"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [8], "expected_sections": ["2 规范性引用文件"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_4() -> None:
    case = '{"kind": "retrieval_quality", "query": "工作环境条件有什么要求？", "must_include": "工作环境条件", "retrieval_must_hit": ["工作环境条件"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [9], "expected_sections": ["4.1.2 工作环境条件。"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_5() -> None:
    case = '{"kind": "retrieval_quality", "query": "外观及安装尺寸有什么要求？", "must_include": "外观及安装尺寸", "retrieval_must_hit": ["外观及安装尺寸"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [10], "expected_sections": ["4.2 外观及安装尺寸"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_6() -> None:
    case = '{"kind": "retrieval_quality", "query": "输出特性参数允差有什么要求？", "must_include": "输出特性参数允差", "retrieval_must_hit": ["输出特性参数允差"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [10], "expected_sections": ["4.5.2 输出特性参数允差。"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_7() -> None:
    case = '{"kind": "retrieval_quality", "query": "额定输出效率有什么要求？", "must_include": "额定输出效率", "retrieval_must_hit": ["额定输出效率"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [10], "expected_sections": ["4.5.3 额定输出效率。"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_8() -> None:
    case = '{"kind": "retrieval_quality", "query": "过载输出能力有什么要求？", "must_include": "过载输出能力", "retrieval_must_hit": ["过载输出能力"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [10], "expected_sections": ["4.5.4 过载输出能力。"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_9() -> None:
    case = '{"kind": "retrieval_quality", "query": "和 4.5.2 的规定有什么要求？", "must_include": "和 4.5.2 的规定", "retrieval_must_hit": ["和 4.5.2 的规定"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [11], "expected_sections": ["4.5.1 和 4.5.2 的规定。"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_10() -> None:
    case = '{"kind": "retrieval_quality", "query": "持续输出能力有什么要求？", "must_include": "持续输出能力", "retrieval_must_hit": ["持续输出能力"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [11], "expected_sections": ["4.5.5 持续输出能力。"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_11() -> None:
    case = '{"kind": "retrieval_quality", "query": "爬电距离、电气间隙和穿通绝缘距离有什么要求？", "must_include": "爬电距离、电气间隙和穿通绝缘距离", "retrieval_must_hit": ["爬电距离、电气间隙和穿通绝缘距离"], "assert_mode": "rich_answer", "source": "local_rq", "expected_pages": [11], "expected_sections": ["4.6.2 爬电距离、电气间隙和穿通绝缘距离。"], "difficulty": "medium", "query_type": "general_search", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_12() -> None:
    case = '{"kind": "evidence", "query": "QC/T 1036—2016：ICS 43.040.10 T 36 # QC # 中华人民共和国汽车行业标准 QC", "must_include": "ICS 43.040.10 T 36 # QC # 中华人民共和国汽车行业标准 QC", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_13() -> None:
    case = '{"kind": "evidence", "query": "QC/T 1036—2016：中华人民共和国工业和信息化部 公 告 2016年 第17号 工业和信息化部批准《不锈", "must_include": "中华人民共和国工业和信息化部 公 告 2016年 第17号 工业和信息化部批准《不锈", "source": "local", "assert_mode": "context_contains", "page_no": 2, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_14() -> None:
    case = '{"kind": "evidence", "query": "QC/T 1036—2016：以上机械行业标准由机械工业出版社出版，汽车行业标准由科 学技术文献出版社出版，船舶行", "must_include": "以上机械行业标准由机械工业出版社出版，汽车行业标准由科 学技术文献出版社出版，船舶行", "source": "local", "assert_mode": "context_contains", "page_no": 2, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_15() -> None:
    case = '{"kind": "evidence", "query": "QC/T 1036—2016：附件：35 项汽车行业标准编号、标准名称和起始实施日期 中华人民共和国工业和信息化部", "must_include": "附件：35 项汽车行业标准编号、标准名称和起始实施日期 中华人民共和国工业和信息化部", "source": "local", "assert_mode": "context_contains", "page_no": 2, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_16() -> None:
    case = '{"kind": "evidence", "query": "QC/T 1036—2016：附件： ### 35 项汽车行业标准编号、标准名称和起始实施日期 | 序号 | 标准", "must_include": "附件： ### 35 项汽车行业标准编号、标准名称和起始实施日期 | 序号 | 标准", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_17() -> None:
    case = '{"kind": "evidence", "query": "QC/T 1036—2016：| 序号 | 标准编号 | 标准名称 | 被代替标准编号 | 起始实施日期 | |", "must_include": "| 序号 | 标准编号 | 标准名称 | 被代替标准编号 | 起始实施日期 | |", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_18() -> None:
    case = '{"kind": "evidence", "query": "QC/T 1036—2016 # 前 言 本标准按照 GB/T 1.1—2009《标", "must_include": "QC/T 1036—2016 # 前 言 本标准按照 GB/T 1.1—2009《标", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_19() -> None:
    case = '{"kind": "evidence", "query": "QC/T 1036—2016：本标准的起草参考了国内外相关标准。", "must_include": "本标准的起草参考了国内外相关标准。", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_20() -> None:
    case = '{"kind": "evidence", "query": "QC/T 1036—2016：本标准由全国汽车标准化技术委员会(SAC/TC 114)提出并归口。", "must_include": "本标准由全国汽车标准化技术委员会(SAC/TC 114)提出并归口。", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_21() -> None:
    case = '{"kind": "evidence", "query": "QC/T 1036—2016：本标准起草单位:上海汽车集团股份有限公司技术中心、长沙汽车电器研究所、上海坤浦电子科", "must_include": "本标准起草单位:上海汽车集团股份有限公司技术中心、长沙汽车电器研究所、上海坤浦电子科", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_22() -> None:
    case = '{"kind": "evidence", "query": "QC/T 1036—2016：本标准起草人:邓恒、胡梦蛟、李伟阳、周建浩、杨红娟、谢勇。", "must_include": "本标准起草人:邓恒、胡梦蛟、李伟阳、周建浩、杨红娟、谢勇。", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_23() -> None:
    case = '{"kind": "definition", "query": "在QC/T 1036—2016中，什么是保护门 shutter？", "must_include": "保护门 shutter", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_24() -> None:
    case = '{"kind": "definition_detail", "query": "在QC/T 1036—2016中，保护门 shutter 的定义是什么？", "must_include": "装在交流输出插座里,用于在插销拔出时能自动地将插孔遮蔽起来的活动部件。", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_25() -> None:
    case = '{"kind": "standard", "query": "QC/T 1036—2016 的标准号和实施日期是什么？", "must_include": "QC/T 1036—2016", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_26() -> None:
    case = '{"kind": "standard", "query": "QC/T 1036—2016 对应的标准编号是什么？", "must_include": "QC/T 1036—2016", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_27() -> None:
    case = '{"kind": "standard", "query": "QC/T 1036—2016 的现行标准号是什么？", "must_include": "QC/T 1036—2016", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_28() -> None:
    case = '{"kind": "publication_date", "query": "QC/T 1036—2016 的发布日期是什么？", "must_include": "2016-04-05", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_29() -> None:
    case = '{"kind": "publication_date", "query": "QC/T 1036—2016 是哪一天发布的？", "must_include": "2016-04-05", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_30() -> None:
    case = '{"kind": "effective_date", "query": "QC/T 1036—2016 的实施日期是什么？", "must_include": "2016-09-01", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_31() -> None:
    case = '{"kind": "effective_date", "query": "QC/T 1036—2016 从哪一天开始实施？", "must_include": "2016-09-01", "source": "local", "assert_mode": "context_contains", "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_32() -> None:
    case = '{"kind": "section", "query": "在QC/T 1036—2016中，是否包含“2 规范性引用文件”这一章节？", "must_include": "2 规范性引用文件", "source": "local", "assert_mode": "context_contains", "page_no": 8, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_33() -> None:
    case = '{"kind": "section", "query": "在QC/T 1036—2016中，是否包含“爬电距离、电气间隙和穿通绝缘距离。”这一章节？", "must_include": "爬电距离、电气间隙和穿通绝缘距离。", "source": "local", "assert_mode": "context_contains", "page_no": 11, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_34() -> None:
    case = '{"kind": "section", "query": "在QC/T 1036—2016中，是否包含“危险性放电防护。”这一章节？", "must_include": "危险性放电防护。", "source": "local", "assert_mode": "context_contains", "page_no": 11, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_35() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "修正正弦波是多少？", "must_include": "修正正弦波", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 10, "coverage_unit_id": "DOC-000004_table_10_3:row:2", "coverage_semantic_key": "修正正弦波"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_36() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "单相 220 V是多少？", "must_include": "单相 220 V", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 10, "coverage_unit_id": "DOC-000004_table_10_17:row:2", "coverage_semantic_key": "单相 220 V"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_37() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "正弦波是多少？", "must_include": "正弦波", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 10, "coverage_unit_id": "DOC-000004_table_10_3:row:1", "coverage_semantic_key": "正弦波"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_38() -> None:
    case = '{"kind": "coverage_parameter_value", "query": "正弦波修正正弦波是多少？", "must_include": "正弦波修正正弦波", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 10, "coverage_unit_id": "DOC-000004_table_10_17:row:1", "coverage_semantic_key": "正弦波修正正弦波"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_39() -> None:
    case = '{"kind": "coverage_requirement", "query": "防止触及危险的带电零部件的防护有哪些要求？", "must_include": "防止触及危险的带电零部件的防护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 11, "coverage_unit_id": "DOC-000004_requirement_11_35", "coverage_semantic_key": "防止触及危险的带电零部件的防护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_40() -> None:
    case = '{"kind": "coverage_requirement", "query": "输入反接保护有哪些要求？", "must_include": "输入反接保护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 12, "coverage_unit_id": "DOC-000004_requirement_12_19", "coverage_semantic_key": "输入反接保护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_41() -> None:
    case = '{"kind": "coverage_requirement", "query": "接线端受力抗拉特性有哪些要求？", "must_include": "接线端受力抗拉特性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 13, "coverage_unit_id": "DOC-000004_requirement_13_15", "coverage_semantic_key": "接线端受力抗拉特性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_42() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐辅助起动特性有哪些要求？", "must_include": "耐辅助起动特性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 13, "coverage_unit_id": "DOC-000004_requirement_13_11", "coverage_semantic_key": "耐辅助起动特性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_43() -> None:
    case = '{"kind": "coverage_requirement", "query": "燃烧特性有哪些要求？", "must_include": "燃烧特性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 14, "coverage_unit_id": "DOC-000004_requirement_14_23", "coverage_semantic_key": "燃烧特性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_44() -> None:
    case = '{"kind": "coverage_requirement", "query": "判定原则有哪些要求？", "must_include": "判定原则", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 21, "coverage_unit_id": "DOC-000004_requirement_21_33", "coverage_semantic_key": "判定原则"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_45() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐久性试验有哪些要求？", "must_include": "耐久性试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 21, "coverage_unit_id": "DOC-000004_requirement_21_19", "coverage_semantic_key": "耐久性试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_46() -> None:
    case = '{"kind": "coverage_requirement", "query": "型式检验条件有哪些要求？", "must_include": "型式检验条件", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 22, "coverage_unit_id": "DOC-000004_requirement_22_2", "coverage_semantic_key": "型式检验条件"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_47() -> None:
    case = '{"kind": "coverage_gap", "query": "b）抗扰试验应符合表4的规定有哪些活动？", "must_include": "b）抗扰试验应符合表4的规定", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 14, "coverage_unit_id": "DOC-000004_procedure_14_31", "coverage_semantic_key": "b）抗扰试验应符合表4的规定"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_48() -> None:
    case = '{"kind": "coverage_gap", "query": "外观与尺寸检查有哪些活动？", "must_include": "外观与尺寸检查", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 15, "coverage_unit_id": "DOC-000004_procedure_15_27", "coverage_semantic_key": "外观与尺寸检查"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_49() -> None:
    case = '{"kind": "coverage_gap", "query": "密封性试验有哪些活动？", "must_include": "密封性试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 15, "coverage_unit_id": "DOC-000004_procedure_15_29", "coverage_semantic_key": "密封性试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_50() -> None:
    case = '{"kind": "coverage_gap", "query": "测量设备与试验用电源有哪些活动？", "must_include": "测量设备与试验用电源", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 15, "coverage_unit_id": "DOC-000004_procedure_15_21", "coverage_semantic_key": "测量设备与试验用电源"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_51() -> None:
    case = '{"kind": "coverage_gap", "query": "输出基本特性有哪些活动？", "must_include": "输出基本特性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 15, "coverage_unit_id": "DOC-000004_procedure_15_35", "coverage_semantic_key": "输出基本特性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_52() -> None:
    case = '{"kind": "coverage_gap", "query": "乘员电击保护试验有哪些活动？", "must_include": "乘员电击保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 16, "coverage_unit_id": "DOC-000004_procedure_16_42", "coverage_semantic_key": "乘员电击保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_53() -> None:
    case = '{"kind": "coverage_gap", "query": "持续输出能力试验有哪些活动？", "must_include": "持续输出能力试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 16, "coverage_unit_id": "DOC-000004_procedure_16_32", "coverage_semantic_key": "持续输出能力试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_54() -> None:
    case = '{"kind": "coverage_gap", "query": "无功电流试验有哪些活动？", "must_include": "无功电流试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 16, "coverage_unit_id": "DOC-000004_procedure_16_34", "coverage_semantic_key": "无功电流试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_55() -> None:
    case = '{"kind": "coverage_gap", "query": "标识检查有哪些活动？", "must_include": "标识检查", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 16, "coverage_unit_id": "DOC-000004_procedure_16_37", "coverage_semantic_key": "标识检查"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_56() -> None:
    case = '{"kind": "coverage_gap", "query": "爬电距离、电气间隙和穿通绝缘距离试验有哪些活动？", "must_include": "爬电距离、电气间隙和穿通绝缘距离试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 16, "coverage_unit_id": "DOC-000004_procedure_16_39", "coverage_semantic_key": "爬电距离、电气间隙和穿通绝缘距离试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_57() -> None:
    case = '{"kind": "coverage_gap", "query": "输出效率试验有哪些活动？", "must_include": "输出效率试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 16, "coverage_unit_id": "DOC-000004_procedure_16_23", "coverage_semantic_key": "输出效率试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_58() -> None:
    case = '{"kind": "coverage_gap", "query": "过载输出能力试验有哪些活动？", "must_include": "过载输出能力试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 16, "coverage_unit_id": "DOC-000004_procedure_16_30", "coverage_semantic_key": "过载输出能力试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_59() -> None:
    case = '{"kind": "coverage_gap", "query": "危险性放电防护试验有哪些活动？", "must_include": "危险性放电防护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 17, "coverage_unit_id": "DOC-000004_procedure_17_25", "coverage_semantic_key": "危险性放电防护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_60() -> None:
    case = '{"kind": "coverage_gap", "query": "短路保护试验有哪些活动？", "must_include": "短路保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 17, "coverage_unit_id": "DOC-000004_procedure_17_14", "coverage_semantic_key": "短路保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_61() -> None:
    case = '{"kind": "coverage_gap", "query": "绝缘电阻和绝缘强度试验有哪些活动？", "must_include": "绝缘电阻和绝缘强度试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 17, "coverage_unit_id": "DOC-000004_procedure_17_27", "coverage_semantic_key": "绝缘电阻和绝缘强度试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_62() -> None:
    case = '{"kind": "coverage_gap", "query": "输入欠压保护试验有哪些活动？", "must_include": "输入欠压保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 17, "coverage_unit_id": "DOC-000004_procedure_17_16", "coverage_semantic_key": "输入欠压保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_63() -> None:
    case = '{"kind": "coverage_gap", "query": "过流保护试验有哪些活动？", "must_include": "过流保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 17, "coverage_unit_id": "DOC-000004_procedure_17_12", "coverage_semantic_key": "过流保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_64() -> None:
    case = '{"kind": "coverage_gap", "query": "保护重启时间试验有哪些活动？", "must_include": "保护重启时间试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 18, "coverage_unit_id": "DOC-000004_procedure_18_21", "coverage_semantic_key": "保护重启时间试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_65() -> None:
    case = '{"kind": "coverage_gap", "query": "保护门试验有哪些活动？", "must_include": "保护门试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 18, "coverage_unit_id": "DOC-000004_procedure_18_32", "coverage_semantic_key": "保护门试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_66() -> None:
    case = '{"kind": "coverage_gap", "query": "抗辅助起动试验有哪些活动？", "must_include": "抗辅助起动试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 18, "coverage_unit_id": "DOC-000004_procedure_18_40", "coverage_semantic_key": "抗辅助起动试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_67() -> None:
    case = '{"kind": "coverage_gap", "query": "拔出插销所需力试验有哪些活动？", "must_include": "拔出插销所需力试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 18, "coverage_unit_id": "DOC-000004_procedure_18_34", "coverage_semantic_key": "拔出插销所需力试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_68() -> None:
    case = '{"kind": "coverage_gap", "query": "插座尺寸检查有哪些活动？", "must_include": "插座尺寸检查", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 18, "coverage_unit_id": "DOC-000004_procedure_18_30", "coverage_semantic_key": "插座尺寸检查"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_69() -> None:
    case = '{"kind": "coverage_gap", "query": "插拔耐久试验有哪些活动？", "must_include": "插拔耐久试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 18, "coverage_unit_id": "DOC-000004_procedure_18_36", "coverage_semantic_key": "插拔耐久试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_70() -> None:
    case = '{"kind": "coverage_gap", "query": "温升试验有哪些活动？", "must_include": "温升试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 18, "coverage_unit_id": "DOC-000004_procedure_18_23", "coverage_semantic_key": "温升试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_71() -> None:
    case = '{"kind": "coverage_gap", "query": "输入反接保护试验有哪些活动？", "must_include": "输入反接保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 18, "coverage_unit_id": "DOC-000004_procedure_18_19", "coverage_semantic_key": "输入反接保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_72() -> None:
    case = '{"kind": "coverage_gap", "query": "输入过压保护试验有哪些活动？", "must_include": "输入过压保护试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 18, "coverage_unit_id": "DOC-000004_procedure_18_17", "coverage_semantic_key": "输入过压保护试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_73() -> None:
    case = '{"kind": "coverage_gap", "query": "输出线缆试验有哪些活动？", "must_include": "输出线缆试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 18, "coverage_unit_id": "DOC-000004_procedure_18_38", "coverage_semantic_key": "输出线缆试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_74() -> None:
    case = '{"kind": "coverage_gap", "query": "低温试验有哪些活动？", "must_include": "低温试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 19, "coverage_unit_id": "DOC-000004_procedure_19_36", "coverage_semantic_key": "低温试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_75() -> None:
    case = '{"kind": "coverage_gap", "query": "抗叠加交流电压试验有哪些活动？", "must_include": "抗叠加交流电压试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 19, "coverage_unit_id": "DOC-000004_procedure_19_11", "coverage_semantic_key": "抗叠加交流电压试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_76() -> None:
    case = '{"kind": "coverage_gap", "query": "抗跌落性试验有哪些活动？", "must_include": "抗跌落性试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 19, "coverage_unit_id": "DOC-000004_procedure_19_34", "coverage_semantic_key": "抗跌落性试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_77() -> None:
    case = '{"kind": "coverage_gap", "query": "接线端受力抗拉试验有哪些活动？", "must_include": "接线端受力抗拉试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 19, "coverage_unit_id": "DOC-000004_procedure_19_32", "coverage_semantic_key": "接线端受力抗拉试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_78() -> None:
    case = '{"kind": "coverage_gap", "query": "湿热循环试验有哪些活动？", "must_include": "湿热循环试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 19, "coverage_unit_id": "DOC-000004_procedure_19_42", "coverage_semantic_key": "湿热循环试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_79() -> None:
    case = '{"kind": "coverage_gap", "query": "燃烧试验有哪些活动？", "must_include": "燃烧试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 19, "coverage_unit_id": "DOC-000004_procedure_19_48", "coverage_semantic_key": "燃烧试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_80() -> None:
    case = '{"kind": "coverage_gap", "query": "耐化学试剂试验有哪些活动？", "must_include": "耐化学试剂试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 19, "coverage_unit_id": "DOC-000004_procedure_19_46", "coverage_semantic_key": "耐化学试剂试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_81() -> None:
    case = '{"kind": "coverage_gap", "query": "耐稳态湿热试验有哪些活动？", "must_include": "耐稳态湿热试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 19, "coverage_unit_id": "DOC-000004_procedure_19_44", "coverage_semantic_key": "耐稳态湿热试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_82() -> None:
    case = '{"kind": "coverage_gap", "query": "辐射骚扰试验有哪些活动？", "must_include": "辐射骚扰试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 19, "coverage_unit_id": "DOC-000004_procedure_19_56", "coverage_semantic_key": "辐射骚扰试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_83() -> None:
    case = '{"kind": "coverage_gap", "query": "高低温贮存试验有哪些活动？", "must_include": "高低温贮存试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 19, "coverage_unit_id": "DOC-000004_procedure_19_40", "coverage_semantic_key": "高低温贮存试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_84() -> None:
    case = '{"kind": "coverage_gap", "query": "高温试验有哪些活动？", "must_include": "高温试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 19, "coverage_unit_id": "DOC-000004_procedure_19_38", "coverage_semantic_key": "高温试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_85() -> None:
    case = '{"kind": "coverage_gap", "query": "耐振动试验有哪些活动？", "must_include": "耐振动试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 21, "coverage_unit_id": "DOC-000004_procedure_21_8", "coverage_semantic_key": "耐振动试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_86() -> None:
    case = '{"kind": "coverage_requirement", "query": "基本要求有哪些要求？", "must_include": "基本要求", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 9, "coverage_unit_id": "DOC-000004:requirement:9:E236E89A1B47", "coverage_semantic_key": "基本要求"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_87() -> None:
    case = '{"kind": "coverage_requirement", "query": "静态电流有哪些要求？", "must_include": "静态电流", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 11, "coverage_unit_id": "DOC-000004:requirement:11:193E87DDBEF6", "coverage_semantic_key": "静态电流"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_88() -> None:
    case = '{"kind": "coverage_requirement", "query": "插销拔出力有哪些要求？", "must_include": "插销拔出力", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 12, "coverage_unit_id": "DOC-000004:requirement:12:09AE3204904A", "coverage_semantic_key": "插销拔出力"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_89() -> None:
    case = '{"kind": "coverage_requirement", "query": "输出短路保护有哪些要求？", "must_include": "输出短路保护", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 12, "coverage_unit_id": "DOC-000004:requirement:12:CEF098497AE1", "coverage_semantic_key": "输出短路保护"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_90() -> None:
    case = '{"kind": "coverage_requirement", "query": "插座插拔耐久有哪些要求？", "must_include": "插座插拔耐久", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 13, "coverage_unit_id": "DOC-000004:requirement:13:8964CB67F00F", "coverage_semantic_key": "插座插拔耐久"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_91() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐低温特性有哪些要求？", "must_include": "耐低温特性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 13, "coverage_unit_id": "DOC-000004:requirement:13:2ACD9F989B26", "coverage_semantic_key": "耐低温特性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_92() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐叠加交流电压特性有哪些要求？", "must_include": "耐叠加交流电压特性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 13, "coverage_unit_id": "DOC-000004:requirement:13:6336C8808584", "coverage_semantic_key": "耐叠加交流电压特性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_93() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐跌落特性有哪些要求？", "must_include": "耐跌落特性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 13, "coverage_unit_id": "DOC-000004:requirement:13:3AFA4FD39627", "coverage_semantic_key": "耐跌落特性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_94() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐高温特性有哪些要求？", "must_include": "耐高温特性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 13, "coverage_unit_id": "DOC-000004:requirement:13:AEAF83A63A00", "coverage_semantic_key": "耐高温特性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_95() -> None:
    case = '{"kind": "coverage_requirement", "query": "输出导线有哪些要求？", "must_include": "输出导线", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 13, "coverage_unit_id": "DOC-000004:requirement:13:E197BD12492A", "coverage_semantic_key": "输出导线"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_96() -> None:
    case = '{"kind": "coverage_requirement", "query": "电磁兼容性有哪些要求？", "must_include": "电磁兼容性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 14, "coverage_unit_id": "DOC-000004:requirement:14:0D3CAC8BF513", "coverage_semantic_key": "电磁兼容性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_97() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐化学试剂特性有哪些要求？", "must_include": "耐化学试剂特性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 14, "coverage_unit_id": "DOC-000004:requirement:14:69F3AC5D02BB", "coverage_semantic_key": "耐化学试剂特性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_98() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐湿热循环特性有哪些要求？", "must_include": "耐湿热循环特性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 14, "coverage_unit_id": "DOC-000004:requirement:14:BDDC9AC8B358", "coverage_semantic_key": "耐湿热循环特性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_99() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐稳态湿热特性有哪些要求？", "must_include": "耐稳态湿热特性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 14, "coverage_unit_id": "DOC-000004:requirement:14:9CB6770228DC", "coverage_semantic_key": "耐稳态湿热特性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_100() -> None:
    case = '{"kind": "coverage_requirement", "query": "高低温贮存特性有哪些要求？", "must_include": "高低温贮存特性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 14, "coverage_unit_id": "DOC-000004:requirement:14:452DDC59FE14", "coverage_semantic_key": "高低温贮存特性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_101() -> None:
    case = '{"kind": "coverage_requirement", "query": "耐振动特性有哪些要求？", "must_include": "耐振动特性", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 15, "coverage_unit_id": "DOC-000004:requirement:15:F8EE29E9F573", "coverage_semantic_key": "耐振动特性"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_102() -> None:
    case = '{"kind": "coverage_requirement", "query": "瞬态抗扰性试验有哪些要求？", "must_include": "瞬态抗扰性试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 20, "coverage_unit_id": "DOC-000004:requirement:20:F99BF5C99567", "coverage_semantic_key": "瞬态抗扰性试验"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_103() -> None:
    case = '{"kind": "coverage_requirement", "query": "标志、包装、运输和贮存有哪些要求？", "must_include": "标志、包装、运输和贮存", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 23, "coverage_unit_id": "DOC-000004:requirement:23:7D5704094A97", "coverage_semantic_key": "标志、包装、运输和贮存"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_104() -> None:
    case = '{"kind": "coverage_requirement", "query": "型式检验抽样方法 从出厂检验合格的同一批产品中随机抽取样品,按表8进行试验。产品的型式检验必须全部符合规定要求,如有个别项目不合格,应重新加倍抽取,就不合格项目进行复查。如仍有不合格项目时,则认为该次型式检验不合格。耐久性项目不合格,则认为该次型式检验不合格,不得加倍抽取有哪些要求？", "must_include": "型式检验抽样方法 从出厂检验合格的同一批产品中随机抽取样品,按表8进行试验。产品的型式检验必须全部符合规定要求,如有个别项目不合格,应重新加倍抽取,就不合格项目进行复查。如仍有不合格项目时,则认为该次型式检验不合格。耐久性项目不合格,则认为该次型式检验不合格,不得加倍抽取", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 22, "coverage_unit_id": "DOC-000004:requirement:22:4BCD1C6B9C5E", "coverage_semantic_key": "型式检验抽样方法 从出厂检验合格的同一批产品中随机抽取样品,按表8进行试验。产品的型式检验必须全部符合规定要求,如有个别项目不合格,应重新加倍抽取,就不合格项目进行复查。如仍有不合格项目时,则认为该次型式检验不合格。耐久性项目不合格,则认为该次型式检验不合格,不得加倍抽取"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.coverage
def test_doc_000004_golden_105() -> None:
    case = '{"kind": "coverage_gap", "query": "瞬态抗扰性试验有哪些活动？", "must_include": "瞬态抗扰性试验", "source": "coverage", "assert_mode": "rich_answer", "target_doc_id": "DOC-000004", "page_no": 20, "coverage_unit_id": "DOC-000004_procedure_20_12", "coverage_semantic_key": "瞬态抗扰性试验"}'
    _assert_case(json.loads(case))
