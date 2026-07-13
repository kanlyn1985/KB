from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .repository import RequirementRepository
from .resolver import RequirementResolver
from .diff import RequirementDiffService
from .compliance import RequirementComplianceService
from .impact import RequirementImpactAnalyzer
from .extraction import RequirementExtractionService
from .package_import import RequirementPackageImportService
from .approval import RequirementApprovalService
from .baseline import RequirementBaselineService
from .release_gate import RequirementReleaseGateService
from .eco import RequirementEcoService


@dataclass(frozen=True)
class RequirementQueryPlan:
    intent: str
    query: str
    project_id: str | None = None
    atom_id: str | None = None
    base_profile_id: str | None = None
    variant_id: str | None = None
    proposed_change: dict[str, Any] | None = None
    release_stage: str | None = None
    eco_id: str | None = None
    confidence: float = 0.0
    clarification_reason: str | None = None
    candidates: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RequirementQueryPlanner:
    """Rule-first query planner for the requirement resolver MVP.

    This module deliberately avoids LLM judgment. It only maps obvious customer/project/
    requirement-atom mentions to deterministic resolver calls. Ambiguous queries return
    clarification_required instead of guessing.
    """

    ATOM_ALIASES: dict[str, tuple[str, ...]] = {
        "REQATOM-DCDC-OUTPUT-RIPPLE": ("输出纹波", "纹波", "纹波电压", "ripple", "output ripple"),
        "REQATOM-DCDC-EFFICIENCY": ("效率", "满载效率", "efficiency"),
        "REQATOM-DCDC-SLEEP-CURRENT": ("休眠电流", "静态电流", "sleep current", "sleep-current"),
    }

    def __init__(self, repo: RequirementRepository):
        self.repo = repo

    @classmethod
    def from_root(cls, root: Path) -> "RequirementQueryPlanner":
        return cls(RequirementRepository(root))

    def plan(self, query: str) -> RequirementQueryPlan:
        normalized = self._normalize(query)
        try:
            projects = self._load_projects()
            atoms = self._load_atoms()
        except sqlite3.OperationalError as exc:
            return RequirementQueryPlan(
                intent="requirement_schema_missing",
                query=query,
                clarification_reason=f"Requirement schema is not initialized: {exc}",
                confidence=1.0,
            )

        project_id = self._match_project(normalized, projects)
        atom_id = self._match_atom(normalized, atoms)

        if self._looks_like_eco(normalized):
            return RequirementQueryPlan(
                intent="requirement_eco",
                query=query,
                project_id=project_id,
                atom_id=atom_id,
                eco_id=self._extract_eco_id(normalized),
                confidence=0.76,
            )

        if self._looks_like_release_gate(normalized):
            if project_id is None:
                return RequirementQueryPlan(
                    intent="clarification_required",
                    query=query,
                    clarification_reason="The query asks for release readiness but no project could be resolved.",
                    candidates=projects,
                    confidence=0.6,
                )
            return RequirementQueryPlan(
                intent="requirement_release_gate",
                query=query,
                project_id=project_id,
                atom_id=atom_id,
                release_stage=self._extract_release_stage(normalized),
                confidence=0.84,
            )

        if self._looks_like_baseline(normalized):
            return RequirementQueryPlan(
                intent="requirement_baseline",
                query=query,
                project_id=project_id,
                atom_id=atom_id,
                confidence=0.78,
            )

        if self._looks_like_import_packages(normalized):
            return RequirementQueryPlan(
                intent="requirement_import_packages",
                query=query,
                project_id=project_id,
                atom_id=atom_id,
                confidence=0.74,
            )

        if self._looks_like_candidates(normalized):
            return RequirementQueryPlan(
                intent="requirement_candidates",
                query=query,
                project_id=project_id,
                atom_id=atom_id,
                confidence=0.78,
            )

        if self._looks_like_impact(normalized):
            if atom_id is None:
                return RequirementQueryPlan(
                    intent="clarification_required",
                    query=query,
                    clarification_reason="The query asks for change impact but no requirement atom could be resolved.",
                    candidates=atoms,
                    confidence=0.6,
                )
            customer_id = self._match_customer(normalized)
            if customer_id is None:
                return RequirementQueryPlan(
                    intent="clarification_required",
                    query=query,
                    atom_id=atom_id,
                    clarification_reason="The query asks for change impact but no customer/common profile could be resolved.",
                    confidence=0.6,
                )
            variant_id = self._find_customer_common_variant(customer_id, atom_id)
            if variant_id is None:
                return RequirementQueryPlan(
                    intent="clarification_required",
                    query=query,
                    atom_id=atom_id,
                    clarification_reason="No customer-common requirement variant was found for the resolved customer and atom.",
                    confidence=0.6,
                )
            proposed_change = self._extract_proposed_change(normalized)
            if not proposed_change:
                return RequirementQueryPlan(
                    intent="clarification_required",
                    query=query,
                    atom_id=atom_id,
                    variant_id=variant_id,
                    clarification_reason="The proposed new value could not be parsed from the query.",
                    confidence=0.6,
                )
            return RequirementQueryPlan(
                intent="requirement_impact",
                query=query,
                atom_id=atom_id,
                variant_id=variant_id,
                proposed_change=proposed_change,
                confidence=0.82,
            )

        if self._looks_like_compliance(normalized):
            if project_id is None:
                return RequirementQueryPlan(
                    intent="clarification_required",
                    query=query,
                    atom_id=atom_id,
                    clarification_reason="The query asks for compliance but no project could be resolved.",
                    candidates=projects,
                    confidence=0.6,
                )
            return RequirementQueryPlan(
                intent="requirement_compliance",
                query=query,
                project_id=project_id,
                atom_id=atom_id,
                confidence=0.85,
            )

        if self._looks_like_review(normalized):
            return RequirementQueryPlan(
                intent="requirement_review",
                query=query,
                project_id=project_id,
                confidence=0.78,
            )

        if self._looks_like_conflict_scan(normalized):
            if project_id is None:
                return RequirementQueryPlan(
                    intent="clarification_required",
                    query=query,
                    clarification_reason="The query asks for conflicts but no project could be resolved.",
                    candidates=projects,
                    confidence=0.6,
                )
            return RequirementQueryPlan(
                intent="requirement_conflict_scan",
                query=query,
                project_id=project_id,
                confidence=0.8,
            )

        if self._looks_like_diff(normalized):
            if project_id is None:
                return RequirementQueryPlan(
                    intent="clarification_required",
                    query=query,
                    clarification_reason="The query asks for project differences but no project could be resolved.",
                    candidates=projects,
                    confidence=0.6,
                )
            base_profile_id = self._find_customer_common_profile(project_id)
            if base_profile_id is None:
                return RequirementQueryPlan(
                    intent="clarification_required",
                    query=query,
                    project_id=project_id,
                    clarification_reason="No customer-common profile was found for the resolved project.",
                    confidence=0.6,
                )
            return RequirementQueryPlan(
                intent="requirement_diff",
                query=query,
                project_id=project_id,
                base_profile_id=base_profile_id,
                confidence=0.85,
            )

        if project_id is None:
            return RequirementQueryPlan(
                intent="clarification_required",
                query=query,
                atom_id=atom_id,
                clarification_reason="No project could be resolved. Requirement answers must be project-scoped.",
                candidates=projects,
                confidence=0.5,
            )

        if atom_id is None:
            return RequirementQueryPlan(
                intent="clarification_required",
                query=query,
                project_id=project_id,
                clarification_reason="No requirement atom could be resolved from the query.",
                candidates=atoms,
                confidence=0.5,
            )

        return RequirementQueryPlan(
            intent="requirement_effective",
            query=query,
            project_id=project_id,
            atom_id=atom_id,
            confidence=0.9,
        )

    def execute(self, plan: RequirementQueryPlan) -> dict[str, Any]:
        if plan.intent == "requirement_effective" and plan.project_id and plan.atom_id:
            effective = RequirementResolver(self.repo).resolve_requirement(plan.project_id, plan.atom_id)
            return {
                "intent": plan.intent,
                "plan": plan.to_dict(),
                "effective_requirement": effective.to_dict(),
            }

        if plan.intent == "requirement_diff" and plan.project_id and plan.base_profile_id:
            diff = RequirementDiffService(self.repo).diff_project_against_profile(
                plan.project_id,
                plan.base_profile_id,
            )
            return {"intent": plan.intent, "plan": plan.to_dict(), "diff": diff}

        if plan.intent == "requirement_impact" and plan.variant_id and plan.proposed_change:
            impact = RequirementImpactAnalyzer(self.repo).analyze_variant_change(
                plan.variant_id,
                plan.proposed_change,
            )
            return {"intent": plan.intent, "plan": plan.to_dict(), "impact": impact}

        if plan.intent == "requirement_compliance" and plan.project_id:
            service = RequirementComplianceService(self.repo)
            if plan.atom_id:
                compliance = service.build_requirement_compliance(plan.project_id, plan.atom_id)
            else:
                compliance = service.build_project_matrix(plan.project_id)
            return {"intent": plan.intent, "plan": plan.to_dict(), "compliance": compliance}

        if plan.intent == "requirement_eco":
            service = RequirementEcoService(self.repo)
            if plan.eco_id:
                return {"intent": plan.intent, "plan": plan.to_dict(), "eco": service.get_change_order(plan.eco_id)}
            return {"intent": plan.intent, "plan": plan.to_dict(), "ecos": service.list_change_orders(project_id=plan.project_id, limit=50)}

        if plan.intent == "requirement_release_gate" and plan.project_id:
            gate = RequirementReleaseGateService(self.repo).evaluate_project(
                plan.project_id,
                stage=plan.release_stage or "DV",
                persist=False,
            )
            return {"intent": plan.intent, "plan": plan.to_dict(), "release_gate": gate}

        if plan.intent == "requirement_baseline":
            baselines = RequirementBaselineService(self.repo).list_baselines(project_id=plan.project_id, limit=50)
            return {"intent": plan.intent, "plan": plan.to_dict(), "baselines": baselines}

        if plan.intent == "requirement_candidates":
            candidates = RequirementExtractionService(self.repo).list_candidates(status="pending_review", limit=50)
            return {"intent": plan.intent, "plan": plan.to_dict(), "candidates": candidates}

        if plan.intent == "requirement_import_packages":
            packages = RequirementPackageImportService(self.repo).list_import_packages(project_id=plan.project_id, limit=50)
            return {"intent": plan.intent, "plan": plan.to_dict(), "import_packages": packages}

        if plan.intent == "requirement_conflict_scan" and plan.project_id:
            requirements = RequirementResolver(self.repo).resolve_project(plan.project_id)
            issues = [
                item.to_dict()
                for item in requirements
                if item.conflict_status != "none" or item.verification_status != "verified"
            ]
            return {"intent": plan.intent, "plan": plan.to_dict(), "issue_count": len(issues), "issues": issues}

        if plan.intent == "requirement_review":
            review = RequirementApprovalService(self.repo).build_review_report(project_id=plan.project_id)
            return {"intent": plan.intent, "plan": plan.to_dict(), "review": review}

        return {"intent": plan.intent, "plan": plan.to_dict(), "status": "not_executed"}

    def _normalize(self, query: str) -> str:
        return query.strip().lower().replace("／", "/").replace("，", ",")

    def _load_projects(self) -> list[dict[str, Any]]:
        with self.repo._conn_ctx() as connection:
            rows = connection.execute(
                """
                SELECT project_id, customer_id, project_code, project_name, product_family
                FROM customer_projects
                ORDER BY customer_id, project_code, project_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def _load_atoms(self) -> list[dict[str, Any]]:
        with self.repo._conn_ctx() as connection:
            rows = connection.execute(
                """
                SELECT atom_id, domain, category, canonical_name, parameter_name, default_unit, constraint_kind
                FROM requirement_atoms
                ORDER BY domain, category, canonical_name
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def _match_project(self, normalized_query: str, projects: list[dict[str, Any]]) -> str | None:
        matches: list[str] = []
        for project in projects:
            tokens = [
                project.get("project_id"),
                project.get("project_code"),
                project.get("project_name"),
            ]
            for token in tokens:
                if token and str(token).lower() in normalized_query:
                    matches.append(str(project["project_id"]))
                    break

        if not matches:
            # Fallback for common shorthand such as "P1 项目" in Chinese text,
            # where word-boundary regexes are unreliable around CJK characters.
            shorthand = [f"p{number}" for number in re.findall(r"p\s*[-_]?\s*(\d+)", normalized_query)]
            for short in shorthand:
                for project in projects:
                    project_id = str(project["project_id"]).lower()
                    project_code = str(project.get("project_code") or "").lower()
                    if project_id.endswith("-" + short) or project_code.endswith("-" + short):
                        matches.append(str(project["project_id"]))

        unique = sorted(set(matches))
        return unique[0] if len(unique) == 1 else None

    def _match_atom(self, normalized_query: str, atoms: list[dict[str, Any]]) -> str | None:
        matches: list[str] = []
        for atom in atoms:
            atom_id = str(atom["atom_id"])
            tokens = [
                atom.get("atom_id"),
                atom.get("canonical_name"),
                atom.get("parameter_name"),
                *(self.ATOM_ALIASES.get(atom_id, ())),
            ]
            if any(token and str(token).lower() in normalized_query for token in tokens):
                matches.append(atom_id)
        unique = sorted(set(matches))
        return unique[0] if len(unique) == 1 else None

    def _find_customer_common_profile(self, project_id: str) -> str | None:
        with self.repo._conn_ctx() as connection:
            project = connection.execute(
                "SELECT customer_id, product_family FROM customer_projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if project is None:
                return None
            row = connection.execute(
                """
                SELECT profile_id
                FROM requirement_profiles
                WHERE profile_type = 'customer_common'
                  AND owner_type = 'customer'
                  AND owner_id = ?
                  AND status = 'active'
                ORDER BY updated_at DESC, profile_id ASC
                LIMIT 1
                """,
                (project["customer_id"],),
            ).fetchone()
        return str(row["profile_id"]) if row else None

    def _match_customer(self, normalized_query: str) -> str | None:
        with self.repo._conn_ctx() as connection:
            rows = connection.execute(
                """
                SELECT customer_id, customer_name, customer_code
                FROM customers
                WHERE status = 'active'
                ORDER BY customer_id ASC
                """
            ).fetchall()
        matches: list[str] = []
        for row in rows:
            tokens = [row["customer_id"], row["customer_name"], row["customer_code"]]
            if any(token and str(token).lower() in normalized_query for token in tokens):
                matches.append(str(row["customer_id"]))
        unique = sorted(set(matches))
        return unique[0] if len(unique) == 1 else None

    def _find_customer_common_variant(self, customer_id: str, atom_id: str) -> str | None:
        with self.repo._conn_ctx() as connection:
            row = connection.execute(
                """
                SELECT v.variant_id
                FROM requirement_variants v
                JOIN requirement_profiles p ON p.profile_id = v.profile_id
                WHERE p.profile_type = 'customer_common'
                  AND p.owner_type = 'customer'
                  AND p.owner_id = ?
                  AND p.status = 'active'
                  AND v.atom_id = ?
                  AND v.status = 'active'
                ORDER BY v.priority ASC, v.updated_at DESC, v.variant_id ASC
                LIMIT 1
                """,
                (customer_id, atom_id),
            ).fetchone()
        return str(row["variant_id"]) if row else None

    def _extract_proposed_change(self, normalized_query: str) -> dict[str, Any] | None:
        match = re.search(r"(?:改成|改为|变成|调整为|to)\s*[≤<>=]*\s*(\d+(?:\.\d+)?)\s*([a-z%μµ毫伏安]*)", normalized_query)
        if match is None:
            # Fallback: use the last number in an impact query as the proposed value.
            numbers = re.findall(r"(\d+(?:\.\d+)?)\s*([a-z%μµ毫伏安]*)", normalized_query)
            if not numbers:
                return None
            raw_value, raw_unit = numbers[-1]
        else:
            raw_value, raw_unit = match.group(1), match.group(2)
        unit = self._normalize_unit(raw_unit)
        return {"value_numeric": float(raw_value), "unit": unit or None}

    def _normalize_unit(self, unit: str | None) -> str | None:
        if not unit:
            return None
        value = unit.strip()
        aliases = {"毫伏": "mV", "mv": "mV", "伏": "V", "ma": "mA", "毫安": "mA", "percent": "%"}
        return aliases.get(value, value)

    def _looks_like_eco(self, normalized_query: str) -> bool:
        return any(token in normalized_query for token in ("eco", "工程变更", "变更单", "工程变更单", "change order", "engineering change"))

    def _extract_eco_id(self, normalized_query: str) -> str | None:
        match = re.search(r"eco-[a-z0-9_.-]+", normalized_query, flags=re.IGNORECASE)
        return match.group(0).upper() if match else None

    def _looks_like_release_gate(self, normalized_query: str) -> bool:
        return any(token in normalized_query for token in ("发布门禁", "准入", "是否可以进入", "能否进入", "release readiness", "release gate", "dv", "pv", "sop")) and any(token in normalized_query for token in ("门禁", "准入", "是否可以", "能否", "readiness", "gate", "进入"))

    def _extract_release_stage(self, normalized_query: str) -> str:
        if "sop" in normalized_query:
            return "SOP"
        if "pv" in normalized_query:
            return "PV"
        if "dv" in normalized_query:
            return "DV"
        return "DV"

    def _looks_like_import_packages(self, normalized_query: str) -> bool:
        return any(token in normalized_query for token in ("需求包", "导入包", "项目需求包", "import package", "package import", "requirement package"))

    def _looks_like_candidates(self, normalized_query: str) -> bool:
        return any(token in normalized_query for token in ("候选需求", "待归类", "待评审需求", "抽取结果", "需要人工确认", "candidate", "candidates"))

    def _looks_like_baseline(self, normalized_query: str) -> bool:
        return any(token in normalized_query for token in ("需求基线", "项目基线", "baseline", "基线版本", "冻结版本", "版本冻结", "回滚", "漂移"))

    def _looks_like_diff(self, normalized_query: str) -> bool:
        return any(token in normalized_query for token in ("差异", "改了哪些", "相对", "不同", "diff"))

    def _looks_like_review(self, normalized_query: str) -> bool:
        return any(token in normalized_query for token in ("需要审批", "审批状态", "评审", "review", "approval"))

    def _looks_like_conflict_scan(self, normalized_query: str) -> bool:
        return any(token in normalized_query for token in ("冲突", "放宽", "缺证据", "缺少证据", "风险"))

    def _looks_like_impact(self, normalized_query: str) -> bool:
        return any(token in normalized_query for token in ("影响哪些", "影响范围", "变更影响", "改成", "改为", "调整为", "impact", "change impact"))

    def _looks_like_compliance(self, normalized_query: str) -> bool:
        return any(token in normalized_query for token in ("是否满足", "是否符合", "合规", "符合性", "测试覆盖", "测试结果", "compliance", "pass/fail"))


def plan_requirement_query(root: Path, query: str) -> dict[str, Any]:
    return RequirementQueryPlanner.from_root(root).plan(query).to_dict()


def execute_requirement_query(root: Path, query: str) -> dict[str, Any]:
    planner = RequirementQueryPlanner.from_root(root)
    plan = planner.plan(query)
    return planner.execute(plan)
