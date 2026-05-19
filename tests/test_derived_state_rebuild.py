from __future__ import annotations

import json
import sys
from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.cli import build_parser, main
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.derived_state import check_derived_state
from enterprise_agent_kb.derived_state_rebuild import rebuild_derived_state
from enterprise_agent_kb.retrieval import ensure_fts_schema, search_knowledge_base_expanded


SCHEMA_PATH = Path("src/enterprise_agent_kb/schema.sql")


def test_rebuild_fts_dry_run_does_not_create_fts_tables_or_stamp(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)

    report = rebuild_derived_state(paths.root, scope="fts", dry_run=True)

    connection = connect(paths.db_file)
    try:
        assert report.status == "ok"
        assert report.items[0].status == "planned"
        assert not _table_exists(connection, "facts_fts")
        assert not (paths.logs / "fts_index.stamp").exists()
    finally:
        connection.close()


def test_rebuild_fts_refreshes_stale_index_and_after_checks_are_ok(tmp_path: Path) -> None:
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
    finally:
        connection.close()

    report = rebuild_derived_state(paths.root, scope="fts")

    assert report.status == "ok"
    assert report.items[0].status == "done"
    assert report.items[0].before["status"] in {"fail", "warn"}
    assert report.items[0].after["status"] == "ok"
    assert report.items[0].changed_counts["facts"] == 1
    checks = check_derived_state(paths.root)
    assert {check.status for check in checks} == {"fresh"}

    connection = connect(paths.db_file)
    try:
        assert _facts_fts_ids(connection) == ["FACT-NEW"]
    finally:
        connection.close()


def test_rebuild_graph_scope_dry_run_plans_orphans_without_changes(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_graph_edge(connection, "EDGE-ORPHAN", "ENT-MISSING-SRC", "ENT-MISSING-DST")
        connection.execute("INSERT INTO edge_evidence_map(edge_id, evidence_id) VALUES ('EDGE-ORPHAN', 'EVID-MISSING')")
        connection.execute("INSERT INTO edge_evidence_map(edge_id, evidence_id) VALUES ('EDGE-MISSING', 'EVID-MISSING')")
        connection.commit()
    finally:
        connection.close()

    report = rebuild_derived_state(paths.root, scope="graph", dry_run=True)

    assert report.status == "ok"
    assert report.items[0].status == "planned"
    assert report.items[0].action == "reconcile_orphans"
    assert report.items[0].changed_counts == {"graph_edges": 1, "edge_evidence_map": 2}
    connection = connect(paths.db_file)
    try:
        assert _table_count(connection, "graph_edges") == 1
        assert _table_count(connection, "edge_evidence_map") == 2
    finally:
        connection.close()


def test_rebuild_graph_scope_reconciles_orphans_and_preserves_primary_rows(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_entity(connection, "ENT-SRC")
        _insert_entity(connection, "ENT-DST")
        _insert_evidence(connection, "EVID-KEEP")
        _insert_graph_edge(connection, "EDGE-KEEP", "ENT-SRC", "ENT-DST")
        _insert_graph_edge(connection, "EDGE-ORPHAN", "ENT-MISSING-SRC", "ENT-MISSING-DST")
        connection.execute("INSERT INTO edge_evidence_map(edge_id, evidence_id) VALUES ('EDGE-KEEP', 'EVID-KEEP')")
        connection.execute("INSERT INTO edge_evidence_map(edge_id, evidence_id) VALUES ('EDGE-ORPHAN', 'EVID-KEEP')")
        connection.execute("INSERT INTO edge_evidence_map(edge_id, evidence_id) VALUES ('EDGE-MISSING', 'EVID-MISSING')")
        connection.commit()
    finally:
        connection.close()

    report = rebuild_derived_state(paths.root, scope="graph")

    assert report.status == "ok"
    assert report.items[0].status == "done"
    assert report.items[0].changed_counts == {"graph_edges": 1, "edge_evidence_map": 2}
    assert report.items[0].after["status"] == "ok"
    connection = connect(paths.db_file)
    try:
        assert _ids(connection, "graph_edges", "edge_id") == ["EDGE-KEEP"]
        assert _ids(connection, "edge_evidence_map", "edge_id") == ["EDGE-KEEP"]
        assert _table_count(connection, "entities") == 2
        assert _table_count(connection, "evidence") == 1
    finally:
        connection.close()


def test_rebuild_wiki_scope_removes_invalid_pages_without_touching_sources(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_document(connection, "DOC-KEEP")
        _insert_entity(connection, "ENT-KEEP")
        _insert_fact(connection, "FACT-KEEP", "有效定义")
        _insert_wiki_page(connection, "WPAGE-KEEP", "ENT-KEEP", '["FACT-KEEP"]', '["DOC-KEEP"]')
        _insert_wiki_page(connection, "WPAGE-MISSING-ENTITY", "ENT-MISSING", '["FACT-KEEP"]', '["DOC-KEEP"]')
        _insert_wiki_page(connection, "WPAGE-MISSING-FACT", "ENT-KEEP", '["FACT-MISSING"]', '["DOC-KEEP"]')
        _insert_wiki_page(connection, "WPAGE-MISSING-DOC", "ENT-KEEP", '["FACT-KEEP"]', '["DOC-MISSING"]')
        _insert_wiki_page(connection, "WPAGE-INVALID-JSON", "ENT-KEEP", '{bad-json', '["DOC-KEEP"]')
        connection.commit()
    finally:
        connection.close()

    dry_run = rebuild_derived_state(paths.root, scope="wiki", dry_run=True)
    assert dry_run.items[0].changed_counts == {"wiki_pages": 4}

    report = rebuild_derived_state(paths.root, scope="wiki")

    assert report.status == "ok"
    assert report.items[0].status == "done"
    assert report.items[0].changed_counts == {"wiki_pages": 4}
    connection = connect(paths.db_file)
    try:
        assert _ids(connection, "wiki_pages", "page_id") == ["WPAGE-KEEP"]
        assert _table_count(connection, "documents") == 1
        assert _table_count(connection, "facts") == 1
        assert _table_count(connection, "entities") == 1
    finally:
        connection.close()


def test_rebuild_coverage_scope_reconciles_mapping_orphans_only(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_source_unit(connection, "UNIT-KEEP")
        _insert_fact(connection, "FACT-KEEP", "有效定义")
        _insert_evidence(connection, "EVID-KEEP")
        connection.execute(
            """
            INSERT INTO source_unit_fact_map(unit_id, fact_id, doc_id, support_type, created_at)
            VALUES ('UNIT-KEEP', 'FACT-KEEP', 'DOC-1', 'primary', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO source_unit_fact_map(unit_id, fact_id, doc_id, support_type, created_at)
            VALUES ('UNIT-MISSING', 'FACT-MISSING', 'DOC-1', 'primary', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO source_unit_evidence_map(unit_id, evidence_id, doc_id, support_type, created_at)
            VALUES ('UNIT-KEEP', 'EVID-KEEP', 'DOC-1', 'primary', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO source_unit_evidence_map(unit_id, evidence_id, doc_id, support_type, created_at)
            VALUES ('UNIT-MISSING', 'EVID-MISSING', 'DOC-1', 'primary', 'now')
            """
        )
        connection.commit()
    finally:
        connection.close()

    report = rebuild_derived_state(paths.root, scope="coverage")

    assert report.status == "ok"
    assert report.items[0].changed_counts == {
        "source_unit_fact_map": 1,
        "source_unit_evidence_map": 1,
    }
    connection = connect(paths.db_file)
    try:
        assert _ids(connection, "source_unit_fact_map", "unit_id") == ["UNIT-KEEP"]
        assert _ids(connection, "source_unit_evidence_map", "unit_id") == ["UNIT-KEEP"]
        assert _table_count(connection, "source_units") == 1
        assert _table_count(connection, "facts") == 1
        assert _table_count(connection, "evidence") == 1
    finally:
        connection.close()


def test_rebuild_all_runs_structural_reconcile_before_fts_refresh(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_wiki_page(connection, "WPAGE-ORPHAN", "ENT-MISSING", '["FACT-MISSING"]', '["DOC-MISSING"]')
        connection.commit()
    finally:
        connection.close()

    report = rebuild_derived_state(paths.root, scope="all")

    assert report.status == "ok"
    assert [item.scope for item in report.items] == ["graph", "wiki", "coverage", "fts"]
    assert report.summary["unsupported"] == 0
    assert report.items[1].changed_counts == {"wiki_pages": 1}
    checks = check_derived_state(paths.root)
    assert {check.status for check in checks} == {"fresh"}
    connection = connect(paths.db_file)
    try:
        assert _table_count(connection, "wiki_pages") == 0
    finally:
        connection.close()


def test_rebuild_full_graph_is_doc_scoped_and_replaces_old_doc_edges(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    _seed_full_rebuild_doc(paths.root, "DOC-A", "ENT-000101", "FACT-A", "EVID-A")
    _seed_full_rebuild_doc(paths.root, "DOC-B", "ENT-000102", "FACT-B", "EVID-B")
    connection = connect(paths.db_file)
    try:
        _insert_graph_edge(connection, "EDGE-OLD-A", "ENT-DOC-A", "ENT-000101", version_scope="DOC-A")
        _insert_graph_edge(connection, "EDGE-OLD-B", "ENT-DOC-B", "ENT-000102", version_scope="DOC-B")
        connection.commit()
    finally:
        connection.close()

    dry_run = rebuild_derived_state(paths.root, scope="graph", mode="full", doc_id="DOC-A", dry_run=True)
    assert dry_run.items[0].status == "planned"
    assert dry_run.items[0].action == "full_rebuild"
    connection = connect(paths.db_file)
    try:
        assert "EDGE-OLD-A" in _ids(connection, "graph_edges", "edge_id")
    finally:
        connection.close()

    report = rebuild_derived_state(paths.root, scope="graph", mode="full", doc_id="DOC-A")

    assert report.status == "ok"
    assert report.items[0].status == "done"
    assert report.items[0].changed_counts["documents"] == 1
    connection = connect(paths.db_file)
    try:
        edge_ids = _ids(connection, "graph_edges", "edge_id")
        assert "EDGE-OLD-A" not in edge_ids
        assert "EDGE-OLD-B" in edge_ids
        doc_a_edges = connection.execute(
            "SELECT count(*) FROM graph_edges WHERE version_scope = 'DOC-A'"
        ).fetchone()[0]
        assert int(doc_a_edges) >= 1
    finally:
        connection.close()


def test_rebuild_full_wiki_removes_stale_rows_for_document(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    _seed_full_rebuild_doc(paths.root, "DOC-A", "ENT-000101", "FACT-A", "EVID-A")
    connection = connect(paths.db_file)
    try:
        _insert_wiki_page(connection, "WPAGE-STALE", "ENT-000101", '["FACT-A"]', '["DOC-A"]')
        connection.execute("UPDATE wiki_pages SET trust_status = 'stale' WHERE page_id = 'WPAGE-STALE'")
        connection.commit()
    finally:
        connection.close()

    report = rebuild_derived_state(paths.root, scope="wiki", mode="full", doc_id="DOC-A")

    assert report.status == "ok"
    assert report.items[0].action == "full_rebuild"
    connection = connect(paths.db_file)
    try:
        page_ids = _ids(connection, "wiki_pages", "page_id")
        assert "WPAGE-STALE" not in page_ids
        assert "WPAGE-000101" in page_ids
    finally:
        connection.close()


def test_rebuild_full_doc_scope_status_ignores_unrelated_global_doctor_issues(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    _seed_full_rebuild_doc(paths.root, "DOC-A", "ENT-000101", "FACT-A", "EVID-A")
    _seed_full_rebuild_doc(paths.root, "DOC-B", "ENT-000102", "FACT-B", "EVID-B")
    connection = connect(paths.db_file)
    try:
        _insert_wiki_page(connection, "WPAGE-B-INVALID", "ENT-000102", '["FACT-MISSING-B"]', '["DOC-B"]')
        connection.commit()
    finally:
        connection.close()

    report = rebuild_derived_state(paths.root, scope="wiki", mode="full", doc_id="DOC-A")

    assert report.status == "ok"
    assert report.items[0].status == "done"
    assert report.items[0].after["status"] == "warn"
    assert report.items[0].after["doc_scoped_issues"] == {}
    connection = connect(paths.db_file)
    try:
        assert "WPAGE-B-INVALID" in _ids(connection, "wiki_pages", "page_id")
    finally:
        connection.close()


def test_rebuild_full_coverage_rebuilds_source_units_from_main_data(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    _seed_full_rebuild_doc(paths.root, "DOC-A", "ENT-000101", "FACT-A", "EVID-A")
    connection = connect(paths.db_file)
    try:
        _insert_source_unit(connection, "UNIT-OLD")
        connection.execute("UPDATE source_units SET doc_id = 'DOC-A' WHERE unit_id = 'UNIT-OLD'")
        connection.commit()
    finally:
        connection.close()

    report = rebuild_derived_state(paths.root, scope="coverage", mode="full", doc_id="DOC-A")

    assert report.status == "ok"
    assert report.items[0].changed_counts["documents"] == 1
    assert report.items[0].changed_counts["source_units"] >= 1
    connection = connect(paths.db_file)
    try:
        unit_ids = _ids(connection, "source_units", "unit_id")
        assert "UNIT-OLD" not in unit_ids
        assert any(unit_id.startswith("DOC-A") for unit_id in unit_ids)
    finally:
        connection.close()


def test_rebuild_full_all_runs_pipeline_order_and_refreshes_fts(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    _seed_full_rebuild_doc(paths.root, "DOC-A", "ENT-000101", "FACT-A", "EVID-A")

    report = rebuild_derived_state(paths.root, scope="all", mode="full", doc_id="DOC-A")

    assert report.status == "ok"
    assert [item.scope for item in report.items] == ["wiki", "graph", "coverage", "fts"]
    assert [item.action for item in report.items] == ["full_rebuild", "full_rebuild", "full_rebuild", "refresh"]
    checks = check_derived_state(paths.root)
    assert {check.status for check in checks} == {"fresh"}


def test_rebuild_cli_parser_and_json_output(tmp_path: Path, monkeypatch, capsys) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    parser = build_parser()

    parsed = parser.parse_args(
        [
            "--root",
            str(paths.root),
            "rebuild-derived-state",
            "--scope",
            "fts",
            "--dry-run",
            "--mode",
            "reconcile",
        ]
    )
    assert parsed.command == "rebuild-derived-state"
    assert parsed.scope == "fts"
    assert parsed.dry_run is True
    assert parsed.mode == "reconcile"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eakb",
            "--root",
            str(paths.root),
            "rebuild-derived-state",
            "--scope",
            "fts",
            "--dry-run",
        ],
    )
    main()

    output = json.loads(capsys.readouterr().out)
    assert output["scope"] == "fts"
    assert output["dry_run"] is True
    assert output["items"][0]["status"] == "planned"


def test_retrieval_guard_still_refreshes_with_public_rebuild_command(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        _insert_fact(connection, "FACT-NEW", "OBC 输入过压保护")
        ensure_fts_schema(connection)
        connection.execute(
            """
            INSERT INTO facts_fts(result_id, doc_id, page_no, searchable_text)
            VALUES ('FACT-OLD', 'DOC-1', 1, 'old stale row')
            """
        )
        connection.commit()

        hits = search_knowledge_base_expanded(
            paths.root,
            "输入过压",
            limit=5,
            connection=connection,
            result_types={"fact"},
        )

        assert hits[0]["result_id"] == "FACT-NEW"
    finally:
        connection.close()


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


def _seed_full_rebuild_doc(
    workspace_root: Path,
    doc_id: str,
    term_entity_id: str,
    fact_id: str,
    evidence_id: str,
) -> None:
    db_path = workspace_root / "db" / "knowledge.db"
    connection = connect(db_path)
    try:
        _insert_document(connection, doc_id)
        _insert_entity_typed(connection, f"ENT-{doc_id}", f"{doc_id}: Test Document", "document")
        _insert_entity_typed(connection, term_entity_id, f"{doc_id} 控制导引电路", "term")
        connection.execute(
            """
            INSERT INTO evidence(
                evidence_id, doc_id, page_id, block_id, block_type, raw_text,
                normalized_text, image_ref, table_ref, page_no, confidence,
                risk_level, evidence_status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'text', ?, ?, NULL, NULL, 1, 1.0, 'low', 'ready', 'now', 'now')
            """,
            (
                evidence_id,
                doc_id,
                f"PAGE-{doc_id}",
                f"BLOCK-{doc_id}",
                f"{doc_id} 控制导引电路用于车辆与供电设备之间信号传输。",
                f"{doc_id} 控制导引电路用于车辆与供电设备之间信号传输。",
            ),
        )
        connection.execute(
            """
            INSERT INTO facts(
                fact_id, fact_type, subject_entity_id, predicate, object_value,
                object_entity_id, qualifiers_json, confidence, fact_status,
                source_doc_id, created_at, updated_at
            )
            VALUES (?, 'term_definition', ?, 'defines', ?, NULL, '{"page_no": 1}', 1.0, 'ready', ?, 'now', 'now')
            """,
            (
                fact_id,
                term_entity_id,
                json.dumps(
                    {
                        "term": f"{doc_id} 控制导引电路",
                        "definition": "用于车辆与供电设备之间信号传输。",
                    },
                    ensure_ascii=False,
                ),
                doc_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO fact_evidence_map(fact_id, evidence_id, support_type)
            VALUES (?, ?, 'direct')
            """,
            (fact_id, evidence_id),
        )
        connection.commit()
    finally:
        connection.close()

    knowledge_units = {
        "doc_id": doc_id,
        "units": [
            {
                "id": f"{doc_id}_definition_1_1",
                "type": "definition",
                "title": f"{doc_id} 控制导引电路",
                "content": "用于车辆与供电设备之间信号传输。",
                "section": "3",
                "page": 1,
            }
        ],
    }
    normalized_dir = workspace_root / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    (normalized_dir / f"{doc_id}.knowledge_units.json").write_text(
        json.dumps(knowledge_units, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _insert_document(connection, doc_id: str) -> None:
    connection.execute(
        """
        INSERT INTO documents(
            doc_id, source_filename, source_type, mime_type, sha256, file_size,
            page_count, language, version_label, source_path, ingest_time,
            update_time, parse_status, quality_status, is_active
        )
        VALUES (?, 'doc.pdf', 'pdf', 'application/pdf', 'sha', 100, 1, 'zh', NULL, 'doc.pdf', 'now', 'now', 'parsed', 'ok', 1)
        """,
        (doc_id,),
    )


def _insert_entity(connection, entity_id: str) -> None:
    _insert_entity_typed(connection, entity_id, entity_id, "term")


def _insert_entity_typed(connection, entity_id: str, canonical_name: str, entity_type: str) -> None:
    connection.execute(
        """
        INSERT INTO entities(
            entity_id, canonical_name, entity_type, alias_json, description,
            source_confidence, entity_status, created_at, updated_at
        )
        VALUES (?, ?, ?, '[]', 'desc', 1.0, 'ready', 'now', 'now')
        """,
        (entity_id, canonical_name, entity_type),
    )


def _insert_evidence(connection, evidence_id: str) -> None:
    connection.execute(
        """
        INSERT INTO evidence(
            evidence_id, doc_id, page_id, block_id, block_type, raw_text,
            normalized_text, image_ref, table_ref, page_no, confidence,
            risk_level, evidence_status, created_at, updated_at
        )
        VALUES (?, 'DOC-1', 'PAGE-1', 'BLOCK-1', 'text', 'raw', 'raw', NULL, NULL, 1, 1.0, 'low', 'ready', 'now', 'now')
        """,
        (evidence_id,),
    )


def _insert_graph_edge(
    connection,
    edge_id: str,
    src_entity_id: str,
    dst_entity_id: str,
    *,
    version_scope: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO graph_edges(
            edge_id, src_entity_id, relation, dst_entity_id, version_scope,
            condition_scope, confidence, edge_status, created_at, updated_at
        )
        VALUES (?, ?, 'related_to', ?, ?, NULL, 1.0, 'ready', 'now', 'now')
        """,
        (edge_id, src_entity_id, dst_entity_id, version_scope),
    )


def _insert_wiki_page(
    connection,
    page_id: str,
    entity_id: str,
    source_fact_ids_json: str,
    source_doc_ids_json: str,
) -> None:
    connection.execute(
        """
        INSERT INTO wiki_pages(
            page_id, page_type, title, slug, entity_id, source_fact_ids_json,
            source_doc_ids_json, trust_status, file_path, updated_at
        )
        VALUES (?, 'term', ?, ?, ?, ?, ?, 'ready', 'wiki.md', 'now')
        """,
        (page_id, page_id, page_id.lower(), entity_id, source_fact_ids_json, source_doc_ids_json),
    )


def _insert_source_unit(connection, unit_id: str) -> None:
    connection.execute(
        """
        INSERT INTO source_units (
            unit_id, doc_id, page_no, block_id, unit_type, text,
            normalized_text, importance, expected_knowledge_type,
            status, metadata_json, created_at, updated_at
        )
        VALUES (?, 'DOC-1', 1, 'BLOCK-1', 'definition_unit', 'text', 'text', 'high', 'term_definition', 'covered', '{}', 'now', 'now')
        """,
        (unit_id,),
    )


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


def _table_count(connection, table_name: str) -> int:
    return int(connection.execute(f"SELECT count(*) FROM {table_name}").fetchone()[0])


def _ids(connection, table_name: str, column_name: str) -> list[str]:
    rows = connection.execute(f"SELECT {column_name} FROM {table_name} ORDER BY {column_name}").fetchall()
    return [str(row[column_name]) for row in rows]


def _facts_fts_ids(connection) -> list[str]:
    rows = connection.execute("SELECT result_id FROM facts_fts ORDER BY result_id").fetchall()
    return [str(row["result_id"]) for row in rows]
