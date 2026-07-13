from __future__ import annotations

import json
import re
from contextlib import closing
from pathlib import Path
from typing import Any

from .approval import RequirementApprovalService
from .baseline import RequirementBaselineService
from .impact import RequirementImpactAnalyzer
from .release_gate import RequirementReleaseGateService
from .repository import RequirementRepository, utc_now
from .resolver import RequirementResolver


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip())
    return value.strip("-") or "eco"


class RequirementEcoService:
    """Engineering Change Order service for requirement-governed projects.

    This is an MVP workflow coordinator, not a full PLM system. It coordinates the
    deterministic requirement services already present in the subsystem:

    * dry-run impact analysis for the proposed requirement variant change;
    * approval request creation and approval state tracking;
    * controlled application of the approved variant value;
    * effective requirement refresh for impacted projects;
    * post-change baseline freeze and release gate evaluation.
    """

    def __init__(self, repo: RequirementRepository):
        self.repo = repo
        self.repo.initialize_schema()

    @classmethod
    def from_root(cls, root: Path) -> "RequirementEcoService":
        return cls(RequirementRepository(root))

    def create_change_order(
        self,
        *,
        project_id: str,
        title: str,
        variant_id: str,
        proposed_change: dict[str, Any],
        change_type: str = "requirement_variant_change",
        created_by: str | None = None,
        description: str | None = None,
        auto_analyze: bool = True,
    ) -> dict[str, Any]:
        now = utc_now()
        eco_id = f"ECO-{_slug(project_id)}-{_slug(variant_id)}-{now.replace(':', '').replace('-', '').replace('.', '')}"
        with closing(self.repo.connection()) as connection:
            connection.execute(
                """
                INSERT INTO requirement_eco_orders (
                    eco_id, project_id, title, description, change_type, status,
                    target_variant_id, proposed_change_json, impact_summary_json,
                    approval_summary_json, baseline_before_id, baseline_after_id,
                    release_gate_before_id, release_gate_after_id, created_by,
                    created_at, updated_at, submitted_at, approved_at, applied_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, NULL, NULL, NULL, NULL)
                """,
                (
                    eco_id,
                    project_id,
                    title,
                    description,
                    change_type,
                    variant_id,
                    _json(proposed_change),
                    created_by,
                    now,
                    now,
                ),
            )
            self._insert_event(connection, eco_id, "created", created_by, description, {"proposed_change": proposed_change})
            connection.commit()
        if auto_analyze:
            return self.analyze_impact(eco_id, actor=created_by)
        return self.get_change_order(eco_id)

    def analyze_impact(self, eco_id: str, *, actor: str | None = None) -> dict[str, Any]:
        eco = self.get_change_order(eco_id, include_actions=False, include_events=False)
        proposed_change = eco.get("proposed_change") or {}
        variant_id = str(eco.get("target_variant_id") or "")
        impact = RequirementImpactAnalyzer(self.repo).analyze_variant_change(variant_id, proposed_change)
        summary = impact.get("summary", {})
        now = utc_now()
        actions = self._actions_from_impact(eco_id, impact, now)
        with closing(self.repo.connection()) as connection:
            connection.execute(
                """
                UPDATE requirement_eco_orders
                SET status='impact_analyzed', impact_summary_json=?, updated_at=?
                WHERE eco_id=?
                """,
                (_json(impact), now, eco_id),
            )
            connection.execute("DELETE FROM requirement_eco_actions WHERE eco_id=?", (eco_id,))
            for action in actions:
                connection.execute(
                    """
                    INSERT INTO requirement_eco_actions (
                        action_id, eco_id, action_type, project_id, atom_id, status,
                        owner, payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        action["action_id"],
                        eco_id,
                        action["action_type"],
                        action.get("project_id"),
                        action.get("atom_id"),
                        action.get("status", "open"),
                        action.get("owner"),
                        _json(action.get("payload", {})),
                        now,
                        now,
                    ),
                )
            self._insert_event(connection, eco_id, "impact_analyzed", actor, None, {"summary": summary, "action_count": len(actions)})
            connection.commit()
        return self.get_change_order(eco_id)

    def submit_for_approval(self, eco_id: str, *, submitted_by: str | None = None, reason: str | None = None) -> dict[str, Any]:
        eco = self.get_change_order(eco_id, include_actions=True, include_events=False)
        if eco.get("status") == "draft":
            eco = self.analyze_impact(eco_id, actor=submitted_by)
        approval = RequirementApprovalService(self.repo).create_approval_request(
            target_type="eco",
            target_id=eco_id,
            project_id=eco.get("project_id"),
            risk_level=self._risk_level_for_eco(eco),
            reason=reason or eco.get("title"),
            requested_by=submitted_by,
        )
        now = utc_now()
        with closing(self.repo.connection()) as connection:
            connection.execute(
                """
                UPDATE requirement_eco_orders
                SET status='approval_pending', approval_summary_json=?, updated_at=?, submitted_at=?
                WHERE eco_id=?
                """,
                (_json({"approval_id": approval["approval_id"], "approval_status": approval["approval_status"]}), now, now, eco_id),
            )
            self._insert_event(connection, eco_id, "submitted_for_approval", submitted_by, reason, {"approval_id": approval["approval_id"]})
            connection.commit()
        return self.get_change_order(eco_id)

    def approve(self, eco_id: str, *, approver: str, comment: str | None = None) -> dict[str, Any]:
        approval_id = f"APR-eco-{eco_id}"
        approval = RequirementApprovalService(self.repo).approve(approval_id, approver=approver, comment=comment)
        now = utc_now()
        with closing(self.repo.connection()) as connection:
            connection.execute(
                """
                UPDATE requirement_eco_orders
                SET status='approved', approval_summary_json=?, updated_at=?, approved_at=?
                WHERE eco_id=?
                """,
                (_json({"approval_id": approval_id, "approval_status": approval.get("approval_status"), "approver": approver}), now, now, eco_id),
            )
            self._insert_event(connection, eco_id, "approved", approver, comment, {"approval_id": approval_id})
            connection.commit()
        return self.get_change_order(eco_id)

    def apply_change(self, eco_id: str, *, applied_by: str | None = None, refresh_effective: bool = True) -> dict[str, Any]:
        eco = self.get_change_order(eco_id, include_actions=True, include_events=False)
        if eco.get("status") != "approved":
            raise ValueError(f"ECO must be approved before apply_change: {eco_id}")
        variant_id = str(eco.get("target_variant_id") or "")
        proposed = eco.get("proposed_change") or {}
        variant = self._load_variant(variant_id)
        new_value = proposed.get("value_numeric", variant.get("value_numeric"))
        new_unit = proposed.get("unit", variant.get("unit"))
        new_operator = proposed.get("operator", variant.get("operator")) or variant.get("operator")
        text = proposed.get("requirement_text") or self._render_variant_text(variant, new_operator, new_value, new_unit)
        now = utc_now()
        with closing(self.repo.connection()) as connection:
            connection.execute(
                """
                UPDATE requirement_variants
                SET operator=COALESCE(?, operator), value_numeric=COALESCE(?, value_numeric),
                    unit=COALESCE(?, unit), requirement_text=?, updated_at=?
                WHERE variant_id=?
                """,
                (new_operator, new_value, new_unit, text, now, variant_id),
            )
            self._insert_event(connection, eco_id, "change_applied", applied_by, None, {"variant_id": variant_id, "proposed_change": proposed})
            connection.execute(
                """
                UPDATE requirement_eco_orders
                SET status='applied', updated_at=?, applied_at=?
                WHERE eco_id=?
                """,
                (now, now, eco_id),
            )
            connection.commit()

        refreshed: list[dict[str, Any]] = []
        if refresh_effective:
            impact = RequirementImpactAnalyzer(self.repo).analyze_variant_change(variant_id, proposed)
            projects = sorted({item.get("project_id") for item in impact.get("affected_projects", []) if item.get("project_id")})
            resolver = RequirementResolver(self.repo)
            for project_id in projects:
                try:
                    refreshed.append({"project_id": project_id, "requirements": [item.to_dict() for item in resolver.resolve_project(str(project_id))]})
                except Exception as exc:
                    refreshed.append({"project_id": project_id, "error": str(exc)})
        eco = self.get_change_order(eco_id)
        eco["refreshed_effective_requirements"] = refreshed
        return eco

    def close_with_release_gate(
        self,
        eco_id: str,
        *,
        stage: str = "DV",
        closed_by: str | None = None,
        freeze_baseline: bool = True,
    ) -> dict[str, Any]:
        eco = self.get_change_order(eco_id, include_actions=True, include_events=False)
        if eco.get("status") not in {"applied", "gate_blocked", "closed"}:
            raise ValueError(f"ECO must be applied before close_with_release_gate: {eco_id}")
        project_id = str(eco.get("project_id"))
        baseline_payload: dict[str, Any] | None = None
        if freeze_baseline:
            baseline_payload = RequirementBaselineService(self.repo).freeze_project_baseline(
                project_id,
                baseline_name=f"{eco_id} post-change baseline",
                source_type="eco_close",
                source_id=eco_id,
                frozen_by=closed_by,
                comment=f"Baseline frozen during ECO closure: {eco_id}",
            )
        baseline_after_id = baseline_payload.get("baseline_id") if baseline_payload else eco.get("baseline_after_id")
        gate = RequirementReleaseGateService(self.repo).evaluate_project(
            project_id,
            stage=stage,
            baseline_id=baseline_after_id,
            evaluated_by=closed_by,
            persist=True,
        )
        final_status = "closed" if gate.get("readiness_status") in {"pass", "conditional_pass"} else "gate_blocked"
        now = utc_now()
        with closing(self.repo.connection()) as connection:
            connection.execute(
                """
                UPDATE requirement_eco_orders
                SET status=?, baseline_after_id=?, release_gate_after_id=?, updated_at=?, closed_at=CASE WHEN ?='closed' THEN ? ELSE closed_at END
                WHERE eco_id=?
                """,
                (final_status, baseline_after_id, gate.get("run_id"), now, final_status, now, eco_id),
            )
            self._insert_event(connection, eco_id, "release_gate_evaluated", closed_by, None, {"gate_run_id": gate.get("run_id"), "readiness_status": gate.get("readiness_status")})
            if final_status == "closed":
                self._insert_event(connection, eco_id, "closed", closed_by, None, {"baseline_id": baseline_after_id})
            connection.commit()
        payload = self.get_change_order(eco_id)
        payload["post_change_baseline"] = baseline_payload
        payload["release_gate"] = gate
        return payload

    def run_full_cycle(
        self,
        *,
        project_id: str,
        title: str,
        variant_id: str,
        proposed_change: dict[str, Any],
        actor: str | None = None,
        stage: str = "DV",
    ) -> dict[str, Any]:
        created = self.create_change_order(project_id=project_id, title=title, variant_id=variant_id, proposed_change=proposed_change, created_by=actor)
        eco_id = created["eco_id"]
        submitted = self.submit_for_approval(eco_id, submitted_by=actor)
        approved = self.approve(eco_id, approver=actor or "eco-approver")
        applied = self.apply_change(eco_id, applied_by=actor)
        closed = self.close_with_release_gate(eco_id, stage=stage, closed_by=actor)
        return {"eco_id": eco_id, "created": created, "submitted": submitted, "approved": approved, "applied": applied, "closed": closed}

    def list_change_orders(self, *, project_id: str | None = None, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with closing(self.repo.connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM requirement_eco_orders
                {where}
                ORDER BY updated_at DESC, created_at DESC, eco_id ASC
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()
        orders = [self._order_from_row(row, include_actions=False, include_events=False) for row in rows]
        return {"eco_count": len(orders), "ecos": orders}

    def get_change_order(self, eco_id: str, *, include_actions: bool = True, include_events: bool = True) -> dict[str, Any]:
        with closing(self.repo.connection()) as connection:
            row = connection.execute("SELECT * FROM requirement_eco_orders WHERE eco_id=?", (eco_id,)).fetchone()
            if row is None:
                raise ValueError(f"unknown eco_id: {eco_id}")
            payload = self._order_from_row(row, include_actions=False, include_events=False)
            if include_actions:
                actions = connection.execute(
                    "SELECT * FROM requirement_eco_actions WHERE eco_id=? ORDER BY created_at ASC, action_id ASC",
                    (eco_id,),
                ).fetchall()
                payload["actions"] = [self._action_from_row(action) for action in actions]
            if include_events:
                events = connection.execute(
                    "SELECT * FROM requirement_eco_events WHERE eco_id=? ORDER BY created_at ASC, event_id ASC",
                    (eco_id,),
                ).fetchall()
                payload["events"] = [self._event_from_row(event) for event in events]
        return payload

    def _load_variant(self, variant_id: str) -> dict[str, Any]:
        with closing(self.repo.connection()) as connection:
            row = connection.execute("SELECT * FROM requirement_variants WHERE variant_id=?", (variant_id,)).fetchone()
        if row is None:
            raise ValueError(f"unknown variant_id: {variant_id}")
        return dict(row)

    def _actions_from_impact(self, eco_id: str, impact: dict[str, Any], now: str) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for project in impact.get("affected_projects", []):
            project_id = project.get("project_id")
            atom_id = project.get("atom_id")
            if project.get("regression_test_required"):
                actions.append({
                    "action_id": f"ECOACT-{_slug(eco_id)}-{_slug(project_id)}-{_slug(atom_id)}-regression",
                    "action_type": "regression_test",
                    "project_id": project_id,
                    "atom_id": atom_id,
                    "status": "open",
                    "payload": {"reason": project.get("reason"), "test_impact": project.get("test_impact")},
                })
            if project.get("review_required"):
                actions.append({
                    "action_id": f"ECOACT-{_slug(eco_id)}-{_slug(project_id)}-{_slug(atom_id)}-review",
                    "action_type": "engineering_review",
                    "project_id": project_id,
                    "atom_id": atom_id,
                    "status": "open",
                    "payload": {"reason": project.get("reason"), "impact_type": project.get("impact_type")},
                })
        return actions

    def _risk_level_for_eco(self, eco: dict[str, Any]) -> str:
        summary = (eco.get("impact") or eco.get("impact_summary") or {}).get("summary", {})
        if summary.get("review_required_count", 0) or summary.get("regression_required_count", 0):
            return "high"
        return "medium"

    def _render_variant_text(self, variant: dict[str, Any], operator: str | None, value: Any, unit: str | None) -> str:
        base = str(variant.get("requirement_text") or variant.get("variant_id"))
        if value is None:
            return base
        parameter = variant.get("parameter_name") or variant.get("atom_id")
        return f"{parameter} {operator or ''} {value}{unit or ''}".strip()

    def _order_from_row(self, row, *, include_actions: bool, include_events: bool) -> dict[str, Any]:
        payload = dict(row)
        payload["proposed_change"] = _loads(payload.pop("proposed_change_json", None), {})
        payload["impact"] = _loads(payload.pop("impact_summary_json", None), None)
        payload["approval_summary"] = _loads(payload.pop("approval_summary_json", None), None)
        return payload

    def _action_from_row(self, row) -> dict[str, Any]:
        payload = dict(row)
        payload["payload"] = _loads(payload.pop("payload_json", None), {})
        return payload

    def _event_from_row(self, row) -> dict[str, Any]:
        payload = dict(row)
        payload["payload"] = _loads(payload.pop("payload_json", None), {})
        return payload

    def _insert_event(self, connection, eco_id: str, event_type: str, actor: str | None, comment: str | None, payload: dict[str, Any] | None = None) -> None:
        now = utc_now()
        event_id = f"ECOEV-{_slug(eco_id)}-{_slug(event_type)}-{now.replace(':', '').replace('-', '').replace('.', '')}"
        connection.execute(
            """
            INSERT INTO requirement_eco_events (event_id, eco_id, event_type, actor, comment, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, eco_id, event_type, actor, comment, _json(payload or {}), now),
        )
