"""Command-line interface (CLI) entry point.

The argparse setup and main() dispatch live in `_orchestrator`. Per-domain
subcommand argument definitions and handlers are split across:
- `_workspace`, `_build`, `_eval`, `_test`, `_serve`.
"""
from __future__ import annotations

from ._orchestrator import build_parser, main

__all__ = ["build_parser", "main"]
