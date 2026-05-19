from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .db import connect
from .parse import parse_document


@dataclass(frozen=True)
class JobRunResult:
    job_id: str
    target_id: str
    status: str
    details: dict[str, object]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def run_parse_jobs(workspace_root: Path, limit: int = 10) -> list[JobRunResult]:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    results: list[JobRunResult] = []

    try:
        pending_jobs = connection.execute(
            """
            SELECT job_id, target_id
            FROM jobs
            WHERE job_type = 'parse_document' AND status = 'pending'
            ORDER BY created_at
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        for job_row in pending_jobs:
            job_id = job_row["job_id"]
            doc_id = job_row["target_id"]
            started_at = _utc_now()

            connection.execute(
                "UPDATE jobs SET status = ?, updated_at = ?, error_message = NULL WHERE job_id = ?",
                ("running", started_at, job_id),
            )
            connection.execute(
                "UPDATE documents SET parse_status = ?, update_time = ? WHERE doc_id = ?",
                ("processing", started_at, doc_id),
            )
            connection.commit()

            try:
                parse_result = parse_document(paths.root, doc_id)
                finished_at = _utc_now()
                details = {
                    "doc_id": parse_result.doc_id,
                    "page_count": parse_result.page_count,
                    "block_count": parse_result.block_count,
                    "normalized_path": str(parse_result.normalized_path),
                    "parser_engine": parse_result.parser_engine,
                }
                connection.execute(
                    """
                    UPDATE jobs
                    SET status = ?, payload_json = ?, updated_at = ?
                    WHERE job_id = ?
                    """,
                    ("completed", json.dumps(details, ensure_ascii=False), finished_at, job_id),
                )
                connection.commit()
                results.append(
                    JobRunResult(
                        job_id=job_id,
                        target_id=doc_id,
                        status="completed",
                        details=details,
                    )
                )
            except Exception as exc:
                failed_at = _utc_now()
                connection.execute(
                    """
                    UPDATE jobs
                    SET status = ?, error_message = ?, retry_count = retry_count + 1, updated_at = ?
                    WHERE job_id = ?
                    """,
                    ("failed", str(exc), failed_at, job_id),
                )
                connection.execute(
                    "UPDATE documents SET parse_status = ?, update_time = ? WHERE doc_id = ?",
                    ("failed", failed_at, doc_id),
                )
                connection.commit()
                results.append(
                    JobRunResult(
                        job_id=job_id,
                        target_id=doc_id,
                        status="failed",
                        details={"error": str(exc)},
                    )
                )

        return results
    finally:
        connection.close()


def summarize_job_results(results: list[JobRunResult]) -> list[dict[str, object]]:
    return [asdict(result) for result in results]
