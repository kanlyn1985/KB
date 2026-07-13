from __future__ import annotations

import json
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .repository import RequirementRepository
from .resolver import RequirementResolver


@dataclass(frozen=True)
class RequirementTestMethod:
    test_method_id: str
    atom_id: str
    name: str
    description: str | None
    procedure_json: dict[str, Any]
    evidence_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RequirementTestCase:
    test_case_id: str
    test_method_id: str
    project_id: str | None
    name: str
    condition_json: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RequirementTestResult:
    result_id: str
    test_case_id: str
    project_id: str
    measured_value_numeric: float | None
    measured_value_text: str | None
    unit: str | None
    status: str
    evidence_id: str | None
    executed_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RequirementComplianceService:
    """Build deterministic test coverage and compliance matrices for effective requirements.

    The service does not decide what the requirement is. It first calls RequirementResolver,
    then evaluates test results against the resolved EffectiveRequirement using the atom's
    constraint_kind. This keeps the evidence/requirement boundary separate from test judgment.
    """

    def __init__(self, repo: RequirementRepository):
        self.repo = repo

    @classmethod
    def from_root(cls, root: Path) -> "RequirementComplianceService":
        return cls(RequirementRepository(root))

    def build_project_matrix(self, project_id: str) -> dict[str, Any]:
        effective_requirements = RequirementResolver(self.repo).resolve_project(project_id)
        rows = [self._build_row(project_id, effective) for effective in effective_requirements]
        summary = self._summarize(rows)
        return {"project_id": project_id, "summary": summary, "rows": rows}

    def build_requirement_compliance(self, project_id: str, atom_id: str) -> dict[str, Any]:
        effective = RequirementResolver(self.repo).resolve_requirement(project_id, atom_id)
        row = self._build_row(project_id, effective)
        return {"project_id": project_id, "atom_id": atom_id, "summary": self._summarize([row]), "row": row}

    def _build_row(self, project_id: str, effective) -> dict[str, Any]:
        methods = self._load_test_methods(effective.atom_id)
        method_payloads = []
        row_statuses: list[str] = []

        if not methods:
            row_statuses.append("missing_test_method")

        for method in methods:
            cases = self._load_test_cases(project_id, method.test_method_id)
            case_payloads = []
            if not cases:
                row_statuses.append("missing_test_case")

            for case in cases:
                result = self._load_latest_test_result(project_id, case.test_case_id)
                evaluation = self._evaluate_result(effective, result)
                row_statuses.append(evaluation["status"])
                case_payloads.append(
                    {
                        "test_case": case.to_dict(),
                        "latest_result": result.to_dict() if result else None,
                        "evaluation": evaluation,
                    }
                )

            method_payloads.append({"test_method": method.to_dict(), "cases": case_payloads})

        compliance_status = self._dominant_status(row_statuses)
        return {
            "atom_id": effective.atom_id,
            "effective_requirement": effective.to_dict(),
            "requirement_conflict_status": effective.conflict_status,
            "requirement_verification_status": effective.verification_status,
            "compliance_status": compliance_status,
            "test_methods": method_payloads,
        }

    def _load_test_methods(self, atom_id: str) -> list[RequirementTestMethod]:
        with closing(self.repo.connection()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM requirement_test_methods
                WHERE atom_id = ? AND status = 'active'
                ORDER BY test_method_id ASC
                """,
                (atom_id,),
            ).fetchall()
        return [self._method_from_row(row) for row in rows]

    def _load_test_cases(self, project_id: str, test_method_id: str) -> list[RequirementTestCase]:
        with closing(self.repo.connection()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM requirement_test_cases
                WHERE test_method_id = ?
                  AND status = 'active'
                  AND (project_id IS NULL OR project_id = ?)
                ORDER BY CASE WHEN project_id = ? THEN 0 ELSE 1 END, priority ASC, test_case_id ASC
                """,
                (test_method_id, project_id, project_id),
            ).fetchall()
        return [self._case_from_row(row) for row in rows]

    def _load_latest_test_result(self, project_id: str, test_case_id: str) -> RequirementTestResult | None:
        with closing(self.repo.connection()) as connection:
            row = connection.execute(
                """
                SELECT * FROM requirement_test_results
                WHERE project_id = ? AND test_case_id = ?
                ORDER BY COALESCE(executed_at, updated_at, created_at) DESC, result_id DESC
                LIMIT 1
                """,
                (project_id, test_case_id),
            ).fetchone()
        return self._result_from_row(row) if row else None

    def _evaluate_result(self, effective, result: RequirementTestResult | None) -> dict[str, Any]:
        if result is None:
            return {"status": "missing_test_result", "reason": "No test result is available for this project/test case."}

        if effective.unit and result.unit and effective.unit != result.unit:
            return {"status": "unit_mismatch", "reason": f"Requirement unit {effective.unit} != result unit {result.unit}."}

        if effective.value_numeric is None or result.measured_value_numeric is None:
            return {"status": "unknown", "reason": "Numeric comparison is not available."}

        atom = self.repo.load_atom(effective.atom_id)
        measured = result.measured_value_numeric
        required = effective.value_numeric

        if atom.constraint_kind == "max_limit":
            passed = measured <= required
            operator = "<="
        elif atom.constraint_kind == "min_limit":
            passed = measured >= required
            operator = ">="
        else:
            return {"status": "unknown", "reason": f"Unsupported constraint_kind: {atom.constraint_kind}."}

        return {
            "status": "pass" if passed else "fail",
            "measured_value_numeric": measured,
            "required_value_numeric": required,
            "operator": operator,
            "unit": effective.unit or result.unit,
            "reason": "Measured value satisfies effective requirement." if passed else "Measured value violates effective requirement.",
        }

    def _dominant_status(self, statuses: list[str]) -> str:
        if not statuses:
            return "not_evaluated"
        for status in [
            "fail",
            "unit_mismatch",
            "missing_test_method",
            "missing_test_case",
            "missing_test_result",
            "unknown",
            "pass",
        ]:
            if status in statuses:
                return status
        return statuses[0]

    def _summarize(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for row in rows:
            status = str(row.get("compliance_status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
        overall_status = "pass"
        if not rows:
            overall_status = "not_evaluated"
        elif any(status in counts for status in ("fail", "unit_mismatch")):
            overall_status = "fail"
        elif any(status in counts for status in ("missing_test_method", "missing_test_case", "missing_test_result", "unknown")):
            overall_status = "incomplete"
        return {"requirement_count": len(rows), "status_counts": counts, "overall_status": overall_status}

    def _method_from_row(self, row) -> RequirementTestMethod:
        raw = row["procedure_json"]
        return RequirementTestMethod(
            test_method_id=row["test_method_id"],
            atom_id=row["atom_id"],
            name=row["name"],
            description=row["description"],
            procedure_json=json.loads(raw) if raw else {},
            evidence_id=row["evidence_id"],
        )

    def _case_from_row(self, row) -> RequirementTestCase:
        raw = row["condition_json"]
        return RequirementTestCase(
            test_case_id=row["test_case_id"],
            test_method_id=row["test_method_id"],
            project_id=row["project_id"],
            name=row["name"],
            condition_json=json.loads(raw) if raw else {},
        )

    def _result_from_row(self, row) -> RequirementTestResult:
        return RequirementTestResult(
            result_id=row["result_id"],
            test_case_id=row["test_case_id"],
            project_id=row["project_id"],
            measured_value_numeric=row["measured_value_numeric"],
            measured_value_text=row["measured_value_text"],
            unit=row["unit"],
            status=row["status"],
            evidence_id=row["evidence_id"],
            executed_at=row["executed_at"],
        )
