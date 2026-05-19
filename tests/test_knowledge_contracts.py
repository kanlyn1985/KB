from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.ingestion_acceptance import validate_document_ingestion
from enterprise_agent_kb.knowledge_contracts import document_knowledge_contract_summary


SCHEMA_PATH = Path("src/enterprise_agent_kb/schema.sql")


def test_document_knowledge_contract_fails_when_source_unit_has_no_fact_shape(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    _seed_document_shell(paths.db_file, "DOC-CONTRACT")
    connection = connect(paths.db_file)
    try:
        _insert_source_unit(connection, "DOC-CONTRACT", "SU-DEF", "definition_unit", "definition")
        _insert_evidence(connection, "DOC-CONTRACT", "EV-DEF")
        connection.execute(
            """
            INSERT INTO source_unit_evidence_map(unit_id, evidence_id, doc_id, support_type, created_at)
            VALUES ('SU-DEF', 'EV-DEF', 'DOC-CONTRACT', 'coverage_matrix', 'now')
            """
        )
        connection.commit()
    finally:
        connection.close()

    summary = document_knowledge_contract_summary(paths.db_file, "DOC-CONTRACT")

    definition = _contract(summary, "definition")
    assert summary["status"] == "failed"
    assert definition["status"] == "failed"
    assert "source_units_without_contract_fact_shape" in definition["issues"]
    assert "source_units_without_fact_links" in definition["issues"]


def test_document_knowledge_contract_tracks_shape_from_source_unit_to_fact_and_golden(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    _seed_document_shell(paths.db_file, "DOC-CONTRACT")
    connection = connect(paths.db_file)
    try:
        _insert_source_unit(connection, "DOC-CONTRACT", "SU-DEF", "definition_unit", "definition")
        _insert_evidence(connection, "DOC-CONTRACT", "EV-DEF")
        _insert_fact(connection, "DOC-CONTRACT", "FACT-DEF", "term_definition")
        connection.execute(
            """
            INSERT INTO source_unit_evidence_map(unit_id, evidence_id, doc_id, support_type, created_at)
            VALUES ('SU-DEF', 'EV-DEF', 'DOC-CONTRACT', 'coverage_matrix', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO source_unit_fact_map(unit_id, fact_id, doc_id, support_type, created_at)
            VALUES ('SU-DEF', 'FACT-DEF', 'DOC-CONTRACT', 'coverage_matrix', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO golden_cases (
                case_id, doc_id, assert_mode, query, must_hit_json, negative_expected_json,
                expected_pages_json, expected_sections_json, expected_evidence_shape,
                status, source, metadata_json, created_at, updated_at
            )
            VALUES (
                'CASE-DEF', 'DOC-CONTRACT', 'context_contains', '术语是什么意思',
                '["术语"]', '[]', '[]', '[]', 'term_definition',
                'active', 'unit', '{}', 'now', 'now'
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    summary = document_knowledge_contract_summary(paths.db_file, "DOC-CONTRACT")

    definition = _contract(summary, "definition")
    assert definition["status"] == "passed"
    assert definition["source_unit_count"] == 1
    assert definition["fact_count"] == 1
    assert definition["linked_fact_unit_count"] == 1
    assert definition["linked_evidence_unit_count"] == 1
    assert definition["golden_case_count"] == 1
    assert "term_definition" in summary["active_evidence_shapes"]


def test_document_knowledge_contract_counts_corpus_eval_golden_by_expected_doc_id(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    _seed_document_shell(paths.db_file, "DOC-CONTRACT")
    connection = connect(paths.db_file)
    try:
        _insert_source_unit(connection, "DOC-CONTRACT", "SU-REQ", "requirement_unit", "requirement")
        _insert_evidence(connection, "DOC-CONTRACT", "EV-REQ")
        _insert_fact(connection, "DOC-CONTRACT", "FACT-REQ", "table_requirement")
        connection.execute(
            """
            INSERT INTO source_unit_evidence_map(unit_id, evidence_id, doc_id, support_type, created_at)
            VALUES ('SU-REQ', 'EV-REQ', 'DOC-CONTRACT', 'coverage_matrix', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO source_unit_fact_map(unit_id, fact_id, doc_id, support_type, created_at)
            VALUES ('SU-REQ', 'FACT-REQ', 'DOC-CONTRACT', 'coverage_matrix', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO golden_cases (
                case_id, doc_id, assert_mode, query, must_hit_json, negative_expected_json,
                expected_pages_json, expected_sections_json, expected_evidence_shape,
                status, source, metadata_json, created_at, updated_at
            )
            VALUES (
                'CASE-REQ', 'CORPUS-RETRIEVAL', 'context_contains', '有哪些要求',
                '["要求"]', '[]', '[]', '[]', 'requirement',
                'active', 'corpus_eval', '{"expected_doc_id":"DOC-CONTRACT"}', 'now', 'now'
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    summary = document_knowledge_contract_summary(paths.db_file, "DOC-CONTRACT")

    requirement = _contract(summary, "requirement")
    assert requirement["golden_case_count"] == 1
    assert "no_active_golden_case_for_shape" not in requirement["issues"]


def test_ingestion_acceptance_reports_document_knowledge_contract(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    _seed_document_shell(paths.db_file, "DOC-CONTRACT")
    _write_coverage_summary(paths.root, "DOC-CONTRACT")
    connection = connect(paths.db_file)
    try:
        connection.execute(
            """
            INSERT INTO blocks(
                block_id, page_id, doc_id, block_type, reading_order, text_content,
                raw_text, bbox_json, parser_confidence, ocr_confidence,
                risk_flags_json, created_at, updated_at
            )
            VALUES ('BLK-1', 'PAGE-1', 'DOC-CONTRACT', 'paragraph', 1, '术语定义',
                    '术语定义', '{}', 1.0, NULL, '[]', 'now', 'now')
            """
        )
        _insert_source_unit(connection, "DOC-CONTRACT", "SU-DEF", "definition_unit", "definition")
        _insert_evidence(connection, "DOC-CONTRACT", "EV-DEF")
        _insert_fact(connection, "DOC-CONTRACT", "FACT-DEF", "term_definition")
        connection.execute(
            """
            INSERT INTO source_unit_evidence_map(unit_id, evidence_id, doc_id, support_type, created_at)
            VALUES ('SU-DEF', 'EV-DEF', 'DOC-CONTRACT', 'coverage_matrix', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO source_unit_fact_map(unit_id, fact_id, doc_id, support_type, created_at)
            VALUES ('SU-DEF', 'FACT-DEF', 'DOC-CONTRACT', 'coverage_matrix', 'now')
            """
        )
        connection.commit()
    finally:
        connection.close()

    result = validate_document_ingestion(paths.root, "DOC-CONTRACT", output_dir=tmp_path / "out")
    contract_check = next(item for item in result.checks if item["name"] == "document_knowledge_contract")

    assert contract_check["status"] in {"passed", "warn"}
    assert contract_check["actual"]["active_contract_count"] >= 1
    assert "term_definition" in contract_check["actual"]["active_evidence_shapes"]


def _seed_document_shell(db_file: Path, doc_id: str) -> None:
    connection = connect(db_file)
    try:
        connection.execute(
            """
            INSERT INTO documents(
                doc_id, source_filename, source_type, mime_type, sha256, file_size,
                page_count, language, version_label, source_path, ingest_time,
                update_time, parse_status, quality_status, is_active
            )
            VALUES (?, 'contract.md', 'markdown', 'text/markdown', 'sha', 10,
                    1, 'zh', NULL, 'contract.md', 'now', 'now', 'parsed', 'ready', 1)
            """,
            (doc_id,),
        )
        connection.execute(
            """
            INSERT INTO pages(
                page_id, doc_id, page_no, width, height, parser_confidence,
                ocr_confidence, risk_level, page_status, screenshot_path,
                created_at, updated_at
            )
            VALUES ('PAGE-1', ?, 1, NULL, NULL, 1.0, NULL, 'low', 'ready', NULL, 'now', 'now')
            """,
            (doc_id,),
        )
        connection.commit()
    finally:
        connection.close()


def _insert_source_unit(connection, doc_id: str, unit_id: str, unit_type: str, role: str) -> None:
    connection.execute(
        """
        INSERT INTO source_units (
            unit_id, doc_id, page_no, block_id, unit_type, text, normalized_text,
            canonical_title, canonical_key, content_role, quality_flags_json,
            importance, expected_knowledge_type, status, metadata_json, created_at, updated_at
        )
        VALUES (?, ?, 1, 'BLK-1', ?, '术语: 定义正文', '术语定义正文',
                '术语', '术语', ?, '[]', 'high', 'term_definition', 'covered', '{}', 'now', 'now')
        """,
        (unit_id, doc_id, unit_type, role),
    )


def _insert_evidence(connection, doc_id: str, evidence_id: str) -> None:
    connection.execute(
        """
        INSERT INTO evidence(
            evidence_id, doc_id, page_id, block_id, block_type, raw_text,
            normalized_text, image_ref, table_ref, page_no, confidence,
            risk_level, evidence_status, created_at, updated_at
        )
        VALUES (?, ?, 'PAGE-1', 'BLK-1', 'paragraph', '术语: 定义正文',
                '术语: 定义正文', NULL, NULL, 1, 1.0, 'low', 'ready', 'now', 'now')
        """,
        (evidence_id, doc_id),
    )


def _insert_fact(connection, doc_id: str, fact_id: str, fact_type: str) -> None:
    connection.execute(
        """
        INSERT INTO facts(
            fact_id, fact_type, subject_entity_id, predicate, object_value, object_entity_id,
            qualifiers_json, confidence, fact_status, source_doc_id, created_at, updated_at
        )
        VALUES (?, ?, NULL, 'defines_term', '{"term":"术语","definition":"定义正文"}', NULL, '{"page_no":1}', 1.0, 'active', ?, 'now', 'now')
        """,
        (fact_id, fact_type, doc_id),
    )


def _write_coverage_summary(root: Path, doc_id: str) -> None:
    reports = root / "coverage_reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{doc_id}.summary.json").write_text(
        """
        {
          "source_unit_count": 1,
          "text_coverage_rate": 1.0,
          "semantic_coverage_rate": 1.0,
          "object_coverage_rate": 1.0,
          "knowledge_page_coverage_rate": 1.0,
          "test_coverage_rate": 1.0,
          "uncovered_counts": {}
        }
        """,
        encoding="utf-8",
    )
    (reports / f"{doc_id}.coverage_report.md").write_text("# coverage\n", encoding="utf-8")


def _contract(summary: dict[str, object], knowledge_type: str) -> dict[str, object]:
    for item in summary.get("contracts") or []:
        if isinstance(item, dict) and item.get("knowledge_type") == knowledge_type:
            return item
    raise AssertionError(f"missing contract: {knowledge_type}")
