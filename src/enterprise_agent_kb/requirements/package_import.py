from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .extraction import RequirementExtractionService
from .repository import RequirementRepository, utc_now
from .resolver import RequirementResolver


@dataclass(frozen=True)
class RequirementPackageSource:
    name: str
    text: str
    source_type: str = "package_text"
    source_id: str | None = None
    document_id: str | None = None
    evidence_id: str | None = None
    fact_id: str | None = None


class RequirementPackageImportService:
    """Import customer/project requirement packages into review-first candidates.

    The service deliberately defaults to review-only import. It can optionally promote
    extracted candidates into a selected profile for MVP demonstrations, but the safe
    path is: import package -> review candidates -> promote selected candidates.
    """

    def __init__(self, repo: RequirementRepository):
        self.repo = repo

    @classmethod
    def from_root(cls, root: Path) -> "RequirementPackageImportService":
        return cls(RequirementRepository(root))

    def import_project_package(
        self,
        *,
        customer_id: str,
        project_id: str,
        project_code: str,
        product_family: str,
        sources: Iterable[dict[str, Any] | RequirementPackageSource],
        customer_name: str | None = None,
        package_name: str | None = None,
        profile_scope: str = "project_overlay",
        auto_promote: bool = False,
        promoted_by: str | None = None,
        refresh_effective: bool = False,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Import a customer project package and return candidate/promotion summary.

        profile_scope controls where promoted variants land:
        - project_overlay: project-specific delta profile, default and safest.
        - customer_common: customer reusable common profile.
        """
        self.repo.initialize_schema()
        normalized_sources = [self._normalize_source(source) for source in sources]
        if not normalized_sources:
            raise ValueError("at least one package source with text is required")
        if profile_scope not in {"project_overlay", "customer_common"}:
            raise ValueError("profile_scope must be project_overlay or customer_common")

        now = utc_now()
        package_id = self._new_package_id(customer_id, project_id)
        context = self._ensure_customer_project_context(
            customer_id=customer_id,
            customer_name=customer_name,
            project_id=project_id,
            project_code=project_code,
            product_family=product_family,
            now=now,
        )
        target_profile_id = (
            context["project_profile_id"] if profile_scope == "project_overlay" else context["customer_profile_id"]
        )

        with closing(self.repo.connection()) as connection:
            connection.execute(
                """
                INSERT INTO requirement_import_packages (
                    package_id, customer_id, project_id, package_name, source_type,
                    profile_scope, customer_profile_id, project_profile_id, status,
                    batch_ids_json, candidate_count, promoted_count, effective_count,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    package_id,
                    customer_id,
                    project_id,
                    package_name or f"{customer_id}/{project_id} requirement package",
                    "mixed" if len({source.source_type for source in normalized_sources}) > 1 else normalized_sources[0].source_type,
                    profile_scope,
                    context["customer_profile_id"],
                    context["project_profile_id"],
                    "importing",
                    "[]",
                    0,
                    0,
                    0,
                    now,
                    now,
                ),
            )
            self._insert_event(connection, package_id, "package_created", actor, f"target_profile={target_profile_id}")
            connection.commit()

        extraction = RequirementExtractionService(self.repo)
        batch_ids: list[str] = []
        candidates: list[dict[str, Any]] = []
        for index, source in enumerate(normalized_sources, start=1):
            result = extraction.extract_from_text(
                source.text,
                source_type=source.source_type,
                source_id=source.source_id or f"{package_id}:{source.name or index}",
                profile_id=target_profile_id,
                document_id=source.document_id,
                fact_id=source.fact_id,
                evidence_id=source.evidence_id,
            )
            batch_ids.append(result["batch_id"])
            candidates.extend(result.get("candidates", []))

        promoted: list[dict[str, Any]] = []
        if auto_promote:
            for candidate in candidates:
                if not candidate.get("suggested_atom_id"):
                    continue
                promoted.append(
                    extraction.promote_candidate(
                        candidate["candidate_id"],
                        profile_id=target_profile_id,
                        promoted_by=promoted_by or actor or "package_import",
                    )
                )

        effective_requirements: list[dict[str, Any]] = []
        if refresh_effective or auto_promote:
            try:
                effective_requirements = [item.to_dict() for item in RequirementResolver(self.repo).resolve_project(project_id)]
            except ValueError:
                effective_requirements = []

        status = "promoted" if promoted else "pending_review"
        if not candidates:
            status = "no_candidates"
        with closing(self.repo.connection()) as connection:
            connection.execute(
                """
                UPDATE requirement_import_packages
                SET status = ?, batch_ids_json = ?, candidate_count = ?, promoted_count = ?,
                    effective_count = ?, updated_at = ?
                WHERE package_id = ?
                """,
                (
                    status,
                    json.dumps(batch_ids, ensure_ascii=False),
                    len(candidates),
                    len(promoted),
                    len(effective_requirements),
                    utc_now(),
                    package_id,
                ),
            )
            self._insert_event(
                connection,
                package_id,
                "package_imported",
                actor,
                f"candidates={len(candidates)}, promoted={len(promoted)}, effective={len(effective_requirements)}",
            )
            connection.commit()

        return {
            "package_id": package_id,
            "status": status,
            "customer_id": customer_id,
            "project_id": project_id,
            "product_family": product_family,
            "profile_scope": profile_scope,
            "target_profile_id": target_profile_id,
            "customer_profile_id": context["customer_profile_id"],
            "project_profile_id": context["project_profile_id"],
            "batch_ids": batch_ids,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "promoted_count": len(promoted),
            "promoted": promoted,
            "effective_count": len(effective_requirements),
            "effective_requirements": effective_requirements,
        }

    def list_import_packages(
        self,
        *,
        customer_id: str | None = None,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        self.repo.initialize_schema()
        clauses: list[str] = []
        params: list[Any] = []
        if customer_id:
            clauses.append("customer_id = ?")
            params.append(customer_id)
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
                SELECT * FROM requirement_import_packages
                {where}
                ORDER BY created_at DESC, package_id ASC
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()
        packages = [self._package_from_row(row) for row in rows]
        return {
            "customer_id": customer_id,
            "project_id": project_id,
            "status": status,
            "package_count": len(packages),
            "packages": packages,
        }

    def refresh_package_effective_requirements(self, package_id: str) -> dict[str, Any]:
        self.repo.initialize_schema()
        package = self.get_import_package(package_id)
        requirements = [
            item.to_dict() for item in RequirementResolver(self.repo).resolve_project(package["project_id"])
        ]
        with closing(self.repo.connection()) as connection:
            connection.execute(
                """
                UPDATE requirement_import_packages
                SET effective_count = ?, updated_at = ?
                WHERE package_id = ?
                """,
                (len(requirements), utc_now(), package_id),
            )
            self._insert_event(connection, package_id, "effective_refreshed", "resolver", f"effective={len(requirements)}")
            connection.commit()
        return {"package_id": package_id, "project_id": package["project_id"], "effective_count": len(requirements), "effective_requirements": requirements}

    def get_import_package(self, package_id: str) -> dict[str, Any]:
        self.repo.initialize_schema()
        with closing(self.repo.connection()) as connection:
            row = connection.execute("SELECT * FROM requirement_import_packages WHERE package_id = ?", (package_id,)).fetchone()
        if row is None:
            raise ValueError(f"unknown package_id: {package_id}")
        return self._package_from_row(row)

    def _ensure_customer_project_context(
        self,
        *,
        customer_id: str,
        customer_name: str | None,
        project_id: str,
        project_code: str,
        product_family: str,
        now: str,
    ) -> dict[str, str]:
        customer_profile_id = self._profile_id("PROFILE", customer_id, product_family, "COMMON")
        project_profile_id = self._profile_id("PROFILE", project_id)
        product_family = product_family.upper()
        with closing(self.repo.connection()) as connection:
            connection.execute(
                """
                INSERT INTO customers (customer_id, customer_name, customer_code, region, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET
                    customer_name=COALESCE(excluded.customer_name, customers.customer_name),
                    updated_at=excluded.updated_at
                """,
                (customer_id, customer_name or customer_id, customer_id, None, now, now),
            )
            connection.execute(
                """
                INSERT INTO customer_projects (
                    project_id, customer_id, project_code, project_name, product_family,
                    product_variant_id, platform_id, lifecycle_status, sop_date, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    customer_id=excluded.customer_id,
                    project_code=excluded.project_code,
                    product_family=excluded.product_family,
                    updated_at=excluded.updated_at
                """,
                (project_id, customer_id, project_code, project_code, product_family, None, None, "development", None, now, now),
            )
            connection.execute(
                """
                INSERT INTO requirement_profiles (
                    profile_id, profile_type, owner_type, owner_id, name, version,
                    description, status, created_at, updated_at
                ) VALUES (?, 'customer_common', 'customer', ?, ?, 'v1', ?, 'active', ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET updated_at=excluded.updated_at
                """,
                (
                    customer_profile_id,
                    customer_id,
                    f"{customer_id} {product_family} 通用需求画像",
                    "Created by requirement package import.",
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO requirement_profiles (
                    profile_id, profile_type, owner_type, owner_id, name, version,
                    description, status, created_at, updated_at
                ) VALUES (?, 'project_overlay', 'project', ?, ?, 'v1', ?, 'active', ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET updated_at=excluded.updated_at
                """,
                (
                    project_profile_id,
                    project_id,
                    f"{project_id} 项目覆盖需求",
                    "Created by requirement package import.",
                    now,
                    now,
                ),
            )
            self._ensure_inheritance(connection, project_profile_id, customer_profile_id, 300, now)
            for parent_profile_id, priority in self._existing_default_parent_profiles(connection, product_family):
                self._ensure_inheritance(connection, project_profile_id, parent_profile_id, priority, now)
                if priority < 300:
                    self._ensure_inheritance(connection, customer_profile_id, parent_profile_id, priority, now)
            connection.commit()
        return {"customer_profile_id": customer_profile_id, "project_profile_id": project_profile_id}

    def _existing_default_parent_profiles(self, connection: sqlite3.Connection, product_family: str) -> list[tuple[str, int]]:
        candidates = [
            (f"PROFILE-STD-{product_family}-MANDATORY", 100),
            (f"PROFILE-{product_family}-BASELINE", 200),
        ]
        existing: list[tuple[str, int]] = []
        for profile_id, priority in candidates:
            row = connection.execute("SELECT profile_id FROM requirement_profiles WHERE profile_id = ?", (profile_id,)).fetchone()
            if row:
                existing.append((profile_id, priority))
        return existing

    def _ensure_inheritance(self, connection: sqlite3.Connection, child_profile_id: str, parent_profile_id: str, priority: int, now: str) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO requirement_profile_inheritance (
                child_profile_id, parent_profile_id, priority, inheritance_type, status, created_at
            ) VALUES (?, ?, ?, 'normal', 'active', ?)
            """,
            (child_profile_id, parent_profile_id, priority, now),
        )

    def _normalize_source(self, source: dict[str, Any] | RequirementPackageSource) -> RequirementPackageSource:
        if isinstance(source, RequirementPackageSource):
            normalized = source
        else:
            normalized = RequirementPackageSource(
                name=str(source.get("name") or source.get("filename") or "package_text"),
                text=str(source.get("text") or ""),
                source_type=str(source.get("source_type") or source.get("sourceType") or "package_text"),
                source_id=source.get("source_id") or source.get("sourceId"),
                document_id=source.get("document_id") or source.get("documentId"),
                evidence_id=source.get("evidence_id") or source.get("evidenceId"),
                fact_id=source.get("fact_id") or source.get("factId"),
            )
        if not normalized.text.strip():
            raise ValueError(f"package source {normalized.name!r} has empty text")
        return normalized

    def _package_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        batch_ids_raw = row["batch_ids_json"] or "[]"
        return {
            "package_id": row["package_id"],
            "customer_id": row["customer_id"],
            "project_id": row["project_id"],
            "package_name": row["package_name"],
            "source_type": row["source_type"],
            "profile_scope": row["profile_scope"],
            "customer_profile_id": row["customer_profile_id"],
            "project_profile_id": row["project_profile_id"],
            "status": row["status"],
            "batch_ids": json.loads(batch_ids_raw),
            "candidate_count": row["candidate_count"],
            "promoted_count": row["promoted_count"],
            "effective_count": row["effective_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _insert_event(self, connection: sqlite3.Connection, package_id: str, event_type: str, actor: str | None, comment: str | None) -> None:
        now = utc_now()
        event_id = f"RIMP-EVT-{package_id}-{event_type}-{abs(hash((event_type, actor, comment, now))) % 100000000}"
        connection.execute(
            """
            INSERT INTO requirement_import_events (event_id, package_id, event_type, actor, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, package_id, event_type, actor, comment, now),
        )

    def _new_package_id(self, customer_id: str, project_id: str) -> str:
        suffix = abs(hash((customer_id, project_id, utc_now()))) % 100000000
        return f"RPKG-{self._safe_id(customer_id)}-{self._safe_id(project_id)}-{suffix}"

    def _profile_id(self, *parts: str) -> str:
        return "-".join(self._safe_id(part) for part in parts if part)

    def _safe_id(self, value: str) -> str:
        return re.sub(r"[^0-9A-Za-z]+", "-", value.strip()).strip("-").upper() or "UNKNOWN"
