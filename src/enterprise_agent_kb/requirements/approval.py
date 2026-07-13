from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any

from .impact import RequirementImpactAnalyzer
from .repository import RequirementRepository, utc_now
from .resolver import RequirementResolver


RISKY_OVERRIDE_TYPES = {"loosen", "disable", "exception"}


class RequirementApprovalService:
    """MVP approval and review service for risky requirement changes.

    The service is deliberately deterministic and database-backed. It does not implement
    a full workflow engine; it provides the minimum governance layer needed to surface
    risky requirement overlays, create approval requests, approve/reject them, and update
    the corresponding requirement_overrides when an approval is granted.
    """

    def __init__(self, repo: RequirementRepository):
        self.repo = repo

    @classmethod
    def from_root(cls, root: Path) -> "RequirementApprovalService":
        return cls(RequirementRepository(root))

    def build_review_report(self, project_id: str | None = None) -> dict[str, Any]:
        items = self.scan_review_items(project_id=project_id)
        approvals = self.list_approvals(project_id=project_id)
        return {
            "project_id": project_id,
            "summary": self._summarize(items, approvals),
            "review_items": items,
            "approvals": approvals,
        }

    def scan_review_items(self, project_id: str | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        items.extend(self._scan_risky_overrides(project_id=project_id))
        items.extend(self._scan_effective_requirement_issues(project_id=project_id))
        return sorted(items, key=lambda item: (item.get("project_id") or "", item.get("severity_rank", 99), item.get("source_id") or ""))

    def create_approval_request(
        self,
        *,
        target_type: str,
        target_id: str,
        project_id: str | None = None,
        atom_id: str | None = None,
        variant_id: str | None = None,
        override_id: str | None = None,
        risk_level: str = "medium",
        reason: str | None = None,
        requested_by: str | None = None,
        evidence_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        approval_id = f"APR-{target_type}-{target_id}".replace("/", "-")
        with closing(self.repo.connection()) as connection:
            connection.execute(
                """
                INSERT INTO requirement_approvals (
                    approval_id, target_type, target_id, project_id, atom_id, variant_id,
                    override_id, risk_level, approval_status, reason, requested_by,
                    approver, evidence_id, created_at, updated_at, submitted_at, decided_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'submitted', ?, ?, NULL, ?, ?, ?, ?, NULL)
                ON CONFLICT(approval_id) DO UPDATE SET
                    project_id=excluded.project_id,
                    atom_id=excluded.atom_id,
                    variant_id=excluded.variant_id,
                    override_id=excluded.override_id,
                    risk_level=excluded.risk_level,
                    approval_status='submitted',
                    reason=excluded.reason,
                    requested_by=excluded.requested_by,
                    evidence_id=COALESCE(excluded.evidence_id, requirement_approvals.evidence_id),
                    updated_at=excluded.updated_at,
                    submitted_at=excluded.submitted_at,
                    decided_at=NULL
                """,
                (
                    approval_id,
                    target_type,
                    target_id,
                    project_id,
                    atom_id,
                    variant_id,
                    override_id,
                    risk_level,
                    reason,
                    requested_by,
                    evidence_id,
                    now,
                    now,
                    now,
                ),
            )
            self._insert_event(connection, approval_id, "submitted", requested_by, reason)
            connection.commit()
        return self.get_approval(approval_id)

    def approve(self, approval_id: str, *, approver: str, evidence_id: str | None = None, comment: str | None = None) -> dict[str, Any]:
        approval = self.get_approval(approval_id)
        now = utc_now()
        final_evidence_id = evidence_id or approval.get("evidence_id")
        with closing(self.repo.connection()) as connection:
            connection.execute(
                """
                UPDATE requirement_approvals
                SET approval_status='approved', approver=?, evidence_id=COALESCE(?, evidence_id),
                    updated_at=?, decided_at=?
                WHERE approval_id=?
                """,
                (approver, evidence_id, now, now, approval_id),
            )
            if approval.get("override_id"):
                connection.execute(
                    """
                    UPDATE requirement_overrides
                    SET approval_status='approved', approver=?, approved_at=?,
                        evidence_id=COALESCE(?, evidence_id), updated_at=?
                    WHERE override_id=?
                    """,
                    (approver, now, final_evidence_id, now, approval["override_id"]),
                )
            self._insert_event(connection, approval_id, "approved", approver, comment)
            connection.commit()
        return self.get_approval(approval_id)

    def reject(self, approval_id: str, *, approver: str, reason: str | None = None) -> dict[str, Any]:
        approval = self.get_approval(approval_id)
        now = utc_now()
        with closing(self.repo.connection()) as connection:
            connection.execute(
                """
                UPDATE requirement_approvals
                SET approval_status='rejected', approver=?, reason=COALESCE(?, reason),
                    updated_at=?, decided_at=?
                WHERE approval_id=?
                """,
                (approver, reason, now, now, approval_id),
            )
            if approval.get("override_id"):
                connection.execute(
                    """
                    UPDATE requirement_overrides
                    SET approval_status='rejected', approver=?, updated_at=?
                    WHERE override_id=?
                    """,
                    (approver, now, approval["override_id"]),
                )
            self._insert_event(connection, approval_id, "rejected", approver, reason)
            connection.commit()
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        with closing(self.repo.connection()) as connection:
            row = connection.execute(
                "SELECT * FROM requirement_approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown approval_id: {approval_id}")
        return dict(row)

    def list_approvals(self, project_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if project_id:
            where.append("project_id = ?")
            params.append(project_id)
        if status:
            where.append("approval_status = ?")
            params.append(status)
        sql = "SELECT * FROM requirement_approvals"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC, approval_id ASC"
        with closing(self.repo.connection()) as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def build_impact_review_report(self, variant_id: str, proposed_change: dict[str, Any]) -> dict[str, Any]:
        impact = RequirementImpactAnalyzer(self.repo).analyze_variant_change(variant_id, proposed_change)
        review_items: list[dict[str, Any]] = []
        for project in impact.get("affected_projects", []):
            if not project.get("review_required"):
                continue
            review_items.append(
                {
                    "review_item_id": f"REV-IMPACT-{variant_id}-{project.get('project_id')}",
                    "review_type": "impact_review_required",
                    "source_type": "impact_analysis",
                    "source_id": variant_id,
                    "project_id": project.get("project_id"),
                    "atom_id": project.get("atom_id"),
                    "severity": "high" if project.get("test_impact", {}).get("estimated_status") == "fail_against_proposed" else "medium",
                    "severity_rank": 1 if project.get("test_impact", {}).get("estimated_status") == "fail_against_proposed" else 2,
                    "status": "pending",
                    "approval_required": True,
                    "evidence_required": False,
                    "reason": project.get("reason"),
                    "recommendation": "Create an approval request or tighten the downstream project overlay before accepting the upstream change.",
                    "context": project,
                }
            )
        return {"impact": impact, "review_items": review_items, "summary": self._summarize(review_items, [])}

    def _scan_risky_overrides(self, project_id: str | None) -> list[dict[str, Any]]:
        params: list[Any] = []
        project_filter = ""
        if project_id:
            project_filter = " AND p.owner_id = ?"
            params.append(project_id)
        placeholders = ",".join("?" for _ in RISKY_OVERRIDE_TYPES)
        params = [*sorted(RISKY_OVERRIDE_TYPES), *params]
        with closing(self.repo.connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT o.*, p.owner_id AS project_id
                FROM requirement_overrides o
                JOIN requirement_profiles p ON p.profile_id = o.profile_id
                WHERE o.override_type IN ({placeholders})
                  AND p.profile_type = 'project_overlay'
                  AND p.owner_type = 'project'
                  AND (o.approval_status != 'approved' OR o.evidence_id IS NULL)
                  {project_filter}
                ORDER BY p.owner_id ASC, o.override_id ASC
                """,
                params,
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            evidence_missing = row["evidence_id"] is None
            severity = self._severity_for(row["risk_level"], evidence_missing=evidence_missing)
            items.append(
                {
                    "review_item_id": f"REV-OVERRIDE-{row['override_id']}",
                    "review_type": "risky_override",
                    "source_type": "override",
                    "source_id": row["override_id"],
                    "project_id": row["project_id"],
                    "atom_id": row["atom_id"],
                    "variant_id": row["new_variant_id"],
                    "override_id": row["override_id"],
                    "severity": severity,
                    "severity_rank": self._severity_rank(severity),
                    "status": "pending",
                    "approval_required": row["approval_status"] != "approved",
                    "evidence_required": evidence_missing,
                    "reason": row["reason"],
                    "recommendation": "Approve with evidence or revise the project overlay to remove the risky relaxation/exception.",
                    "context": dict(row),
                }
            )
        return items

    def _scan_effective_requirement_issues(self, project_id: str | None) -> list[dict[str, Any]]:
        project_ids = [project_id] if project_id else self._load_project_ids()
        items: list[dict[str, Any]] = []
        resolver = RequirementResolver(self.repo)
        for pid in project_ids:
            if not pid:
                continue
            try:
                effective_requirements = resolver.resolve_project(pid)
            except ValueError:
                continue
            for effective in effective_requirements:
                if effective.conflict_status == "none" and effective.verification_status == "verified":
                    continue
                severity = "high" if effective.conflict_status in {"hard_blocker", "approval_required"} else "medium"
                items.append(
                    {
                        "review_item_id": f"REV-EFFECTIVE-{pid}-{effective.atom_id}",
                        "review_type": "effective_requirement_issue",
                        "source_type": "effective_requirement",
                        "source_id": f"EFF-{pid}-{effective.atom_id}",
                        "project_id": pid,
                        "atom_id": effective.atom_id,
                        "variant_id": effective.selected_variant_id,
                        "severity": severity,
                        "severity_rank": self._severity_rank(severity),
                        "status": "pending",
                        "approval_required": effective.conflict_status == "approval_required",
                        "evidence_required": effective.verification_status != "verified",
                        "reason": f"conflict_status={effective.conflict_status}, verification_status={effective.verification_status}",
                        "recommendation": "Review the requirement resolution path, evidence binding, and approval status.",
                        "context": effective.to_dict(),
                    }
                )
        return items

    def _load_project_ids(self) -> list[str]:
        with closing(self.repo.connection()) as connection:
            rows = connection.execute("SELECT project_id FROM customer_projects ORDER BY project_id ASC").fetchall()
        return [str(row["project_id"]) for row in rows]

    def _insert_event(self, connection, approval_id: str, event_type: str, actor: str | None, comment: str | None) -> None:
        now = utc_now()
        event_id = f"APREV-{approval_id}-{event_type}-{now}"
        connection.execute(
            """
            INSERT OR REPLACE INTO requirement_approval_events (
                event_id, approval_id, event_type, actor, comment, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, approval_id, event_type, actor, comment, now),
        )

    def _summarize(self, items: list[dict[str, Any]], approvals: list[dict[str, Any]]) -> dict[str, Any]:
        review_type_counts: dict[str, int] = {}
        severity_counts: dict[str, int] = {}
        approval_status_counts: dict[str, int] = {}
        for item in items:
            review_type = str(item.get("review_type") or "unknown")
            severity = str(item.get("severity") or "unknown")
            review_type_counts[review_type] = review_type_counts.get(review_type, 0) + 1
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        for approval in approvals:
            status = str(approval.get("approval_status") or "unknown")
            approval_status_counts[status] = approval_status_counts.get(status, 0) + 1
        return {
            "review_item_count": len(items),
            "approval_count": len(approvals),
            "review_type_counts": review_type_counts,
            "severity_counts": severity_counts,
            "approval_status_counts": approval_status_counts,
            "approval_required_count": sum(1 for item in items if item.get("approval_required")),
            "evidence_required_count": sum(1 for item in items if item.get("evidence_required")),
        }

    def _severity_for(self, risk_level: str | None, *, evidence_missing: bool) -> str:
        if evidence_missing:
            return "high"
        normalized = str(risk_level or "medium").lower()
        if normalized in {"critical", "high"}:
            return "high"
        if normalized == "low":
            return "low"
        return "medium"

    def _severity_rank(self, severity: str) -> int:
        return {"high": 1, "medium": 2, "low": 3}.get(severity, 9)
