"""Source-unit persistence: matrix → source_units/source_unit_*_map tables.

Extracted from `closed_loop_store._impl` (formerly closed_loop_store.py) to
reduce the monolith's surface. Cross-module callers inside this package
must import via `from ._source_units import ...`.
"""
from __future__ import annotations

import json

from ._helpers import (
    _as_int,
    _json_object,
    _normalize_text,
    _optional_text,
    _stable_id,
    _string_ids,
)
from ._runtime import utc_now


def sync_source_units_from_matrix(
    connection,
    doc_id: str,
    matrix_rows: list[dict[str, object]],
    *,
    generated_at: str | None = None,
) -> int:
    now = generated_at or utc_now()
    _ensure_source_units_columns(connection)
    ensure_source_unit_mapping_tables(connection)
    connection.execute("DELETE FROM source_unit_fact_map WHERE doc_id = ?", (doc_id,))
    connection.execute("DELETE FROM source_unit_evidence_map WHERE doc_id = ?", (doc_id,))
    connection.execute("DELETE FROM source_units WHERE doc_id = ?", (doc_id,))
    for row in matrix_rows:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        locator = row.get("source_locator") if isinstance(row.get("source_locator"), dict) else {}
        source_text = str(row.get("source_text") or "")
        unit_id = str(row.get("unit_id") or _stable_id("UNIT", doc_id, row))
        canonical_title = _optional_text(row.get("canonical_title") or metadata.get("canonical_title"))
        canonical_key = _optional_text(row.get("canonical_key") or row.get("semantic_key"))
        content_role = _optional_text(row.get("content_role") or metadata.get("content_role"))
        quality_flags = row.get("quality_flags") if isinstance(row.get("quality_flags"), list) else metadata.get("quality_flags")
        connection.execute(
            """
            INSERT INTO source_units (
                unit_id, doc_id, page_no, block_id, unit_type, text,
                normalized_text, canonical_title, canonical_key, content_role,
                quality_flags_json, importance, expected_knowledge_type,
                status, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unit_id,
                doc_id,
                _as_int(row.get("page_no")),
                _optional_text(locator.get("block_id")),
                str(row.get("unit_type") or "unknown"),
                source_text,
                _normalize_text(source_text),
                canonical_title,
                canonical_key,
                content_role,
                json.dumps(quality_flags if isinstance(quality_flags, list) else [], ensure_ascii=False),
                _optional_text(row.get("importance")),
                _optional_text(metadata.get("knowledge_unit_type") or row.get("unit_type")),
                str(row.get("coverage_status") or "unknown"),
                json.dumps(
                    {
                        "semantic_key": row.get("semantic_key"),
                        "aliases": row.get("aliases") or [],
                        "source_locator": locator,
                        "metadata": metadata,
                        "covered_by": row.get("covered_by") or {},
                        "coverage_flags": row.get("coverage_flags") or {},
                        "semantic_misaligned": row.get("semantic_misaligned"),
                    },
                    ensure_ascii=False,
                ),
                now,
                now,
            ),
        )
        _persist_source_unit_links(connection, unit_id, doc_id, row, now)
    return len(matrix_rows)


def _ensure_source_units_columns(connection) -> None:
    rows = connection.execute("PRAGMA table_info(source_units)").fetchall()
    columns = {str(row["name"]) for row in rows}
    additions = {
        "canonical_title": "ALTER TABLE source_units ADD COLUMN canonical_title TEXT",
        "canonical_key": "ALTER TABLE source_units ADD COLUMN canonical_key TEXT",
        "content_role": "ALTER TABLE source_units ADD COLUMN content_role TEXT",
        "quality_flags_json": "ALTER TABLE source_units ADD COLUMN quality_flags_json TEXT NOT NULL DEFAULT '[]'",
    }
    for column, statement in additions.items():
        if column not in columns:
            connection.execute(statement)


def ensure_source_unit_mapping_tables(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS source_unit_fact_map (
            unit_id TEXT NOT NULL,
            fact_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            support_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (unit_id, fact_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS source_unit_evidence_map (
            unit_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            support_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (unit_id, evidence_id)
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_source_unit_fact_map_doc_id ON source_unit_fact_map(doc_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_source_unit_fact_map_fact_id ON source_unit_fact_map(fact_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_source_unit_evidence_map_doc_id ON source_unit_evidence_map(doc_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_source_unit_evidence_map_evidence_id ON source_unit_evidence_map(evidence_id)")


def backfill_source_unit_mappings_from_metadata(
    connection,
    *,
    doc_id: str | None = None,
    generated_at: str | None = None,
    only_missing: bool = False,
) -> dict[str, int]:
    ensure_source_unit_mapping_tables(connection)
    now = generated_at or utc_now()
    missing_filter = """
        AND (
            NOT EXISTS (
                SELECT 1
                FROM source_unit_fact_map sfm
                WHERE sfm.unit_id = su.unit_id
            )
            OR NOT EXISTS (
                SELECT 1
                FROM source_unit_evidence_map sem
                WHERE sem.unit_id = su.unit_id
            )
        )
    """
    if doc_id:
        rows = connection.execute(
            f"""
            SELECT su.unit_id, su.doc_id, su.metadata_json
            FROM source_units su
            WHERE su.doc_id = ?
            {missing_filter if only_missing else ""}
            ORDER BY unit_id
            """,
            (doc_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            f"""
            SELECT su.unit_id, su.doc_id, su.metadata_json
            FROM source_units su
            WHERE 1 = 1
            {missing_filter if only_missing else ""}
            ORDER BY doc_id, unit_id
            """
        ).fetchall()

    fact_link_count = 0
    evidence_link_count = 0
    for row in rows:
        metadata = _json_object(row["metadata_json"])
        covered_by = metadata.get("covered_by") if isinstance(metadata.get("covered_by"), dict) else {}
        fact_ids = _string_ids(covered_by.get("fact_ids"))
        evidence_ids = _string_ids(covered_by.get("evidence_ids"))
        if not evidence_ids and fact_ids:
            evidence_ids = _linked_evidence_ids_for_facts(connection, fact_ids)
        fact_link_count += _insert_source_unit_fact_links(
            connection,
            unit_id=str(row["unit_id"]),
            doc_id=str(row["doc_id"]),
            fact_ids=fact_ids,
            support_type="coverage_metadata",
            now=now,
        )
        evidence_link_count += _insert_source_unit_evidence_links(
            connection,
            unit_id=str(row["unit_id"]),
            doc_id=str(row["doc_id"]),
            evidence_ids=evidence_ids,
            support_type="coverage_metadata",
            now=now,
        )
    return {
        "source_unit_count": len(rows),
        "fact_link_count": fact_link_count,
        "evidence_link_count": evidence_link_count,
    }


def _persist_source_unit_links(connection, unit_id: str, doc_id: str, row: dict[str, object], now: str) -> None:
    covered_by = row.get("covered_by") if isinstance(row.get("covered_by"), dict) else {}
    fact_ids = _string_ids(covered_by.get("fact_ids"))
    evidence_ids = _string_ids(covered_by.get("evidence_ids"))
    if not evidence_ids and fact_ids:
        evidence_ids = _linked_evidence_ids_for_facts(connection, fact_ids)
    _insert_source_unit_fact_links(
        connection,
        unit_id=unit_id,
        doc_id=doc_id,
        fact_ids=fact_ids,
        support_type="coverage_matrix",
        now=now,
    )
    _insert_source_unit_evidence_links(
        connection,
        unit_id=unit_id,
        doc_id=doc_id,
        evidence_ids=evidence_ids,
        support_type="coverage_matrix",
        now=now,
    )


def _insert_source_unit_fact_links(
    connection,
    *,
    unit_id: str,
    doc_id: str,
    fact_ids: list[str],
    support_type: str,
    now: str,
) -> int:
    inserted = 0
    for fact_id in fact_ids:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO source_unit_fact_map (
                unit_id, fact_id, doc_id, support_type, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (unit_id, fact_id, doc_id, support_type, now),
        )
        inserted += max(int(cursor.rowcount or 0), 0)
    return inserted


def _insert_source_unit_evidence_links(
    connection,
    *,
    unit_id: str,
    doc_id: str,
    evidence_ids: list[str],
    support_type: str,
    now: str,
) -> int:
    inserted = 0
    for evidence_id in evidence_ids:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO source_unit_evidence_map (
                unit_id, evidence_id, doc_id, support_type, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (unit_id, evidence_id, doc_id, support_type, now),
        )
        inserted += max(int(cursor.rowcount or 0), 0)
    return inserted


def _linked_evidence_ids_for_facts(connection, fact_ids: list[str]) -> list[str]:
    evidence_ids: set[str] = set()
    for fact_id in fact_ids:
        rows = connection.execute(
            """
            SELECT evidence_id
            FROM fact_evidence_map
            WHERE fact_id = ?
            ORDER BY evidence_id
            """,
            (fact_id,),
        ).fetchall()
        evidence_ids.update(str(row["evidence_id"]) for row in rows if row["evidence_id"])
    return sorted(evidence_ids)
