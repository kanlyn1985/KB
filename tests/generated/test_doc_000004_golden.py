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
@pytest.mark.page_coverage
def test_doc_000004_golden_12() -> None:
    case = '{"kind": "page_coverage", "query": "第1页 ICS 43.040.10 T 36 # QC # 中华人民共和国汽车行业标", "must_include": "ICS 43.040.10 T 36 # QC # 中华人民共和国汽车行业标", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_13() -> None:
    case = '{"kind": "page_coverage", "query": "第2页 以上机械行业标准由机械工业出版社出版，汽车行业标准由科 学技术文献出版社出版", "must_include": "以上机械行业标准由机械工业出版社出版，汽车行业标准由科 学技术文献出版社出版", "source": "local", "assert_mode": "context_contains", "page_no": 2, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_14() -> None:
    case = '{"kind": "page_coverage", "query": "第3页 附件： ### 35 项汽车行业标准编号、标准名称和起始实施日期 | 序号", "must_include": "附件： ### 35 项汽车行业标准编号、标准名称和起始实施日期 | 序号", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_15() -> None:
    case = '{"kind": "page_coverage", "query": "第4页 | 序号 | 标准编号 | 标准名称 | 被代替标准编号 | 起始实施日期", "must_include": "| 序号 | 标准编号 | 标准名称 | 被代替标准编号 | 起始实施日期", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_16() -> None:
    case = '{"kind": "page_coverage", "query": "第5页 | 序号 | 标准编号 | 标准名称 | 被代替标准编号 | 起始实施日期", "must_include": "| 序号 | 标准编号 | 标准名称 | 被代替标准编号 | 起始实施日期", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_17() -> None:
    case = '{"kind": "page_coverage", "query": "第7页 QC/T 1036—2016 # 前 言 本标准按照 GB/T 1.1—20", "must_include": "QC/T 1036—2016 # 前 言 本标准按照 GB/T 1.1—20", "source": "local", "assert_mode": "context_contains", "page_no": 7, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_18() -> None:
    case = '{"kind": "page_coverage", "query": "第8页 GB 1002—2008 家用和类似用途单相插头插座型式、基本参数和尺寸 G", "must_include": "GB 1002—2008 家用和类似用途单相插头插座型式、基本参数和尺寸 G", "source": "local", "assert_mode": "context_contains", "page_no": 8, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_19() -> None:
    case = '{"kind": "page_coverage", "query": "第9页 4—2016 道路车辆 电气/电子部件对窄带辐射电磁能的抗扰性试验方法 第", "must_include": "4—2016 道路车辆 电气/电子部件对窄带辐射电磁能的抗扰性试验方法 第", "source": "local", "assert_mode": "context_contains", "page_no": 9, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_20() -> None:
    case = '{"kind": "page_coverage", "query": "第11页 逆变器输出视在功率为额定值的 120%时，持续工作时间应不少于 3 min", "must_include": "逆变器输出视在功率为额定值的 120%时，持续工作时间应不少于 3 min", "source": "local", "assert_mode": "context_contains", "page_no": 11, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_21() -> None:
    case = '{"kind": "page_coverage", "query": "第12页 输入电路对交流接地，输入电路对输出电路和输出电路对交流接地应承受 1 500", "must_include": "输入电路对交流接地，输入电路对输出电路和输出电路对交流接地应承受 1 500", "source": "local", "assert_mode": "context_contains", "page_no": 12, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_22() -> None:
    case = '{"kind": "page_coverage", "query": "第13页 逆变器输出插座,应满足 10 000 次全行程循环的正常插拔操作。耐久试验中", "must_include": "逆变器输出插座,应满足 10 000 次全行程循环的正常插拔操作。耐久试验中", "source": "local", "assert_mode": "context_contains", "page_no": 13, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_23() -> None:
    case = '{"kind": "page_coverage", "query": "第14页 **4.15 耐湿热循环特性** 逆变器应经受湿热循环试验，试验中按规定带负", "must_include": "**4.15 耐湿热循环特性** 逆变器应经受湿热循环试验，试验中按规定带负", "source": "local", "assert_mode": "context_contains", "page_no": 14, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_24() -> None:
    case = '{"kind": "page_coverage", "query": "第15页 4.22 耐久性 逆变器应能承受 7 500 次的开启循环试验，试验后的逆变", "must_include": "4.22 耐久性 逆变器应能承受 7 500 次的开启循环试验，试验后的逆变", "source": "local", "assert_mode": "context_contains", "page_no": 15, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_25() -> None:
    case = '{"kind": "page_coverage", "query": "第16页 逆变器输出端连接 100%额定输出功率的阻性负载，分别测量直流输入功率和交流", "must_include": "逆变器输出端连接 100%额定输出功率的阻性负载，分别测量直流输入功率和交流", "source": "local", "assert_mode": "context_contains", "page_no": 16, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_26() -> None:
    case = '{"kind": "page_coverage", "query": "第17页 在输入端施加试验电压，在逆变器输出端分别施加额定功率 50% 的电阻性负载", "must_include": "在输入端施加试验电压，在逆变器输出端分别施加额定功率 50% 的电阻性负载", "source": "local", "assert_mode": "context_contains", "page_no": 17, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_27() -> None:
    case = '{"kind": "page_coverage", "query": "第18页 **5.6.6 温升试验。** 逆变器在最高输入电压、额定输出频率及额定输出", "must_include": "**5.6.6 温升试验。** 逆变器在最高输入电压、额定输出频率及额定输出", "source": "local", "assert_mode": "context_contains", "page_no": 18, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_28() -> None:
    case = '{"kind": "page_coverage", "query": "第19页 **5.15 湿热循环试验** 逆变器按照 GB/T 28046.4—201", "must_include": "**5.15 湿热循环试验** 逆变器按照 GB/T 28046.4—201", "source": "local", "assert_mode": "context_contains", "page_no": 19, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_29() -> None:
    case = '{"kind": "page_coverage", "query": "第20页 QC/T 1036—2016 **表 5 瞬态抗扰性试验** | 测试脉冲", "must_include": "QC/T 1036—2016 **表 5 瞬态抗扰性试验** | 测试脉冲", "source": "local", "assert_mode": "context_contains", "page_no": 20, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_30() -> None:
    case = '{"kind": "page_coverage", "query": "第23页 QC/T 1036—2016 7 标志、包装、运输和贮存 产品的标志、包装、", "must_include": "QC/T 1036—2016 7 标志、包装、运输和贮存 产品的标志、包装、", "source": "local", "assert_mode": "context_contains", "page_no": 23, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000004_golden_31() -> None:
    case = '{"kind": "page_coverage", "query": "第24页 QC/T 1036—2016 中华人民共和国汽车行业标准 汽 车 电 源 逆", "must_include": "QC/T 1036—2016 中华人民共和国汽车行业标准 汽 车 电 源 逆", "source": "local", "assert_mode": "context_contains", "page_no": 24, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_32() -> None:
    case = '{"kind": "evidence", "query": "QC_T 1036-2016 汽车电源逆变器-免费标准网_www.upbz.net：ICS 43.040.10 T 36 # QC # 中华人民共和国汽车行业标准 QC", "must_include": "ICS 43.040.10 T 36 # QC # 中华人民共和国汽车行业标准 QC", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_33() -> None:
    case = '{"kind": "evidence", "query": "QC_T 1036-2016 汽车电源逆变器-免费标准网_www.upbz.net：中华人民共和国工业和信息化部 公 告 2016年 第17号 工业和信息化部批准《不锈", "must_include": "中华人民共和国工业和信息化部 公 告 2016年 第17号 工业和信息化部批准《不锈", "source": "local", "assert_mode": "context_contains", "page_no": 2, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000004_golden_34() -> None:
    case = '{"kind": "evidence", "query": "QC_T 1036-2016 汽车电源逆变器-免费标准网_www.upbz.net：以上机械行业标准由机械工业出版社出版，汽车行业标准由科 学技术文献出版社出版，船舶行", "must_include": "以上机械行业标准由机械工业出版社出版，汽车行业标准由科 学技术文献出版社出版，船舶行", "source": "local", "assert_mode": "context_contains", "page_no": 2, "target_doc_id": "DOC-000004"}'
    _assert_case(json.loads(case))
