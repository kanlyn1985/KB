from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.derived_state import (
    check_derived_state,
    derived_state_specs,
    get_derived_state_spec,
    write_fts_freshness_stamp,
)
from enterprise_agent_kb.retrieval import ensure_fts_schema


SCHEMA_PATH = Path("src/enterprise_agent_kb/schema.sql")


def test_registry_exposes_stable_fts_specs() -> None:
    specs = {spec.state_id: spec for spec in derived_state_specs()}

    assert set(specs) >= {"facts_fts", "evidence_fts", "wiki_fts"}
    assert specs["facts_fts"].source_tables == ("facts",)
    assert specs["facts_fts"].artifact_tables == ("facts_fts",)
    assert specs["facts_fts"].rebuild_command == "rebuild-derived-state --scope fts"
    assert get_derived_state_spec("facts_fts") == specs["facts_fts"]


def test_missing_artifact_is_reported_without_creating_fts_tables(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        assert not _table_exists(connection, "facts_fts")

        checks = check_derived_state(paths.root, state_id="facts_fts", connection=connection)

        assert checks[0].status == "missing"
        assert checks[0].severity == "fail"
        assert checks[0].source_count == 0
        assert checks[0].artifact_count is None
        assert checks[0].recommended_actions == ("rebuild-derived-state --scope fts",)
        assert not _table_exists(connection, "facts_fts")
    finally:
        connection.close()


def test_stale_fts_reports_missing_and_orphan_rows(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_fact(connection, "FACT-NEW")
        ensure_fts_schema(connection)
        connection.execute(
            """
            INSERT INTO facts_fts(result_id, doc_id, page_no, searchable_text)
            VALUES ('FACT-OLD', 'DOC-1', 1, 'old fact')
            """
        )
        connection.commit()
        _write_stamp(paths.logs / "fts_index.stamp")

        check = check_derived_state(paths.root, state_id="facts_fts", connection=connection)[0]

        assert check.status == "stale"
        assert check.severity == "warn"
        assert check.source_count == 1
        assert check.artifact_count == 1
        assert check.missing_count == 1
        assert check.orphan_count == 1
        assert "missing indexed rows: 1" in check.message
        assert "orphan indexed rows: 1" in check.message
    finally:
        connection.close()


def test_stale_fts_reports_source_signature_mismatch(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)

    connection = connect(paths.db_file)
    try:
        _insert_fact(connection, "FACT-1")
        ensure_fts_schema(connection)
        connection.execute(
            """
            INSERT INTO facts_fts(result_id, doc_id, page_no, searchable_text)
            VALUES ('FACT-1', 'DOC-1', 1, 'current fact')
            """
        )
        connection.commit()
        write_fts_freshness_stamp(paths, connection)
        _insert_fact(connection, "FACT-2")

        check = check_derived_state(paths.root, state_id="facts_fts", connection=connection)[0]

        assert check.status == "stale"
        assert check.severity == "warn"
        assert "source signature differs from stamp" in check.message
    finally:
        connection.close()


def test_unrelated_run_writes_do_not_mark_fts_stale(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_fact(connection, "FACT-1")
        ensure_fts_schema(connection)
        connection.execute(
            """
            INSERT INTO facts_fts(result_id, doc_id, page_no, searchable_text)
            VALUES ('FACT-1', 'DOC-1', 1, 'current fact')
            """
        )
        connection.commit()
        write_fts_freshness_stamp(paths, connection)
        connection.execute(
            """
            INSERT INTO retrieval_runs(
                run_id, query, query_type, doc_scope, retrieved_evidence_ids_json,
                reranked_ids_json, scores_json, code_version, metadata_json, created_at
            )
            VALUES (
                'RET-UNRELATED', 'query', 'definition', 'global', '[]',
                '[]', '{}', 'test-code', '{}', 'now'
            )
            """
        )
        connection.commit()

        check = check_derived_state(paths.root, state_id="facts_fts", connection=connection)[0]

        assert check.status == "fresh"
        assert check.severity == "ok"
    finally:
        connection.close()


def test_fresh_fts_reports_ok(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_fact(connection, "FACT-1")
        ensure_fts_schema(connection)
        connection.execute(
            """
            INSERT INTO facts_fts(result_id, doc_id, page_no, searchable_text)
            VALUES ('FACT-1', 'DOC-1', 1, 'current fact')
            """
        )
        connection.commit()
        write_fts_freshness_stamp(paths, connection)

        check = check_derived_state(paths.root, state_id="facts_fts", connection=connection)[0]

        assert check.status == "fresh"
        assert check.severity == "ok"
        assert check.source_count == 1
        assert check.artifact_count == 1
        assert check.missing_count == 0
        assert check.orphan_count == 0
        assert check.recommended_actions == ()
    finally:
        connection.close()


def _insert_fact(connection, fact_id: str) -> None:
    connection.execute(
        """
        INSERT INTO facts(
            fact_id, fact_type, subject_entity_id, predicate, object_value,
            object_entity_id, qualifiers_json, confidence, fact_status,
            source_doc_id, created_at, updated_at
        )
        VALUES (?, 'definition', NULL, 'defines', 'current fact', NULL, '{}', 1.0, 'active', 'DOC-1', 'now', 'now')
        """,
        (fact_id,),
    )
    connection.commit()


def _write_stamp(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ok", encoding="utf-8")


def _table_exists(connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view') AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None
