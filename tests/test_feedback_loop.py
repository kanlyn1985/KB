"""Tests for feedback_loop module."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from enterprise_agent_kb.feedback_loop import (
    EvalFailure,
    FeedbackAction,
    analyze_eval_failures,
    generate_feedback_actions,
    execute_feedback_actions,
)


def test_analyze_eval_failures_missing_file(tmp_path: Path) -> None:
    """analyze_eval_failures returns empty list when file doesn't exist."""
    result = analyze_eval_failures(tmp_path / "nonexistent.json")
    assert result == []


def test_analyze_eval_failures_empty_file(tmp_path: Path) -> None:
    """analyze_eval_failures returns empty list for empty JSON."""
    path = tmp_path / "eval.json"
    path.write_text("", encoding="utf-8")
    result = analyze_eval_failures(path)
    assert result == []


def test_analyze_eval_failures_no_failures(tmp_path: Path) -> None:
    """analyze_eval_failures returns empty list when all cases pass."""
    path = tmp_path / "eval.json"
    path.write_text(
        json.dumps({
            "cases": [
                {"query": "q1", "status": "passed", "must_include": "m1"},
                {"query": "q2", "status": "PASS", "must_include": "m2"},
            ],
        }),
        encoding="utf-8",
    )
    result = analyze_eval_failures(path)
    assert result == []


def test_analyze_eval_failures_retrieval_miss(tmp_path: Path) -> None:
    """analyze_eval_failures attributes retrieval_miss for zero hits."""
    path = tmp_path / "eval.json"
    path.write_text(
        json.dumps({
            "cases": [
                {
                    "query": "test query",
                    "status": "failed",
                    "must_include": "answer",
                    "retrieval_hits": 0,
                    "answer_match": False,
                },
            ],
        }),
        encoding="utf-8",
    )
    result = analyze_eval_failures(path)
    assert len(result) == 1
    assert result[0].failure_type == "retrieval_miss"
    assert result[0].root_cause == "retrieval_blank"


def test_analyze_eval_failures_answer_mismatch(tmp_path: Path) -> None:
    """analyze_eval_failures attributes answer_mismatch for non-zero hits but no answer match."""
    path = tmp_path / "eval.json"
    path.write_text(
        json.dumps({
            "cases": [
                {
                    "query": "test query",
                    "status": "failed",
                    "must_include": "answer",
                    "retrieval_hits": 5,
                    "answer_match": False,
                },
            ],
        }),
        encoding="utf-8",
    )
    result = analyze_eval_failures(path)
    assert len(result) == 1
    assert result[0].failure_type == "answer_mismatch"
    assert result[0].root_cause == "answer_construction_failed"


def test_analyze_eval_failures_context_miss(tmp_path: Path) -> None:
    """analyze_eval_failures attributes context_miss when answer matches but context doesn't."""
    path = tmp_path / "eval.json"
    path.write_text(
        json.dumps({
            "cases": [
                {
                    "query": "test query",
                    "status": "failed",
                    "must_include": "answer",
                    "retrieval_hits": 5,
                    "answer_match": True,
                    "context_match": False,
                },
            ],
        }),
        encoding="utf-8",
    )
    result = analyze_eval_failures(path)
    assert len(result) == 1
    assert result[0].failure_type == "context_miss"
    assert result[0].root_cause == "context_gap"


def test_analyze_eval_failures_doc_id_in_must_include(tmp_path: Path) -> None:
    """analyze_eval_failures can infer doc_id from must_include text."""
    path = tmp_path / "eval.json"
    path.write_text(
        json.dumps({
            "cases": [
                {
                    "query": "test query",
                    "status": "failed",
                    "must_include": "DOC-000003 expected answer",
                    "retrieval_hits": 0,
                },
            ],
        }),
        encoding="utf-8",
    )
    result = analyze_eval_failures(path)
    assert len(result) == 1
    assert result[0].case_must_include == "DOC-000003 expected answer"


def test_execute_feedback_actions_dry_run(tmp_path: Path) -> None:
    """execute_feedback_actions in dry_run mode doesn't execute."""
    actions = [
        FeedbackAction(
            action_type="auto_activate_golden",
            doc_id="DOC-000001",
            details={"reason": "retrieval_miss"},
        ),
    ]
    result = execute_feedback_actions(tmp_path, actions, dry_run=True)
    assert len(result) == 1
    assert result[0]["status"] == "dry_run"


def test_execute_feedback_actions_unknown_action(tmp_path: Path) -> None:
    """execute_feedback_actions handles unknown action types."""
    actions = [
        FeedbackAction(
            action_type="unknown_action",
            doc_id="DOC-000001",
            details={},
        ),
    ]
    result = execute_feedback_actions(tmp_path, actions)
    assert len(result) == 1
    assert result[0]["status"] == "unknown_action"