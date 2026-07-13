from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .answer import answer_requirement_query
from .approval import RequirementApprovalService
from .compliance import RequirementComplianceService
from .diff import RequirementDiffService
from .impact import RequirementImpactAnalyzer
from .extraction import RequirementExtractionService
from .package_import import RequirementPackageImportService
from .baseline import RequirementBaselineService
from .release_gate import RequirementReleaseGateService
from .eco import RequirementEcoService
from .query import execute_requirement_query, plan_requirement_query
from .repository import RequirementRepository
from .resolver import RequirementResolver
from .seed import seed_sample_data


def configure_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    subparsers = parser.add_subparsers(dest="requirement_command", required=True)

    subparsers.add_parser("init-schema", help="Create or upgrade requirement management tables.")
    subparsers.add_parser("seed-sample", help="Insert a small CUST-A/DCDC sample requirement dataset.")

    resolve_parser = subparsers.add_parser("resolve", help="Resolve one effective requirement for a project.")
    resolve_parser.add_argument("--project-id", required=True)
    resolve_parser.add_argument("--atom-id", required=True)

    resolve_project_parser = subparsers.add_parser("resolve-project", help="Resolve all known requirements for a project.")
    resolve_project_parser.add_argument("--project-id", required=True)

    diff_parser = subparsers.add_parser("diff", help="Diff project effective requirements against a base profile.")
    diff_parser.add_argument("--project-id", required=True)
    diff_parser.add_argument("--base-profile-id", required=True)

    scan_parser = subparsers.add_parser("scan-conflicts", help="Resolve a project and return non-clean requirements.")
    scan_parser.add_argument("--project-id", required=True)

    plan_parser = subparsers.add_parser("plan-query", help="Plan a natural-language requirement query without executing it.")
    plan_parser.add_argument("--query", required=True)

    ask_parser = subparsers.add_parser("ask", help="Answer a natural-language requirement query through the MVP resolver.")
    ask_parser.add_argument("--query", required=True)
    ask_parser.add_argument("--raw", action="store_true", help="Return the full JSON payload instead of only direct_answer.")

    impact_parser = subparsers.add_parser("impact", help="Dry-run requirement variant change impact analysis.")
    impact_parser.add_argument("--variant-id", required=True)
    impact_parser.add_argument("--new-value", type=float, required=True)
    impact_parser.add_argument("--unit")
    impact_parser.add_argument("--operator")

    compliance_parser = subparsers.add_parser("compliance", help="Build a test coverage and compliance matrix for a project.")
    compliance_parser.add_argument("--project-id", required=True)
    compliance_parser.add_argument("--atom-id", help="Optional requirement atom to evaluate.")

    review_parser = subparsers.add_parser("review", help="Build a requirement review and approval-risk report.")
    review_parser.add_argument("--project-id", help="Optional project ID to limit the review report.")

    approval_list_parser = subparsers.add_parser("list-approvals", help="List requirement approval requests.")
    approval_list_parser.add_argument("--project-id")
    approval_list_parser.add_argument("--status")

    request_parser = subparsers.add_parser("request-approval", help="Create or resubmit an approval request.")
    request_parser.add_argument("--target-type", required=True)
    request_parser.add_argument("--target-id", required=True)
    request_parser.add_argument("--project-id")
    request_parser.add_argument("--atom-id")
    request_parser.add_argument("--variant-id")
    request_parser.add_argument("--override-id")
    request_parser.add_argument("--risk-level", default="medium")
    request_parser.add_argument("--reason")
    request_parser.add_argument("--requested-by")
    request_parser.add_argument("--evidence-id")

    approve_parser = subparsers.add_parser("approve", help="Approve a requirement approval request.")
    approve_parser.add_argument("--approval-id", required=True)
    approve_parser.add_argument("--approver", required=True)
    approve_parser.add_argument("--evidence-id")
    approve_parser.add_argument("--comment")

    reject_parser = subparsers.add_parser("reject", help="Reject a requirement approval request.")
    reject_parser.add_argument("--approval-id", required=True)
    reject_parser.add_argument("--approver", required=True)
    reject_parser.add_argument("--reason")


    extract_parser = subparsers.add_parser("extract-candidates", help="Extract review-only requirement candidates from text or facts.")
    extract_source = extract_parser.add_mutually_exclusive_group(required=True)
    extract_source.add_argument("--text", help="Raw requirement text to scan.")
    extract_source.add_argument("--doc-id", help="Extract candidates from facts belonging to this document ID.")
    extract_parser.add_argument("--profile-id", help="Suggested target requirement profile for promoted variants.")
    extract_parser.add_argument("--limit", type=int, default=50)

    list_candidates_parser = subparsers.add_parser("list-candidates", help="List extracted requirement candidates awaiting review.")
    list_candidates_parser.add_argument("--batch-id")
    list_candidates_parser.add_argument("--status")
    list_candidates_parser.add_argument("--profile-id")
    list_candidates_parser.add_argument("--limit", type=int, default=100)

    promote_parser = subparsers.add_parser("promote-candidate", help="Promote one reviewed candidate into requirement_variants.")
    promote_parser.add_argument("--candidate-id", required=True)
    promote_parser.add_argument("--profile-id", help="Override the candidate's suggested target profile.")
    promote_parser.add_argument("--promoted-by")

    reject_candidate_parser = subparsers.add_parser("reject-candidate", help="Reject one requirement candidate.")
    reject_candidate_parser.add_argument("--candidate-id", required=True)
    reject_candidate_parser.add_argument("--reviewer")
    reject_candidate_parser.add_argument("--reason")


    import_parser = subparsers.add_parser("import-package", help="Import a customer project requirement package into review-first candidates.")
    import_parser.add_argument("--customer-id", required=True)
    import_parser.add_argument("--customer-name")
    import_parser.add_argument("--project-id", required=True)
    import_parser.add_argument("--project-code")
    import_parser.add_argument("--product-family", default="DCDC")
    import_parser.add_argument("--package-name")
    import_parser.add_argument("--profile-scope", choices=["project_overlay", "customer_common"], default="project_overlay")
    import_parser.add_argument("--text", action="append", help="Requirement text block. Can be repeated.")
    import_parser.add_argument("--text-file", type=Path, action="append", help="UTF-8 text file containing requirement text. Can be repeated.")
    import_parser.add_argument("--auto-promote", action="store_true", help="Immediately promote extracted candidates into the selected profile. Safe default is review-only.")
    import_parser.add_argument("--promoted-by")
    import_parser.add_argument("--refresh-effective", action="store_true")

    list_packages_parser = subparsers.add_parser("list-import-packages", help="List customer/project requirement package imports.")
    list_packages_parser.add_argument("--customer-id")
    list_packages_parser.add_argument("--project-id")
    list_packages_parser.add_argument("--status")
    list_packages_parser.add_argument("--limit", type=int, default=100)

    refresh_package_parser = subparsers.add_parser("refresh-import-package", help="Recompute effective requirements for an imported package project.")
    refresh_package_parser.add_argument("--package-id", required=True)



    freeze_baseline_parser = subparsers.add_parser("freeze-baseline", help="Freeze the current resolved requirements as a project baseline snapshot.")
    freeze_baseline_parser.add_argument("--project-id", required=True)
    freeze_baseline_parser.add_argument("--name")
    freeze_baseline_parser.add_argument("--version")
    freeze_baseline_parser.add_argument("--parent-baseline-id")
    freeze_baseline_parser.add_argument("--frozen-by")
    freeze_baseline_parser.add_argument("--comment")

    list_baselines_parser = subparsers.add_parser("list-baselines", help="List frozen project requirement baselines.")
    list_baselines_parser.add_argument("--project-id")
    list_baselines_parser.add_argument("--status")
    list_baselines_parser.add_argument("--limit", type=int, default=100)

    show_baseline_parser = subparsers.add_parser("show-baseline", help="Show one frozen requirement baseline with its snapshot items.")
    show_baseline_parser.add_argument("--baseline-id", required=True)
    show_baseline_parser.add_argument("--no-items", action="store_true")

    diff_baselines_parser = subparsers.add_parser("diff-baselines", help="Compare two frozen requirement baselines.")
    diff_baselines_parser.add_argument("--base-baseline-id", required=True)
    diff_baselines_parser.add_argument("--head-baseline-id", required=True)

    drift_parser = subparsers.add_parser("baseline-drift", help="Compare a frozen baseline against current resolver output.")
    drift_parser.add_argument("--baseline-id", required=True)

    rollback_parser = subparsers.add_parser("rollback-baseline", help="Build a dry-run rollback plan for a frozen baseline.")
    rollback_parser.add_argument("--baseline-id", required=True)



    release_gate_parser = subparsers.add_parser("release-gate", help="Evaluate DV/PV/SOP release readiness for a project.")
    release_gate_parser.add_argument("--project-id", required=True)
    release_gate_parser.add_argument("--stage", choices=["DV", "PV", "SOP"], default="DV")
    release_gate_parser.add_argument("--baseline-id")
    release_gate_parser.add_argument("--evaluated-by")
    release_gate_parser.add_argument("--no-persist", action="store_true")

    list_release_gate_parser = subparsers.add_parser("list-release-gates", help="List persisted release gate evaluations.")
    list_release_gate_parser.add_argument("--project-id")
    list_release_gate_parser.add_argument("--stage", choices=["DV", "PV", "SOP"])
    list_release_gate_parser.add_argument("--status")
    list_release_gate_parser.add_argument("--limit", type=int, default=100)

    show_release_gate_parser = subparsers.add_parser("show-release-gate", help="Show one release gate run and findings.")
    show_release_gate_parser.add_argument("--run-id", required=True)


    create_eco_parser = subparsers.add_parser("create-eco", help="Create an engineering change order and run deterministic impact analysis.")
    create_eco_parser.add_argument("--project-id", required=True)
    create_eco_parser.add_argument("--title", required=True)
    create_eco_parser.add_argument("--variant-id", required=True)
    create_eco_parser.add_argument("--new-value", type=float, required=True)
    create_eco_parser.add_argument("--unit")
    create_eco_parser.add_argument("--operator")
    create_eco_parser.add_argument("--created-by")
    create_eco_parser.add_argument("--description")
    create_eco_parser.add_argument("--no-auto-analyze", action="store_true")

    eco_submit_parser = subparsers.add_parser("submit-eco", help="Submit an ECO for approval.")
    eco_submit_parser.add_argument("--eco-id", required=True)
    eco_submit_parser.add_argument("--submitted-by")
    eco_submit_parser.add_argument("--reason")

    eco_approve_parser = subparsers.add_parser("approve-eco", help="Approve an ECO approval request.")
    eco_approve_parser.add_argument("--eco-id", required=True)
    eco_approve_parser.add_argument("--approver", required=True)
    eco_approve_parser.add_argument("--comment")

    eco_apply_parser = subparsers.add_parser("apply-eco", help="Apply an approved ECO requirement variant change.")
    eco_apply_parser.add_argument("--eco-id", required=True)
    eco_apply_parser.add_argument("--applied-by")
    eco_apply_parser.add_argument("--no-refresh-effective", action="store_true")

    eco_close_parser = subparsers.add_parser("close-eco", help="Freeze post-change baseline and rerun release gate for an applied ECO.")
    eco_close_parser.add_argument("--eco-id", required=True)
    eco_close_parser.add_argument("--stage", choices=["DV", "PV", "SOP"], default="DV")
    eco_close_parser.add_argument("--closed-by")
    eco_close_parser.add_argument("--no-freeze-baseline", action="store_true")

    eco_full_parser = subparsers.add_parser("run-eco-cycle", help="Run the full ECO cycle in a controlled workspace.")
    eco_full_parser.add_argument("--project-id", required=True)
    eco_full_parser.add_argument("--title", required=True)
    eco_full_parser.add_argument("--variant-id", required=True)
    eco_full_parser.add_argument("--new-value", type=float, required=True)
    eco_full_parser.add_argument("--unit")
    eco_full_parser.add_argument("--operator")
    eco_full_parser.add_argument("--actor")
    eco_full_parser.add_argument("--stage", choices=["DV", "PV", "SOP"], default="DV")

    list_eco_parser = subparsers.add_parser("list-ecos", help="List engineering change orders.")
    list_eco_parser.add_argument("--project-id")
    list_eco_parser.add_argument("--status")
    list_eco_parser.add_argument("--limit", type=int, default=100)

    show_eco_parser = subparsers.add_parser("show-eco", help="Show one engineering change order.")
    show_eco_parser.add_argument("--eco-id", required=True)

    return parser


def handle_requirement_command(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    repo = RequirementRepository(root)

    if args.requirement_command == "init-schema":
        tables = repo.initialize_schema()
        return {"status": "ok", "tables": tables}

    if args.requirement_command == "seed-sample":
        counts = seed_sample_data(root)
        return {"status": "ok", "inserted_or_replaced": counts}

    if args.requirement_command == "resolve":
        effective = RequirementResolver(repo).resolve_requirement(args.project_id, args.atom_id)
        return effective.to_dict()

    if args.requirement_command == "resolve-project":
        requirements = RequirementResolver(repo).resolve_project(args.project_id)
        return {
            "project_id": args.project_id,
            "count": len(requirements),
            "requirements": [requirement.to_dict() for requirement in requirements],
        }

    if args.requirement_command == "diff":
        return RequirementDiffService(repo).diff_project_against_profile(
            args.project_id,
            args.base_profile_id,
        )

    if args.requirement_command == "scan-conflicts":
        requirements = RequirementResolver(repo).resolve_project(args.project_id)
        issues = [
            requirement.to_dict()
            for requirement in requirements
            if requirement.conflict_status != "none" or requirement.verification_status != "verified"
        ]
        return {"project_id": args.project_id, "issue_count": len(issues), "issues": issues}

    if args.requirement_command == "plan-query":
        return plan_requirement_query(root, args.query)

    if args.requirement_command == "ask":
        payload = answer_requirement_query(root, args.query)
        if args.raw:
            return payload
        return {"direct_answer": payload["direct_answer"], "intent": payload.get("intent"), "plan": payload.get("plan")}

    if args.requirement_command == "impact":
        return RequirementImpactAnalyzer(repo).analyze_variant_change(
            args.variant_id,
            {"value_numeric": args.new_value, "unit": args.unit, "operator": args.operator},
        )

    if args.requirement_command == "compliance":
        service = RequirementComplianceService(repo)
        if getattr(args, "atom_id", None):
            return service.build_requirement_compliance(args.project_id, args.atom_id)
        return service.build_project_matrix(args.project_id)

    if args.requirement_command == "review":
        return RequirementApprovalService(repo).build_review_report(project_id=getattr(args, "project_id", None))

    if args.requirement_command == "list-approvals":
        return {
            "approvals": RequirementApprovalService(repo).list_approvals(
                project_id=getattr(args, "project_id", None),
                status=getattr(args, "status", None),
            )
        }

    if args.requirement_command == "request-approval":
        return RequirementApprovalService(repo).create_approval_request(
            target_type=args.target_type,
            target_id=args.target_id,
            project_id=args.project_id,
            atom_id=args.atom_id,
            variant_id=args.variant_id,
            override_id=args.override_id,
            risk_level=args.risk_level,
            reason=args.reason,
            requested_by=args.requested_by,
            evidence_id=args.evidence_id,
        )

    if args.requirement_command == "approve":
        return RequirementApprovalService(repo).approve(
            args.approval_id,
            approver=args.approver,
            evidence_id=args.evidence_id,
            comment=args.comment,
        )

    if args.requirement_command == "reject":
        return RequirementApprovalService(repo).reject(
            args.approval_id,
            approver=args.approver,
            reason=args.reason,
        )


    if args.requirement_command == "extract-candidates":
        service = RequirementExtractionService(repo)
        if getattr(args, "text", None):
            return service.extract_from_text(args.text, profile_id=getattr(args, "profile_id", None))
        return service.extract_from_facts(
            doc_id=getattr(args, "doc_id", None),
            profile_id=getattr(args, "profile_id", None),
            limit=getattr(args, "limit", 50),
        )

    if args.requirement_command == "list-candidates":
        return RequirementExtractionService(repo).list_candidates(
            batch_id=getattr(args, "batch_id", None),
            status=getattr(args, "status", None),
            profile_id=getattr(args, "profile_id", None),
            limit=getattr(args, "limit", 100),
        )

    if args.requirement_command == "promote-candidate":
        return RequirementExtractionService(repo).promote_candidate(
            args.candidate_id,
            profile_id=getattr(args, "profile_id", None),
            promoted_by=getattr(args, "promoted_by", None),
        )

    if args.requirement_command == "reject-candidate":
        return RequirementExtractionService(repo).reject_candidate(
            args.candidate_id,
            reviewer=getattr(args, "reviewer", None),
            reason=getattr(args, "reason", None),
        )


    if args.requirement_command == "import-package":
        sources = []
        for index, text in enumerate(getattr(args, "text", None) or [], start=1):
            sources.append({"name": f"inline-{index}", "text": text, "source_type": "cli_text"})
        for path in getattr(args, "text_file", None) or []:
            sources.append({"name": path.name, "text": path.read_text(encoding="utf-8"), "source_type": "cli_text_file", "source_id": str(path)})
        if not sources:
            raise ValueError("--text or --text-file is required for import-package")
        return RequirementPackageImportService(repo).import_project_package(
            customer_id=args.customer_id,
            customer_name=getattr(args, "customer_name", None),
            project_id=args.project_id,
            project_code=args.project_code or args.project_id,
            product_family=args.product_family,
            package_name=getattr(args, "package_name", None),
            profile_scope=args.profile_scope,
            sources=sources,
            auto_promote=args.auto_promote,
            promoted_by=getattr(args, "promoted_by", None),
            refresh_effective=args.refresh_effective,
            actor=getattr(args, "promoted_by", None) or "cli",
        )

    if args.requirement_command == "list-import-packages":
        return RequirementPackageImportService(repo).list_import_packages(
            customer_id=getattr(args, "customer_id", None),
            project_id=getattr(args, "project_id", None),
            status=getattr(args, "status", None),
            limit=getattr(args, "limit", 100),
        )

    if args.requirement_command == "refresh-import-package":
        return RequirementPackageImportService(repo).refresh_package_effective_requirements(args.package_id)



    if args.requirement_command == "freeze-baseline":
        return RequirementBaselineService(repo).freeze_project_baseline(
            args.project_id,
            baseline_name=getattr(args, "name", None),
            baseline_version=getattr(args, "version", None),
            parent_baseline_id=getattr(args, "parent_baseline_id", None),
            frozen_by=getattr(args, "frozen_by", None),
            comment=getattr(args, "comment", None),
        )

    if args.requirement_command == "list-baselines":
        return RequirementBaselineService(repo).list_baselines(
            project_id=getattr(args, "project_id", None),
            status=getattr(args, "status", None),
            limit=getattr(args, "limit", 100),
        )

    if args.requirement_command == "show-baseline":
        return RequirementBaselineService(repo).get_baseline(args.baseline_id, include_items=not getattr(args, "no_items", False))

    if args.requirement_command == "diff-baselines":
        return RequirementBaselineService(repo).compare_baselines(args.base_baseline_id, args.head_baseline_id)

    if args.requirement_command == "baseline-drift":
        return RequirementBaselineService(repo).detect_drift(args.baseline_id)

    if args.requirement_command == "rollback-baseline":
        return RequirementBaselineService(repo).build_rollback_plan(args.baseline_id)



    if args.requirement_command == "release-gate":
        return RequirementReleaseGateService(repo).evaluate_project(
            args.project_id,
            stage=getattr(args, "stage", "DV"),
            baseline_id=getattr(args, "baseline_id", None),
            evaluated_by=getattr(args, "evaluated_by", None),
            persist=not getattr(args, "no_persist", False),
        )

    if args.requirement_command == "list-release-gates":
        return RequirementReleaseGateService(repo).list_runs(
            project_id=getattr(args, "project_id", None),
            stage=getattr(args, "stage", None),
            status=getattr(args, "status", None),
            limit=getattr(args, "limit", 100),
        )

    if args.requirement_command == "show-release-gate":
        return RequirementReleaseGateService(repo).get_run(args.run_id)


    if args.requirement_command == "create-eco":
        return RequirementEcoService(repo).create_change_order(
            project_id=args.project_id,
            title=args.title,
            variant_id=args.variant_id,
            proposed_change={"value_numeric": args.new_value, "unit": args.unit, "operator": args.operator},
            created_by=getattr(args, "created_by", None),
            description=getattr(args, "description", None),
            auto_analyze=not getattr(args, "no_auto_analyze", False),
        )

    if args.requirement_command == "submit-eco":
        return RequirementEcoService(repo).submit_for_approval(
            args.eco_id,
            submitted_by=getattr(args, "submitted_by", None),
            reason=getattr(args, "reason", None),
        )

    if args.requirement_command == "approve-eco":
        return RequirementEcoService(repo).approve(
            args.eco_id,
            approver=args.approver,
            comment=getattr(args, "comment", None),
        )

    if args.requirement_command == "apply-eco":
        return RequirementEcoService(repo).apply_change(
            args.eco_id,
            applied_by=getattr(args, "applied_by", None),
            refresh_effective=not getattr(args, "no_refresh_effective", False),
        )

    if args.requirement_command == "close-eco":
        return RequirementEcoService(repo).close_with_release_gate(
            args.eco_id,
            stage=getattr(args, "stage", "DV"),
            closed_by=getattr(args, "closed_by", None),
            freeze_baseline=not getattr(args, "no_freeze_baseline", False),
        )

    if args.requirement_command == "run-eco-cycle":
        return RequirementEcoService(repo).run_full_cycle(
            project_id=args.project_id,
            title=args.title,
            variant_id=args.variant_id,
            proposed_change={"value_numeric": args.new_value, "unit": args.unit, "operator": args.operator},
            actor=getattr(args, "actor", None),
            stage=getattr(args, "stage", "DV"),
        )

    if args.requirement_command == "list-ecos":
        return RequirementEcoService(repo).list_change_orders(
            project_id=getattr(args, "project_id", None),
            status=getattr(args, "status", None),
            limit=getattr(args, "limit", 100),
        )

    if args.requirement_command == "show-eco":
        return RequirementEcoService(repo).get_change_order(args.eco_id)

    raise ValueError(f"unsupported requirement command: {args.requirement_command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m enterprise_agent_kb.requirements.cli")
    parser.add_argument("--root", type=Path, default=Path("knowledge_base"))
    configure_parser(parser)


    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = handle_requirement_command(args.root, args)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
