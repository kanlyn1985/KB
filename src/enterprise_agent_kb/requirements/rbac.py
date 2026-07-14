"""Phase 6: RBAC permission model for the Requirement Resolver.

Four roles with escalating permissions:

  viewer   : read-only (list, show, resolve queries)
  reviewer : viewer + promote/reject candidates, review extraction batches
  approver : reviewer + approve/reject approvals, freeze baselines
  admin    : approver + apply ECO, close ECO, create ECO, import packages

Design:
- Pure-Python permission checks, no DB writes, no LLM, never raises (returns
  bool). The caller decides how to handle denial.
- Permission checks are enforced at the service layer (eco/approval/baseline/
  extraction) via the require_permission() decorator or explicit check.
- Roles are stored in requirement_users table (user_id, role, project_id).
  project_id NULL means global role; non-NULL means project-scoped.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .repository import RequirementRepository, utc_now

# Role hierarchy: admin > approver > reviewer > viewer
ROLE_VIEWER = "viewer"
ROLE_REVIEWER = "reviewer"
ROLE_APPROVER = "approver"
ROLE_ADMIN = "admin"

ROLE_LEVELS: dict[str, int] = {
    ROLE_VIEWER: 0,
    ROLE_REVIEWER: 1,
    ROLE_APPROVER: 2,
    ROLE_ADMIN: 3,
}

# Permission -> minimum role level required
PERMISSIONS: dict[str, int] = {
    # Read operations
    "requirement.view": ROLE_LEVELS[ROLE_VIEWER],
    "requirement.resolve": ROLE_LEVELS[ROLE_VIEWER],
    "requirement.list_candidates": ROLE_LEVELS[ROLE_VIEWER],
    # Candidate review
    "requirement.promote_candidate": ROLE_LEVELS[ROLE_REVIEWER],
    "requirement.reject_candidate": ROLE_LEVELS[ROLE_REVIEWER],
    "requirement.extract_candidates": ROLE_LEVELS[ROLE_REVIEWER],
    # Approval governance
    "requirement.approve": ROLE_LEVELS[ROLE_APPROVER],
    "requirement.reject_approval": ROLE_LEVELS[ROLE_APPROVER],
    "requirement.freeze_baseline": ROLE_LEVELS[ROLE_APPROVER],
    # ECO and admin operations
    "requirement.create_eco": ROLE_LEVELS[ROLE_ADMIN],
    "requirement.apply_eco": ROLE_LEVELS[ROLE_ADMIN],
    "requirement.close_eco": ROLE_LEVELS[ROLE_ADMIN],
    "requirement.import_package": ROLE_LEVELS[ROLE_ADMIN],
}


@dataclass(frozen=True)
class UserInfo:
    user_id: str
    role: str
    project_id: str | None
    display_name: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "role": self.role,
            "project_id": self.project_id,
            "display_name": self.display_name,
        }


class RequirementRbacService:
    """Role-based access control for the Requirement Resolver.

    Manages user-role assignments and permission checks. Project-scoped roles
    (project_id non-NULL) override global roles (project_id NULL) for that
    project. Global roles apply to all projects without a scoped override.
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS requirement_users (
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        project_id TEXT,
        display_name TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, project_id)
    );
    """

    def __init__(self, repo: RequirementRepository):
        self.repo = repo
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self.repo._conn_ctx() as conn:
            conn.execute(self.SCHEMA_SQL)
            conn.commit()

    @classmethod
    def from_root(cls, root: Path) -> "RequirementRbacService":
        return cls(RequirementRepository(root))

    def assign_role(self, *, user_id: str, role: str, project_id: str | None = None, display_name: str | None = None) -> dict[str, Any]:
        if role not in ROLE_LEVELS:
            raise ValueError(f"unknown role: {role}; valid: {list(ROLE_LEVELS)}")
        now = utc_now()
        # Use COALESCE to handle NULL project_id in conflict target (SQLite
        # NULL != NULL in ON CONFLICT, so we normalize to empty string for the
        # PK, storing NULL back in the row).
        pk_project = project_id if project_id is not None else ""
        with self.repo._conn_ctx() as conn:
            conn.execute(
                """
                INSERT INTO requirement_users (user_id, role, project_id, display_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, project_id) DO UPDATE SET
                    role=excluded.role, display_name=excluded.display_name, updated_at=excluded.updated_at
                """,
                (user_id, role, project_id, display_name, now, now),
            )
            # If project_id is NULL, ON CONFLICT won't match (NULL!=NULL), so
            # use a DELETE-then-INSERT pattern for global roles.
            if project_id is None:
                conn.execute(
                    "DELETE FROM requirement_users WHERE user_id=? AND project_id IS NULL",
                    (user_id,),
                )
                conn.execute(
                    """
                    INSERT INTO requirement_users (user_id, role, project_id, display_name, created_at, updated_at)
                    VALUES (?, ?, NULL, ?, ?, ?)
                    """,
                    (user_id, role, display_name, now, now),
                )
            conn.commit()
        return {"user_id": user_id, "role": role, "project_id": project_id, "status": "assigned"}

    def get_user_role(self, user_id: str, project_id: str | None = None) -> str:
        """Get the effective role for a user on a project.
        Project-scoped role takes priority; falls back to global role (project_id=NULL);
        falls back to viewer if no assignment exists."""
        with self.repo._conn_ctx() as conn:
            if project_id:
                row = conn.execute(
                    "SELECT role FROM requirement_users WHERE user_id=? AND project_id=?",
                    (user_id, project_id),
                ).fetchone()
                if row:
                    return row["role"]
            row = conn.execute(
                "SELECT role FROM requirement_users WHERE user_id=? AND project_id IS NULL",
                (user_id,),
            ).fetchone()
            if row:
                return row["role"]
        return ROLE_VIEWER

    def has_permission(self, user_id: str, permission: str, project_id: str | None = None) -> bool:
        if permission not in PERMISSIONS:
            return False
        role = self.get_user_role(user_id, project_id)
        user_level = ROLE_LEVELS.get(role, 0)
        return user_level >= PERMISSIONS[permission]

    def require_permission(self, user_id: str, permission: str, project_id: str | None = None) -> None:
        if not self.has_permission(user_id, permission, project_id):
            role = self.get_user_role(user_id, project_id)
            raise PermissionError(
                f"user '{user_id}' (role={role}) lacks permission '{permission}'" + (f" on project '{project_id}'" if project_id else "")
            )

    def list_users(self, *, project_id: str | None = None) -> dict[str, Any]:
        where = ""
        params: list[Any] = []
        if project_id:
            where = "WHERE project_id = ? OR project_id IS NULL"
            params.append(project_id)
        with self.repo._conn_ctx() as conn:
            rows = conn.execute(
                f"SELECT user_id, role, project_id, display_name FROM requirement_users {where} ORDER BY user_id",
                params,
            ).fetchall()
        users = [UserInfo(row["user_id"], row["role"], row["project_id"], row["display_name"]).to_dict() for row in rows]
        return {"user_count": len(users), "users": users}
