from __future__ import annotations

import sqlite3
from pathlib import Path


WORKSPACE = Path("knowledge_base")


def resolve_doc_id_by_filename(*substrings: str, workspace: Path = WORKSPACE) -> str:
    db_path = workspace / "db" / "knowledge.db"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT doc_id, source_filename, source_path
            FROM documents
            ORDER BY doc_id
            """
        ).fetchall()
    finally:
        connection.close()

    lowered = [value.lower() for value in substrings if value]
    for row in rows:
        haystack = " ".join(
            [
                str(row["doc_id"] or ""),
                str(row["source_filename"] or ""),
                str(row["source_path"] or ""),
            ]
        ).lower()
        if all(token in haystack for token in lowered):
            return str(row["doc_id"])
    raise AssertionError(f"document not found for substrings={substrings!r}")

