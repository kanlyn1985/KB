from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any

from .comparator import RequirementComparator
from .compliance import RequirementComplianceService
from .models import RequirementAtom, RequirementVariant
from .repository import RequirementRepository
from .resolver import RequirementResolver


class RequirementImpactAnalyzer:
    """Dry-run impact analysis for proposed requirement variant changes.

    This service does not write the proposed change into the database. It treats the
    requested update as a hypothetical upstream requirement change, then enumerates
    projects that inherit the changed profile and reports whether each project would
    change directly, already has a stricter downstream override, or would need review
    because its downstream override becomes looser than the proposed customer/common
    requirement.
    """

    def __init__(self, repo: RequirementRepository):
        self.repo = repo
        self.resolver = RequirementResolver(repo)
        self.comparator = RequirementComparator()

    @classmethod
    def from_root(cls, root: Path) -> "RequirementImpactAnalyzer":
        return cls(RequirementRepository(root))

    def analyze_variant_change(self, variant_id: str, proposed_change: dict[str, Any]) -> dict[str, Any]:
        original = self._load_variant_by_id(variant_id)
        atom = self.repo.load_atom(original.atom_id)
        source_profile = self.repo.load_profile(original.profile_id)
        proposed = self._build_proposed_variant(original, proposed_change)
        affected_project_ids = self._find_projects_inheriting_profile(original.profile_id)

        projects: list[dict[str, Any]] = []
        for project_id in affected_project_ids:
            projects.append(self._analyze_project(project_id, atom, original, proposed))

        summary = self._summarize(projects)
        return {
            "variant_id": variant_id,
            "atom_id": original.atom_id,
            "source_profile": {
                "profile_id": source_profile.profile_id,
                "profile_type": source_profile.profile_type,
                "owner_type": source_profile.owner_type,
                "owner_id": source_profile.owner_id,
                "name": source_profile.name,
            },
            "current_variant": self._variant_payload(original),
            "proposed_variant": self._variant_payload(proposed),
            "summary": summary,
            "affected_projects": projects,
        }

    def _analyze_project(
        self,
        project_id: str,
        atom: RequirementAtom,
        original: RequirementVariant,
        proposed: RequirementVariant,
    ) -> dict[str, Any]:
        current = self.resolver.resolve_requirement(project_id, atom.atom_id)
        selected = self._load_variant_by_id(current.selected_variant_id) if current.selected_variant_id else None
        path_variant_ids = [step.variant_id for step in current.resolution_path if step.variant_id]
        is_direct = current.selected_variant_id == original.variant_id
        current_payload = current.to_dict()

        impact_type = "not_impacted"
        regression_test_required = False
        review_required = False
        reason = "The changed variant is not in the current resolution path."

        proposed_comparison: dict[str, Any] | None = None
        if is_direct:
            impact_type = "effective_value_changed"
            regression_test_required = True
            review_required = False
            reason = "The project currently selects the changed variant as its effective requirement."
        elif selected is not None and original.variant_id in path_variant_ids:
            compare = self.comparator.compare(atom, proposed, selected)
            proposed_comparison = {
                "effect": compare.effect,
                "reason": compare.reason,
                "confidence": compare.confidence,
            }
            if compare.effect == "loosen":
                impact_type = "downstream_override_looser_than_proposed"
                regression_test_required = True
                review_required = True
                reason = "A downstream project override would be looser than the proposed upstream requirement."
            elif compare.effect == "tighten":
                impact_type = "downstream_override_already_stricter"
                regression_test_required = False
                review_required = False
                reason = "The downstream project override remains stricter than the proposed upstream requirement."
            elif compare.effect in {"same", "clarify"}:
                impact_type = "downstream_override_equivalent_or_clarified"
                regression_test_required = False
                review_required = False
                reason = "The downstream override appears equivalent or only changes conditions."
            else:
                impact_type = "downstream_override_needs_review"
                regression_test_required = True
                review_required = True
                reason = "The downstream override comparison is not decisive."

        test_impact = self._estimate_test_impact(project_id, proposed)
        if test_impact["estimated_status"] == "fail_against_proposed":
            regression_test_required = True
            review_required = True

        before_compliance = RequirementComplianceService(self.repo).build_requirement_compliance(project_id, atom.atom_id)
        return {
            "project_id": project_id,
            "atom_id": atom.atom_id,
            "impact_type": impact_type,
            "reason": reason,
            "current_effective_requirement": current_payload,
            "proposed_requirement": self._variant_payload(proposed),
            "selected_variant_id": current.selected_variant_id,
            "changed_variant_in_resolution_path": original.variant_id in path_variant_ids,
            "proposed_vs_selected_comparison": proposed_comparison,
            "regression_test_required": regression_test_required,
            "review_required": review_required,
            "test_impact": test_impact,
            "current_compliance_summary": before_compliance.get("summary"),
        }

    def _estimate_test_impact(self, project_id: str, proposed: RequirementVariant) -> dict[str, Any]:
        methods = self._load_test_methods(proposed.atom_id)
        cases: list[dict[str, Any]] = []
        estimated_statuses: list[str] = []
        for method in methods:
            for case in self._load_test_cases(project_id, method["test_method_id"]):
                result = self._load_latest_test_result(project_id, case["test_case_id"])
                estimate = self._estimate_result_status(proposed, result)
                estimated_statuses.append(estimate["status"])
                cases.append({"test_method": method, "test_case": case, "latest_result": result, "estimate": estimate})

        if not methods:
            estimated_status = "missing_test_method"
        elif not cases:
            estimated_status = "missing_test_case"
        elif "fail_against_proposed" in estimated_statuses:
            estimated_status = "fail_against_proposed"
        elif "missing_test_result" in estimated_statuses:
            estimated_status = "missing_test_result"
        elif "unknown" in estimated_statuses:
            estimated_status = "unknown"
        else:
            estimated_status = "pass_against_proposed"

        return {"estimated_status": estimated_status, "affected_test_methods": methods, "affected_test_cases": cases}

    def _estimate_result_status(self, proposed: RequirementVariant, result: dict[str, Any] | None) -> dict[str, Any]:
        if result is None:
            return {"status": "missing_test_result", "reason": "No result is available for the affected test case."}
        if proposed.unit and result.get("unit") and proposed.unit != result.get("unit"):
            return {"status": "unknown", "reason": "Unit mismatch prevents deterministic proposed-value comparison."}
        if proposed.value_numeric is None or result.get("measured_value_numeric") is None:
            return {"status": "unknown", "reason": "Numeric comparison is not available."}

        atom = self.repo.load_atom(proposed.atom_id)
        measured = float(result["measured_value_numeric"])
        required = float(proposed.value_numeric)
        if atom.constraint_kind == "max_limit":
            passed = measured <= required
        elif atom.constraint_kind == "min_limit":
            passed = measured >= required
        else:
            return {"status": "unknown", "reason": f"Unsupported constraint_kind: {atom.constraint_kind}."}
        return {
            "status": "pass_against_proposed" if passed else "fail_against_proposed",
            "measured_value_numeric": measured,
            "proposed_value_numeric": required,
            "unit": proposed.unit or result.get("unit"),
        }

    def _find_projects_inheriting_profile(self, profile_id: str) -> list[str]:
        with self.repo._conn_ctx() as connection:
            rows = connection.execute(
                """
                SELECT profile_id, owner_id
                FROM requirement_profiles
                WHERE profile_type = 'project_overlay'
                  AND owner_type = 'project'
                  AND status = 'active'
                ORDER BY owner_id ASC
                """
            ).fetchall()
        affected: list[str] = []
        for row in rows:
            chain = self.repo.expand_profile_inheritance(row["profile_id"])
            if any(profile.profile_id == profile_id for profile in chain):
                affected.append(str(row["owner_id"]))
        return affected

    def _load_variant_by_id(self, variant_id: str | None) -> RequirementVariant:
        if not variant_id:
            raise ValueError("variant_id is required")
        with self.repo._conn_ctx() as connection:
            row = connection.execute(
                "SELECT * FROM requirement_variants WHERE variant_id = ?",
                (variant_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown variant_id: {variant_id}")
        return self.repo._variant_from_row(row)  # Reuse repository row mapping for MVP adapter.

    def _build_proposed_variant(self, original: RequirementVariant, proposed_change: dict[str, Any]) -> RequirementVariant:
        value = proposed_change.get("value_numeric", proposed_change.get("new_value", original.value_numeric))
        try:
            value_numeric = float(value) if value is not None else None
        except (TypeError, ValueError):
            value_numeric = original.value_numeric
        unit = str(proposed_change.get("unit") or original.unit) if (proposed_change.get("unit") or original.unit) else None
        operator = str(proposed_change.get("operator") or original.operator) if (proposed_change.get("operator") or original.operator) else None
        text = proposed_change.get("requirement_text") or self._render_requirement_text(original, value_numeric, unit, operator)
        return replace(
            original,
            variant_id=f"PROPOSED-{original.variant_id}",
            value_numeric=value_numeric,
            unit=unit,
            operator=operator,
            requirement_text=str(text),
        )

    def _render_requirement_text(
        self,
        original: RequirementVariant,
        value_numeric: float | None,
        unit: str | None,
        operator: str | None,
    ) -> str:
        if value_numeric is None:
            return f"Proposed change for {original.requirement_text}"
        value_text = int(value_numeric) if float(value_numeric).is_integer() else value_numeric
        return f"拟变更：{original.atom_id} {operator or ''} {value_text}{unit or ''}".strip()

    def _variant_payload(self, variant: RequirementVariant) -> dict[str, Any]:
        return {
            "variant_id": variant.variant_id,
            "atom_id": variant.atom_id,
            "profile_id": variant.profile_id,
            "requirement_text": variant.requirement_text,
            "operator": variant.operator,
            "value_numeric": variant.value_numeric,
            "value_text": variant.value_text,
            "unit": variant.unit,
            "condition_json": variant.condition_json,
            "mandatory_level": variant.mandatory_level,
            "evidence_id": variant.evidence_id,
        }

    def _load_test_methods(self, atom_id: str) -> list[dict[str, Any]]:
        with self.repo._conn_ctx() as connection:
            rows = connection.execute(
                """
                SELECT test_method_id, atom_id, name, description, evidence_id
                FROM requirement_test_methods
                WHERE atom_id = ? AND status = 'active'
                ORDER BY test_method_id ASC
                """,
                (atom_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _load_test_cases(self, project_id: str, test_method_id: str) -> list[dict[str, Any]]:
        with self.repo._conn_ctx() as connection:
            rows = connection.execute(
                """
                SELECT test_case_id, test_method_id, project_id, name, condition_json
                FROM requirement_test_cases
                WHERE test_method_id = ?
                  AND status = 'active'
                  AND (project_id IS NULL OR project_id = ?)
                ORDER BY CASE WHEN project_id = ? THEN 0 ELSE 1 END, priority ASC, test_case_id ASC
                """,
                (test_method_id, project_id, project_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def _load_latest_test_result(self, project_id: str, test_case_id: str) -> dict[str, Any] | None:
        with self.repo._conn_ctx() as connection:
            row = connection.execute(
                """
                SELECT result_id, test_case_id, project_id, measured_value_numeric,
                       measured_value_text, unit, status, evidence_id, executed_at
                FROM requirement_test_results
                WHERE project_id = ? AND test_case_id = ?
                ORDER BY COALESCE(executed_at, updated_at, created_at) DESC, result_id DESC
                LIMIT 1
                """,
                (project_id, test_case_id),
            ).fetchone()
        return dict(row) if row else None

    def _summarize(self, projects: list[dict[str, Any]]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        regression_required_count = 0
        review_required_count = 0
        for project in projects:
            impact_type = str(project.get("impact_type") or "unknown")
            counts[impact_type] = counts.get(impact_type, 0) + 1
            if project.get("regression_test_required"):
                regression_required_count += 1
            if project.get("review_required"):
                review_required_count += 1
        return {
            "affected_project_count": len(projects),
            "impact_type_counts": counts,
            "regression_required_count": regression_required_count,
            "review_required_count": review_required_count,
        }
