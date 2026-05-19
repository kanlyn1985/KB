from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.config import AppPaths
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.workspace_admin import reset_workspace_data


def test_reset_workspace_data_clears_rows_and_generated_files(tmp_path: Path) -> None:
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
                "abc",
                1,
                None,
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
        connection.commit()
    finally:
        connection.close()

    generated = paths.normalized / "x.json"
    generated.write_text("{}", encoding="utf-8")
    raw_file = paths.raw / "sample.pdf"
    raw_file.write_text("raw", encoding="utf-8")

    result = reset_workspace_data(paths.root, keep_raw=True)

    assert result.deleted_rows["documents"] == 1
    assert result.deleted_files["normalized"] == 1
    assert raw_file.exists()

