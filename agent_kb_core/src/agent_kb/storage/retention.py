from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from .maintenance import KnowledgeMaintenance
from .migrations import SchemaMigrator


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class LegalHold:
    hold_id: str
    tenant_id: str
    logical_document_id: str
    reason: str
    status: str
    created_by: str
    created_at: str
    released_at: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LegalHoldStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        SchemaMigrator(connection).migrate()

    def place(
        self,
        *,
        tenant_id: str,
        logical_document_id: str,
        reason: str,
        created_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> LegalHold:
        hold = LegalHold(
            hold_id=f"hold_{uuid4().hex}",
            tenant_id=tenant_id,
            logical_document_id=logical_document_id,
            reason=reason,
            status="active",
            created_by=created_by,
            created_at=_iso(),
            released_at=None,
            metadata=dict(metadata or {}),
        )
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO legal_holds(
                    hold_id, tenant_id, logical_document_id, reason, status,
                    created_by, created_at, released_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    hold.hold_id,
                    hold.tenant_id,
                    hold.logical_document_id,
                    hold.reason,
                    hold.status,
                    hold.created_by,
                    hold.created_at,
                    json.dumps(hold.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )
        return hold

    def release(self, hold_id: str) -> None:
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE legal_holds
                SET status = 'released', released_at = ?
                WHERE hold_id = ? AND status = 'active'
                """,
                (_iso(), hold_id),
            )
        if cursor.rowcount == 0:
            raise KeyError(hold_id)

    def active_for(self, logical_document_id: str) -> list[LegalHold]:
        rows = self.connection.execute(
            """
            SELECT * FROM legal_holds
            WHERE logical_document_id = ? AND status = 'active'
            ORDER BY created_at
            """,
            (logical_document_id,),
        )
        return [_from_row(row) for row in rows]


@dataclass(frozen=True)
class RetentionPolicy:
    policy_id: str
    tenant_id: str
    retain_days: int
    statuses: tuple[str, ...] = ("deprecated", "deleted")
    dry_run: bool = True

    def __post_init__(self) -> None:
        if self.retain_days < 0:
            raise ValueError("retain_days must be non-negative")
        if not self.statuses:
            raise ValueError("at least one lifecycle status is required")


@dataclass(frozen=True)
class RetentionPlan:
    tenant_id: str
    policy_id: str
    cutoff: str
    eligible_document_ids: list[str]
    held_document_ids: list[str]
    purgeable_document_ids: list[str]
    evaluated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetentionRun:
    run_id: str
    policy_id: str
    tenant_id: str
    evaluated_count: int
    eligible_document_ids: list[str]
    held_document_ids: list[str]
    purged_document_ids: list[str]
    dry_run: bool
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RetentionManager:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        SchemaMigrator(connection).migrate()

    def plan(self, policy: RetentionPolicy, *, now: datetime | None = None) -> RetentionPlan:
        current = now or _utc_now()
        cutoff = _iso(current - timedelta(days=policy.retain_days))
        placeholders = ",".join("?" for _ in policy.statuses)
        rows = list(
            self.connection.execute(
                f"""
                SELECT logical_document_id FROM documents
                WHERE status IN ({placeholders}) AND updated_at <= ?
                ORDER BY logical_document_id
                """,
                [*policy.statuses, cutoff],
            )
        )
        eligible = [str(row["logical_document_id"]) for row in rows]
        hold_store = LegalHoldStore(self.connection)
        held = [document_id for document_id in eligible if hold_store.active_for(document_id)]
        held_set = set(held)
        purgeable = [document_id for document_id in eligible if document_id not in held_set]
        return RetentionPlan(
            tenant_id=policy.tenant_id,
            policy_id=policy.policy_id,
            cutoff=cutoff,
            eligible_document_ids=eligible,
            held_document_ids=held,
            purgeable_document_ids=purgeable,
            evaluated_at=_iso(current),
        )

    def record(
        self,
        policy: RetentionPolicy,
        plan: RetentionPlan,
        *,
        purged_document_ids: list[str] | None = None,
        held_document_ids: list[str] | None = None,
    ) -> RetentionRun:
        run = RetentionRun(
            run_id=f"ret_{uuid4().hex}",
            policy_id=policy.policy_id,
            tenant_id=policy.tenant_id,
            evaluated_count=len(plan.eligible_document_ids),
            eligible_document_ids=list(plan.eligible_document_ids),
            held_document_ids=sorted(set(held_document_ids or plan.held_document_ids)),
            purged_document_ids=sorted(set(purged_document_ids or [])),
            dry_run=policy.dry_run,
            created_at=plan.evaluated_at,
        )
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO retention_runs(
                    run_id, policy_id, tenant_id, evaluated_count,
                    eligible_json, held_json, purged_json, dry_run, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.policy_id,
                    run.tenant_id,
                    run.evaluated_count,
                    json.dumps(run.eligible_document_ids, ensure_ascii=False, sort_keys=True),
                    json.dumps(run.held_document_ids, ensure_ascii=False, sort_keys=True),
                    json.dumps(run.purged_document_ids, ensure_ascii=False, sort_keys=True),
                    int(run.dry_run),
                    run.created_at,
                ),
            )
        return run

    def execute(self, policy: RetentionPolicy, *, now: datetime | None = None) -> RetentionRun:
        plan = self.plan(policy, now=now)
        purged: list[str] = []
        if not policy.dry_run:
            maintenance = KnowledgeMaintenance(self.connection)
            for document_id in plan.purgeable_document_ids:
                maintenance.purge_document(document_id)
                purged.append(document_id)
        return self.record(policy, plan, purged_document_ids=purged)


def _from_row(row: sqlite3.Row) -> LegalHold:
    return LegalHold(
        hold_id=row["hold_id"],
        tenant_id=row["tenant_id"],
        logical_document_id=row["logical_document_id"],
        reason=row["reason"],
        status=row["status"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        released_at=row["released_at"],
        metadata=json.loads(row["metadata_json"] or "{}"),
    )
