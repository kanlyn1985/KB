"""Evaluation and testing infrastructure.

This module contains database operations for evaluation runs,
golden cases, and test results.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ..config import AppPaths
from ..db import connect
from ..domain.eval import EvalRun, GoldenCase, RetrievalRun


class EvalRepository:
    """Repository for evaluation runs."""

    def __init__(self, workspace_root: Path):
        """Initialize evaluation repository."""
        self.paths = AppPaths.from_root(workspace_root)
        self.connection = connect(self.paths.db_file)

    def record_eval_run(
        self,
        suite_id: str,
        structured: dict[str, object],
        runtime_code_version: str,
    ) -> str:
        """Record an evaluation run."""
        run_id = f"eval-{suite_id}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

        self.connection.execute(
            """
            INSERT INTO eval_runs (run_id, suite_id, timestamp, status, structured_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, suite_id, datetime.now(UTC).isoformat(), "complete", json.dumps(structured)),
        )

        self.connection.commit()
        return run_id

    def get_eval_run_detail(self, eval_run_id: str) -> dict[str, object] | None:
        """Get evaluation run details."""
        row = self.connection.execute(
            "SELECT * FROM eval_runs WHERE run_id = ?",
            (eval_run_id,),
        ).fetchone()

        if not row:
            return None

        return {
            "run_id": row["run_id"],
            "suite_id": row["suite_id"],
            "timestamp": row["timestamp"],
            "status": row["status"],
            "structured": json.loads(row.get("structured_json") or "{}"),
        }

    def list_eval_runs(
        self,
        suite_id: str | None = None,
        limit: int = 30,
    ) -> list[dict[str, object]]:
        """List evaluation runs."""
        if suite_id:
            rows = self.connection.execute(
                "SELECT * FROM eval_runs WHERE suite_id = ? ORDER BY timestamp DESC LIMIT ?",
                (suite_id, limit),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM eval_runs ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [
            {
                "run_id": row["run_id"],
                "suite_id": row["suite_id"],
                "timestamp": row["timestamp"],
                "status": row["status"],
            }
            for row in rows
        ]


class GoldenCaseRepository:
    """Repository for golden test cases."""

    def __init__(self, workspace_root: Path):
        """Initialize golden case repository."""
        self.paths = AppPaths.from_root(workspace_root)
        self.connection = connect(self.paths.db_file)

    def sync_golden_cases(self, cases: list[dict[str, object]]) -> int:
        """Sync golden cases to database."""
        count = 0
        for case in cases:
            case_id = case.get("case_id")
            if not case_id:
                continue

            self.connection.execute(
                """
                INSERT OR REPLACE INTO golden_cases (case_id, query, doc_id, expected_json, metadata_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    case.get("query"),
                    case.get("doc_id"),
                    json.dumps(case.get("expected_result", {})),
                    json.dumps(case.get("metadata", {})),
                    case.get("status", "active"),
                    case.get("created_at", datetime.now(UTC).isoformat()),
                ),
            )
            count += 1

        self.connection.commit()
        return count

    def list_golden_cases(self, limit: int = 100) -> list[dict[str, object]]:
        """List golden cases."""
        rows = self.connection.execute(
            "SELECT * FROM golden_cases WHERE status = 'active' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        return [
            {
                "case_id": row["case_id"],
                "query": row["query"],
                "doc_id": row["doc_id"],
                "expected": json.loads(row.get("expected_json") or "{}"),
                "metadata": json.loads(row.get("metadata_json") or "{}"),
            }
            for row in rows
        ]

    def load_golden_cases_from_file(self, golden_path: Path) -> list[dict[str, object]]:
        """Load golden cases from JSON file."""
        if not golden_path.exists():
            return []

        data = json.loads(golden_path.read_text(encoding="utf-8"))
        return data.get("cases", [])


class RetrievalRepository:
    """Repository for retrieval runs."""

    def __init__(self, workspace_root: Path):
        """Initialize retrieval repository."""
        self.paths = AppPaths.from_root(workspace_root)
        self.connection = connect(self.paths.db_file)

    def record_retrieval_run(
        self,
        query: str,
        hit_count: int,
        context: dict[str, object],
    ) -> str:
        """Record a retrieval run."""
        run_id = f"retrieval-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

        self.connection.execute(
            """
            INSERT INTO retrieval_runs (run_id, query, timestamp, hit_count, context_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, query, datetime.now(UTC).isoformat(), hit_count, json.dumps(context)),
        )

        self.connection.commit()
        return run_id

    def list_retrieval_runs(self, limit: int = 30) -> list[dict[str, object]]:
        """List retrieval runs."""
        rows = self.connection.execute(
            "SELECT * FROM retrieval_runs ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()

        return [
            {
                "run_id": row["run_id"],
                "query": row["query"],
                "timestamp": row["timestamp"],
                "hit_count": row["hit_count"],
            }
            for row in rows
        ]
