"""Tests for evaluation domain models."""

from __future__ import annotations

import pytest

from enterprise_agent_kb.domain.eval import (
    EvalRun,
    GoldenCase,
    RetrievalRun,
    FailureRecord,
    FailureAnalysis,
)


class TestEvalRun:
    """Test EvalRun domain model."""

    def test_create_eval_run(self) -> None:
        """Should create evaluation run with required fields."""
        run = EvalRun(
            run_id="eval-test-001",
            suite_id="test-suite",
            timestamp="2026-06-01T12:00:00",
        )
        assert run.run_id == "eval-test-001"
        assert run.suite_id == "test-suite"

    def test_eval_run_default_status(self) -> None:
        """EvalRun should have pending as default status."""
        run = EvalRun(
            run_id="eval-test-002",
            suite_id="test-suite",
            timestamp="2026-06-01T12:00:00",
        )
        assert run.status == "pending"

    def test_is_complete_returns_true_when_complete(self) -> None:
        """is_complete should return True when status is complete."""
        run = EvalRun(
            run_id="eval-test-003",
            suite_id="test-suite",
            timestamp="2026-06-01T12:00:00",
            status="complete",
        )
        assert run.is_complete()

    def test_is_complete_returns_false_when_pending(self) -> None:
        """is_complete should return False when status is pending."""
        run = EvalRun(
            run_id="eval-test-004",
            suite_id="test-suite",
            timestamp="2026-06-01T12:00:00",
            status="pending",
        )
        assert not run.is_complete()


class TestGoldenCase:
    """Test GoldenCase domain model."""

    def test_create_golden_case(self) -> None:
        """Should create golden case with required fields."""
        case = GoldenCase(
            case_id="case-001",
            query="test query",
            doc_id="DOC-001",
            expected_result={"answer": "test answer"},
        )
        assert case.case_id == "case-001"
        assert case.query == "test query"

    def test_is_active_returns_true_when_active(self) -> None:
        """is_active should return True when status is active."""
        case = GoldenCase(
            case_id="case-002",
            query="test query",
            doc_id="DOC-002",
            expected_result={},
            status="active",
        )
        assert case.is_active()

    def test_is_active_returns_false_when_inactive(self) -> None:
        """is_active should return False when status is not active."""
        case = GoldenCase(
            case_id="case-003",
            query="test query",
            doc_id="DOC-003",
            expected_result={},
            status="draft",
        )
        assert not case.is_active()


class TestRetrievalRun:
    """Test RetrievalRun domain model."""

    def test_create_retrieval_run(self) -> None:
        """Should create retrieval run with required fields."""
        run = RetrievalRun(
            run_id="retrieval-001",
            query="test query",
            timestamp="2026-06-01T12:00:00",
            hit_count=5,
        )
        assert run.run_id == "retrieval-001"
        assert run.hit_count == 5

    def test_retrieval_run_default_status(self) -> None:
        """RetrievalRun should have success as default status."""
        run = RetrievalRun(
            run_id="retrieval-002",
            query="test query",
            timestamp="2026-06-01T12:00:00",
            hit_count=0,
        )
        assert run.status == "success"


class FailureRecordDomain:
    """Test FailureRecord domain model."""

    def test_create_test_failure(self) -> None:
        """Should create test failure with required fields."""
        failure = FailureRecord(
            case_id="case-001",
            failure_type="assertion_failed",
            actual_result={"actual": "wrong"},
            expected_result={"expected": "correct"},
        )
        assert failure.case_id == "case-001"
        assert failure.failure_type == "assertion_failed"


class FailureRecordAnalysis:
    """Test FailureAnalysis domain model."""

    def test_create_failure_analysis(self) -> None:
        """Should create failure analysis."""
        analysis = FailureAnalysis(
            eval_run_id="eval-test-001",
            case_id="case-001",
        )
        assert analysis.eval_run_id == "eval-test-001"
        assert len(analysis.failures) == 0
        assert len(analysis.root_causes) == 0

    def test_failure_analysis_with_failures(self) -> None:
        """Should create failure analysis with failures."""
        failure = FailureRecord(
            case_id="case-002",
            failure_type="assertion_failed",
            actual_result={},
            expected_result={},
        )
        analysis = FailureAnalysis(
            eval_run_id="eval-test-002",
            case_id="case-002",
            failures=[failure],
            root_causes=["logic error"],
            suggested_fixes=["fix the bug"],
        )
        assert len(analysis.failures) == 1
        assert "logic error" in analysis.root_causes
