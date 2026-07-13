"""Requirement subcommand family.

Adapter that wires the Requirement Resolver program (`enterprise_agent_kb.requirements.cli`)
into the modular CLI orchestrator pattern used by the rest of the CLI
(`register_subcommand` + `handle_command`). This replaces the single-file
`cli.py` patch shipped in the overlay package, which targeted a legacy
single-file CLI layout that no longer matches this repository.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from enterprise_agent_kb.requirements.cli import (
    configure_parser as _configure_requirement_parser,
    handle_requirement_command,
)


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "requirement",
        help="Manage customer/project requirement profiles and effective requirements.",
    )
    _configure_requirement_parser(parser)


def handle_command(args: argparse.Namespace, schema_path: Path) -> bool:
    if args.command != "requirement":
        return False
    result: dict[str, Any] = handle_requirement_command(args.root, args)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return True
