"""Workspace-level commands: init, status, doctor, governance, rebuild, prune, quarantine, register, reset.

Extracted from `cli._impl` to isolate the per-domain argparse
subparser definitions and the corresponding main() handler branches.
The orchestrator (`cli._impl.build_parser` and `cli._impl.main`)
re-exports the public surface.
"""
from __future__ import annotations


import json
from pathlib import Path

from ..bootstrap import initialize_workspace, workspace_status
from ..db_hygiene import quarantine_suspicious_db_files
from ..derived_state_rebuild import REBUILD_MODES, REBUILD_SCOPES, rebuild_derived_state
from ..ingest import register_document
from ..run_governance import prune_stale_runs
from ..workspace_admin import reset_workspace_data
from ..workspace_doctor import DOCTOR_SCOPES, format_workspace_doctor_report, run_workspace_doctor
from ..workspace_governance import (
    GOVERNANCE_POLICIES,
    format_workspace_governance_report,
    run_workspace_governance,
)


def register_subcommand(subparsers) -> None:
    """Register the subparser(s) for this command family."""
    subparsers.add_parser("init", help="Create the workspace layout and SQLite schema.")
    subparsers.add_parser("status", help="Print workspace and database status.")
    doctor_parser = subparsers.add_parser(
        "workspace-doctor",
        help="Run read-only workspace hygiene diagnostics.",
    )
    doctor_parser.add_argument(
        "--scope",
        choices=DOCTOR_SCOPES,
        default="all",
        help="Diagnostic scope to run.",
    )
    doctor_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of text.",
    )
    governance_parser = subparsers.add_parser(
        "workspace-governance",
        help="Build a policy-based data governance plan and optionally execute safe actions.",
    )
    governance_parser.add_argument(
        "--scope",
        choices=DOCTOR_SCOPES,
        default="all",
        help="Diagnostic scope to govern.",
    )
    governance_parser.add_argument(
        "--policy",
        choices=GOVERNANCE_POLICIES,
        default="conservative",
        help="Governance policy. Conservative mode only executes safe derived-state repairs.",
    )
    governance_parser.add_argument(
        "--execute-safe",
        action="store_true",
        help="Execute actions classified as safe_to_auto_fix. Historical run pruning remains dry-run only.",
    )
    governance_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of text.",
    )
    rebuild_parser = subparsers.add_parser(
        "rebuild-derived-state",
        help="Rebuild derived state artifacts.",
    )
    rebuild_parser.add_argument(
        "--scope",
        choices=REBUILD_SCOPES,
        default="fts",
        help="Derived state scope to rebuild.",
    )
    rebuild_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report planned rebuild actions without changing data.",
    )
    rebuild_parser.add_argument(
        "--mode",
        choices=REBUILD_MODES,
        default="reconcile",
        help="Rebuild mode. reconcile cleans orphan artifacts; full regenerates graph/wiki/coverage from source data.",
    )
    rebuild_parser.add_argument(
        "--doc-id",
        default=None,
        help="Limit full rebuild to one active document. Only valid with --mode full and graph/wiki/coverage/all scopes.",
    )
    prune_runs_parser = subparsers.add_parser(
        "prune-stale-runs",
        help="Plan or prune stale/unknown retrieval and eval runs.",
    )
    prune_runs_parser.add_argument(
        "--suite-id",
        default=None,
        help="Only prune eval_runs for this suite. Retrieval runs are skipped when this is set.",
    )
    prune_runs_parser.add_argument(
        "--older-than-days",
        type=int,
        default=None,
        help="Only prune candidate runs older than this many days.",
    )
    prune_runs_parser.add_argument(
        "--keep-current-code-version",
        action="store_true",
        default=True,
        help="Keep runs from the current code version.",
    )
    prune_runs_parser.add_argument(
        "--keep-latest-code-versions",
        type=int,
        default=0,
        help="Also keep runs from the latest N non-empty code versions in each run table.",
    )
    prune_runs_parser.add_argument(
        "--archive-dir",
        type=Path,
        default=None,
        help="Directory for JSON archives written before --execute deletes candidate runs.",
    )
    prune_runs_parser.add_argument(
        "--allow-without-current-baseline",
        action="store_true",
        help="Allow --execute even when the current code version has no retrieval/eval baseline rows.",
    )
    prune_mode_group = prune_runs_parser.add_mutually_exclusive_group()
    prune_mode_group.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Report candidate runs without deleting data. This is the default.",
    )
    prune_mode_group.add_argument(
        "--execute",
        dest="dry_run",
        action="store_false",
        help="Delete the planned stale/unknown runs.",
    )
    prune_runs_parser.set_defaults(dry_run=True)
    quarantine_db_parser = subparsers.add_parser(
        "quarantine-suspicious-db-files",
        help="Plan or quarantine extra suspicious .db files outside the primary database path.",
    )
    quarantine_db_mode_group = quarantine_db_parser.add_mutually_exclusive_group()
    quarantine_db_mode_group.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Report suspicious database files without moving them. This is the default.",
    )
    quarantine_db_mode_group.add_argument(
        "--execute",
        dest="dry_run",
        action="store_false",
        help="Move suspicious database files into knowledge_base/quarantine/db.",
    )
    quarantine_db_parser.set_defaults(dry_run=True)
    register_parser = subparsers.add_parser(
        "register",
        help="Register a source document into the knowledge base.",
    )
    register_parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to the source file to ingest.",
    )
    reset_parser = subparsers.add_parser(
        "reset-workspace",
        help="Delete ingested records and generated artifacts.",
    )
    reset_parser.add_argument(
        "--drop-raw",
        action="store_true",
        help="Also delete files under raw/.",
    )




def handle_command(args, schema_path) -> bool:
    """Handle the main() branch for this command family."""
    if args.command == "init":
        paths = initialize_workspace(args.root, schema_path)
        print(f"initialized workspace: {paths.root}")
        print(f"database: {paths.db_file}")
        return True
    if args.command == "status":
        status = workspace_status(args.root)
        print(json.dumps(status, indent=2, ensure_ascii=False))
        return True
    if args.command == "workspace-doctor":
        report = run_workspace_doctor(args.root, scope=args.scope)
        if args.json:
            print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(format_workspace_doctor_report(report))
        return True
    if args.command == "workspace-governance":
        report = run_workspace_governance(
            args.root,
            scope=args.scope,
            policy=args.policy,
            execute_safe=args.execute_safe,
        )
        if args.json:
            print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(format_workspace_governance_report(report))
        return True
    if args.command == "rebuild-derived-state":
        report = rebuild_derived_state(
            args.root,
            scope=args.scope,
            dry_run=args.dry_run,
            mode=args.mode,
            doc_id=args.doc_id,
        )
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return True
    if args.command == "prune-stale-runs":
        report = prune_stale_runs(
            args.root,
            suite_id=args.suite_id,
            older_than_days=args.older_than_days,
            keep_current_code_version=args.keep_current_code_version,
            keep_latest_code_versions=args.keep_latest_code_versions,
            allow_without_current_baseline=args.allow_without_current_baseline,
            archive_dir=args.archive_dir,
            dry_run=args.dry_run,
        )
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return True
    if args.command == "quarantine-suspicious-db-files":
        report = quarantine_suspicious_db_files(args.root, dry_run=args.dry_run)
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return True
    if args.command == "register":
        result = register_document(args.root, args.file)
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "job_id": result.job_id,
                    "deduplicated": result.deduplicated,
                    "stored_path": str(result.stored_path),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return True
    if args.command == "reset-workspace":
        result = reset_workspace_data(args.root, keep_raw=not args.drop_raw)
        print(
            json.dumps(
                {
                    "keep_raw": result.keep_raw,
                    "deleted_rows": result.deleted_rows,
                    "deleted_files": result.deleted_files,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return True

    return False
