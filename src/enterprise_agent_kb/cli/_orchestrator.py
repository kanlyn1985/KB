"""CLI orchestrator: argparse setup and main() dispatch.

Subcommand argument definitions and main() handlers are split across the
following per-domain submodules:
- `_workspace`: init, status, doctor, governance, rebuild, prune,
  quarantine, register, reset
- `_build`: parse, convert, jobs, quality, evidence, facts, entities,
  wiki, coverage, test-gaps, drafts, graph, build-document/file/batch
- `_eval`: graph-report, run-query-repair-smoke, run-user-query-retrieval-eval,
  generate-corpus-eval-cases, run-corpus-retrieval-eval,
  generate-golden-candidates
- `_test`: build-quality, check-quality, auto-close-coverage, revalidate-golden
- `_serve`: diagnostics, parse-risk-actions, parse-risk-repair-review,
  validate-document-ingestion, uncovered-priority-report, search,
  query-context, answer-query, agent-query, serve-api, serve-mcp

Each submodule exposes `register_subcommand(subparsers)` and
`handle_command(args, schema_path) -> bool` entrypoints. This orchestrator
walks the families in the original order and dispatches to the first
match.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from ._workspace import register_subcommand as _workspace_register, handle_command as _workspace_handle
from ._build import register_subcommand as _build_register, handle_command as _build_handle
from ._eval import register_subcommand as _eval_register, handle_command as _eval_handle
from ._test import register_subcommand as _test_register, handle_command as _test_handle
from ._serve import register_subcommand as _serve_register, handle_command as _serve_handle
from ._requirement import register_subcommand as _requirement_register, handle_command as _requirement_handle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eakb",
        description="Enterprise agent knowledge base bootstrap CLI.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("knowledge_base"),
        help="Workspace root directory for the knowledge base.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand families (in original order):
    _workspace_register(subparsers)
    _build_register(subparsers)
    _eval_register(subparsers)
    _test_register(subparsers)
    _serve_register(subparsers)
    _requirement_register(subparsers)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    # The schema lives in the parent package directory, not in cli/.
    schema_path = Path(__file__).resolve().parent.parent / "schema.sql"

    # Dispatch to the matching subcommand family. Each handler returns
    # True if it recognized and ran the command, False otherwise. The
    # first handler that returns True wins; the rest are skipped.
    for handler in (
        _workspace_handle,
        _build_handle,
        _eval_handle,
        _test_handle,
        _serve_handle,
        _requirement_handle,
    ):
        if handler(args, schema_path):
            return
    parser.error(f"unsupported command: {args.command}")
