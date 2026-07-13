from __future__ import annotations

import json
import re
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .approval import RequirementApprovalService
from .baseline import RequirementBaselineService
from .compliance import RequirementComplianceService
from .repository import RequirementRepository, utc_now
from .resolver import RequirementResolver


RELEASE_STAGES = {"DV", "PV", "SOP"}


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip())
    return value.strip("-") or "release-gate"


@dataclass(frozen=True)
class ReleaseGatePolicy:
    stage: str
    evidence_gaps_block: bool
    incomplete_tests_block: bool
    require_all_passed_tests: bool

    @classmethod
    def for_stage(cls, stage: str) -> "ReleaseGatePolicy":
        normalized = (stage or "DV").upper()
        if normalized not in RELEASE_STAGES:
            raise ValueError(f"unsupported release gate stage: {stage}")
        if normalized == "DV":
            return cls(stage="DV", evidence_gaps_block=False, incomplete_tests_block=False, require_all_passed_tests=False)
        if normalized == "PV":
            return cls(stage="PV", evidence_gaps_block=True, incomplete_tests_block=True, require_all_passed_tests=False)
        return cls(stage="SOP", evidence_gaps_block=True, incomplete_tests_block=True, require_all_passed_tests=True)


class RequirementReleaseGateService:
    """Evaluate DV/PV/SOP readiness using baseline, resolver, compliance, and approval state.

    The gate is deterministic and read-mostly. It does not approve changes, mutate
    requirements, or create tests. It can persist an evaluation run for auditability,
    but all release decisions are derived from current requirement subsystem state.
    """

    def __init__(self, repo: RequirementRepository):
        self.repo = repo
        self.repo.initialize_schema()

    @classmethod
    def from_root(cls, root: Path) -> "RequirementReleaseGateService":
        return cls(RequirementRepository(root))

    def evaluate_project(
        self,
        project_id: str,
        *,
        stage: str = "DV",
        baseline_id: str | None = None,
        evaluated_by: str | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        policy = ReleaseGatePolicy.for_stage(stage)
        now = utc_now()
        findings: list[dict[str, Any]] = []

        baseline_payload = self._resolve_baseline(project_id, baseline_id)
        baseline_id = baseline_payload.get("baseline_id")
        baseline_missing = baseline_id is None
        if baseline_missing:
            findings.append(self._finding("baseline_missing", "blocker", "baseline", None, None, "No frozen requirement baseline exists for this project.", "Freeze a project requirement baseline before release readiness evaluation."))

        drift_payload: dict[str, Any] | None = None
        if baseline_id:
            try:
                drift_payload = RequirementBaselineService(self.repo).detect_drift(str(baseline_id))
                drift_summary = drift_payload.get("summary", {})
                drift_count = int(drift_summary.get("drifted", 0) or 0)
                if drift_count > 0:
                    findings.append(self._finding("baseline_drift", "blocker", "baseline", str(baseline_id), None, f"Current effective requirements drifted from frozen baseline: {drift_count} item(s).", "Resolve drift or freeze a new baseline for this release stage.", {"drift_summary": drift_summary}))
            except Exception as exc:  # keep gate evaluation explainable rather than crashing late
                findings.append(self._finding("baseline_drift_error", "blocker", "baseline", str(baseline_id), None, f"Could not compute baseline drift: {exc}", "Check baseline integrity and rerun the gate."))

        effective_requirements = RequirementResolver(self.repo).resolve_project(project_id)
        for req in effective_requirements:
            if req.conflict_status in {"hard_blocker", "approval_required"}:
                findings.append(self._finding("requirement_conflict", "blocker", "effective_requirement", req.selected_variant_id, req.atom_id, f"Requirement has blocking conflict_status={req.conflict_status}: {req.effective_requirement_text}", "Resolve the conflict or complete the required approval before passing the gate."))
            elif req.conflict_status != "none":
                severity = "blocker" if policy.stage in {"PV", "SOP"} else "warning"
                findings.append(self._finding("requirement_conflict", severity, "effective_requirement", req.selected_variant_id, req.atom_id, f"Requirement has conflict_status={req.conflict_status}: {req.effective_requirement_text}", "Review and clear the conflict before later release stages."))
            if req.verification_status != "verified":
                severity = "blocker" if policy.evidence_gaps_block else "warning"
                findings.append(self._finding("evidence_gap", severity, "effective_requirement", req.selected_variant_id, req.atom_id, f"Requirement evidence status is {req.verification_status}: {req.effective_requirement_text}", "Bind the requirement to evidence or mark it as approved manual evidence."))

        review_report = RequirementApprovalService(self.repo).build_review_report(project_id=project_id)
        pending_approvals = [item for item in review_report.get("approvals", []) if item.get("approval_status") in {"draft", "submitted"}]
        for approval in pending_approvals:
            findings.append(self._finding("pending_approval", "blocker", "approval", approval.get("approval_id"), approval.get("atom_id"), f"Approval is still {approval.get('approval_status')}: {approval.get('approval_id')}", "Approve, reject, or withdraw the approval request before passing the gate."))
        for item in review_report.get("review_items", []):
            severity = "blocker" if item.get("approval_required") else "warning"
            findings.append(self._finding("review_item", severity, item.get("source_type") or "review", item.get("source_id"), item.get("atom_id"), f"Review item remains open: {item.get('review_type')} / {item.get('reason') or ''}", item.get("recommendation") or "Close or explicitly accept this review item."))

        compliance = RequirementComplianceService(self.repo).build_project_matrix(project_id)
        compliance_summary = compliance.get("summary", {})
        status_counts = compliance_summary.get("status_counts", {}) or {}
        for status, count in sorted(status_counts.items()):
            if not count:
                continue
            if status in {"fail", "unit_mismatch"}:
                findings.append(self._finding("compliance_failure", "blocker", "compliance", status, None, f"Compliance matrix has {count} {status} row(s).", "Fix the failing test result or update the effective requirement with approved evidence."))
            elif status in {"missing_test_method", "missing_test_case", "missing_test_result", "unknown"}:
                severity = "blocker" if policy.incomplete_tests_block else "warning"
                findings.append(self._finding("test_coverage_gap", severity, "compliance", status, None, f"Compliance matrix has {count} {status} row(s).", "Add test coverage and latest project test results before later release stages."))
            elif status != "pass" and policy.require_all_passed_tests:
                findings.append(self._finding("non_pass_status", "blocker", "compliance", status, None, f"SOP requires all evaluated requirements to pass; found {count} {status} row(s).", "Resolve non-pass compliance statuses before SOP readiness."))

        blocker_count = sum(1 for item in findings if item["severity"] == "blocker")
        warning_count = sum(1 for item in findings if item["severity"] == "warning")
        readiness_status = "blocked" if blocker_count else ("conditional_pass" if warning_count else "pass")
        check_count = 5 + len(effective_requirements)
        score_numeric = max(0.0, 100.0 - blocker_count * 25.0 - warning_count * 5.0)
        run_id = f"RGATE-{_slug(project_id)}-{policy.stage}-{now.replace(':', '').replace('-', '').replace('.', '')}"

        result = {
            "run_id": run_id,
            "project_id": project_id,
            "stage": policy.stage,
            "baseline_id": baseline_id,
            "readiness_status": readiness_status,
            "score_numeric": score_numeric,
            "blocker_count": blocker_count,
            "warning_count": warning_count,
            "check_count": check_count,
            "evaluated_by": evaluated_by,
            "evaluated_at": now,
            "policy": policy.__dict__,
            "baseline": baseline_payload,
            "baseline_drift": drift_payload,
            "requirement_count": len(effective_requirements),
            "compliance_summary": compliance_summary,
            "review_summary": review_report.get("summary", {}),
            "findings": findings,
        }
        if persist:
            self._persist_run(result)
        return result

    def list_runs(self, *, project_id: str | None = None, stage: str | None = None, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if stage:
            clauses.append("stage = ?")
            params.append(stage.upper())
        if status:
            clauses.append("readiness_status = ?")
            params.append(status)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with closing(self.repo.connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT run_id, project_id, stage, baseline_id, readiness_status,
                       blocker_count, warning_count, check_count, score_numeric,
                       evaluated_by, evaluated_at, created_at
                FROM requirement_release_gate_runs
                {where}
                ORDER BY evaluated_at DESC, run_id DESC
                LIMIT ?
                """,
                [*params, int(limit)],
            ).fetchall()
        runs = [dict(row) for row in rows]
        return {"run_count": len(runs), "runs": runs}

    def get_run(self, run_id: str) -> dict[str, Any]:
        with closing(self.repo.connection()) as connection:
            row = connection.execute("SELECT * FROM requirement_release_gate_runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise ValueError(f"unknown release gate run_id: {run_id}")
            findings = connection.execute(
                """
                SELECT * FROM requirement_release_gate_findings
                WHERE run_id = ?
                ORDER BY CASE severity WHEN 'blocker' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                         finding_type ASC, finding_id ASC
                """,
                (run_id,),
            ).fetchall()
        payload = dict(row)
        try:
            payload["payload"] = json.loads(payload.get("payload_json") or "{}")
        except json.JSONDecodeError:
            payload["payload"] = {}
        payload["findings"] = [self._finding_row_to_dict(item) for item in findings]
        return payload

    def _resolve_baseline(self, project_id: str, baseline_id: str | None) -> dict[str, Any]:
        service = RequirementBaselineService(self.repo)
        if baseline_id:
            baseline = service.get_baseline(baseline_id, include_items=False)
            return {"baseline_id": baseline.get("baseline_id"), "status": baseline.get("status"), "baseline_version": baseline.get("baseline_version"), "source": "explicit"}
        listed = service.list_baselines(project_id=project_id, status="frozen", limit=1)
        baselines = listed.get("baselines", [])
        if not baselines:
            return {"baseline_id": None, "status": "missing", "source": "latest_frozen"}
        baseline = baselines[0]
        return {"baseline_id": baseline.get("baseline_id"), "status": baseline.get("status"), "baseline_version": baseline.get("baseline_version"), "source": "latest_frozen"}

    def _finding(self, finding_type: str, severity: str, source_type: str | None, source_id: str | None, atom_id: str | None, message: str, recommendation: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "finding_type": finding_type,
            "severity": severity,
            "source_type": source_type,
            "source_id": source_id,
            "atom_id": atom_id,
            "message": message,
            "recommendation": recommendation,
            "payload": payload or {},
        }

    def _persist_run(self, result: dict[str, Any]) -> None:
        now = utc_now()
        with closing(self.repo.connection()) as connection:
            connection.execute(
                """
                INSERT INTO requirement_release_gate_runs (
                    run_id, project_id, stage, baseline_id, readiness_status,
                    blocker_count, warning_count, check_count, score_numeric,
                    evaluated_by, evaluated_at, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result["run_id"],
                    result["project_id"],
                    result["stage"],
                    result.get("baseline_id"),
                    result["readiness_status"],
                    result["blocker_count"],
                    result["warning_count"],
                    result["check_count"],
                    result["score_numeric"],
                    result.get("evaluated_by"),
                    result["evaluated_at"],
                    _json(result),
                    now,
                ),
            )
            for index, finding in enumerate(result.get("findings", []), start=1):
                connection.execute(
                    """
                    INSERT INTO requirement_release_gate_findings (
                        finding_id, run_id, project_id, stage, finding_type, severity,
                        source_type, source_id, atom_id, message, recommendation,
                        payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"RGF-{_slug(result['run_id'])}-{index:03d}",
                        result["run_id"],
                        result["project_id"],
                        result["stage"],
                        finding.get("finding_type"),
                        finding.get("severity"),
                        finding.get("source_type"),
                        finding.get("source_id"),
                        finding.get("atom_id"),
                        finding.get("message"),
                        finding.get("recommendation"),
                        _json(finding.get("payload") or {}),
                        now,
                    ),
                )
            connection.commit()

    def _finding_row_to_dict(self, row) -> dict[str, Any]:
        payload = dict(row)
        try:
            payload["payload"] = json.loads(payload.get("payload_json") or "{}")
        except json.JSONDecodeError:
            payload["payload"] = {}
        return payload
