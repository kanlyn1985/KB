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
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class LeaderLease:
    lease_name: str
    holder_id: str
    acquired_at: str
    renewed_at: str
    expires_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def active_at(self, now: datetime | None = None) -> bool:
        return _parse(self.expires_at) > (now or _utc_now()).astimezone(UTC)


class SQLiteLeaderLeaseStore:
    """Cross-process leader lease for one SQLite coordination database.

    The lease is suitable for embedded single-node deployments and scheduler
    election. Large horizontally distributed deployments should replace this
    adapter with Redis, Consul, etcd, or the platform-native lease API while
    preserving the same acquire/renew/release contract.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        SchemaMigrator(connection).migrate()

    def acquire(
        self,
        lease_name: str,
        holder_id: str,
        *,
        lease_seconds: int = 30,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> LeaderLease | None:
        name = str(lease_name or "").strip()
        holder = str(holder_id or "").strip()
        if not name or not holder:
            raise ValueError("lease_name and holder_id are required")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        current = (now or _utc_now()).astimezone(UTC)
        expires = current + timedelta(seconds=int(lease_seconds))
        with self.connection:
            row = self.connection.execute(
                "SELECT * FROM leader_leases WHERE lease_name = ?",
                (name,),
            ).fetchone()
            if row is not None:
                existing = _from_row(row)
                if existing.holder_id != holder and existing.active_at(current):
                    return None
                acquired_at = existing.acquired_at if existing.holder_id == holder else _iso(current)
            else:
                acquired_at = _iso(current)
            self.connection.execute(
                """
                INSERT INTO leader_leases(
                    lease_name, holder_id, acquired_at, renewed_at, expires_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(lease_name) DO UPDATE SET
                    holder_id = excluded.holder_id,
                    acquired_at = excluded.acquired_at,
                    renewed_at = excluded.renewed_at,
                    expires_at = excluded.expires_at,
                    metadata_json = excluded.metadata_json
                """,
                (
                    name,
                    holder,
                    acquired_at,
                    _iso(current),
                    _iso(expires),
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
        return self.get(name)

    def renew(
        self,
        lease_name: str,
        holder_id: str,
        *,
        lease_seconds: int = 30,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> LeaderLease | None:
        current = (now or _utc_now()).astimezone(UTC)
        existing = self.get(lease_name)
        if existing is None or existing.holder_id != holder_id or not existing.active_at(current):
            return None
        return self.acquire(
            lease_name,
            holder_id,
            lease_seconds=lease_seconds,
            metadata=existing.metadata if metadata is None else metadata,
            now=current,
        )

    def release(self, lease_name: str, holder_id: str) -> bool:
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM leader_leases WHERE lease_name = ? AND holder_id = ?",
                (lease_name, holder_id),
            )
        return cursor.rowcount == 1

    def get(self, lease_name: str) -> LeaderLease | None:
        row = self.connection.execute(
            "SELECT * FROM leader_leases WHERE lease_name = ?",
            (lease_name,),
        ).fetchone()
        return _from_row(row) if row is not None else None

    def prune_expired(self, *, now: datetime | None = None) -> int:
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM leader_leases WHERE expires_at <= ?",
                (_iso((now or _utc_now()).astimezone(UTC)),),
            )
        return int(cursor.rowcount)


def _from_row(row: sqlite3.Row) -> LeaderLease:
    return LeaderLease(
        lease_name=row["lease_name"],
        holder_id=row["holder_id"],
        acquired_at=row["acquired_at"],
        renewed_at=row["renewed_at"],
        expires_at=row["expires_at"],
        metadata=json.loads(row["metadata_json"] or "{}"),
    )
