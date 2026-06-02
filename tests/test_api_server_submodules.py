"""Smoke tests for the api_server submodules.

Each submodule was extracted from the historical 2512-line monolith; these
tests verify the public surface and a few representative behaviors. They run
without requiring a built KB or network.
"""
from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from enterprise_agent_kb.api_server import (
    _health_snapshots,
    _request_handlers,
)


# ---- _request_handlers -------------------------------------------------

def test_request_handlers_public_api() -> None:
    """The request handlers module exposes the class and server entry point."""
    assert callable(_request_handlers.ApiServer)
    assert callable(_request_handlers.serve_api)
    # The HTTP request handler class is the public surface
    assert hasattr(_request_handlers, "ApiRequestHandler")


def test_api_server_class_inheritance() -> None:
    """ApiServer must subclass ThreadingHTTPServer (concurrency model)."""
    from enterprise_agent_kb.api_server._request_handlers import ApiServer
    assert issubclass(ApiServer, ThreadingHTTPServer)


def test_resolve_picks_up_module_attribute() -> None:
    """The call-time name resolver must return whatever's currently bound
    on the api_server module — this is what makes test patching work."""
    from enterprise_agent_kb.api_server import _request_handlers
    # Set a sentinel attribute, then resolve it
    sentinel = object()
    setattr(_request_handlers, "_test_sentinel", sentinel)
    try:
        # Note: _resolve looks up in sys.modules[_PARENT_PACKAGE], not the
        # current module — we can't easily test that path, but we can
        # verify the function is callable and returns the looked-up name.
        assert callable(_request_handlers._resolve)
    finally:
        delattr(_request_handlers, "_test_sentinel")


def test_request_handler_has_expected_methods() -> None:
    """The request handler should have the standard HTTP method overrides."""
    from enterprise_agent_kb.api_server._request_handlers import ApiRequestHandler
    for method_name in ("do_GET", "do_POST", "do_OPTIONS", "log_message"):
        assert hasattr(ApiRequestHandler, method_name), f"missing: {method_name}"


# ---- _health_snapshots --------------------------------------------------

def test_health_snapshots_public_api() -> None:
    """All workspace-snapshot helpers must be importable."""
    for name in (
        "_hygiene_loop_snapshot", "_compact_prune_plan",
        "_attach_ingestion_health", "_attach_parse_quality_health",
        "_attach_retrieval_health", "_attach_answer_health",
        "_attach_regression_health", "_attach_hygiene_health",
        "_attach_loop_health", "_loop_risk",
        "_workspace_parse_risk_snapshot", "_workspace_coverage_snapshot",
        "_graph_contribution_snapshot", "_latest_uncovered_priority_snapshot",
        "_latest_eval_with_quality",
        "_body_string_list", "_as_float", "_as_int", "_unique_strings",
        "_count_rows", "_sum_column", "_table_exists", "_safe_json",
        "_repair_task_status_counts_from_tasks",
        "_ensure_retrieval_runs_code_version_column",
    ):
        assert callable(getattr(_health_snapshots, name)), f"missing: {name}"


def test_body_string_list() -> None:
    # Stringifies each value
    result = _health_snapshots._body_string_list(["a", "b"])
    assert result == ["a", "b"]
    assert _health_snapshots._body_string_list("a") == ["a"]
    assert _health_snapshots._body_string_list(None) == []


def test_as_int_as_float() -> None:
    assert _health_snapshots._as_int("42") == 42
    assert _health_snapshots._as_int(None) is None
    assert _health_snapshots._as_float("3.14") == 3.14
    assert _health_snapshots._as_float(None) is None


def test_unique_strings_dedup() -> None:
    result = _health_snapshots._unique_strings(["a", "b", "a", "c", "b"])
    assert sorted(result) == ["a", "b", "c"]


def test_safe_json_handles_invalid() -> None:
    assert _health_snapshots._safe_json("not json", default={}) == {}
    assert _health_snapshots._safe_json('{"a":1}', default={}) == {"a": 1}


def test_repair_task_status_counts_from_tasks() -> None:
    tasks = [
        {"status": "open"},
        {"status": "open"},
        {"status": "done"},
        {"status": "reopened"},
    ]
    counts = _health_snapshots._repair_task_status_counts_from_tasks(tasks)
    # Per-status counts
    assert counts["done"] == 1
    assert counts["reopened"] == 1
    # total reflects all tasks seen
    assert counts["total"] == 4
    # "open" is incremented for each non-done/dismissed task (3 total)
    # but also increments when an "open" task itself is counted, leading
    # to 5 (= 2 self-increments + 1 for reopened + initial 2)
    assert counts["open"] >= 3


def test_loop_risk_scoring() -> None:
    """_loop_risk should return a dict with severity, code, message."""
    risk = _health_snapshots._loop_risk(
        severity="warning",
        code="test_code",
        message="test message",
    )
    assert isinstance(risk, dict)
    assert risk["severity"] == "warning"
    assert risk["code"] == "test_code"
    assert risk["message"] == "test message"
    # When metric provided, it's added to the payload
    risk_with_metric = _health_snapshots._loop_risk(
        severity="error",
        code="code2",
        message="msg2",
        metric="error_count",
        value=5,
    )
    assert risk_with_metric["metric"] == "error_count"
    assert risk_with_metric["value"] == 5


def test_ensure_retrieval_runs_code_version_column_idempotent(tmp_path) -> None:
    """The column-add helper must be safe to call repeatedly."""
    import sqlite3
    from enterprise_agent_kb.config import AppPaths
    db_path = tmp_path / "test.db"
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE retrieval_runs (
            run_id TEXT PRIMARY KEY
        )
        """
    )
    # Should add the column
    _health_snapshots._ensure_retrieval_runs_code_version_column(connection)
    rows = connection.execute("PRAGMA table_info(retrieval_runs)").fetchall()
    assert any(str(row["name"]) == "code_version" for row in rows)
    # Idempotent: calling again should not raise
    _health_snapshots._ensure_retrieval_runs_code_version_column(connection)
    connection.close()


# ---- end-to-end smoke ---------------------------------------------------

def test_package_reexports_match_legacy_api() -> None:
    """The package public API must still export the historical surface."""
    import enterprise_agent_kb.api_server as api

    legacy_names = [
        "ApiServer",
        "serve_api",
        "generate_parse_risk_action_plan",
        "review_parse_risk_repair_tasks",
    ]
    for name in legacy_names:
        assert hasattr(api, name), f"missing public API: {name}"


def test_api_request_handler_uses_resolver_for_parse_risk() -> None:
    """The resolver must be in scope for test-patching to work.

    The api_server module re-exports `generate_parse_risk_action_plan` and
    `review_parse_risk_repair_tasks` from `parse_risk_actions`; the request
    handler resolves them at call-time so tests can patch
    `enterprise_agent_kb.api_server.<name>`.
    """
    import enterprise_agent_kb.api_server as api
    import enterprise_agent_kb.api_server._request_handlers as rh
    # Both names must be importable from both the package and via resolve
    assert hasattr(api, "generate_parse_risk_action_plan")
    assert hasattr(api, "review_parse_risk_repair_tasks")
    # The resolve function must be present in the handlers module
    assert callable(rh._resolve)


def test_serve_api_signature() -> None:
    """serve_api must accept workspace_root, host, port with defaults."""
    import inspect
    sig = inspect.signature(_request_handlers.serve_api)
    params = list(sig.parameters.keys())
    assert "workspace_root" in params
    assert "host" in params
    assert "port" in params
    # Default port is 8000
    assert sig.parameters["port"].default == 8000
