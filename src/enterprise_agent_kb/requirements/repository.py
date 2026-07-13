from __future__ import annotations

import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone


class _TxnConnectionProxy:
    """Proxy wrapping a real sqlite3.Connection while a transaction is bound.

    ``commit`` and ``close`` are no-ops so that inner services (approval,
    baseline, gate, resolver) sharing the same repository do not prematurely
    commit or close the outer ECO transaction. ``rollback`` and all other
    attributes pass through to the real connection.
    """

    __slots__ = ("_real",)

    def __init__(self, real: sqlite3.Connection):
        object.__setattr__(self, "_real", real)

    def commit(self) -> None:  # no-op: outer transaction owns commit
        pass

    def close(self) -> None:  # no-op: outer transaction owns lifecycle
        pass

    def rollback(self) -> None:
        self._real.rollback()

    def __getattr__(self, name: str):
        return getattr(self._real, name)
from pathlib import Path
from typing import Any, Iterable

from ..config import AppPaths
from ..db import connect
from ..migrations import apply_pending_migrations, current_version
from .models import (
    CustomerProject,
    EffectiveRequirement,
    RequirementAtom,
    RequirementOverride,
    RequirementProfile,
    RequirementVariant,
)
from .schema import PROFILE_PRIORITY, SCHEMA_SQL


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RequirementRepository:
    def __init__(self, root: Path):
        self.root = root
        self.paths = AppPaths.from_root(root)
        self._txn_conn: sqlite3.Connection | None = None

    def connection(self) -> sqlite3.Connection | _TxnConnectionProxy:
        """Return the current transaction connection if one is active, else a
        fresh connection. When a transaction is active (via ``transaction()``
        context manager), all services sharing this repo reuse the same
        proxied connection so cross-service operations stay within one
        transaction and inner ``commit()``/``close()`` become no-ops."""
        if self._txn_conn is not None:
            return _TxnConnectionProxy(self._txn_conn)
        return connect(self.paths.db_file)

    @contextmanager
    def transaction(self):
        """Bind a single connection to this repo for the duration of the
        ``with`` block. All ``connection()`` / ``_conn_ctx()`` calls return a
        proxy over this connection, so multi-service operations (e.g. ECO
        ``apply_change`` calling resolver + variant update + approval) share
        one transaction. The proxy no-ops inner ``commit``/``close`` so only
        the outer owner commits. On exception the transaction is rolled back.
        """
        if self._txn_conn is not None:
            # Nested: yield a proxy over the outer connection, do not own it.
            yield _TxnConnectionProxy(self._txn_conn)
            return
        real = connect(self.paths.db_file)
        self._txn_conn = real
        try:
            yield _TxnConnectionProxy(real)
            real.commit()
        except Exception:
            real.rollback()
            raise
        finally:
            self._txn_conn = None
            real.close()

    @contextmanager
    def _conn_ctx(self):
        """Connection context manager. If a transaction is bound, yields a
        proxy (commit/close are no-ops) without closing. Otherwise opens and
        closes a fresh connection."""
        if self._txn_conn is not None:
            yield _TxnConnectionProxy(self._txn_conn)
            return
        with closing(connect(self.paths.db_file)) as conn:
            yield conn

    def initialize_schema(self) -> list[str]:
        """Create or upgrade requirement management tables via the KB1
        migration framework (PRAGMA user_version + migrations/NNN_*.sql).

        Applies all pending migrations whose version > current user_version,
        including 002_requirement_program.sql (the 28 requirement_* tables).
        Falls back to the legacy SCHEMA_SQL executescript path if the
        migrations directory cannot be located (e.g. running from a source
        layout where the package migrations/ dir is not co-located).
        """
        self.paths.db_dir.mkdir(parents=True, exist_ok=True)
        migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
        with self._conn_ctx() as connection:
            if migrations_dir.is_dir():
                apply_pending_migrations(connection, migrations_dir)
            else:
                # Fallback: legacy inline SCHEMA_SQL path (idempotent).
                connection.executescript(SCHEMA_SQL)
            connection.commit()
            rows = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name LIKE 'requirement_%'
                   OR name IN ('customers', 'customer_projects', 'effective_requirements')
                ORDER BY name
                """
            ).fetchall()
            return [row["name"] for row in rows]

    def load_project(self, project_id: str) -> CustomerProject:
        with self._conn_ctx() as connection:
            row = connection.execute(
                "SELECT * FROM customer_projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown project_id: {project_id}")
        return CustomerProject(
            project_id=row["project_id"],
            customer_id=row["customer_id"],
            project_code=row["project_code"],
            product_family=row["product_family"],
            product_variant_id=row["product_variant_id"],
            platform_id=row["platform_id"],
            lifecycle_status=row["lifecycle_status"],
        )

    def load_atom(self, atom_id: str) -> RequirementAtom:
        with self._conn_ctx() as connection:
            row = connection.execute(
                "SELECT * FROM requirement_atoms WHERE atom_id = ?",
                (atom_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown atom_id: {atom_id}")
        return self._atom_from_row(row)

    def load_atoms_for_profiles(self, profile_ids: Iterable[str]) -> list[RequirementAtom]:
        profile_ids = list(profile_ids)
        if not profile_ids:
            return []
        placeholders = ",".join("?" for _ in profile_ids)
        with self._conn_ctx() as connection:
            rows = connection.execute(
                f"""
                SELECT DISTINCT a.*
                FROM requirement_atoms a
                JOIN requirement_variants v ON v.atom_id = a.atom_id
                WHERE v.profile_id IN ({placeholders}) AND v.status = 'active'
                ORDER BY a.domain, a.category, a.canonical_name
                """,
                profile_ids,
            ).fetchall()
        return [self._atom_from_row(row) for row in rows]

    def find_project_profile(self, project_id: str) -> RequirementProfile | None:
        with self._conn_ctx() as connection:
            row = connection.execute(
                """
                SELECT * FROM requirement_profiles
                WHERE owner_type = 'project'
                  AND owner_id = ?
                  AND profile_type = 'project_overlay'
                  AND status = 'active'
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        return self._profile_from_row(row) if row else None

    def load_profile(self, profile_id: str) -> RequirementProfile:
        with self._conn_ctx() as connection:
            row = connection.execute(
                "SELECT * FROM requirement_profiles WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown profile_id: {profile_id}")
        return self._profile_from_row(row)

    def expand_profile_inheritance(self, profile_id: str) -> list[RequirementProfile]:
        seen: set[str] = set()
        ordered: list[RequirementProfile] = []

        def visit(current_id: str) -> None:
            if current_id in seen:
                return
            seen.add(current_id)
            with self._conn_ctx() as connection:
                parent_rows = connection.execute(
                    """
                    SELECT parent_profile_id
                    FROM requirement_profile_inheritance
                    WHERE child_profile_id = ? AND status = 'active'
                    ORDER BY priority ASC, parent_profile_id ASC
                    """,
                    (current_id,),
                ).fetchall()
            for parent in parent_rows:
                visit(parent["parent_profile_id"])
            ordered.append(self.load_profile(current_id))

        visit(profile_id)
        return sorted(ordered, key=lambda p: (p.priority, p.profile_id))

    def load_variants(self, atom_id: str, profile_ids: list[str]) -> list[RequirementVariant]:
        if not profile_ids:
            return []
        placeholders = ",".join("?" for _ in profile_ids)
        with self._conn_ctx() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM requirement_variants
                WHERE atom_id = ? AND profile_id IN ({placeholders}) AND status = 'active'
                ORDER BY priority ASC, updated_at DESC, variant_id ASC
                """,
                [atom_id, *profile_ids],
            ).fetchall()
        return [self._variant_from_row(row) for row in rows]

    def load_overrides(self, atom_id: str, profile_ids: list[str]) -> list[RequirementOverride]:
        if not profile_ids:
            return []
        placeholders = ",".join("?" for _ in profile_ids)
        with self._conn_ctx() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM requirement_overrides
                WHERE atom_id = ? AND profile_id IN ({placeholders})
                ORDER BY created_at ASC, override_id ASC
                """,
                [atom_id, *profile_ids],
            ).fetchall()
        return [self._override_from_row(row) for row in rows]

    def save_effective_requirement(self, effective: EffectiveRequirement, code_version: str | None = None) -> None:
        selected = effective.selected_variant_id
        effective_id = f"EFF-{effective.project_id}-{effective.atom_id}"
        now = utc_now()
        with self._conn_ctx() as connection:
            connection.execute(
                """
                INSERT INTO effective_requirements (
                    effective_id, project_id, atom_id, selected_variant_id,
                    effective_requirement_text, parameter_name, operator,
                    value_numeric, value_text, unit, condition_json,
                    resolution_path_json, conflict_status, verification_status,
                    approval_status, computed_at, code_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, atom_id) DO UPDATE SET
                    selected_variant_id=excluded.selected_variant_id,
                    effective_requirement_text=excluded.effective_requirement_text,
                    operator=excluded.operator,
                    value_numeric=excluded.value_numeric,
                    value_text=excluded.value_text,
                    unit=excluded.unit,
                    condition_json=excluded.condition_json,
                    resolution_path_json=excluded.resolution_path_json,
                    conflict_status=excluded.conflict_status,
                    verification_status=excluded.verification_status,
                    approval_status=excluded.approval_status,
                    computed_at=excluded.computed_at,
                    code_version=excluded.code_version
                """,
                (
                    effective_id,
                    effective.project_id,
                    effective.atom_id,
                    selected,
                    effective.effective_requirement_text,
                    None,
                    effective.operator,
                    effective.value_numeric,
                    effective.value_text,
                    effective.unit,
                    json.dumps(effective.condition_json, ensure_ascii=False, sort_keys=True),
                    json.dumps([step.to_dict() for step in effective.resolution_path], ensure_ascii=False),
                    effective.conflict_status,
                    effective.verification_status,
                    effective.approval_status,
                    now,
                    code_version,
                ),
            )
            connection.commit()

    def insert_many(self, table: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        keys = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in keys)
        columns = ", ".join(keys)
        sql = f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})"
        with self._conn_ctx() as connection:
            connection.executemany(sql, [[row.get(key) for key in keys] for row in rows])
            connection.commit()
        return len(rows)

    def _atom_from_row(self, row: sqlite3.Row) -> RequirementAtom:
        return RequirementAtom(
            atom_id=row["atom_id"],
            domain=row["domain"],
            category=row["category"],
            canonical_name=row["canonical_name"],
            parameter_name=row["parameter_name"],
            default_unit=row["default_unit"],
            constraint_kind=row["constraint_kind"],
        )

    def _profile_from_row(self, row: sqlite3.Row) -> RequirementProfile:
        profile_type = row["profile_type"]
        return RequirementProfile(
            profile_id=row["profile_id"],
            profile_type=profile_type,
            owner_type=row["owner_type"],
            owner_id=row["owner_id"],
            name=row["name"],
            version=row["version"],
            status=row["status"],
            priority=PROFILE_PRIORITY.get(profile_type, 999),
        )

    def _variant_from_row(self, row: sqlite3.Row) -> RequirementVariant:
        condition_raw = row["condition_json"]
        return RequirementVariant(
            variant_id=row["variant_id"],
            atom_id=row["atom_id"],
            profile_id=row["profile_id"],
            requirement_text=row["requirement_text"],
            operator=row["operator"],
            value_numeric=row["value_numeric"],
            value_text=row["value_text"],
            unit=row["unit"],
            condition_json=json.loads(condition_raw) if condition_raw else {},
            mandatory_level=row["mandatory_level"],
            priority=row["priority"] or 100,
            evidence_id=row["evidence_id"],
            fact_id=row["fact_id"],
            document_id=row["document_id"],
            status=row["status"],
        )

    def _override_from_row(self, row: sqlite3.Row) -> RequirementOverride:
        return RequirementOverride(
            override_id=row["override_id"],
            profile_id=row["profile_id"],
            atom_id=row["atom_id"],
            base_variant_id=row["base_variant_id"],
            new_variant_id=row["new_variant_id"],
            override_type=row["override_type"],
            evidence_id=row["evidence_id"],
            approval_status=row["approval_status"],
            risk_level=row["risk_level"],
        )
