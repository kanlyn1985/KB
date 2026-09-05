from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from agent_kb.storage.migrations import SchemaMigrator


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class DistributedRateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: float
    limit: int
    window_seconds: int

    def to_dict(self) -> dict[str, int | float | bool]:
        return asdict(self)


class SQLiteDistributedRateLimiter:
    """Cross-process fixed-window limiter for services sharing one SQLite DB."""

    def __init__(self, connection: sqlite3.Connection, *, limit: int = 60, window_seconds: int = 60) -> None:
        if limit < 1 or window_seconds < 1:
            raise ValueError("limit and window_seconds must be positive")
        self.connection = connection
        self.limit = int(limit)
        self.window_seconds = int(window_seconds)
        SchemaMigrator(connection).migrate()

    def consume(self, key: str, *, cost: int = 1, now: datetime | None = None) -> DistributedRateLimitDecision:
        if cost < 1:
            raise ValueError("cost must be positive")
        current = (now or _utc_now()).astimezone(UTC)
        epoch = int(current.timestamp())
        window_start_epoch = epoch - (epoch % self.window_seconds)
        window_start = datetime.fromtimestamp(window_start_epoch, tz=UTC)
        window_end = window_start + timedelta(seconds=self.window_seconds)
        with self.connection:
            row = self.connection.execute(
                "SELECT count FROM distributed_rate_limits WHERE bucket_key = ? AND window_start = ?",
                (key, _iso(window_start)),
            ).fetchone()
            count = int(row[0]) if row else 0
            allowed = count + cost <= self.limit
            if allowed:
                self.connection.execute(
                    """
                    INSERT INTO distributed_rate_limits(bucket_key, window_start, count, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(bucket_key, window_start) DO UPDATE SET
                        count = excluded.count,
                        updated_at = excluded.updated_at
                    """,
                    (key, _iso(window_start), count + cost, _iso(current)),
                )
                count += cost
            self.connection.execute(
                "DELETE FROM distributed_rate_limits WHERE window_start < ?",
                (_iso(window_start - timedelta(seconds=self.window_seconds * 2)),),
            )
        return DistributedRateLimitDecision(
            allowed=allowed,
            remaining=max(0, self.limit - count),
            retry_after_seconds=0.0 if allowed else max(0.0, (window_end - current).total_seconds()),
            limit=self.limit,
            window_seconds=self.window_seconds,
        )


@dataclass(frozen=True)
class WorkerRecord:
    worker_id: str
    tenant_id: str
    status: str
    capabilities: list[str]
    heartbeat_at: str
    expires_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SQLiteWorkerRegistry:
    """Shared worker heartbeat and capability registry."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        SchemaMigrator(connection).migrate()

    def heartbeat(
        self,
        worker_id: str,
        *,
        tenant_id: str,
        capabilities: list[str] | None = None,
        status: str = "ready",
        lease_seconds: int = 90,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> WorkerRecord:
        current = now or _utc_now()
        expires = current + timedelta(seconds=max(1, int(lease_seconds)))
        record = WorkerRecord(
            worker_id=worker_id,
            tenant_id=tenant_id,
            status=status,
            capabilities=sorted(set(capabilities or [])),
            heartbeat_at=_iso(current),
            expires_at=_iso(expires),
            metadata=dict(metadata or {}),
        )
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO worker_heartbeats(
                    worker_id, tenant_id, status, capabilities_json,
                    heartbeat_at, expires_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    tenant_id = excluded.tenant_id,
                    status = excluded.status,
                    capabilities_json = excluded.capabilities_json,
                    heartbeat_at = excluded.heartbeat_at,
                    expires_at = excluded.expires_at,
                    metadata_json = excluded.metadata_json
                """,
                (
                    record.worker_id,
                    record.tenant_id,
                    record.status,
                    json.dumps(record.capabilities, ensure_ascii=False, sort_keys=True),
                    record.heartbeat_at,
                    record.expires_at,
                    json.dumps(record.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )
        return record

    def list_active(self, *, tenant_id: str | None = None, now: datetime | None = None) -> list[WorkerRecord]:
        timestamp = _iso(now or _utc_now())
        if tenant_id:
            rows = self.connection.execute(
                "SELECT * FROM worker_heartbeats WHERE tenant_id = ? AND expires_at > ? ORDER BY worker_id",
                (tenant_id, timestamp),
            )
        else:
            rows = self.connection.execute(
                "SELECT * FROM worker_heartbeats WHERE expires_at > ? ORDER BY tenant_id, worker_id",
                (timestamp,),
            )
        return [_worker_from_row(row) for row in rows]

    def prune_expired(self, *, now: datetime | None = None) -> int:
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM worker_heartbeats WHERE expires_at <= ?",
                (_iso(now or _utc_now()),),
            )
        return int(cursor.rowcount)


def _worker_from_row(row: sqlite3.Row) -> WorkerRecord:
    return WorkerRecord(
        worker_id=row["worker_id"],
        tenant_id=row["tenant_id"],
        status=row["status"],
        capabilities=json.loads(row["capabilities_json"] or "[]"),
        heartbeat_at=row["heartbeat_at"],
        expires_at=row["expires_at"],
        metadata=json.loads(row["metadata_json"] or "{}"),
    )
