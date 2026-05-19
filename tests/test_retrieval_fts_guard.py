from __future__ import annotations

import os
from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.retrieval import (
    ensure_fts_schema,
    refresh_fts_index,
    search_knowledge_base,
    search_knowledge_base_expanded,
)


SCHEMA_PATH = Path("src/enterprise_agent_kb/schema.sql")


def test_shared_connection_search_refreshes_stale_fts(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_fact(connection, "FACT-NEW", "传导充电 conductive charge")
        ensure_fts_schema(connection)
        connection.execute(
            """
            INSERT INTO facts_fts(result_id, doc_id, page_no, searchable_text)
            VALUES ('FACT-OLD', 'DOC-1', 1, 'old stale row')
            """
        )
        connection.commit()
        _write_old_stamp(paths.logs / "fts_index.stamp", paths.db_file)

        hits = search_knowledge_base_expanded(
            paths.root,
            "传导充电",
            limit=5,
            connection=connection,
            result_types={"fact"},
        )

        assert hits[0]["result_id"] == "FACT-NEW"
        assert _facts_fts_ids(connection) == ["FACT-NEW"]
    finally:
        connection.close()


def test_own_connection_search_still_refreshes_missing_fts(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_fact(connection, "FACT-1", "OBC 输入过压保护")
    finally:
        connection.close()

    hits = search_knowledge_base(paths.root, "输入过压", limit=5)

    assert any(hit["result_id"] == "FACT-1" for hit in hits)
    connection = connect(paths.db_file)
    try:
        assert _facts_fts_ids(connection) == ["FACT-1"]
    finally:
        connection.close()


def test_refresh_fts_index_keeps_count_contract(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_evidence(connection, "EVID-1", "传导充电定义")
        _insert_fact(connection, "FACT-1", "传导充电 conductive charge")
        _insert_wiki_page(connection, "WPAGE-1", "传导充电")
    finally:
        connection.close()

    counts = refresh_fts_index(paths.root)

    assert counts == {"evidence": 1, "facts": 1, "wiki": 1}


def _insert_fact(connection, fact_id: str, object_value: str) -> None:
    connection.execute(
        """
        INSERT INTO facts(
            fact_id, fact_type, subject_entity_id, predicate, object_value,
            object_entity_id, qualifiers_json, confidence, fact_status,
            source_doc_id, created_at, updated_at
        )
        VALUES (?, 'term_definition', NULL, 'defines', ?, NULL, '{"page_no": 1}', 1.0, 'active', 'DOC-1', 'now', 'now')
        """,
        (fact_id, object_value),
    )
    connection.commit()


def _insert_evidence(connection, evidence_id: str, normalized_text: str) -> None:
    connection.execute(
        """
        INSERT INTO evidence(
            evidence_id, doc_id, page_id, block_id, block_type, raw_text,
            normalized_text, image_ref, table_ref, page_no, confidence,
            risk_level, evidence_status, created_at, updated_at
        )
        VALUES (?, 'DOC-1', 'PAGE-1', 'BLOCK-1', 'paragraph', ?, ?, NULL, NULL, 1, 1.0, 'low', 'ready', 'now', 'now')
        """,
        (evidence_id, normalized_text, normalized_text),
    )
    connection.commit()


def _insert_wiki_page(connection, page_id: str, title: str) -> None:
    connection.execute(
        """
        INSERT INTO wiki_pages(
            page_id, page_type, title, slug, entity_id, source_fact_ids_json,
            source_doc_ids_json, trust_status, file_path, updated_at
        )
        VALUES (?, 'term', ?, ?, NULL, '[]', '["DOC-1"]', 'ready', 'wiki.md', 'now')
        """,
        (page_id, title, title),
    )
    connection.commit()


def _facts_fts_ids(connection) -> list[str]:
    rows = connection.execute("SELECT result_id FROM facts_fts ORDER BY result_id").fetchall()
    return [str(row["result_id"]) for row in rows]


def _write_old_stamp(stamp_path: Path, db_path: Path) -> None:
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text("ok", encoding="utf-8")
    old_time = db_path.stat().st_mtime - 10
    os.utime(stamp_path, (old_time, old_time))
