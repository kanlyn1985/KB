from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agent_kb.storage.migrations import SchemaMigrator


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    tenant_id: str
    principal_id: str
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    metadata: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLog:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        SchemaMigrator(connection).migrate()

    def record(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        outcome: str = "success",
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=f"audit_{uuid4().hex}",
            tenant_id=tenant_id,
            principal_id=principal_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            metadata=dict(metadata or {}),
            created_at=_utc_now_iso(),
        )
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO audit_events(
                    event_id, tenant_id, principal_id, action, resource_type,
                    resource_id, outcome, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.tenant_id,
                    event.principal_id,
                    event.action,
                    event.resource_type,
                    event.resource_id,
                    event.outcome,
                    json.dumps(event.metadata, ensure_ascii=False, sort_keys=True),
                    event.created_at,
                ),
            )
        return event

    def list(
        self,
        *,
        tenant_id: str,
        principal_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        if principal_id:
            rows = self.connection.execute(
                """
                SELECT * FROM audit_events
                WHERE tenant_id = ? AND principal_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (tenant_id, principal_id, max(1, int(limit))),
            )
        else:
            rows = self.connection.execute(
                """
                SELECT * FROM audit_events
                WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?
                """,
                (tenant_id, max(1, int(limit))),
            )
        return [_from_row(row) for row in rows]


def _from_row(row: sqlite3.Row) -> AuditEvent:
    return AuditEvent(
        event_id=row["event_id"],
        tenant_id=row["tenant_id"],
        principal_id=row["principal_id"],
        action=row["action"],
        resource_type=row["resource_type"],
        resource_id=row["resource_id"],
        outcome=row["outcome"],
        metadata=json.loads(row["metadata_json"] or "{}"),
        created_at=row["created_at"],
    )
