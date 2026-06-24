from __future__ import annotations

import json
from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.evidence import build_evidence_for_document


def test_build_evidence_skips_structure_markdown_blocks(tmp_path: Path) -> None:
    schema_path = Path("src/enterprise_agent_kb/schema.sql")
    paths = initialize_workspace(tmp_path / "kb", schema_path)
    connection = connect(paths.db_file)
    try:
        connection.execute(
            """
            INSERT INTO documents (
                doc_id, source_filename, source_type, mime_type, sha256, file_size,
                page_count, language, version_label, source_path, ingest_time,
                update_time, parse_status, quality_status, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "DOC-TEST",
                "a.pdf",
                "pdf",
                "application/pdf",
                "sha",
                1,
                1,
                None,
                None,
                str(paths.raw / "a.pdf"),
                "2026-04-20T00:00:00+00:00",
                "2026-04-20T00:00:00+00:00",
                "parsed",
                "passed",
                1,
            ),
        )
        connection.execute(
            """
            INSERT INTO pages (
                page_id, doc_id, page_no, width, height, parser_confidence,
                ocr_confidence, risk_level, page_status, screenshot_path,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "PAGE-1",
                "DOC-TEST",
                1,
                None,
                None,
                0.9,
                0.9,
                "low",
                "ready",
                None,
                "2026-04-20T00:00:00+00:00",
                "2026-04-20T00:00:00+00:00",
            ),
        )
        # Use realistic-length content: the noise filter (_is_noise_block)
        # skips blocks shorter than 30 chars with < 5 CJK chars, so the
        # content block must carry real clause text to be kept.
        rows = [
            (
                "BLK-1",
                "ocr_markdown",
                "# 范围\n本标准规定了车载诊断系统的通用要求，适用于M1类车辆的OBD系统。",
                "# 范围\n本标准规定了车载诊断系统的通用要求，适用于M1类车辆的OBD系统。",
            ),
            (
                "BLK-2",
                "structure_markdown",
                "## 结构提示",
                "## 结构提示",
            ),
        ]
        for block_id, block_type, text_content, raw_text in rows:
            connection.execute(
                """
                INSERT INTO blocks (
                    block_id, page_id, doc_id, block_type, reading_order,
                    text_content, raw_text, bbox_json, parser_confidence,
                    ocr_confidence, risk_flags_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    block_id,
                    "PAGE-1",
                    "DOC-TEST",
                    block_type,
                    1,
                    text_content,
                    raw_text,
                    None,
                    0.9,
                    0.9,
                    "[]",
                    "2026-04-20T00:00:00+00:00",
                    "2026-04-20T00:00:00+00:00",
                ),
            )
        connection.commit()
    finally:
        connection.close()

    result = build_evidence_for_document(paths.root, "DOC-TEST")
    payload = json.loads(result.export_path.read_text(encoding="utf-8"))

    assert result.evidence_count == 1
    assert result.skipped_block_count == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["block_type"] == "ocr_markdown"


def test_build_evidence_keeps_review_required_text_blocks(tmp_path: Path) -> None:
    schema_path = Path("src/enterprise_agent_kb/schema.sql")
    paths = initialize_workspace(tmp_path / "kb", schema_path)
    connection = connect(paths.db_file)
    try:
        connection.execute(
            """
            INSERT INTO documents (
                doc_id, source_filename, source_type, mime_type, sha256, file_size,
                page_count, language, version_label, source_path, ingest_time,
                update_time, parse_status, quality_status, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "DOC-TEST",
                "a.pdf",
                "pdf",
                "application/pdf",
                "sha",
                1,
                1,
                None,
                None,
                str(paths.raw / "a.pdf"),
                "2026-04-20T00:00:00+00:00",
                "2026-04-20T00:00:00+00:00",
                "parsed",
                "review_required",
                1,
            ),
        )
        connection.execute(
            """
            INSERT INTO pages (
                page_id, doc_id, page_no, width, height, parser_confidence,
                ocr_confidence, risk_level, page_status, screenshot_path,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "PAGE-1",
                "DOC-TEST",
                1,
                None,
                None,
                0.82,
                0.82,
                "high",
                "review_required",
                None,
                "2026-04-20T00:00:00+00:00",
                "2026-04-20T00:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO blocks (
                block_id, page_id, doc_id, block_type, reading_order,
                text_content, raw_text, bbox_json, parser_confidence,
                ocr_confidence, risk_flags_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "BLK-1",
                "PAGE-1",
                "DOC-TEST",
                "ocr_markdown",
                1,
                "A.5.5 绝缘监测装置应满足规定要求。",
                "A.5.5 绝缘监测装置应满足规定要求。",
                None,
                0.82,
                0.82,
                '["low_readability"]',
                "2026-04-20T00:00:00+00:00",
                "2026-04-20T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    result = build_evidence_for_document(paths.root, "DOC-TEST")
    payload = json.loads(result.export_path.read_text(encoding="utf-8"))

    assert result.evidence_count == 1
    assert result.skipped_block_count == 0
    assert payload["items"][0]["risk_level"] == "high"
    assert payload["items"][0]["text"].startswith("A.5.5")
