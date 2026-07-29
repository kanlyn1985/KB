"""Lean SQLite job queue (self-contained schema; no agent_kb migrator).

At-least-once delivery with claim lease, retries, and optional idempotency keys.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

JOB_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS background_jobs (
    job_id          TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    job_type        TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    status          TEXT NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    available_at    TEXT NOT NULL,
    locked_by       TEXT,
    locked_at       TEXT,
    result_json     TEXT,
    error           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_claim
    ON background_jobs(status, available_at, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_tenant
    ON background_jobs(tenant_id, status);

CREATE TABLE IF NOT EXISTS job_idempotency (
    tenant_id       TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    job_id          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key)
);
"""


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

    TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(JOB_SCHEMA_SQL)
        self.connection.commit()

    @classmethod
    def open(cls, path: str | Path) -> SQLiteJobQueue:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        return cls(conn)

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
                        INSERT INTO job_idempotency(
                            tenant_id, idempotency_key, job_id, created_at
                        ) VALUES (?, ?, ?, ?)
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
            existing_job = self.get(str(row["job_id"]))
            if existing_job is None:
                raise RuntimeError("idempotency record references a missing job")
            return existing_job
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
        filters = [
            "status = 'queued'",
            "available_at <= ?",
            "attempts < max_attempts",
        ]
        params: list[Any] = [now]
        if tenant_id:
            filters.append("tenant_id = ?")
            params.append(tenant_id)
        if job_types:
            normalized_types = sorted(str(item) for item in job_types if str(item))
            if not normalized_types:
                return None
            filters.append(
                f"job_type IN ({','.join('?' for _ in normalized_types)})"
            )
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

    def fail(
        self, job_id: str, error: str, *, retry_delay_seconds: float = 0.0
    ) -> None:
        row = self.connection.execute(
            "SELECT attempts, max_attempts FROM background_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise KeyError(job_id)
        terminal = int(row["attempts"]) >= int(row["max_attempts"])
        status = "failed" if terminal else "queued"
        available = _iso(
            _utc_now() + timedelta(seconds=max(0.0, float(retry_delay_seconds)))
        )
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
                SET status = 'cancelled', locked_by = NULL, locked_at = NULL,
                    updated_at = ?
                WHERE job_id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled')
                """,
                (_iso(), job_id),
            )
        if cursor.rowcount == 0 and self.get(job_id) is None:
            raise KeyError(job_id)

    def clear_idempotency(
        self,
        idempotency_key: str,
        *,
        tenant_id: str = "default",
    ) -> bool:
        """Drop an idempotency binding so the same key can submit a new job."""
        key = str(idempotency_key or "").strip()
        if not key:
            return False
        with self.connection:
            cursor = self.connection.execute(
                """
                DELETE FROM job_idempotency
                WHERE tenant_id = ? AND idempotency_key = ?
                """,
                (tenant_id, key),
            )
        return cursor.rowcount > 0

    def requeue(
        self,
        job_id: str,
        *,
        payload_updates: dict[str, Any] | None = None,
        reset_attempts: bool = True,
        clear_idempotency_key: bool = False,
    ) -> BackgroundJob:
        """Move a terminal/non-running job back to ``queued`` for another try.

        Optionally merge ``payload_updates`` (e.g. higher ``max_tokens`` /
        ``text_limit``) and reset attempts. When ``clear_idempotency_key`` is
        set, any idempotency rows pointing at this job are removed so a later
        ``submit`` with the same key creates a fresh job instead of reusing.
        """
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.status == "running":
            raise RuntimeError(f"cannot requeue running job {job_id}")
        payload = dict(job.payload)
        if payload_updates:
            payload.update(payload_updates)
        now = _iso()
        with self.connection:
            self.connection.execute(
                """
                UPDATE background_jobs
                SET status = 'queued',
                    payload_json = ?,
                    attempts = CASE WHEN ? THEN 0 ELSE attempts END,
                    error = NULL,
                    result_json = NULL,
                    locked_by = NULL,
                    locked_at = NULL,
                    available_at = ?,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    1 if reset_attempts else 0,
                    now,
                    now,
                    job_id,
                ),
            )
            if clear_idempotency_key:
                self.connection.execute(
                    "DELETE FROM job_idempotency WHERE job_id = ?",
                    (job_id,),
                )
        updated = self.get(job_id)
        assert updated is not None
        return updated

    def get(self, job_id: str) -> BackgroundJob | None:
        row = self.connection.execute(
            "SELECT * FROM background_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
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
                    json.dumps(result, ensure_ascii=False, sort_keys=True)
                    if result is not None
                    else None,
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
