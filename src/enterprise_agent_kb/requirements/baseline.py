from __future__ import annotations

import json
import re
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .compliance import RequirementComplianceService
from .repository import RequirementRepository, utc_now
from .resolver import RequirementResolver


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return value.strip("-") or "baseline"


def _signature(payload: dict[str, Any]) -> str:
    comparable = {
        "atom_id": payload.get("atom_id"),
        "selected_variant_id": payload.get("selected_variant_id"),
        "effective_requirement_text": payload.get("effective_requirement_text"),
        "operator": payload.get("operator"),
        "value_numeric": payload.get("value_numeric"),
        "value_text": payload.get("value_text"),
        "unit": payload.get("unit"),
        "condition_json": payload.get("condition_json") or {},
        "conflict_status": payload.get("conflict_status"),
        "verification_status": payload.get("verification_status"),
        "approval_status": payload.get("approval_status"),
    }
    return _json(comparable)


@dataclass(frozen=True)
class FrozenBaseline:
    baseline_id: str
    project_id: str
    baseline_version: str
    status: str
    requirement_count: int
    conflict_count: int
    verification_gap_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "project_id": self.project_id,
            "baseline_version": self.baseline_version,
            "status": self.status,
            "requirement_count": self.requirement_count,
            "conflict_count": self.conflict_count,
            "verification_gap_count": self.verification_gap_count,
        }


class RequirementBaselineService:
    """Freeze, compare, and audit project requirement baselines.

    A baseline is an immutable snapshot of resolved EffectiveRequirement rows for one
    project. It is derived state: it records the resolved requirements at a decision
    point, but does not replace profiles, variants, approvals, or evidence bindings.
    """

    def __init__(self, repo: RequirementRepository):
        self.repo = repo
        self.repo.initialize_schema()

    @classmethod
    def from_root(cls, root: Path) -> "RequirementBaselineService":
        return cls(RequirementRepository(root))

    def freeze_project_baseline(
        self,
        project_id: str,
        *,
        baseline_name: str | None = None,
        baseline_version: str | None = None,
        parent_baseline_id: str | None = None,
        source_type: str = "manual_freeze",
        source_id: str | None = None,
        frozen_by: str | None = None,
        comment: str | None = None,
    ) -> dict[str, Any]:
        requirements = RequirementResolver(self.repo).resolve_project(project_id)
        if not requirements:
            raise ValueError(f"no requirements could be resolved for project_id: {project_id}")
        requirement_payloads = [req.to_dict() for req in requirements]
        conflict_count = sum(1 for req in requirements if req.conflict_status != "none")
        verification_gap_count = sum(1 for req in requirements if req.verification_status != "verified")
        compliance_summary = self._build_compliance_summary(project_id)

        rows = []
        for payload in requirement_payloads:
            atom_id = str(payload["atom_id"])
            rows.append(
                {
                    "baseline_id": None,  # filled after version is resolved in-transaction
                    "item_id": None,
                    "project_id": project_id,
                    "atom_id": atom_id,
                    "selected_variant_id": payload.get("selected_variant_id"),
                    "effective_requirement_text": payload.get("effective_requirement_text") or "",
                    "operator": payload.get("operator"),
                    "value_numeric": payload.get("value_numeric"),
                    "value_text": payload.get("value_text"),
                    "unit": payload.get("unit"),
                    "condition_json": _json(payload.get("condition_json") or {}),
                    "conflict_status": payload.get("conflict_status"),
                    "verification_status": payload.get("verification_status"),
                    "approval_status": payload.get("approval_status"),
                    "effective_snapshot_json": _json(payload),
                    "signature": _signature(payload),
                    "created_at": None,  # filled in-transaction
                }
            )

        now = utc_now()
        with self.repo._conn_ctx() as connection:
            # Version is computed inside the connection so COUNT+INSERT are
            # atomic against the same connection. When called standalone the
            # Python sqlite3 driver auto-begins a deferred transaction on the
            # first DML; when called inside an ECO ``transaction()`` the proxy
            # guarantees a single shared connection (no concurrent writer).
            version = baseline_version or self._next_version_locked(connection, project_id)
            baseline_id = f"RBL-{_slug(project_id)}-{_slug(version)}"
            existing = connection.execute(
                "SELECT baseline_id FROM requirement_baselines WHERE baseline_id = ?",
                (baseline_id,),
            ).fetchone()
            if existing:
                raise ValueError(f"baseline already exists: {baseline_id}")
            # Backfill derived ids now that version is known.
            for row in rows:
                row["baseline_id"] = baseline_id
                row["item_id"] = f"RBLITEM-{_slug(baseline_id)}-{_slug(row['atom_id'])}"
                row["created_at"] = now
            connection.execute(
                """
                INSERT INTO requirement_baselines (
                    baseline_id, project_id, baseline_name, baseline_version,
                    parent_baseline_id, source_type, source_id, status,
                    frozen_by, frozen_at, requirement_count, conflict_count,
                    verification_gap_count, compliance_summary_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'frozen', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    baseline_id,
                    project_id,
                    baseline_name or f"{project_id} requirement baseline {version}",
                    version,
                    parent_baseline_id,
                    source_type,
                    source_id,
                    frozen_by,
                    now,
                    len(rows),
                    conflict_count,
                    verification_gap_count,
                    _json(compliance_summary),
                    now,
                    now,
                ),
            )
            if rows:
                keys = list(rows[0].keys())
                placeholders = ",".join("?" for _ in keys)
                connection.executemany(
                    f"INSERT INTO requirement_baseline_items ({','.join(keys)}) VALUES ({placeholders})",
                    [[row[key] for key in keys] for row in rows],
                )
            self._insert_event(connection, baseline_id, "frozen", frozen_by, comment or "baseline frozen")
            connection.commit()

        return {
            "status": "frozen",
            "baseline_id": baseline_id,
            "project_id": project_id,
            "baseline_version": version,
            "requirement_count": len(rows),
            "conflict_count": conflict_count,
            "verification_gap_count": verification_gap_count,
            "compliance_summary": compliance_summary,
            "items": rows,
        }

    def list_baselines(self, *, project_id: str | None = None, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        clauses = []
        params: list[Any] = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self.repo._conn_ctx() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM requirement_baselines
                {where}
                ORDER BY frozen_at DESC, baseline_id DESC
                LIMIT ?
                """,
                [*params, int(limit)],
            ).fetchall()
        baselines = [self._baseline_row_to_dict(row) for row in rows]
        return {"baseline_count": len(baselines), "baselines": baselines}

    def get_baseline(self, baseline_id: str, *, include_items: bool = True) -> dict[str, Any]:
        with self.repo._conn_ctx() as connection:
            row = connection.execute("SELECT * FROM requirement_baselines WHERE baseline_id = ?", (baseline_id,)).fetchone()
            if row is None:
                raise ValueError(f"unknown baseline_id: {baseline_id}")
            baseline = self._baseline_row_to_dict(row)
            if include_items:
                items = connection.execute(
                    """
                    SELECT * FROM requirement_baseline_items
                    WHERE baseline_id = ?
                    ORDER BY atom_id ASC
                    """,
                    (baseline_id,),
                ).fetchall()
                baseline["items"] = [self._item_row_to_dict(item) for item in items]
        return baseline

    def compare_baselines(self, base_baseline_id: str, head_baseline_id: str) -> dict[str, Any]:
        base = self.get_baseline(base_baseline_id, include_items=True)
        head = self.get_baseline(head_baseline_id, include_items=True)
        base_items = {item["atom_id"]: item for item in base.get("items", [])}
        head_items = {item["atom_id"]: item for item in head.get("items", [])}
        atoms = sorted(set(base_items) | set(head_items))
        added: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        changed: list[dict[str, Any]] = []
        unchanged: list[dict[str, Any]] = []
        for atom_id in atoms:
            b = base_items.get(atom_id)
            h = head_items.get(atom_id)
            if b is None and h is not None:
                added.append({"atom_id": atom_id, "head": h})
            elif h is None and b is not None:
                removed.append({"atom_id": atom_id, "base": b})
            elif b and h and b["signature"] != h["signature"]:
                changed.append({"atom_id": atom_id, "base": b, "head": h, "change_summary": self._summarize_item_change(b, h)})
            elif b and h:
                unchanged.append({"atom_id": atom_id, "item": h})
        return {
            "base_baseline_id": base_baseline_id,
            "head_baseline_id": head_baseline_id,
            "project_id": head.get("project_id"),
            "summary": {
                "added": len(added),
                "removed": len(removed),
                "changed": len(changed),
                "unchanged": len(unchanged),
            },
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged": unchanged,
        }

    def detect_drift(self, baseline_id: str) -> dict[str, Any]:
        baseline = self.get_baseline(baseline_id, include_items=True)
        project_id = baseline["project_id"]
        current = RequirementResolver(self.repo).resolve_project(project_id)
        current_map = {req.atom_id: req.to_dict() for req in current}
        baseline_items = {item["atom_id"]: item for item in baseline.get("items", [])}
        atoms = sorted(set(current_map) | set(baseline_items))
        drifted: list[dict[str, Any]] = []
        missing_current: list[dict[str, Any]] = []
        new_current: list[dict[str, Any]] = []
        unchanged: list[dict[str, Any]] = []
        for atom_id in atoms:
            b = baseline_items.get(atom_id)
            c = current_map.get(atom_id)
            if b is None and c is not None:
                new_current.append({"atom_id": atom_id, "current": c})
            elif c is None and b is not None:
                missing_current.append({"atom_id": atom_id, "baseline": b})
            elif b and c:
                current_sig = _signature(c)
                if current_sig != b["signature"]:
                    drifted.append({"atom_id": atom_id, "baseline": b, "current": c, "change_summary": self._summarize_snapshot_change(b, c)})
                else:
                    unchanged.append({"atom_id": atom_id})
        return {
            "baseline_id": baseline_id,
            "project_id": project_id,
            "summary": {
                "drifted": len(drifted),
                "new_current": len(new_current),
                "missing_current": len(missing_current),
                "unchanged": len(unchanged),
            },
            "drifted": drifted,
            "new_current": new_current,
            "missing_current": missing_current,
            "unchanged": unchanged,
        }

    def build_rollback_plan(self, baseline_id: str) -> dict[str, Any]:
        drift = self.detect_drift(baseline_id)
        baseline = self.get_baseline(baseline_id, include_items=True)
        actions = []
        for item in drift.get("drifted", []):
            baseline_item = item["baseline"]
            actions.append(
                {
                    "action": "restore_requirement_variant_or_overlay",
                    "atom_id": baseline_item["atom_id"],
                    "target_selected_variant_id": baseline_item.get("selected_variant_id"),
                    "target_requirement": baseline_item.get("effective_requirement_text"),
                    "note": "MVP returns a dry-run rollback plan. Apply through profile/variant change control before freezing a new baseline.",
                }
            )
        for item in drift.get("new_current", []):
            actions.append({"action": "review_new_requirement", "atom_id": item["atom_id"], "note": "Current requirement was not in the frozen baseline."})
        for item in drift.get("missing_current", []):
            actions.append({"action": "restore_missing_requirement", "atom_id": item["atom_id"], "note": "Frozen baseline item is absent from current resolver output."})
        return {
            "baseline_id": baseline_id,
            "project_id": baseline["project_id"],
            "mode": "dry_run",
            "action_count": len(actions),
            "actions": actions,
            "drift_summary": drift["summary"],
        }

    def _next_version(self, project_id: str) -> str:
        with self.repo._conn_ctx() as connection:
            return self._next_version_locked(connection, project_id)

    def _next_version_locked(self, connection, project_id: str) -> str:
        """Compute the next baseline version. Must be called inside a held
        transaction (BEGIN IMMEDIATE) to avoid concurrent COUNT/MAX races."""
        row = connection.execute(
            "SELECT COUNT(*) AS c FROM requirement_baselines WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return f"v{int(row['c']) + 1}"

    def _build_compliance_summary(self, project_id: str) -> dict[str, Any]:
        try:
            matrix = RequirementComplianceService(self.repo).build_project_matrix(project_id)
            return dict(matrix.get("summary") or {})
        except Exception as exc:  # pragma: no cover - compliance is supplemental to freeze
            return {"status": "unavailable", "error": str(exc)}

    def _insert_event(self, connection, baseline_id: str, event_type: str, actor: str | None, comment: str | None) -> None:
        now = utc_now()
        connection.execute(
            """
            INSERT INTO requirement_baseline_events (event_id, baseline_id, event_type, actor, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"RBLEVT-{_slug(baseline_id)}-{_slug(event_type)}-{int(__import__('time').time() * 1000)}", baseline_id, event_type, actor, comment, now),
        )

    def _baseline_row_to_dict(self, row) -> dict[str, Any]:
        summary_raw = row["compliance_summary_json"]
        return {
            "baseline_id": row["baseline_id"],
            "project_id": row["project_id"],
            "baseline_name": row["baseline_name"],
            "baseline_version": row["baseline_version"],
            "parent_baseline_id": row["parent_baseline_id"],
            "source_type": row["source_type"],
            "source_id": row["source_id"],
            "status": row["status"],
            "frozen_by": row["frozen_by"],
            "frozen_at": row["frozen_at"],
            "requirement_count": row["requirement_count"],
            "conflict_count": row["conflict_count"],
            "verification_gap_count": row["verification_gap_count"],
            "compliance_summary": json.loads(summary_raw) if summary_raw else {},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _item_row_to_dict(self, row) -> dict[str, Any]:
        return {
            "baseline_id": row["baseline_id"],
            "item_id": row["item_id"],
            "project_id": row["project_id"],
            "atom_id": row["atom_id"],
            "selected_variant_id": row["selected_variant_id"],
            "effective_requirement_text": row["effective_requirement_text"],
            "operator": row["operator"],
            "value_numeric": row["value_numeric"],
            "value_text": row["value_text"],
            "unit": row["unit"],
            "condition_json": json.loads(row["condition_json"]) if row["condition_json"] else {},
            "conflict_status": row["conflict_status"],
            "verification_status": row["verification_status"],
            "approval_status": row["approval_status"],
            "effective_snapshot": json.loads(row["effective_snapshot_json"]),
            "signature": row["signature"],
            "created_at": row["created_at"],
        }

    def _summarize_item_change(self, base: dict[str, Any], head: dict[str, Any]) -> dict[str, Any]:
        fields = ["selected_variant_id", "operator", "value_numeric", "value_text", "unit", "condition_json", "conflict_status", "verification_status", "approval_status"]
        changed = {field: {"base": base.get(field), "head": head.get(field)} for field in fields if base.get(field) != head.get(field)}
        return changed

    def _summarize_snapshot_change(self, baseline_item: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        fields = ["selected_variant_id", "operator", "value_numeric", "value_text", "unit", "condition_json", "conflict_status", "verification_status", "approval_status"]
        changed = {field: {"baseline": baseline_item.get(field), "current": current.get(field)} for field in fields if baseline_item.get(field) != current.get(field)}
        return changed
