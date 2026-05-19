from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.cli import build_parser
from enterprise_agent_kb.coverage import (
    _is_actionable_test_gap_row,
    _is_source_unit_inventory_noise,
    _soft_contains,
    _stable_fact_fallback_unit_id,
    build_coverage_for_document,
    build_test_gap_candidates_for_document,
)
from enterprise_agent_kb.coverage_diagnostics import build_all_docs_uncovered_priority_report
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.generated_tests import (
    _build_golden_case_summary,
    _trace_metrics_from_context,
    assess_all_coverage_test_draft_readiness,
    assess_coverage_test_draft_readiness_for_document,
    close_coverage_test_gaps,
    generate_coverage_test_drafts_for_document,
    promote_coverage_test_drafts_for_document,
    run_coverage_promoted_tests_for_document,
)


def _make_runtime(tmp_path: Path) -> tuple[Path, Path]:
    schema_path = Path(__file__).resolve().parents[1] / "src" / "enterprise_agent_kb" / "schema.sql"
    temp_path = tmp_path / "coverage_runtime"
    temp_path.mkdir(parents=True, exist_ok=True)
    workspace = temp_path / "knowledge_base"
    initialize_workspace(workspace, schema_path)
    return temp_path, workspace


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def test_trace_metrics_flattens_shape_contract() -> None:
    metrics = _trace_metrics_from_context(
        {
            "rewrite": {"query_type": "test_method_lookup"},
            "retrieval_plan": {"channels": ["facts"], "graph_candidate_count": 0},
            "evidence_judgement": {
                "sufficient": True,
                "reason": "top evidence covers test method",
                "evidence_shape": "test_method",
                "shape_diagnostics": {
                    "shape_contract": {
                        "query_type": "test_method_lookup",
                        "allowed_shapes": ["test_method"],
                        "required": True,
                        "matched": True,
                    },
                    "shape_contract_diagnosis": {
                        "reason": "contract_matched",
                        "action": "无需处理",
                    },
                },
            },
        }
    )

    assert metrics["evidence_shape"] == "test_method"
    assert metrics["shape_contract_query_type"] == "test_method_lookup"
    assert metrics["shape_contract_allowed_shapes"] == ["test_method"]
    assert metrics["shape_contract_required"] is True
    assert metrics["shape_contract_matched"] is True
    assert metrics["shape_contract_failure_reason"] == "contract_matched"


def _seed_minimal_coverage_chain(workspace: Path, doc_id: str) -> None:
    now = _now()
    connection = connect(workspace / "db" / "knowledge.db")
    try:
        connection.execute(
            """
            INSERT INTO documents (
                doc_id, source_filename, source_type, mime_type, sha256, file_size, page_count,
                language, version_label, source_path, ingest_time, update_time,
                parse_status, quality_status, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                "sample_standard.md",
                "markdown",
                "text/markdown",
                "sha256-test",
                123,
                1,
                "zh",
                None,
                str(workspace / "raw" / "sample_standard.md"),
                now,
                now,
                "ready",
                "ready",
                1,
            ),
        )
        connection.execute(
            """
            INSERT INTO pages (
                page_id, doc_id, page_no, width, height, parser_confidence, ocr_confidence,
                risk_level, page_status, screenshot_path, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("PAGE-000001", doc_id, 1, None, None, 1.0, 1.0, "low", "ready", None, now, now),
        )

        evidence_rows = [
            (
                "EV-000001",
                "BLK-000001",
                "控制导引电路是用于车辆与供电设备之间信号传输或通信的电路。",
            ),
            (
                "EV-000002",
                "BLK-000002",
                "A.2 充电控制导引电路 | CP | 占空比 | D | % | 50 | 状态B",
            ),
            (
                "EV-000003",
                "BLK-000003",
                "A.2 充电控制导引电路 | 检测点1 | 检测点1电压 | U1 | V | 12 | 状态A",
            ),
            (
                "EV-000004",
                "BLK-000004",
                "本文件适用于采用数字通信的充电系统，其供电网侧额定电压不超过 AC1000 V。",
            ),
        ]
        for evidence_id, block_id, text in evidence_rows:
            connection.execute(
                """
                INSERT INTO evidence (
                    evidence_id, doc_id, page_id, block_id, block_type, raw_text, normalized_text,
                    image_ref, table_ref, page_no, confidence, risk_level, evidence_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (evidence_id, doc_id, "PAGE-000001", block_id, "text", text, text, None, None, 1, 0.95, "low", "ready", now, now),
            )

        entities = [
            ("ENT-000001", "控制导引电路", "term", "term definition"),
            ("ENT-000002", "CP占空比", "parameter_topic", "CP duty cycle"),
            ("ENT-000003", "检测点1电压", "parameter_topic", "detection point voltage"),
        ]
        for entity_id, canonical_name, entity_type, description in entities:
            connection.execute(
                """
                INSERT INTO entities (
                    entity_id, canonical_name, entity_type, alias_json, description,
                    source_confidence, entity_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (entity_id, canonical_name, entity_type, "[]", description, 0.95, "ready", now, now),
            )

        fact_rows = [
            (
                "FACT-000001",
                "term_definition",
                "defines_term",
                {"term": "控制导引电路", "definition": "用于车辆与供电设备之间信号传输或通信的电路。"},
                None,
                "ENT-000001",
                "EV-000001",
            ),
            (
                "FACT-000002",
                "parameter_value",
                "has_parameter_value",
                {
                    "table_title": "A.2 充电控制导引电路",
                    "object": "CP",
                    "parameter": "占空比",
                    "symbol": "D",
                    "unit": "%",
                    "nominal_value": "50",
                    "max_value": "51",
                    "min_value": "49",
                    "state": "状态B",
                    "focus_tags": ["CP", "控制导引"],
                    "detection_points": [],
                },
                None,
                "ENT-000002",
                "EV-000002",
            ),
            (
                "FACT-000003",
                "parameter_value",
                "has_parameter_value",
                {
                    "table_title": "A.2 充电控制导引电路",
                    "object": "检测点1",
                    "parameter": "检测点1电压",
                    "symbol": "U1",
                    "unit": "V",
                    "nominal_value": "12",
                    "max_value": "12.6",
                    "min_value": "11.4",
                    "state": "状态A",
                    "focus_tags": ["检测点1", "控制导引"],
                    "detection_points": ["检测点1"],
                },
                None,
                "ENT-000003",
                "EV-000003",
            ),
            (
                "FACT-000004",
                "requirement",
                "has_requirement",
                {
                    "title": "1 范围",
                    "topic": "范围",
                    "subject": "范围",
                    "scope_type": "overview",
                    "content": "本文件适用于采用数字通信的充电系统，其供电网侧额定电压不超过 AC1000 V。",
                },
                None,
                None,
                "EV-000004",
            ),
        ]
        for fact_id, fact_type, predicate, payload, subject_entity_id, object_entity_id, evidence_id in fact_rows:
            connection.execute(
                """
                INSERT INTO facts (
                    fact_id, fact_type, subject_entity_id, predicate, object_value,
                    object_entity_id, qualifiers_json, confidence, fact_status,
                    source_doc_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fact_id,
                    fact_type,
                    subject_entity_id,
                    predicate,
                    json.dumps(payload, ensure_ascii=False),
                    object_entity_id,
                    json.dumps({"page_no": 1, "risk_level": "low"}, ensure_ascii=False),
                    0.95,
                    "ready",
                    doc_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO fact_evidence_map (fact_id, evidence_id, support_type)
                VALUES (?, ?, ?)
                """,
                (fact_id, evidence_id, "direct"),
            )

        wiki_rows = [
            ("WPAGE-000001", "term", "控制导引电路", "ENT-000001", ["FACT-000001"]),
            ("WPAGE-000002", "parameter_topic", "CP占空比", "ENT-000002", ["FACT-000002"]),
            ("WPAGE-000003", "parameter_topic", "检测点1电压", "ENT-000003", ["FACT-000003"]),
        ]
        for page_id, page_type, title, entity_id, source_fact_ids in wiki_rows:
            connection.execute(
                """
                INSERT INTO wiki_pages (
                    page_id, page_type, title, slug, entity_id, source_fact_ids_json,
                    source_doc_ids_json, trust_status, file_path, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page_id,
                    page_type,
                    title,
                    f"{page_type}-{page_id.lower()}",
                    entity_id,
                    json.dumps(source_fact_ids, ensure_ascii=False),
                    json.dumps([doc_id], ensure_ascii=False),
                    "ready",
                    str(workspace / "wiki" / f"{page_id}.md"),
                    now,
                ),
            )

        knowledge_units = {
            "doc_id": doc_id,
            "unit_count": 3,
            "units": [
                {
                    "id": f"{doc_id}_definition_1_1",
                    "type": "definition",
                    "title": "控制导引电路",
                    "content": "用于车辆与供电设备之间信号传输或通信的电路。",
                    "section": "3",
                    "page": 1,
                },
                {
                    "id": f"{doc_id}_requirement_1_2",
                    "type": "requirement",
                    "title": "1 范围",
                    "content": "本文件适用于采用数字通信的充电系统，其供电网侧额定电压不超过 AC1000 V。",
                    "section": "1",
                    "page": 1,
                    "subject": "范围",
                    "topic": "范围",
                    "scope_type": "overview",
                    "condition": None,
                    "threshold": "不超过 AC1000 V",
                },
                {
                    "id": f"{doc_id}_table_1_3",
                    "type": "table_requirement",
                    "title": "A.2 充电控制导引电路",
                    "content": "",
                    "section": "A.2",
                    "page": 1,
                    "table_title": "A.2 充电控制导引电路",
                    "headers": ["对象", "参数a", "符号", "单位", "标称值", "最大值b", "最小值b", "对应状态d"],
                    "rows": [
                        ["CP", "占空比", "D", "%", "50", "51", "49", "状态B"],
                        ["检测点1", "检测点1电压", "U1", "V", "12", "12.6", "11.4", "状态A"],
                    ],
                },
            ],
        }
        (workspace / "normalized" / f"{doc_id}.knowledge_units.json").write_text(
            json.dumps(knowledge_units, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        connection.commit()
    finally:
        connection.close()


def _write_generated_cases(generated_dir: Path, doc_id: str) -> None:
    generated_dir.mkdir(parents=True, exist_ok=True)
    (generated_dir / f"{doc_id}.golden.json").write_text(
        json.dumps(
            {
                "doc_id": doc_id,
                "cases": [
                    {
                        "kind": "definition",
                        "query": "什么是控制导引电路？",
                        "must_include": "控制导引电路",
                        "assert_mode": "rich_answer",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (generated_dir / "user_style_query_regression_cases_test.json").write_text(
        json.dumps(
            [
                {
                    "name": "cp_duty_cycle_meaning",
                    "query": "CP占空比是什么意思",
                    "expected_target_topic": "CP占空比",
                    "expected_top_entity_name": "CP占空比",
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


@pytest.mark.unit
def test_build_coverage_generates_v0_reports(tmp_path: Path) -> None:
    temp_path, workspace = _make_runtime(tmp_path)
    doc_id = "DOC-TEST-0001"
    _seed_minimal_coverage_chain(workspace, doc_id)
    generated_dir = temp_path / "tests" / "generated"
    _write_generated_cases(generated_dir, doc_id)

    result = build_coverage_for_document(workspace, doc_id, tests_generated_dir=generated_dir)

    assert result.source_unit_count >= 4
    assert result.text_coverage_rate > 0
    assert result.semantic_coverage_rate > 0
    assert result.object_coverage_rate > 0
    assert result.test_coverage_rate > 0

    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert summary["unit_type_summary"]["parameter_row_unit"]["count"] >= 2

    matrix = json.loads(result.matrix_path.read_text(encoding="utf-8"))
    cp_row = next(
        item
        for item in matrix["items"]
        if item["unit_type"] == "parameter_row_unit" and item["semantic_key"] == "CP占空比"
    )
    assert cp_row["covered_by"]["fact_ids"]
    assert cp_row["covered_by"]["entity_ids"]
    assert cp_row["covered_by"]["regression_case_ids"]

    candidates_path = workspace / "coverage_reports" / f"{doc_id}.test_gap_candidates.json"
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    assert candidates["candidate_count"] >= 1
    assert any(item["coverage_status"] == "u3_not_tested" for item in candidates["items"])
    assert any(item["recommended_query_seed"] == "检测点1电压是多少？" for item in candidates["items"])


@pytest.mark.unit
def test_build_test_gap_candidates_can_limit_output(tmp_path: Path) -> None:
    temp_path, workspace = _make_runtime(tmp_path)
    doc_id = "DOC-TEST-0001"
    _seed_minimal_coverage_chain(workspace, doc_id)
    generated_dir = temp_path / "tests" / "generated"
    _write_generated_cases(generated_dir, doc_id)
    build_coverage_for_document(workspace, doc_id, tests_generated_dir=generated_dir)

    result = build_test_gap_candidates_for_document(workspace, doc_id, limit=1)

    assert result.candidate_count == 1
    payload = json.loads(result.candidates_path.read_text(encoding="utf-8"))
    assert payload["candidate_count"] == 1
    assert payload["items"][0]["recommended_query_seed"]


@pytest.mark.unit
def test_build_test_gap_candidates_can_exclude_rejected_units(tmp_path: Path) -> None:
    temp_path, workspace = _make_runtime(tmp_path)
    doc_id = "DOC-TEST-0001"
    _seed_minimal_coverage_chain(workspace, doc_id)
    generated_dir = temp_path / "tests" / "generated"
    _write_generated_cases(generated_dir, doc_id)
    build_coverage_for_document(workspace, doc_id, tests_generated_dir=generated_dir)

    first = build_test_gap_candidates_for_document(workspace, doc_id, limit=1)
    first_payload = json.loads(first.candidates_path.read_text(encoding="utf-8"))
    excluded_unit_id = first_payload["items"][0]["unit_id"]

    second = build_test_gap_candidates_for_document(
        workspace,
        doc_id,
        limit=10,
        excluded_unit_ids={excluded_unit_id},
    )
    second_payload = json.loads(second.candidates_path.read_text(encoding="utf-8"))

    assert second_payload["excluded_candidate_count"] == 1
    assert all(item["unit_id"] != excluded_unit_id for item in second_payload["items"])


@pytest.mark.unit
def test_fact_fallback_source_unit_ids_do_not_embed_fact_ids() -> None:
    first = _stable_fact_fallback_unit_id(
        "DOC-TEST",
        "definition_unit",
        12,
        "控制导引功能",
        "通过电子或者机械的方式反映连接状态。",
    )
    second = _stable_fact_fallback_unit_id(
        "DOC-TEST",
        "definition_unit",
        12,
        "控制导引功能",
        "通过电子或者机械的方式反映连接状态。",
    )

    assert first == second
    assert "FACT-" not in first
    assert first.startswith("DOC-TEST:definition:12:")


@pytest.mark.unit
def test_coverage_soft_contains_normalizes_roman_numerals_and_cjk_punctuation() -> None:
    assert _soft_contains("状态Ⅱ：试验中不能完成设计功能", "状态 II :试验中不能完成设计功能")
    assert _soft_contains(
        "a）按照图 A.1 接好试验电路，电子负载设置为恒阻负载模式；",
        "a) 按照图 A.1 接好试验电路，电子负载设置为恒阻负载模式；",
    )


@pytest.mark.unit
def test_coverage_test_gap_filters_low_value_candidates() -> None:
    assert not _is_actionable_test_gap_row({"unit_type": "parameter_row_unit", "semantic_key": "VA"})
    assert not _is_actionable_test_gap_row({"unit_type": "parameter_row_unit", "semantic_key": "时刻"})
    assert not _is_actionable_test_gap_row({"unit_type": "parameter_row_unit", "semantic_key": "DP3"})
    assert not _is_actionable_test_gap_row({"unit_type": "parameter_row_unit", "semantic_key": "S+/S-"})
    assert not _is_actionable_test_gap_row({"unit_type": "parameter_row_unit", "semantic_key": "Vdc (C1/C2前)"})
    assert not _is_actionable_test_gap_row({"unit_type": "definition_unit", "semantic_key": "VDA QMC [space] AUTOMOTIVE SPICE®"})
    assert not _is_actionable_test_gap_row(
        {
            "unit_type": "requirement_unit",
            "semantic_key": "Automatic reclosing of protective devices ........................................................................ 47 15 Emergency switching or disconnect (optional) .............................................................. 48",
            "source_excerpt": "",
        }
    )
    assert _is_actionable_test_gap_row({"unit_type": "definition_unit", "semantic_key": "控制导引电路 control pilot circuit"})


@pytest.mark.unit
def test_source_unit_inventory_filters_structural_and_symbol_noise() -> None:
    assert _is_source_unit_inventory_noise(
        unit_type="requirement_unit",
        semantic_key="目 次",
        source_text="前言 1 范围 2 规范性引用文件",
        quality_flags=[],
    )
    assert _is_source_unit_inventory_noise(
        unit_type="requirement_unit",
        semantic_key="概述",
        source_text="应符合表1的规定",
        quality_flags=[],
    )
    assert _is_source_unit_inventory_noise(
        unit_type="definition_unit",
        semantic_key="车辆插座 车辆插头 充电电缆 供电插头 车辆接口 供电插座",
        source_text="标引序号说明： ☆——连接点。",
        quality_flags=[],
    )
    assert _is_source_unit_inventory_noise(
        unit_type="parameter_row_unit",
        semantic_key="U1b",
        source_text="U1b | V | 6 | 6.8 | 5.2",
        quality_flags=[],
    )
    assert _is_source_unit_inventory_noise(
        unit_type="requirement_unit",
        semantic_key="3",
        source_text="从这个方面讲，PRM 或 PAM 也不应该表示产品要素的层次结构。",
        quality_flags=[],
    )
    assert _is_source_unit_inventory_noise(
        unit_type="definition_unit",
        semantic_key="条款 6.2，“过程评估模型范围”",
        source_text="Automotive SPICE 过程参考模型满足 ISO/IEC 33004:2015 条款 5 的要求。",
        quality_flags=[],
    )
    assert _is_source_unit_inventory_noise(
        unit_type="requirement_unit",
        semantic_key="Automatic reclosing of protective devices ........................................................................ 47 15 Emergency switching or disconnect (optional) .............................................................. 48",
        source_text="",
        quality_flags=[],
    )
    assert _is_source_unit_inventory_noise(
        unit_type="requirement_unit",
        semantic_key="© ISO 2015 - All rights reserved",
        source_text="© ISO 2015 - All rights reserved",
        quality_flags=[],
    )
    assert _is_source_unit_inventory_noise(
        unit_type="requirement_unit",
        semantic_key="Introduction",
        source_text="Introduction",
        quality_flags=[],
    )
    assert not _is_source_unit_inventory_noise(
        unit_type="requirement_unit",
        semantic_key="噪声",
        source_text="逆变器在 40 dB(A)～45 dB(A) 的环境中人耳距离逆变器 30 cm 应不能明显感觉到逆变器的运行声音。",
        quality_flags=[],
    )


@pytest.mark.unit
def test_coverage_matches_source_unit_to_cross_type_fact(tmp_path: Path) -> None:
    temp_path, workspace = _make_runtime(tmp_path)
    doc_id = "DOC-TEST-0001"
    _seed_minimal_coverage_chain(workspace, doc_id)
    connection = connect(workspace / "db" / "knowledge.db")
    now = _now()
    try:
        connection.execute(
            """
            INSERT INTO evidence (
                evidence_id, doc_id, page_id, block_id, block_type, raw_text, normalized_text,
                image_ref, table_ref, page_no, confidence, risk_level, evidence_status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "EV-000099",
                doc_id,
                "PAGE-000001",
                "BLK-000099",
                "text",
                "表 Z.9 特殊兼容性矩阵 | 项目 | 要求 |",
                "表 Z.9 特殊兼容性矩阵 | 项目 | 要求 |",
                None,
                None,
                1,
                0.9,
                "low",
                "ready",
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO facts (
                fact_id, fact_type, subject_entity_id, predicate, object_value,
                object_entity_id, qualifiers_json, confidence, fact_status,
                source_doc_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "FACT-000099",
                "table_requirement",
                "ENT-000001",
                "has_table_requirement",
                json.dumps({"table_title": "表 Z.9 特殊兼容性矩阵", "headers": ["项目", "要求"], "rows": []}, ensure_ascii=False),
                None,
                json.dumps({"page_no": 1}, ensure_ascii=False),
                0.8,
                "ready",
                doc_id,
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO fact_evidence_map (fact_id, evidence_id, support_type)
            VALUES (?, ?, ?)
            """,
            ("FACT-000099", "EV-000099", "supports"),
        )
        connection.commit()
    finally:
        connection.close()

    units_path = workspace / "normalized" / f"{doc_id}.knowledge_units.json"
    payload = json.loads(units_path.read_text(encoding="utf-8"))
    payload["units"].append(
        {
            "id": f"{doc_id}_definition_1_99",
            "type": "definition",
            "title": "表 Z.9 特殊兼容性矩阵",
            "content": "| 项目 | 要求 |",
            "section": "A.1",
            "page": 1,
            "subject": None,
            "topic": None,
            "scope_type": None,
            "condition": None,
            "threshold": None,
            "table_title": None,
            "table_no": None,
            "headers": None,
            "rows": None,
        }
    )
    units_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    result = build_coverage_for_document(workspace, doc_id, tests_generated_dir=temp_path / "tests" / "generated")
    matrix = json.loads(result.matrix_path.read_text(encoding="utf-8"))
    row = next(item for item in matrix["items"] if item["unit_id"] == f"{doc_id}_definition_1_99")

    assert row["covered_by"]["fact_ids"] == ["FACT-000099"]
    assert row["coverage_flags"]["semantic_covered"] is True
    assert row["semantic_misaligned"] is False


@pytest.mark.unit
def test_coverage_promotes_procedure_units_with_canonical_metadata_to_source_units(tmp_path: Path) -> None:
    temp_path, workspace = _make_runtime(tmp_path)
    doc_id = "DOC-TEST-0001"
    _seed_minimal_coverage_chain(workspace, doc_id)

    units_path = workspace / "normalized" / f"{doc_id}.knowledge_units.json"
    payload = json.loads(units_path.read_text(encoding="utf-8"))
    payload["units"].append(
        {
            "id": f"{doc_id}_procedure_53_1",
            "type": "procedure",
            "title": "53 PUBLIC",
            "content": "SWE.2.BP1: 开发软件架构设计。SWE.2.BP2: 分配软件需求。",
            "section": "4.4.2",
            "page": 53,
            "canonical_title": ". SWE.2 软件架构设计",
            "content_role": "procedure",
            "quality_flags": ["old_cached_metadata"],
        }
    )
    payload["units"].append(
        {
            "id": f"{doc_id}_procedure_54_1",
            "type": "procedure",
            "title": "4.4.2. SWE.2 软件架构设计",
            "content": "SWE.2.BP3: 分析软件架构。",
            "section": "4.4.2",
            "page": 54,
        }
    )
    units_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    result = build_coverage_for_document(workspace, doc_id, tests_generated_dir=temp_path / "tests" / "generated")
    matrix = json.loads(result.matrix_path.read_text(encoding="utf-8"))
    row = next(item for item in matrix["items"] if item["unit_id"] == f"{doc_id}_procedure_53_1")

    assert row["unit_type"] == "process_unit"
    assert row["semantic_key"] == "SWE.2"
    assert row["canonical_title"] == "SWE.2 基本实践"
    assert row["content_role"] == "process_practice"
    assert "layout_title_noise" in row["quality_flags"]
    assert "old_cached_metadata" in row["quality_flags"]
    titled_row = next(item for item in matrix["items"] if item["unit_id"] == f"{doc_id}_procedure_54_1")
    assert titled_row["canonical_title"] == "SWE.2 软件架构设计"

    connection = connect(workspace / "db" / "knowledge.db")
    try:
        stored = connection.execute(
            """
            SELECT unit_type, canonical_title, canonical_key, content_role, quality_flags_json
            FROM source_units
            WHERE unit_id = ?
            """,
            (f"{doc_id}_procedure_53_1",),
        ).fetchone()
    finally:
        connection.close()

    assert stored is not None
    assert stored["unit_type"] == "process_unit"
    assert stored["canonical_title"] == "SWE.2 基本实践"
    assert stored["canonical_key"] == "SWE.2"
    assert stored["content_role"] == "process_practice"
    assert "process_code_extracted" in stored["quality_flags_json"]


@pytest.mark.unit
def test_coverage_source_unit_inventory_filters_layout_boilerplate(tmp_path: Path) -> None:
    temp_path, workspace = _make_runtime(tmp_path)
    doc_id = "DOC-TEST-0001"
    _seed_minimal_coverage_chain(workspace, doc_id)

    units_path = workspace / "normalized" / f"{doc_id}.knowledge_units.json"
    payload = json.loads(units_path.read_text(encoding="utf-8"))
    payload["units"].append(
        {
            "id": f"{doc_id}_definition_2_1",
            "type": "definition",
            "title": "VDA QMC AUTOMOTIVE SPICE®",
            "content": "PUBLIC 是用于标识公开发布版本的页眉文本。",
            "section": None,
            "page": 2,
        }
    )
    payload["units"].append(
        {
            "id": f"{doc_id}_requirement_2_2",
            "type": "requirement",
            "title": "PUBLIC",
            "content": "PUBLIC 页眉应显示在发布版本页面上。",
            "section": None,
            "page": 2,
            "subject": "PUBLIC",
            "topic": "PUBLIC",
            "scope_type": "layout",
        }
    )
    payload["units"].append(
        {
            "id": f"{doc_id}_table_2_3",
            "type": "table_requirement",
            "title": "噪声表",
            "content": "",
            "section": None,
            "page": 2,
            "table_title": "噪声表",
            "headers": ["时刻", "参数", "符号", "单位"],
            "rows": [["T1", "时刻", "T", "s"]],
        }
    )
    units_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    result = build_coverage_for_document(workspace, doc_id, tests_generated_dir=temp_path / "tests" / "generated")
    matrix = json.loads(result.matrix_path.read_text(encoding="utf-8"))

    assert not any(item["unit_id"] == f"{doc_id}_definition_2_1" for item in matrix["items"])
    assert not any(item["unit_id"] == f"{doc_id}_requirement_2_2" for item in matrix["items"])
    assert not any(item["unit_id"] == f"{doc_id}_table_2_3:row:1" for item in matrix["items"])
    connection = connect(workspace / "db" / "knowledge.db")
    try:
        stored_count = connection.execute(
            "SELECT COUNT(*) FROM source_units WHERE unit_id = ?",
            (f"{doc_id}_definition_2_1",),
        ).fetchone()[0]
    finally:
        connection.close()
    assert stored_count == 0


@pytest.mark.unit
def test_build_all_docs_uncovered_priority_report(tmp_path: Path) -> None:
    temp_path, workspace = _make_runtime(tmp_path)
    doc_id = "DOC-TEST-0001"
    _seed_minimal_coverage_chain(workspace, doc_id)
    generated_dir = temp_path / "tests" / "generated"
    _write_generated_cases(generated_dir, doc_id)
    build_coverage_for_document(workspace, doc_id, tests_generated_dir=generated_dir)

    result = build_all_docs_uncovered_priority_report(workspace, output_dir=temp_path / "reports")

    assert result.document_count == 1
    assert result.issue_count >= 1
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["documents"][0]["doc_id"] == doc_id
    assert payload["root_cause_counts"]["golden_gap"] >= 1
    report = result.report_path.read_text(encoding="utf-8")
    assert "Suggested Fix Order" in report


@pytest.mark.unit
def test_uncovered_priority_report_classifies_rejected_test_gaps(tmp_path: Path) -> None:
    temp_path, workspace = _make_runtime(tmp_path)
    doc_id = "DOC-TEST-0001"
    _seed_minimal_coverage_chain(workspace, doc_id)
    generated_dir = temp_path / "tests" / "generated"
    _write_generated_cases(generated_dir, doc_id)
    build_coverage_for_document(workspace, doc_id, tests_generated_dir=generated_dir)
    matrix_path = workspace / "coverage_reports" / f"{doc_id}.coverage_matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    rejected_unit_id = next(
        item["unit_id"]
        for item in matrix["items"]
        if item.get("coverage_status") == "u3_not_tested"
    )
    (workspace / "coverage_reports" / "coverage_test_gap_rejections.json").write_text(
        json.dumps({"documents": {doc_id: {rejected_unit_id: {"quality_flags": ["weak_anchor"]}}}}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = build_all_docs_uncovered_priority_report(workspace, output_dir=temp_path / "reports")
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))

    issue = next(item for item in payload["top_issues"] if item["unit_id"] == rejected_unit_id)
    assert issue["root_cause"] == "test_gap_rejected"
    assert payload["root_cause_counts"]["test_gap_rejected"] >= 1


@pytest.mark.unit
def test_uncovered_priority_report_classifies_low_value_parameter_rows_as_noise(tmp_path: Path) -> None:
    temp_path, workspace = _make_runtime(tmp_path)
    doc_id = "DOC-TEST-0001"
    _seed_minimal_coverage_chain(workspace, doc_id)
    generated_dir = temp_path / "tests" / "generated"
    _write_generated_cases(generated_dir, doc_id)
    build_coverage_for_document(workspace, doc_id, tests_generated_dir=generated_dir)
    matrix_path = workspace / "coverage_reports" / f"{doc_id}.coverage_matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    matrix["items"].append(
        {
            "unit_id": f"{doc_id}:parameter-row:1:NOISE",
            "unit_type": "parameter_row_unit",
            "importance": "high",
            "page_no": 1,
            "semantic_key": "DP3",
            "source_text": "DP3",
            "coverage_status": "u3_not_tested",
            "semantic_misaligned": False,
            "covered_by": {
                "evidence_ids": ["EV-000001"],
                "fact_ids": ["FACT-000001"],
                "entity_ids": ["ENT-000001"],
                "wiki_page_ids": [],
                "golden_case_ids": [],
                "regression_case_ids": [],
            },
        }
    )
    matrix_path.write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")

    result = build_all_docs_uncovered_priority_report(
        workspace,
        output_dir=temp_path / "reports",
        rebuild_missing_coverage=False,
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    issue = next(item for item in payload["top_issues"] if item["unit_id"] == f"{doc_id}:parameter-row:1:NOISE")
    assert issue["root_cause"] == "source_unit_noise"


@pytest.mark.unit
def test_generate_coverage_test_drafts_from_test_gaps(tmp_path: Path) -> None:
    temp_path, workspace = _make_runtime(tmp_path)
    doc_id = "DOC-TEST-0001"
    _seed_minimal_coverage_chain(workspace, doc_id)
    generated_dir = temp_path / "tests" / "generated"
    _write_generated_cases(generated_dir, doc_id)
    build_coverage_for_document(workspace, doc_id, tests_generated_dir=generated_dir)

    result = generate_coverage_test_drafts_for_document(workspace, doc_id, limit=2)

    assert result["draft_case_count"] <= 2
    assert result["json_path"].endswith(".coverage_test_drafts.json")
    assert result["report_path"].endswith(".coverage_test_drafts.md")
    draft_payload = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert draft_payload["cases"]
    first_case = draft_payload["cases"][0]
    assert first_case["status"] == "draft"
    assert first_case["golden_case"]["source"] == "coverage"
    assert first_case["golden_case"]["query"]
    assert first_case["golden_case"]["expected_evidence_shape"]
    connection = connect(workspace / "db" / "knowledge.db")
    try:
        source_unit_count = connection.execute(
            "SELECT COUNT(*) FROM source_units WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()[0]
        assert source_unit_count >= 1
    finally:
        connection.close()


@pytest.mark.unit
def test_promote_coverage_test_drafts_into_golden_suite(tmp_path: Path) -> None:
    temp_path, workspace = _make_runtime(tmp_path)
    doc_id = "DOC-TEST-0001"
    _seed_minimal_coverage_chain(workspace, doc_id)
    generated_dir = temp_path / "tests" / "generated"
    _write_generated_cases(generated_dir, doc_id)
    build_coverage_for_document(workspace, doc_id, tests_generated_dir=generated_dir)
    generate_coverage_test_drafts_for_document(workspace, doc_id, limit=2)

    result = promote_coverage_test_drafts_for_document(workspace, doc_id, require_validated=False)

    assert result["promoted_case_count"] >= 1
    assert result["added_case_count"] >= 1
    golden_payload = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert any(case.get("source") == "coverage" for case in golden_payload["cases"])
    assert Path(result["pytest_path"]).exists()
    connection = connect(workspace / "db" / "knowledge.db")
    try:
        golden_case_count = connection.execute(
            "SELECT COUNT(*) FROM golden_cases WHERE doc_id = ? AND status = 'active'",
            (doc_id,),
        ).fetchone()[0]
        shaped_golden_case_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM golden_cases
            WHERE doc_id = ?
              AND status = 'active'
              AND expected_evidence_shape IS NOT NULL
              AND expected_evidence_shape <> ''
            """,
            (doc_id,),
        ).fetchone()[0]
        assert golden_case_count == len(golden_payload["cases"])
        assert shaped_golden_case_count >= 1
    finally:
        connection.close()
    generated_pytest = Path(result["pytest_path"]).read_text(encoding="utf-8")
    assert "@pytest.mark.coverage" in generated_pytest

    run_result = run_coverage_promoted_tests_for_document(workspace, doc_id)
    assert run_result["case_count"] >= 1
    assert run_result["validation_mode"] == "trace"
    assert run_result["success"] is True


@pytest.mark.unit
def test_close_coverage_test_gaps_runs_full_golden_gap_loop(tmp_path: Path) -> None:
    temp_path, workspace = _make_runtime(tmp_path)
    doc_id = "DOC-TEST-0001"
    _seed_minimal_coverage_chain(workspace, doc_id)
    generated_dir = temp_path / "tests" / "generated"
    _write_generated_cases(generated_dir, doc_id)
    build_coverage_for_document(workspace, doc_id, tests_generated_dir=generated_dir)

    result = close_coverage_test_gaps(
        workspace,
        doc_ids=[doc_id],
        limit_per_doc=2,
        validation_mode="trace",
        promote=True,
    )

    assert result["document_count"] == 1
    assert result["totals"]["draft_case_count"] >= 1
    assert result["totals"]["validation_passed_count"] >= 1
    assert result["totals"]["promoted_case_count"] >= 1
    assert "pruned_obsolete_case_count" in result["documents"][0]
    assert result["totals"]["coverage_test_failed"] == 0
    assert Path(str(result["json_path"])).exists()
    assert Path(str(result["uncovered_priority_report"]["json_path"])).exists()

    golden_payload = json.loads((generated_dir / f"{doc_id}.golden.json").read_text(encoding="utf-8"))
    assert any(case.get("source") == "coverage" for case in golden_payload["cases"])


@pytest.mark.unit
def test_assess_coverage_test_draft_readiness_flags_noise(tmp_path: Path) -> None:
    temp_path, workspace = _make_runtime(tmp_path)
    doc_id = "DOC-TEST-0001"
    tests_dir = temp_path / "tests" / "generated"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / f"{doc_id}.coverage_test_drafts.json").write_text(
        json.dumps(
            {
                "doc_id": doc_id,
                "validated": False,
                "cases": [
                    {
                        "name": "good_definition",
                        "unit_type": "definition_unit",
                        "page_no": 1,
                        "semantic_key": "控制导引电路",
                        "query": "什么是控制导引电路？",
                        "must_include": ["控制导引电路"],
                        "validation_status": "not_validated",
                        "golden_case": {
                            "kind": "coverage_definition",
                            "query": "什么是控制导引电路？",
                            "must_include": "控制导引电路",
                            "source": "coverage",
                            "assert_mode": "rich_answer",
                        },
                    },
                    {
                        "name": "bad_boilerplate",
                        "unit_type": "definition_unit",
                        "page_no": 2,
                        "semantic_key": "VDA QMC [SPACE] AUTOMOTIVE SPICE®",
                        "query": "什么是VDA QMC [SPACE] AUTOMOTIVE SPICE®？",
                        "must_include": ["VDA QMC"],
                        "validation_status": "not_validated",
                        "golden_case": {
                            "kind": "coverage_definition",
                            "query": "什么是VDA QMC [SPACE] AUTOMOTIVE SPICE®？",
                            "must_include": "VDA QMC",
                            "source": "coverage",
                            "assert_mode": "rich_answer",
                        },
                    },
                    {
                        "name": "clause_heading",
                        "unit_type": "requirement_unit",
                        "page_no": 3,
                        "semantic_key": "C.4.6 供电模式（可选功能）",
                        "query": "C.4.6 供电模式（可选功能）有哪些要求？",
                        "must_include": ["C.4.6 供电模式（可选功能）"],
                        "validation_status": "not_validated",
                        "golden_case": {
                            "kind": "coverage_requirement",
                            "query": "C.4.6 供电模式（可选功能）有哪些要求？",
                            "must_include": "C.4.6 供电模式（可选功能）",
                            "source": "coverage",
                            "assert_mode": "rich_answer",
                        },
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    result = assess_coverage_test_draft_readiness_for_document(workspace, doc_id)

    statuses = {case["name"]: case["readiness_status"] for case in result["cases"]}
    assert statuses["good_definition"] == "ready_for_validation"
    assert statuses["bad_boilerplate"] == "reject"
    assert statuses["clause_heading"] == "ready_for_validation"
    assert result["status_counts"]["ready_for_validation"] == 2
    assert result["status_counts"]["reject"] == 1


@pytest.mark.unit
def test_assess_all_coverage_test_draft_readiness(tmp_path: Path) -> None:
    temp_path, workspace = _make_runtime(tmp_path)
    doc_id = "DOC-TEST-0001"
    _seed_minimal_coverage_chain(workspace, doc_id)
    generated_dir = temp_path / "tests" / "generated"
    _write_generated_cases(generated_dir, doc_id)
    build_coverage_for_document(workspace, doc_id, tests_generated_dir=generated_dir)
    generate_coverage_test_drafts_for_document(workspace, doc_id, limit=2)

    result = assess_all_coverage_test_draft_readiness(workspace)

    assert result["document_count"] == 1
    assert result["assessed_document_count"] == 1
    assert Path(result["json_path"]).exists()
    assert Path(result["report_path"]).exists()


@pytest.mark.unit
def test_golden_summary_keeps_coverage_and_answer_quality_together(tmp_path: Path) -> None:
    golden_path = tmp_path / "DOC-TEST.golden.json"
    golden_path.write_text(
        json.dumps(
            {
                "cases": [
                    {"query": "第1页 原文片段", "must_include": "原文片段", "assert_mode": "context_contains"},
                    {"query": "什么是CC？", "must_include": "连接确认功能", "assert_mode": "rich_answer"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    summary = _build_golden_case_summary(golden_path, passed=2, failed=0)

    assert summary["case_mix"] == {"context_contains": 1, "rich_answer": 1}
    assert summary["coverage_recall"]["total"] == 1
    assert summary["answer_quality"]["total"] == 1
    assert summary["coverage_recall"]["label"] == "覆盖召回"
    assert summary["answer_quality"]["label"] == "答案质量"


@pytest.mark.unit
def test_cli_parser_contains_build_coverage_command() -> None:
    parser = build_parser()
    commands = parser._subparsers._group_actions[0].choices.keys()
    assert "build-coverage" in commands
    assert "build-test-gaps" in commands
    assert "generate-coverage-test-drafts" in commands
    assert "close-coverage-test-gaps" in commands
    assert "validate-coverage-test-drafts" in commands
    assert "assess-coverage-test-draft-readiness" in commands
    assert "promote-coverage-test-drafts" in commands
    assert "run-coverage-promoted-tests" in commands
    assert "uncovered-priority-report" in commands
