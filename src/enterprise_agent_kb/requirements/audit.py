"""Phase 6: Unified audit log bridge for the Requirement Resolver.

Writes requirement-domain events into the KB1 audit_log table so all
requirement changes (candidate/promotion/approval/baseline/ECO/import) are
traceable in a single audit trail alongside KB1 system events.

Design:
- Pure write helper, never raises (best-effort audit logging).
- Each event gets a stable event_id (REQAUDIT-{source_table}-{source_id}-{ts}).
- payload_json includes actor, action, entity ids, and diff summary.
- If audit_log table does not exist (standalone workspace), silently skips.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .repository import RequirementRepository, utc_now


class RequirementAuditLogger:
    """Write requirement events into the KB1 audit_log table."""

    def __init__(self, repo: RequirementRepository):
        self.repo = repo

    @classmethod
    def from_root(cls, root: Path) -> "RequirementAuditLogger":
        return cls(RequirementRepository(root))

    def log(
        self,
        *,
        event_type: str,
        actor: str | None = None,
        project_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str | None:
        """Write one audit event. Returns event_id or None if skipped."""
        now = utc_now()
        event_id = f"REQAUDIT-{event_type}-{now.replace(':', '').replace('-', '').replace('.', '')}"
        full_payload = {
            "actor": actor,
            "project_id": project_id,
            "domain": "requirement",
            **(payload or {}),
        }
        try:
            with self.repo._conn_ctx() as conn:
                check = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'"
                ).fetchone()
                if not check:
                    return None
                conn.execute(
                    """
                    INSERT INTO audit_log (event_id, event_type, timestamp, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (event_id, f"requirement.{event_type}", now, json.dumps(full_payload, ensure_ascii=False, sort_keys=True)),
                )
                conn.commit()
        except Exception:
            return None
        return event_id

    def list_events(
        self,
        *,
        event_type_prefix: str = "requirement.",
        limit: int = 100,
    ) -> dict[str, Any]:
        """List requirement audit events from audit_log."""
        try:
            with self.repo._conn_ctx() as conn:
                check = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'"
                ).fetchone()
                if not check:
                    return {"event_count": 0, "events": []}
                rows = conn.execute(
                    """
                    SELECT event_id, event_type, timestamp, payload_json
                    FROM audit_log
                    WHERE event_type LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (f"{event_type_prefix}%", limit),
                ).fetchall()
        except Exception:
            return {"event_count": 0, "events": []}
        events = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
            except (json.JSONDecodeError, TypeError):
                payload = {}
            events.append({
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "timestamp": row["timestamp"],
                "payload": payload,
            })
        return {"event_count": len(events), "events": events}
