from __future__ import annotations

import json

import pytest

from enterprise_agent_kb.facts import _extract_term_definitions, _sanitize_payload


@pytest.mark.unit
def test_extract_term_definitions_from_term_page() -> None:
    text = """
### 3.3 功能 function

#### 3.3.1

## 控制导引电路 control pilot circuit

设计用于电动汽车和供电设备之间信号传输或通信的电路。

注：对于模式2，控制导引电路是电动汽车与缆上控制与保护装置之间信号传输或通信的电路。

#### 3.3.2

## 控制导引功能 control pilot function；CP

用于监控电动汽车和供电设备之间交互的功能。
"""
    items = _extract_term_definitions(text)
    terms = {item[2]["term"]: item[2]["definition"] for item in items}

    assert "控制导引电路 control pilot circuit" in terms
    assert "设计用于电动汽车和供电设备之间信号传输或通信的电路。" in terms["控制导引电路 control pilot circuit"]
    assert "控制导引功能 control pilot function;CP" in terms


@pytest.mark.unit
def test_extract_term_definitions_rejects_revision_bullets() -> None:
    text = """
本文件代替 GB/T 18487.1—2015。

s）增加了模式2和3使用数字通信的适用性要求（见第6章）；

t）将电击防护的一般要求更改为通则。
"""
    items = _extract_term_definitions(text)
    assert items == []


@pytest.mark.unit
def test_extract_term_definitions_accepts_process_attribute_scope() -> None:
    text = """
过程属性名称

过程部署过程属性

过程属性范围

过程部署过程属性是：对标准过程作为已定义过程进行部署而实现其过程成果的程度的度量。
"""
    items = _extract_term_definitions(text)
    terms = {item[2]["term"]: item[2]["definition"] for item in items}

    assert terms["过程部署过程属性"] == "过程部署过程属性是:对标准过程作为已定义过程进行部署而实现其过程成果的程度的度量。"


@pytest.mark.unit
def test_extract_term_definitions_accepts_process_group_sentences() -> None:
    text = """
获取过程组（ACQ）包括客户执行的过程，或者当供应商为了获取产品或服务而作为其供应商的客户时所执行的过程。

系统工程过程组（SYS）由多个过程组成，这些过程用于管理客户和内部需求的挖掘和管理、系统架构的定义以及在系统级别的集成和验证。
"""
    items = _extract_term_definitions(text)
    terms = {item[2]["term"]: item[2]["definition"] for item in items}

    assert "获取过程组（ACQ）" in terms
    assert "客户执行的过程" in terms["获取过程组（ACQ）"]
    assert "系统工程过程组（SYS）" in terms
    assert "系统架构的定义" in terms["系统工程过程组（SYS）"]


@pytest.mark.unit
def test_fact_payload_sanitizer_removes_html_space_artifacts() -> None:
    payload = {
        "step_text": "&nbsp;&nbsp;试验方法及步骤:\n&nbsp;&nbsp;a) 接好试验电路。",
        "rows": [["交流&nbsp;输入", "过压"]],
    }

    cleaned = _sanitize_payload(payload)

    assert "&nbsp;" not in json.dumps(cleaned, ensure_ascii=False)
    assert cleaned["step_text"] == "试验方法及步骤:\na) 接好试验电路。"
    assert cleaned["rows"][0][0] == "交流 输入"
