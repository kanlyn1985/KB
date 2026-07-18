from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable
from uuid import uuid4

from agent_kb.storage.migrations import SchemaMigrator


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class BackgroundJob:
    job_id: str
    tenant_id: str
    job_type: str
    payload: dict[str, Any]
    status: str
    attempts: int
    max_attempts: int
    available_at: str
    locked_by: str | None
    locked_at: str | None
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SQLiteJobQueue:
    """Transactional at-least-once queue with idempotent submission support."""

    TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        SchemaMigrator(connection).migrate()

    def submit(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        tenant_id: str = "default",
        max_attempts: int = 3,
        delay_seconds: float = 0.0,
        idempotency_key: str | None = None,
    ) -> BackgroundJob:
        if not job_type.strip():
            raise ValueError("job_type is required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        normalized_key = str(idempotency_key or "").strip() or None
        if normalized_key:
            existing = self.connection.execute(
                """
                SELECT job_id FROM job_idempotency
                WHERE tenant_id = ? AND idempotency_key = ?
                """,
                (tenant_id, normalized_key),
            ).fetchone()
            if existing is not None:
                job = self.get(str(existing["job_id"]))
                if job is not None:
                    return job

        now = _utc_now()
        job_id = f"job_{uuid4().hex}"
        available = now + timedelta(seconds=max(0.0, float(delay_seconds)))
        try:
            with self.connection:
                self.connection.execute(
                    """
                    INSERT INTO background_jobs(
                        job_id, tenant_id, job_type, payload_json, status, attempts,
                        max_attempts, available_at, locked_by, locked_at, result_json,
                        error, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'queued', 0, ?, ?, NULL, NULL, NULL, NULL, ?, ?)
                    """,
                    (
                        job_id,
                        tenant_id,
                        job_type.strip(),
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        int(max_attempts),
                        _iso(available),
                        _iso(now),
                        _iso(now),
                    ),
                )
                if normalized_key:
                    self.connection.execute(
                        """
                        INSERT INTO job_idempotency(tenant_id, idempotency_key, job_id, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (tenant_id, normalized_key, job_id, _iso(now)),
                    )
        except sqlite3.IntegrityError:
            if not normalized_key:
                raise
            row = self.connection.execute(
                """
                SELECT job_id FROM job_idempotency
                WHERE tenant_id = ? AND idempotency_key = ?
                """,
                (tenant_id, normalized_key),
            ).fetchone()
            if row is None:
                raise
            existing = self.get(str(row["job_id"]))
            if existing is None:
                raise RuntimeError("idempotency record references a missing job")
            return existing
        job = self.get(job_id)
        assert job is not None
        return job

    def claim(
        self,
        worker_id: str,
        *,
        lease_seconds: int = 300,
        tenant_id: str | None = None,
        job_types: set[str] | None = None,
    ) -> BackgroundJob | None:
        now = _iso()
        stale_before = _iso(_utc_now() - timedelta(seconds=max(1, int(lease_seconds))))
        filters = ["status = 'queued'", "available_at <= ?", "attempts < max_attempts"]
        params: list[Any] = [now]
        if tenant_id:
            filters.append("tenant_id = ?")
            params.append(tenant_id)
        if job_types:
            normalized_types = sorted(str(item) for item in job_types if str(item))
            if not normalized_types:
                return None
            filters.append(f"job_type IN ({','.join('?' for _ in normalized_types)})")
            params.extend(normalized_types)
        with self.connection:
            self.connection.execute(
                """
                UPDATE background_jobs
                SET status = 'queued', locked_by = NULL, locked_at = NULL, updated_at = ?
                WHERE status = 'running' AND locked_at < ? AND attempts < max_attempts
                """,
                (now, stale_before),
            )
            row = self.connection.execute(
                f"""
                SELECT job_id FROM background_jobs
                WHERE {' AND '.join(filters)}
                ORDER BY created_at, job_id
                LIMIT 1
                """,
                params,
            ).fetchone()
            if row is None:
                return None
            cursor = self.connection.execute(
                """
                UPDATE background_jobs
                SET status = 'running', attempts = attempts + 1,
                    locked_by = ?, locked_at = ?, updated_at = ?
                WHERE job_id = ? AND status = 'queued'
                """,
                (worker_id, now, now, row["job_id"]),
            )
            if cursor.rowcount != 1:
                return None
        return self.get(str(row["job_id"]))

    def succeed(self, job_id: str, result: dict[str, Any] | None = None) -> None:
        self._finish(job_id, "succeeded", result=result, error=None)

    def fail(self, job_id: str, error: str, *, retry_delay_seconds: float = 0.0) -> None:
        row = self.connection.execute(
            "SELECT attempts, max_attempts FROM background_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise KeyError(job_id)
        terminal = int(row["attempts"]) >= int(row["max_attempts"])
        status = "failed" if terminal else "queued"
        available = _iso(_utc_now() + timedelta(seconds=max(0.0, float(retry_delay_seconds))))
        with self.connection:
            self.connection.execute(
                """
                UPDATE background_jobs
                SET status = ?, error = ?, available_at = ?, locked_by = NULL,
                    locked_at = NULL, updated_at = ?
                WHERE job_id = ?
                """,
                (status, str(error)[:4000], available, _iso(), job_id),
            )

    def cancel(self, job_id: str) -> None:
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE background_jobs
                SET status = 'cancelled', locked_by = NULL, locked_at = NULL, updated_at = ?
                WHERE job_id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled')
                """,
                (_iso(), job_id),
            )
        if cursor.rowcount == 0 and self.get(job_id) is None:
            raise KeyError(job_id)

    def get(self, job_id: str) -> BackgroundJob | None:
        row = self.connection.execute("SELECT * FROM background_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return _job_from_row(row) if row is not None else None

    def list(
        self,
        *,
        status: str | None = None,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[BackgroundJob]:
        filters: list[str] = []
        params: list[Any] = []
        if status:
            filters.append("status = ?")
            params.append(status)
        if tenant_id:
            filters.append("tenant_id = ?")
            params.append(tenant_id)
        query = "SELECT * FROM background_jobs"
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        return [_job_from_row(row) for row in self.connection.execute(query, params)]

    def run_once(
        self,
        worker_id: str,
        handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any] | None]],
        *,
        tenant_id: str | None = None,
    ) -> BackgroundJob | None:
        job = self.claim(worker_id, tenant_id=tenant_id, job_types=set(handlers))
        if job is None:
            return None
        handler = handlers.get(job.job_type)
        if handler is None:
            self.fail(job.job_id, f"unsupported job type: {job.job_type}")
            return self.get(job.job_id)
        try:
            result = handler(dict(job.payload))
        except Exception as exc:
            self.fail(job.job_id, f"{type(exc).__name__}: {exc}")
        else:
            self.succeed(job.job_id, result or {})
        return self.get(job.job_id)

    def _finish(
        self,
        job_id: str,
        status: str,
        *,
        result: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE background_jobs
                SET status = ?, result_json = ?, error = ?, locked_by = NULL,
                    locked_at = NULL, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    status,
                    json.dumps(result, ensure_ascii=False, sort_keys=True) if result is not None else None,
                    error,
                    _iso(),
                    job_id,
                ),
            )
        if cursor.rowcount == 0:
            raise KeyError(job_id)


def _job_from_row(row: sqlite3.Row) -> BackgroundJob:
    return BackgroundJob(
        job_id=row["job_id"],
        tenant_id=row["tenant_id"],
        job_type=row["job_type"],
        payload=json.loads(row["payload_json"] or "{}"),
        status=row["status"],
        attempts=int(row["attempts"]),
        max_attempts=int(row["max_attempts"]),
        available_at=row["available_at"],
        locked_by=row["locked_by"],
        locked_at=row["locked_at"],
        result=json.loads(row["result_json"]) if row["result_json"] else None,
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
