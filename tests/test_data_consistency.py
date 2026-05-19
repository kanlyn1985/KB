from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.mark.integration
def test_database_consistency_for_built_docs() -> None:
    db_path = Path("knowledge_base/db/knowledge.db")
    if not db_path.exists():
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        docs = conn.execute(
            """
            select doc_id from documents
            where parse_status = 'parsed'
            order by doc_id
            """
        ).fetchall()

        for doc in docs:
            doc_id = doc["doc_id"]

            fact_count = conn.execute(
                "select count(*) from facts where source_doc_id = ?",
                (doc_id,),
            ).fetchone()[0]
            fact_map_count = conn.execute(
                """
                select count(*)
                from fact_evidence_map m
                join facts f on m.fact_id = f.fact_id
                where f.source_doc_id = ?
                """,
                (doc_id,),
            ).fetchone()[0]
            assert fact_map_count >= fact_count

            edge_count = conn.execute(
                "select count(*) from graph_edges where version_scope = ?",
                (doc_id,),
            ).fetchone()[0]
            edge_map_count = conn.execute(
                """
                select count(*)
                from edge_evidence_map m
                join graph_edges g on m.edge_id = g.edge_id
                where g.version_scope = ?
                """,
                (doc_id,),
            ).fetchone()[0]
            assert edge_count == 0 or edge_map_count >= edge_count

            for row in conn.execute(
                """
                select file_path
                from wiki_pages
                where json_extract(source_doc_ids_json, '$[0]') = ?
                """,
                (doc_id,),
            ):
                assert Path(row["file_path"]).exists()
    finally:
        conn.close()
