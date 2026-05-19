from __future__ import annotations

from pathlib import Path

from .db import connect
from .quality import assess_document_quality


def assess_pending_quality(workspace_root: Path, limit: int = 10) -> list[dict[str, object]]:
    connection = connect(Path(workspace_root) / "db" / "knowledge.db")
    try:
        doc_ids = [
            row["doc_id"]
            for row in connection.execute(
                """
                SELECT doc_id
                FROM documents
                WHERE parse_status = 'parsed'
                ORDER BY update_time
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]
    finally:
        connection.close()

    results: list[dict[str, object]] = []
    for doc_id in doc_ids:
        result = assess_document_quality(workspace_root, doc_id)
        results.append(
            {
                "doc_id": result.doc_id,
                "overall_score": result.overall_score,
                "high_risk_page_count": result.high_risk_page_count,
                "review_required_count": result.review_required_count,
                "blocked_count": result.blocked_count,
                "report_path": str(result.report_path),
            }
        )
    return results
