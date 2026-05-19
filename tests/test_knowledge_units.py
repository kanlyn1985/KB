from __future__ import annotations

from pathlib import Path
import json

from enterprise_agent_kb.knowledge_units import extract_knowledge_units
from test_helpers import resolve_doc_id_by_filename


def test_extract_knowledge_units_from_cleaned_doc_ir() -> None:
    doc_id = resolve_doc_id_by_filename("18487.1", ".pdf")
    bundle = extract_knowledge_units(Path(f"knowledge_base/normalized/{doc_id}.cleaned_doc_ir.json"))

    assert bundle.doc_id == doc_id
    assert bundle.unit_count > 0
    assert any(unit.type == "definition" for unit in bundle.units)
    assert any(unit.type == "requirement" for unit in bundle.units)
    assert any(unit.type == "table_requirement" for unit in bundle.units)
    assert any(unit.type == "procedure" for unit in bundle.units)
    assert not any(unit.type == "procedure" and unit.title == "前言" for unit in bundle.units)
    structured_requirements = [unit for unit in bundle.units if unit.type == "requirement" and unit.threshold]
    assert structured_requirements
    structured_tables = [unit for unit in bundle.units if unit.type == "table_requirement" and unit.headers]
    assert structured_tables
    assert any(unit.type == "table_requirement" and unit.table_no for unit in bundle.units)


def test_extract_knowledge_units_does_not_treat_table_caption_as_definition(tmp_path: Path) -> None:
    cleaned_ir_path = tmp_path / "DOC-TEST.cleaned_doc_ir.json"
    cleaned_ir_path.write_text(
        json.dumps(
            {
                "doc_id": "DOC-TEST",
                "pages": [
                    {
                        "page_no": 1,
                        "blocks": [
                            {"type": "paragraph", "text": "表 C.4 直流充电控制时序表"},
                            {"type": "paragraph", "text": "| 时刻 | 说明 |\n| :--- | :--- |\n| T1 | 用于连接确认 |"},
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = extract_knowledge_units(cleaned_ir_path)

    assert not any(unit.type == "definition" for unit in bundle.units)
    table_units = [unit for unit in bundle.units if unit.type == "table_requirement"]
    assert len(table_units) == 1
    assert table_units[0].table_title == "表 C.4 直流充电控制时序表"


def test_extract_knowledge_units_treats_aspice_bp_as_procedure_not_definition(tmp_path: Path) -> None:
    cleaned_ir_path = tmp_path / "DOC-TEST.cleaned_doc_ir.json"
    cleaned_ir_path.write_text(
        json.dumps(
            {
                "doc_id": "DOC-TEST",
                "pages": [
                    {
                        "page_no": 1,
                        "blocks": [
                            {
                                "type": "paragraph",
                                "text": "**SWE.1.BP5: 确保一致性和建立双向可追溯性。**确保软件需求与系统架构之间的一致性并建立双向可追溯性。",
                            },
                            {"type": "paragraph", "text": "*注 9: 冗余的可追溯性是非意图的。*"},
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = extract_knowledge_units(cleaned_ir_path)

    assert not any(unit.type == "definition" for unit in bundle.units)
    procedure_units = [unit for unit in bundle.units if unit.type == "procedure"]
    assert len(procedure_units) == 1
    assert "SWE.1.BP5" in procedure_units[0].content


def test_extract_knowledge_units_does_not_pair_complete_definition_blocks(tmp_path: Path) -> None:
    cleaned_ir_path = tmp_path / "DOC-TEST.cleaned_doc_ir.json"
    cleaned_ir_path.write_text(
        json.dumps(
            {
                "doc_id": "DOC-TEST",
                "pages": [
                    {
                        "page_no": 1,
                        "blocks": [
                            {
                                "type": "paragraph",
                                "text": "**3.5.2 电缆储存装置 cable management system** 一个或多个装置，用于收纳保护电缆组件避免物理损坏和/或便于操作。",
                            },
                            {
                                "type": "paragraph",
                                "text": "**3.5.3 电缆加长组件 cord extension set** 装配有非拆线插头及与之匹配的非拆线便携式插座或插头。",
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = extract_knowledge_units(cleaned_ir_path)

    assert not any(unit.type == "definition" for unit in bundle.units)


def test_extract_knowledge_units_does_not_pair_normative_clause_as_definition(tmp_path: Path) -> None:
    cleaned_ir_path = tmp_path / "DOC-TEST.cleaned_doc_ir.json"
    cleaned_ir_path.write_text(
        json.dumps(
            {
                "doc_id": "DOC-TEST",
                "pages": [
                    {
                        "page_no": 1,
                        "blocks": [
                            {"type": "paragraph", "text": "充电机应具备保护自身和车辆的手段，并防止交流供电回路短路等问题。"},
                            {"type": "paragraph", "text": "一旦直流供电回路发生短路，充电机应立即通过过流保护装置中断短路电流。"},
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = extract_knowledge_units(cleaned_ir_path)

    assert not any(unit.type == "definition" for unit in bundle.units)
    assert any(unit.type == "requirement" for unit in bundle.units)


def test_extract_knowledge_units_does_not_pair_table_value_body_as_definition(tmp_path: Path) -> None:
    cleaned_ir_path = tmp_path / "DOC-TEST.cleaned_doc_ir.json"
    cleaned_ir_path.write_text(
        json.dumps(
            {
                "doc_id": "DOC-TEST",
                "pages": [
                    {
                        "page_no": 1,
                        "blocks": [
                            {"type": "paragraph", "text": "功能特性状态要求"},
                            {
                                "type": "paragraph",
                                "text": "80%250个工频周期300个工频周期状态II70%25个工频周期30个工频周期状态II40%10个工频周期12个工频周期状态III",
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = extract_knowledge_units(cleaned_ir_path)

    assert not any(unit.type == "definition" for unit in bundle.units)


def test_extract_knowledge_units_detects_english_requirement(tmp_path: Path) -> None:
    cleaned_ir_path = tmp_path / "DOC-TEST.cleaned_doc_ir.json"
    cleaned_ir_path.write_text(
        json.dumps(
            {
                "doc_id": "DOC-TEST",
                "pages": [
                    {
                        "page_no": 1,
                        "blocks": [
                            {"type": "heading", "text": "6.5 Service requirements"},
                            {
                                "type": "paragraph",
                                "text": "The server shall transmit the positive response message to the client.",
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = extract_knowledge_units(cleaned_ir_path)

    assert bundle.unit_count == 1
    assert bundle.units[0].type == "requirement"
    assert bundle.units[0].content_role == "general_requirement"


def test_extract_knowledge_units_does_not_treat_requirements_noun_as_normative(tmp_path: Path) -> None:
    cleaned_ir_path = tmp_path / "DOC-TEST.cleaned_doc_ir.json"
    cleaned_ir_path.write_text(
        json.dumps(
            {
                "doc_id": "DOC-TEST",
                "pages": [
                    {
                        "page_no": 1,
                        "blocks": [
                            {"type": "heading", "text": "Foreword"},
                            {"type": "paragraph", "text": "Part 1: Specification and requirements"},
                            {
                                "type": "paragraph",
                                "text": "This document specifies the implementation requirements of a common diagnostic service.",
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = extract_knowledge_units(cleaned_ir_path)

    assert not any(unit.type == "requirement" for unit in bundle.units)


def test_extract_knowledge_units_ignores_toc_heading_and_iso_boilerplate(tmp_path: Path) -> None:
    cleaned_ir_path = tmp_path / "DOC-TEST.cleaned_doc_ir.json"
    cleaned_ir_path.write_text(
        json.dumps(
            {
                "doc_id": "DOC-TEST",
                "pages": [
                    {
                        "page_no": 1,
                        "blocks": [
                            {
                                "type": "heading",
                                "text": "Data link layer diagnostic implementation requirements.....................................................................................14",
                            },
                            {
                                "type": "paragraph",
                                "text": "Attention is drawn to the possibility that some elements may be the subject of patent rights. ISO shall not be held responsible for identifying any patent rights.",
                            },
                            {
                                "type": "heading",
                                "text": "6.5 Service requirements",
                            },
                            {
                                "type": "paragraph",
                                "text": "The server shall transmit the positive response message to the client.",
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = extract_knowledge_units(cleaned_ir_path)

    assert bundle.unit_count == 1
    assert bundle.units[0].title == "6.5 Service requirements"
    assert bundle.units[0].content.startswith("The server shall")


def test_extract_knowledge_units_ignores_figure_step_heading_noise(tmp_path: Path) -> None:
    cleaned_ir_path = tmp_path / "DOC-TEST.cleaned_doc_ir.json"
    cleaned_ir_path.write_text(
        json.dumps(
            {
                "doc_id": "DOC-TEST",
                "pages": [
                    {
                        "page_no": 1,
                        "blocks": [
                            {
                                "type": "heading",
                                "text": "18 | Server T_Data.con: When the diagnostic service is completely processed, the server then restarts its timer.",
                            },
                            {
                                "type": "paragraph",
                                "text": "The server shall re-activate the timer.",
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = extract_knowledge_units(cleaned_ir_path)

    assert bundle.unit_count == 1
    assert bundle.units[0].title == "page_1_requirement"


def test_extract_knowledge_units_ignores_figure_key_heading_and_uses_requirement_subject(tmp_path: Path) -> None:
    cleaned_ir_path = tmp_path / "DOC-TEST.cleaned_doc_ir.json"
    cleaned_ir_path.write_text(
        json.dumps(
            {
                "doc_id": "DOC-TEST",
                "pages": [
                    {
                        "page_no": 18,
                        "blocks": [
                            {
                                "type": "heading",
                                "text": "10\n11",
                            },
                            {
                                "type": "heading",
                                "text": "26\nClient T_Data.con: Upon the indication of the completed transmission of a request message.",
                            },
                            {
                                "type": "paragraph",
                                "text": "Server T_Data.ind: The reception of the request message is indicated in the server. The server shall re-activate the timer.",
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = extract_knowledge_units(cleaned_ir_path)

    assert bundle.unit_count == 1
    unit = bundle.units[0]
    assert unit.title == "page_18_requirement"
    assert unit.subject == "Server T_Data.ind"
    assert unit.topic == "Server T_Data.ind"


def test_extract_knowledge_units_does_not_pair_section_heading_as_definition(tmp_path: Path) -> None:
    cleaned_ir_path = tmp_path / "DOC-TEST.cleaned_doc_ir.json"
    cleaned_ir_path.write_text(
        json.dumps(
            {
                "doc_id": "DOC-TEST",
                "pages": [
                    {
                        "page_no": 1,
                        "blocks": [
                            {"type": "paragraph", "text": "**2.3.1. 电能质量影响**"},
                            {"type": "paragraph", "text": "大规模 EV 接入电网会对电网运行的稳定性产生影响。"},
                            {"type": "paragraph", "text": ". 工作产品类型"},
                            {"type": "paragraph", "text": "在对过程属性进行评级时，工作产品可以作为证据。"},
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = extract_knowledge_units(cleaned_ir_path)

    assert not any(unit.type == "definition" for unit in bundle.units)


def test_extract_knowledge_units_does_not_pair_layout_boilerplate_as_definition(tmp_path: Path) -> None:
    cleaned_ir_path = tmp_path / "DOC-TEST.cleaned_doc_ir.json"
    cleaned_ir_path.write_text(
        json.dumps(
            {
                "doc_id": "DOC-TEST",
                "pages": [
                    {
                        "page_no": 1,
                        "blocks": [
                            {"type": "paragraph", "text": "VDA QMC AUTOMOTIVE SPICE®"},
                            {"type": "paragraph", "text": "PUBLIC 是用于标识公开发布版本的页眉文本。"},
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = extract_knowledge_units(cleaned_ir_path)

    assert not any(unit.type == "definition" for unit in bundle.units)


def test_extract_knowledge_units_does_not_pair_author_name_list_as_definition(tmp_path: Path) -> None:
    cleaned_ir_path = tmp_path / "DOC-TEST.cleaned_doc_ir.json"
    cleaned_ir_path.write_text(
        json.dumps(
            {
                "doc_id": "DOC-TEST",
                "pages": [
                    {
                        "page_no": 1,
                        "blocks": [
                            {"type": "paragraph", "text": "山博轩，杨郁"},
                            {
                                "type": "paragraph",
                                "text": "物理层为车网交互的物理基础，即电动汽车、充电站、智能电网。通过传感和通信技术采集状态信息。",
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = extract_knowledge_units(cleaned_ir_path)

    assert not any(unit.type == "definition" for unit in bundle.units)


def test_extract_knowledge_units_does_not_pair_figure_legend_as_definition(tmp_path: Path) -> None:
    cleaned_ir_path = tmp_path / "DOC-TEST.cleaned_doc_ir.json"
    cleaned_ir_path.write_text(
        json.dumps(
            {
                "doc_id": "DOC-TEST",
                "pages": [
                    {
                        "page_no": 1,
                        "blocks": [
                            {"type": "paragraph", "text": "车辆插座 车辆插头 电缆组件 车辆接口"},
                            {"type": "paragraph", "text": "标引序号说明： ☆——连接点。 注：电缆组件是供电设备的一部分。"},
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = extract_knowledge_units(cleaned_ir_path)

    assert not any(unit.type == "definition" for unit in bundle.units)
