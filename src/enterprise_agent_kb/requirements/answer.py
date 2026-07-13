from __future__ import annotations

from pathlib import Path
from typing import Any

from .query import RequirementQueryPlanner


def answer_requirement_query(root: Path, query: str) -> dict[str, Any]:
    """Return a deterministic answer payload for requirement-scoped queries.

    This is intentionally separate from the existing answer_api. It can be called by the
    main query chain later, after the MVP resolver has proven stable.
    """
    planner = RequirementQueryPlanner.from_root(root)
    plan = planner.plan(query)
    result = planner.execute(plan)
    return {**result, "direct_answer": render_requirement_answer(result)}


def render_requirement_answer(result: dict[str, Any]) -> str:
    intent = result.get("intent")
    if intent == "requirement_effective":
        effective = result.get("effective_requirement", {})
        path = effective.get("resolution_path", [])
        lines = [
            f"最终有效需求：{effective.get('effective_requirement_text', '')}",
            f"项目：{effective.get('project_id', '')}",
            f"需求原子：{effective.get('atom_id', '')}",
            f"冲突状态：{effective.get('conflict_status', '')}",
            f"证据状态：{effective.get('verification_status', '')}",
        ]
        if path:
            lines.append("解析路径：")
            for step in path:
                lines.append(
                    f"- {step.get('profile_type')} / {step.get('profile_id')}: "
                    f"{step.get('requirement_text')} ({step.get('effect')})"
                )
        evidence_ids = effective.get("evidence_ids") or []
        if evidence_ids:
            lines.append("证据ID：" + ", ".join(evidence_ids))
        return "\n".join(lines)

    if intent == "requirement_diff":
        diff = result.get("diff", {}).get("diff", {})
        lines = ["项目需求差异："]
        for bucket in ("added", "tightened", "loosened", "replaced", "ambiguous"):
            items = diff.get(bucket) or []
            if not items:
                continue
            lines.append(f"{bucket}: {len(items)}")
            for item in items:
                if isinstance(item, dict):
                    lines.append(
                        f"- {item.get('atom_id')}: {item.get('base_requirement', '')} -> "
                        f"{item.get('project_requirement', '')} ({item.get('effect', '')})"
                    )
        return "\n".join(lines)

    if intent == "requirement_impact":
        impact = result.get("impact", {})
        summary = impact.get("summary", {})
        lines = [
            f"变更影响分析：{impact.get('variant_id', '')}",
            f"需求原子：{impact.get('atom_id', '')}",
            f"受影响项目数：{summary.get('affected_project_count', 0)}",
            f"需要回归测试：{summary.get('regression_required_count', 0)}",
            f"需要评审/审批：{summary.get('review_required_count', 0)}",
        ]
        for project in impact.get("affected_projects", []):
            current = project.get("current_effective_requirement", {})
            proposed = project.get("proposed_requirement", {})
            lines.append(
                f"- {project.get('project_id')}: {project.get('impact_type')} / "
                f"current={current.get('effective_requirement_text', '')} / "
                f"proposed={proposed.get('requirement_text', '')} / "
                f"regression={project.get('regression_test_required')} / "
                f"review={project.get('review_required')}"
            )
        return "\n".join(lines)

    if intent == "requirement_compliance":
        compliance = result.get("compliance", {})
        summary = compliance.get("summary", {})
        rows = compliance.get("rows") or ([compliance.get("row")] if compliance.get("row") else [])
        lines = [
            f"合规矩阵：项目 {compliance.get('project_id', '')}",
            f"总体状态：{summary.get('overall_status', '')}",
            f"状态计数：{summary.get('status_counts', {})}",
        ]
        for row in rows:
            if not isinstance(row, dict):
                continue
            effective = row.get("effective_requirement", {})
            lines.append(
                f"- {row.get('atom_id')}: {effective.get('effective_requirement_text', '')} / "
                f"compliance={row.get('compliance_status')} / "
                f"requirement_conflict={row.get('requirement_conflict_status')}"
            )
        return "\n".join(lines)

    if intent == "requirement_conflict_scan":
        issues = result.get("issues", [])
        lines = [f"发现问题需求：{len(issues)}"]
        for issue in issues:
            lines.append(
                f"- {issue.get('atom_id')}: {issue.get('effective_requirement_text')} / "
                f"conflict={issue.get('conflict_status')} / verification={issue.get('verification_status')}"
            )
        return "\n".join(lines)

    if intent == "requirement_review":
        review = result.get("review", {})
        summary = review.get("summary", {})
        lines = [
            f"需求评审/审批报告：项目 {review.get('project_id') or 'ALL'}",
            f"待评审项：{summary.get('review_item_count', 0)}",
            f"需要审批：{summary.get('approval_required_count', 0)}",
            f"需要补证据：{summary.get('evidence_required_count', 0)}",
        ]
        for item in review.get("review_items", []):
            lines.append(
                f"- {item.get('project_id')}: {item.get('review_type')} / "
                f"{item.get('source_id')} / severity={item.get('severity')} / "
                f"approval_required={item.get('approval_required')} / evidence_required={item.get('evidence_required')}"
            )
        return "\n".join(lines)






    if intent == "requirement_eco":
        if result.get("eco"):
            eco = result.get("eco", {})
            lines = [
                f"工程变更单：{eco.get('eco_id', '')}",
                f"项目：{eco.get('project_id', '')}",
                f"状态：{eco.get('status', '')}",
                f"目标需求版本：{eco.get('target_variant_id', '')}",
                f"拟变更：{eco.get('proposed_change', {})}",
            ]
            impact = eco.get("impact") or {}
            if impact:
                summary = impact.get("summary", {})
                lines.extend([
                    f"受影响项目：{summary.get('affected_project_count', 0)}",
                    f"需要回归测试：{summary.get('regression_required_count', 0)}",
                    f"需要评审：{summary.get('review_required_count', 0)}",
                ])
            for action in eco.get("actions", [])[:20]:
                lines.append(f"- action={action.get('action_type')} / project={action.get('project_id')} / status={action.get('status')}")
            return "\n".join(lines)
        payload = result.get("ecos", {})
        ecos = payload.get("ecos", [])
        lines = [f"工程变更单：{payload.get('eco_count', len(ecos))}"]
        for eco in ecos:
            lines.append(f"- {eco.get('eco_id')}: project={eco.get('project_id')} / status={eco.get('status')} / target={eco.get('target_variant_id')}")
        return "\n".join(lines)

    if intent == "requirement_release_gate":
        gate = result.get("release_gate", {})
        lines = [
            f"发布门禁：项目 {gate.get('project_id', '')} / 阶段 {gate.get('stage', '')}",
            f"结论：{gate.get('readiness_status', '')}",
            f"评分：{gate.get('score_numeric', '')}",
            f"阻断项：{gate.get('blocker_count', 0)}",
            f"警告项：{gate.get('warning_count', 0)}",
            f"基线：{gate.get('baseline_id') or 'missing'}",
        ]
        for finding in gate.get("findings", [])[:20]:
            lines.append(
                f"- [{finding.get('severity')}] {finding.get('finding_type')}: "
                f"{finding.get('message')}"
            )
        return "\n".join(lines)

    if intent == "requirement_baseline":
        payload = result.get("baselines", {})
        baselines = payload.get("baselines", [])
        lines = [f"项目需求基线：{payload.get('baseline_count', len(baselines))}"]
        for baseline in baselines:
            lines.append(
                f"- {baseline.get('baseline_id')}: project={baseline.get('project_id')} / "
                f"version={baseline.get('baseline_version')} / status={baseline.get('status')} / "
                f"requirements={baseline.get('requirement_count')} / conflicts={baseline.get('conflict_count')}"
            )
        return "\n".join(lines)

    if intent == "requirement_import_packages":
        payload = result.get("import_packages", {})
        packages = payload.get("packages", [])
        lines = [f"需求包导入记录：{payload.get('package_count', len(packages))}"]
        for package in packages:
            lines.append(
                f"- {package.get('package_id')}: customer={package.get('customer_id')} / "
                f"project={package.get('project_id')} / status={package.get('status')} / "
                f"candidates={package.get('candidate_count')} / promoted={package.get('promoted_count')}"
            )
        return "\n".join(lines)

    if intent == "requirement_candidates":
        payload = result.get("candidates", {})
        candidates = payload.get("candidates", [])
        lines = [
            f"待评审需求候选：{payload.get('candidate_count', len(candidates))}",
        ]
        for candidate in candidates:
            lines.append(
                f"- {candidate.get('candidate_id')}: {candidate.get('normalized_text')} / "
                f"atom={candidate.get('suggested_atom_id')} / "
                f"value={candidate.get('operator') or ''}{candidate.get('value_numeric') or ''}{candidate.get('unit') or ''} / "
                f"confidence={candidate.get('confidence')} / status={candidate.get('status')}"
            )
        return "\n".join(lines)

    plan = result.get("plan", {})
    reason = plan.get("clarification_reason") or "该问题尚不能由 Requirement Resolver MVP 确定性处理。"
    return f"需要澄清：{reason}"
