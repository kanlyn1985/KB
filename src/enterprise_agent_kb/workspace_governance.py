from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .closed_loop_store import utc_now
from .derived_state_rebuild import DerivedStateRebuildReport, rebuild_derived_state
from .workspace_doctor import DOCTOR_SCOPES, WorkspaceDoctorIssue, WorkspaceDoctorReport, run_workspace_doctor


GOVERNANCE_POLICIES = ("conservative",)
_SAFE_DERIVED_SCOPES = {"fts", "graph", "wiki"}
_SAFE_COVERAGE_ISSUES = {
    "source_unit_fact_missing_unit",
    "source_unit_fact_missing_fact",
    "source_unit_evidence_missing_unit",
    "source_unit_evidence_missing_evidence",
}


@dataclass(frozen=True)
class WorkspaceGovernanceStep:
    step_id: str
    issue_id: str
    scope: str
    severity: str
    category: str
    action_type: str
    command: str
    executable: bool
    executed: bool
    status: str
    reason: str
    issue_details: dict[str, object]
    result: dict[str, object] | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceGovernanceReport:
    policy: str
    scope: str
    execute_safe: bool
    status: str
    workspace_root: str
    generated_at: str
    summary: dict[str, int]
    doctor_before: WorkspaceDoctorReport
    doctor_after: WorkspaceDoctorReport | None
    steps: tuple[WorkspaceGovernanceStep, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "scope": self.scope,
            "execute_safe": self.execute_safe,
            "status": self.status,
            "workspace_root": self.workspace_root,
            "generated_at": self.generated_at,
            "summary": self.summary,
            "doctor_before": self.doctor_before.to_dict(),
            "doctor_after": self.doctor_after.to_dict() if self.doctor_after is not None else None,
            "steps": [step.to_dict() for step in self.steps],
        }


def run_workspace_governance(
    workspace_root: Path,
    *,
    scope: str = "all",
    policy: str = "conservative",
    execute_safe: bool = False,
) -> WorkspaceGovernanceReport:
    if scope not in DOCTOR_SCOPES:
        raise ValueError(f"Unknown workspace governance scope: {scope}")
    if policy not in GOVERNANCE_POLICIES:
        raise ValueError(f"Unknown workspace governance policy: {policy}")

    doctor_before = run_workspace_doctor(workspace_root, scope=scope)
    steps = [
        _step_from_issue(index, issue, execute_safe=execute_safe)
        for index, issue in enumerate(doctor_before.issues, start=1)
    ]
    if execute_safe:
        steps = [_execute_step(workspace_root, step) for step in steps]
        doctor_after = run_workspace_doctor(workspace_root, scope=scope)
    else:
        doctor_after = None
    summary = _summary(steps)
    status = _status(doctor_before, doctor_after, steps)
    return WorkspaceGovernanceReport(
        policy=policy,
        scope=scope,
        execute_safe=execute_safe,
        status=status,
        workspace_root=str(workspace_root),
        generated_at=utc_now(),
        summary=summary,
        doctor_before=doctor_before,
        doctor_after=doctor_after,
        steps=tuple(steps),
    )


def format_workspace_governance_report(report: WorkspaceGovernanceReport) -> str:
    lines = [
        f"Workspace governance: {report.status}",
        f"Policy: {report.policy}",
        f"Scope: {report.scope}",
        f"Execute safe: {str(report.execute_safe).lower()}",
        (
            "Summary: "
            f"planned={report.summary.get('planned', 0)}, "
            f"executed={report.summary.get('executed', 0)}, "
            f"safe_to_auto_fix={report.summary.get('safe_to_auto_fix', 0)}, "
            f"historical_residue={report.summary.get('historical_residue', 0)}, "
            f"manual_review_required={report.summary.get('manual_review_required', 0)}, "
            f"active_data_corruption={report.summary.get('active_data_corruption', 0)}"
        ),
    ]
    if not report.steps:
        lines.append("")
        lines.append("No governance actions needed.")
        return "\n".join(lines)

    lines.append("")
    lines.append("Plan:")
    for step in report.steps:
        marker = "executed" if step.executed else "planned"
        lines.append(
            f"- [{step.category}] {step.scope}/{step.issue_id}: {marker}; "
            f"action={step.command}; reason={step.reason}"
        )
    return "\n".join(lines)


def _step_from_issue(
    index: int,
    issue: WorkspaceDoctorIssue,
    *,
    execute_safe: bool,
) -> WorkspaceGovernanceStep:
    category, action_type, command, executable, reason = _classify_issue(issue)
    return WorkspaceGovernanceStep(
        step_id=f"GOV-{index:04d}",
        issue_id=issue.issue_id,
        scope=issue.scope,
        severity=issue.severity,
        category=category,
        action_type=action_type,
        command=command,
        executable=bool(executable and execute_safe),
        executed=False,
        status="planned",
        reason=reason,
        issue_details=dict(issue.details),
        result=None,
    )


def _classify_issue(issue: WorkspaceDoctorIssue) -> tuple[str, str, str, bool, str]:
    if issue.scope in _SAFE_DERIVED_SCOPES:
        return (
            "safe_to_auto_fix",
            "rebuild_derived_state",
            f"rebuild-derived-state --scope {issue.scope}",
            True,
            "派生索引或派生引用残留，可由幂等重建或 reconcile 修复，不改主数据。",
        )
    if issue.scope == "coverage" and issue.issue_id in _SAFE_COVERAGE_ISSUES:
        return (
            "safe_to_auto_fix",
            "rebuild_derived_state",
            "rebuild-derived-state --scope coverage",
            True,
            "source unit 映射表存在孤儿引用，可安全 reconcile 映射派生行。",
        )
    if issue.scope == "runs":
        return (
            "historical_residue",
            "prune_stale_runs_dry_run",
            "prune-stale-runs --keep-current-code-version --keep-latest-code-versions 3 --dry-run",
            False,
            "旧/未知 code_version 的运行记录是历史残留；保守策略只生成剪枝计划，不自动删除。",
        )
    if issue.issue_id in {"workspace_root_missing", "workspace_database_missing", "workspace_database_empty"}:
        return (
            "active_data_corruption",
            "manual_review",
            issue.recommended_actions[0] if issue.recommended_actions else "manual-review",
            False,
            "工作区或主库不可用，属于活跃数据破坏，不能由派生状态治理自动修复。",
        )
    return (
        "manual_review_required",
        "manual_review",
        issue.recommended_actions[0] if issue.recommended_actions else "manual-review",
        False,
        "该问题需要先确认主数据、解析或抽取根因，不能按派生残留自动处理。",
    )


def _execute_step(workspace_root: Path, step: WorkspaceGovernanceStep) -> WorkspaceGovernanceStep:
    if not step.executable:
        return step
    if step.action_type != "rebuild_derived_state":
        return step

    result: DerivedStateRebuildReport = rebuild_derived_state(
        workspace_root,
        scope=step.scope,
        dry_run=False,
        mode="reconcile",
    )
    result_payload: dict[str, object] = result.to_dict()
    status = result.status
    if step.scope != "fts" and result.status == "ok":
        fts_result = rebuild_derived_state(
            workspace_root,
            scope="fts",
            dry_run=False,
            mode="reconcile",
        )
        result_payload = {
            "primary": result.to_dict(),
            "dependent_fts_refresh": fts_result.to_dict(),
        }
        status = _combine_status(result.status, fts_result.status)
    return WorkspaceGovernanceStep(
        step_id=step.step_id,
        issue_id=step.issue_id,
        scope=step.scope,
        severity=step.severity,
        category=step.category,
        action_type=step.action_type,
        command=step.command,
        executable=step.executable,
        executed=True,
        status=status,
        reason=step.reason,
        issue_details=step.issue_details,
        result=result_payload,
    )


def _summary(steps: list[WorkspaceGovernanceStep]) -> dict[str, int]:
    summary = {
        "planned": len(steps),
        "executed": 0,
        "safe_to_auto_fix": 0,
        "historical_residue": 0,
        "manual_review_required": 0,
        "active_data_corruption": 0,
    }
    for step in steps:
        if step.executed:
            summary["executed"] += 1
        if step.category in summary:
            summary[step.category] += 1
    return summary


def _combine_status(*statuses: str) -> str:
    if any(status == "fail" for status in statuses):
        return "fail"
    if any(status == "warn" for status in statuses):
        return "warn"
    return "ok"


def _status(
    doctor_before: WorkspaceDoctorReport,
    doctor_after: WorkspaceDoctorReport | None,
    steps: list[WorkspaceGovernanceStep],
) -> str:
    if doctor_after is not None:
        if doctor_after.status == "ok":
            return "ok"
        if any(step.category in {"active_data_corruption", "manual_review_required"} for step in steps):
            return "manual_review_required"
        return doctor_after.status
    if doctor_before.status == "ok":
        return "ok"
    if any(step.category in {"active_data_corruption", "manual_review_required"} for step in steps):
        return "manual_review_required"
    return "planned"


def write_workspace_governance_report(report: WorkspaceGovernanceReport, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = report.generated_at.replace(":", "").replace("-", "")
    report_path = output_dir / f"workspace-governance-{timestamp}.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return report_path
