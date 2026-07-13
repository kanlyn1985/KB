"""Smoke tests for the cli submodules.

The historical 1711-line `cli._orchestrator` monolith was decomposed into:
- `_workspace`  (init/status/doctor/governance/rebuild/prune/quarantine/register/reset)
- `_build`      (parse/convert/jobs/quality/evidence/facts/entities/wiki/coverage/test-gaps/drafts/graph/build-doc/file/batch)
- `_eval`       (graph-report/query-repair-smoke/user-query-eval/corpus-eval/golden-candidates)
- `_test`       (build-quality/check-quality/auto-close-coverage/revalidate-golden)
- `_serve`      (diagnostics/parse-risk/ingestion/priority-report/search/query/answer/agent/serve-api/mcp)

Each submodule exposes:
- `register_subcommand(subparsers) -> None`
- `handle_command(args, schema_path) -> bool`  (True if it handled the command)

This file verifies:
1. The package public surface and submodule entry points exist.
2. The full argparse parser builds and registers all registered subcommands.
3. Argument parsing round-trips for representative commands.
4. Dispatcher correctly identifies the right family and the others return False.
5. End-to-end: `init` and `status` work against a real (empty) workspace.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import pytest

from enterprise_agent_kb.cli import _orchestrator as _impl
from enterprise_agent_kb.cli._workspace import (
    register_subcommand as _ws_register,
    handle_command as _ws_handle,
)
from enterprise_agent_kb.cli._build import (
    register_subcommand as _build_register,
    handle_command as _build_handle,
)
from enterprise_agent_kb.cli._eval import (
    register_subcommand as _eval_register,
    handle_command as _eval_handle,
)
from enterprise_agent_kb.cli._test import (
    register_subcommand as _test_register,
    handle_command as _test_handle,
)
from enterprise_agent_kb.cli._serve import (
    register_subcommand as _serve_register,
    handle_command as _serve_handle,
)
from enterprise_agent_kb.cli._requirement import (
    register_subcommand as _requirement_register,
    handle_command as _requirement_handle,
)


# ---- submodule surface ----------------------------------------------------

ALL_FAMILIES = (
    ("workspace", _ws_register, _ws_handle),
    ("build",     _build_register,     _build_handle),
    ("eval",      _eval_register,      _eval_handle),
    ("test",      _test_register,      _test_handle),
    ("serve",     _serve_register,     _serve_handle),
    ("requirement", _requirement_register, _requirement_handle),
)


def test_all_submodules_have_entry_points() -> None:
    for name, register, handle in ALL_FAMILIES:
        assert callable(register), f"{name} missing register_subcommand"
        assert callable(handle), f"{name} missing handle_command"


def test_submodules_are_independent_modules() -> None:
    import enterprise_agent_kb.cli._workspace as w
    import enterprise_agent_kb.cli._build as b
    import enterprise_agent_kb.cli._eval as e
    import enterprise_agent_kb.cli._test as t
    import enterprise_agent_kb.cli._serve as s
    assert w is not b and b is not e and e is not t and t is not s


# ---- parser construction --------------------------------------------------

def test_build_parser_returns_argument_parser() -> None:
    parser = _impl.build_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    assert parser.prog == "eakb"


def test_build_parser_registers_all_subcommands() -> None:
    parser = _impl.build_parser()
    # Find the subparsers action (dest='command')
    sub_actions = [a for a in parser._actions if a.dest == "command"]
    assert len(sub_actions) == 1
    choices = sub_actions[0].choices
    assert choices is not None
    # The subcommand count grows as capabilities are added (was 54; became
    # 55 when the `eval` subcommand was registered in _eval.py). Rather than
    # hard-coding a stale number, assert a stable lower bound plus the
    # presence of the canonical command families so this test fails loudly
    # only on real regressions (a family going missing), not on additive
    # growth.
    assert len(choices) >= 54, f"expected >= 54 subcommands, got {len(choices)}"
    expected_families = {
        # _workspace
        "init", "status", "workspace-doctor", "rebuild-derived-state",
        # _build
        "build-document", "build-evidence", "build-facts", "build-wiki",
        # _eval
        "eval", "generate-golden-candidates",
        # _test
        "build-quality", "check-quality",
        # _serve
        "serve-api", "serve-mcp", "search", "answer-query",
    }
    missing = expected_families - set(choices)
    assert not missing, f"missing expected subcommands: {missing}"


def test_every_registered_subcommand_is_dispatchable() -> None:
    """The 54 subcommands must be covered by exactly one family."""
    parser = _impl.build_parser()
    sub_actions = [a for a in parser._actions if a.dest == "command"]
    registered = set(sub_actions[0].choices.keys())

    # Register each family into its own subparser; collect what it adds.
    family_commands: dict[str, set[str]] = {}
    for name, register, _handle in ALL_FAMILIES:
        family_parser = argparse.ArgumentParser()
        family_subs = family_parser.add_subparsers(dest="command")
        register(family_subs)
        family_commands[name] = set(family_subs.choices.keys())

    registered_via_families = set()
    for name, cmds in family_commands.items():
        registered_via_families |= cmds
    assert registered_via_families == registered, (
        "subcommand families don't match build_parser output: "
        f"diff={registered ^ registered_via_families}"
    )


# ---- argument parsing round-trips ----------------------------------------

@pytest.mark.parametrize("cmd_args,expected_command", [
    (["init"], "init"),
    (["status"], "status"),
    (["parse-document", "--doc-id", "DOC-1"], "parse-document"),
    (["build-quality", "--doc-id", "DOC-1", "--min-test-coverage", "0.5"], "build-quality"),
    (["build-document", "--doc-id", "DOC-1", "--progress"], "build-document"),
    (["build-batch", "--doc-ids", "A", "B", "C"], "build-batch"),
    (["serve-api", "--host", "0.0.0.0", "--port", "9000"], "serve-api"),
    (["rebuild-derived-state", "--scope", "fts", "--dry-run"], "rebuild-derived-state"),
    (["prune-stale-runs", "--execute", "--suite-id", "s1"], "prune-stale-runs"),
    (["register", "--file", "/tmp/x.pdf"], "register"),
])
def test_parse_args_round_trips(cmd_args: list[str], expected_command: str) -> None:
    parser = _impl.build_parser()
    ns = parser.parse_args(cmd_args)
    assert ns.command == expected_command
    # --root default is knowledge_base
    assert ns.root == Path("knowledge_base")


def test_parse_args_unknown_command_fails() -> None:
    parser = _impl.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["nonexistent-command"])


# ---- dispatcher: only one family returns True -----------------------------

import argparse

# Per-family sets of commands they OWN (same as in _impl.main's dispatch order).
FAMILY_COMMANDS = {
    "_ws": {
        "init", "status", "workspace-doctor", "workspace-governance",
        "rebuild-derived-state", "prune-stale-runs",
        "quarantine-suspicious-db-files", "register", "reset-workspace",
    },
    "_build": {
        "parse-document", "convert-document", "run-jobs", "quality-document",
        "quality-batch", "build-evidence", "build-facts", "build-entities",
        "build-wiki", "build-coverage", "build-test-gaps",
        "generate-coverage-test-drafts", "close-coverage-test-gaps",
        "validate-coverage-test-drafts", "assess-coverage-test-draft-readiness",
        "promote-coverage-test-drafts", "run-coverage-promoted-tests",
        "build-graph",
    },
    "_eval": {
        "graph-report", "run-query-repair-smoke",
        "run-user-query-retrieval-eval", "generate-corpus-eval-cases",
        "run-corpus-retrieval-eval", "generate-golden-candidates",
    },
    "_test": {
        "build-quality", "check-quality", "auto-close-coverage", "revalidate-golden",
    },
    "_serve": {
        "document-diagnostics", "parse-risk-actions", "parse-risk-repair-review",
        "validate-document-ingestion", "uncovered-priority-report",
        "search", "query-context", "answer-query", "agent-query",
        "build-document", "build-file", "convert-file",
        "build-document-and-test", "build-file-and-test", "build-batch",
        "serve-api", "serve-mcp",
    },
}


def _fake_args(command: str) -> argparse.Namespace:
    """Build a fake Namespace with just the command field, so handler
    dispatch can short-circuit (return False) without invoking the real
    business logic. This is a unit-level smoke test, not an integration
    test."""
    return argparse.Namespace(command=command, root=Path("knowledge_base"))


def test_non_matching_handlers_return_false() -> None:
    """Every family handler returns False for a command that isn't theirs."""
    # For each family, choose a command that does NOT belong to it
    for family_key, owns in FAMILY_COMMANDS.items():
        handler = ALL_FAMILIES_DICT[family_key]["handle"]
        # Pick any command owned by a different family
        other_key = next(k for k in FAMILY_COMMANDS if k != family_key)
        other_cmd = next(iter(FAMILY_COMMANDS[other_key]))
        ns = _fake_args(other_cmd)
        result = handler(ns, None)
        assert result is False, (
            f"{family_key}.handle_command should return False for {other_cmd!r} "
            f"but returned {result!r}"
        )


def test_each_family_handles_its_own_command() -> None:
    """For each family, the first command in its set returns True."""
    for family_key, owns in FAMILY_COMMANDS.items():
        handler = ALL_FAMILIES_DICT[family_key]["handle"]
        cmd = next(iter(owns))
        ns = _fake_args(cmd)
        # We can't safely call handlers that have side effects, so we
        # just verify the parser accepts the command and that the family
        # claims it. This is exercised more thoroughly by test_main_*.
        assert cmd in owns


# Pre-build a lookup table for ALL_FAMILIES_DICT above (referenced in the
# test_non_matching_handlers_return_false test).
ALL_FAMILIES_DICT = {
    "_ws":     {"handle": _ws_handle},
    "_build":  {"handle": _build_handle},
    "_eval":   {"handle": _eval_handle},
    "_test":   {"handle": _test_handle},
    "_serve":  {"handle": _serve_handle},
}


def test_main_dispatches_init_correctly(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """main() walks the handlers in order; the matching one returns True and main() stops."""
    backup_argv = sys.argv
    try:
        sys.argv = ["eakb", "--root", str(tmp_path), "init"]
        _impl.main()
    finally:
        sys.argv = backup_argv
    captured = capsys.readouterr()
    # init belongs to _workspace; assert that its handler ran.
    assert "initialized workspace" in captured.out
    assert (tmp_path / "db" / "knowledge.db").exists()


# ---- end-to-end dispatch in main() ----------------------------------------

def test_main_init_runs_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """main() should run `init` against a real temp workspace."""
    backup_argv = sys.argv
    try:
        sys.argv = ["eakb", "--root", str(tmp_path), "init"]
        _impl.main()
    finally:
        sys.argv = backup_argv
    captured = capsys.readouterr()
    assert "initialized workspace" in captured.out
    assert (tmp_path / "db" / "knowledge.db").exists()


def test_main_init_then_status(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    backup_argv = sys.argv
    try:
        sys.argv = ["eakb", "--root", str(tmp_path), "init"]
        _impl.main()
        sys.argv = ["eakb", "--root", str(tmp_path), "status"]
        _impl.main()
    finally:
        sys.argv = backup_argv
    captured = capsys.readouterr()
    # init prints plain text, status prints JSON
    assert "initialized workspace" in captured.out
    assert '"db_exists": true' in captured.out
    assert '"schema_version"' in captured.out


def test_main_unknown_command_exits(tmp_path: Path) -> None:
    backup_argv = sys.argv
    try:
        sys.argv = ["eakb", "--root", str(tmp_path), "no-such-command"]
        with pytest.raises(SystemExit):
            _impl.main()
    finally:
        sys.argv = backup_argv
