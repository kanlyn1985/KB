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
@pytest.mark.page_coverage
def test_doc_000009_golden_1() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第1页 ICS 43.040 CCS T 35 # GB # 中华人民共和国国家标准", "must_include": "ICS 43.040 CCS T 35 # GB # 中华人民共和国国家标准", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_2() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第3页 GB/T 40432—2021 # 前 言 本文件按照GB/T 1.1—20", "must_include": "GB/T 40432—2021 # 前 言 本文件按照GB/T 1.1—20", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_3() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第4页 GB 4824—2019 工业、科学和医疗设备 射频骚扰特性 限值和测量方法", "must_include": "GB 4824—2019 工业、科学和医疗设备 射频骚扰特性 限值和测量方法", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_4() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第5页 3.3 **充电效率 charging efficiency** 输出功率与", "must_include": "3.3 **充电效率 charging efficiency** 输出功率与", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_5() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第6页 GB/T 40432—2021 4.2.3 直流输出限压特性 具有恒压输出特", "must_include": "GB/T 40432—2021 4.2.3 直流输出限压特性 具有恒压输出特", "source": "local", "assert_mode": "context_contains", "page_no": 6, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_6() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第8页 4.4.2 耐电压性 在车载充电机的各独立带电端口回路与地(外壳)之间、彼此", "must_include": "4.4.2 耐电压性 在车载充电机的各独立带电端口回路与地(外壳)之间、彼此", "source": "local", "assert_mode": "context_contains", "page_no": 8, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_7() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第9页 表 6 浪涌(冲击)抗扰度试验项目及功能等级要求 | 试验项目 | 试验严酷", "must_include": "表 6 浪涌(冲击)抗扰度试验项目及功能等级要求 | 试验项目 | 试验严酷", "source": "local", "assert_mode": "context_contains", "page_no": 9, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_8() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第10页 GB/T 40432—2021 **表 7 电压暂降和短时中断试验项目及功能", "must_include": "GB/T 40432—2021 **表 7 电压暂降和短时中断试验项目及功能", "source": "local", "assert_mode": "context_contains", "page_no": 10, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_9() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第11页 GB/T 40432—2021 4.6 环境适应性 4.6.1 环境条件 4", "must_include": "GB/T 40432—2021 4.6 环境适应性 4.6.1 环境条件 4", "source": "local", "assert_mode": "context_contains", "page_no": 11, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_10() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第12页 5.1.2 仪器设备要求 试验用设备应采用比受试设备技术指标至少高一个等级", "must_include": "5.1.2 仪器设备要求 试验用设备应采用比受试设备技术指标至少高一个等级", "source": "local", "assert_mode": "context_contains", "page_no": 12, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_11() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第13页 GB/T 40432—2021 ![图 1 充电试验基本原理图](https", "must_include": "GB/T 40432—2021 ![图 1 充电试验基本原理图](https", "source": "local", "assert_mode": "context_contains", "page_no": 13, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_12() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第14页 5.3.4 直流输出限压特性试验 试验方法及步骤： a) 按照图 1 接好试", "must_include": "5.3.4 直流输出限压特性试验 试验方法及步骤： a) 按照图 1 接好试", "source": "local", "assert_mode": "context_contains", "page_no": 14, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_13() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第17页 5.4.3.2 直流输出欠压保护试验 试验方法及步骤: a) 按照图 1 接", "must_include": "5.4.3.2 直流输出欠压保护试验 试验方法及步骤: a) 按照图 1 接", "source": "local", "assert_mode": "context_contains", "page_no": 17, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_14() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第18页 5.6 电磁兼容试验 5.6.1 工作状态 车载充电机在充电工作状态下进行电", "must_include": "5.6 电磁兼容试验 5.6.1 工作状态 车载充电机在充电工作状态下进行电", "source": "local", "assert_mode": "context_contains", "page_no": 18, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_15() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第19页 5.6.3.6 电压波动和闪烁试验 5.6.3.6.1 当车载充电机额定输入", "must_include": "5.6.3.6 电压波动和闪烁试验 5.6.3.6.1 当车载充电机额定输入", "source": "local", "assert_mode": "context_contains", "page_no": 19, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_16() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第20页 5.7.4 耐振动试验 车载充电机的振动试验根据其在车辆中的安装部位，按 G", "must_include": "5.7.4 耐振动试验 车载充电机的振动试验根据其在车辆中的安装部位，按 G", "source": "local", "assert_mode": "context_contains", "page_no": 20, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_17() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第22页 GB/T 40432—2021 A.1.1.9 交流输出带非阻性负载能力 逆", "must_include": "GB/T 40432—2021 A.1.1.9 交流输出带非阻性负载能力 逆", "source": "local", "assert_mode": "context_contains", "page_no": 22, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_18() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第23页 ![放电试验基本原理图](A.1) 功率分析仪 电流取样装置 电压取样装置", "must_include": "![放电试验基本原理图](A.1) 功率分析仪 电流取样装置 电压取样装置", "source": "local", "assert_mode": "context_contains", "page_no": 23, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
@pytest.mark.page_coverage
def test_doc_000009_golden_19() -> None:
    case = '{"kind": "page_coverage", "query": "GBT+40432-2021：第25页 GB/T 40432—2021 a) 按照图 A.1 接好试验电路,电子负载", "must_include": "GB/T 40432—2021 a) 按照图 A.1 接好试验电路,电子负载", "source": "local", "assert_mode": "context_contains", "page_no": 25, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_20() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：ICS 43.040 CCS T 35 # GB # 中华人民共和国国家标准 GB/", "must_include": "ICS 43.040 CCS T 35 # GB # 中华人民共和国国家标准 GB/", "source": "local", "assert_mode": "context_contains", "page_no": 1, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_21() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：GB/T 40432—2021 # 前 言 本文件按照GB/T 1.1—2020《标", "must_include": "GB/T 40432—2021 # 前 言 本文件按照GB/T 1.1—2020《标", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_22() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：请注意本文件的某些内容可能涉及专利。本文件的发布机构不承担识别专利的责任。", "must_include": "请注意本文件的某些内容可能涉及专利。本文件的发布机构不承担识别专利的责任。", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_23() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：本文件由中华人民共和国工业和信息化部提出。", "must_include": "本文件由中华人民共和国工业和信息化部提出。", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_24() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：本文件由全国汽车标准化技术委员会(SAC/TC 114)归口。", "must_include": "本文件由全国汽车标准化技术委员会(SAC/TC 114)归口。", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_25() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：本文件起草单位:北京新能源汽车股份有限公司、苏州汇川联合动力系统有限公司、华为技术有", "must_include": "本文件起草单位:北京新能源汽车股份有限公司、苏州汇川联合动力系统有限公司、华为技术有", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_26() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：本文件主要起草人:赵春阳、符志辉、许晓、曹冬冬、叶铱塬、闫亚江、赵凌霄、徐枭、张晓彬", "must_include": "本文件主要起草人:赵春阳、符志辉、许晓、曹冬冬、叶铱塬、闫亚江、赵凌霄、徐枭、张晓彬", "source": "local", "assert_mode": "context_contains", "page_no": 3, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_27() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：GB/T 40432—2021 # 电动汽车用传导式车载充电机 ### 1 范围 本", "must_include": "GB/T 40432—2021 # 电动汽车用传导式车载充电机 ### 1 范围 本", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_28() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：本文件适用于标称输入电压为 220 V(AC)(单相)或 380 V(AC)(三相)", "must_include": "本文件适用于标称输入电压为 220 V(AC)(单相)或 380 V(AC)(三相)", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_29() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：### 2 规范性引用文件 下列文件中的内容通过文中的规范性引用而构成本文件必不可少", "must_include": "### 2 规范性引用文件 下列文件中的内容通过文中的规范性引用而构成本文件必不可少", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_30() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：GB 4824—2019 工业、科学和医疗设备 射频骚扰特性 限值和测量方法 GB/", "must_include": "GB 4824—2019 工业、科学和医疗设备 射频骚扰特性 限值和测量方法 GB/", "source": "local", "assert_mode": "context_contains", "page_no": 4, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_31() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：GB/T 40432—2021 3.1 **车载充电机 on-board charg", "must_include": "GB/T 40432—2021 3.1 **车载充电机 on-board charg", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_32() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：3.3 **充电效率 charging efficiency** 输出功率与输入有功", "must_include": "3.3 **充电效率 charging efficiency** 输出功率与输入有功", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_33() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：3.4 **输出电压误差 output voltage tolerance** 实际", "must_include": "3.4 **输出电压误差 output voltage tolerance** 实际", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))

@pytest.mark.integration
@pytest.mark.benchmark
def test_doc_000009_golden_34() -> None:
    case = '{"kind": "evidence", "query": "GBT+40432-2021：3.5 **输出电流误差 output current tolerance** 实际", "must_include": "3.5 **输出电流误差 output current tolerance** 实际", "source": "local", "assert_mode": "context_contains", "page_no": 5, "target_doc_id": "DOC-000009"}'
    _assert_case(json.loads(case))
