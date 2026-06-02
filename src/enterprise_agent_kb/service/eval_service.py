"""Evaluation and testing application services.

This module contains business logic for evaluation,
golden case management, and failure analysis.
"""

from __future__ import annotations

from pathlib import Path

from ..config import AppPaths
from ..domain.eval import EvalRun, GoldenCase, FailureRecord, FailureAnalysis
from ..infrastructure.eval_repository import EvalRepository, GoldenCaseRepository


class EvalService:
    """Service for evaluation run management."""

    def __init__(self, workspace_root: Path):
        """Initialize evaluation service."""
        self.paths = AppPaths.from_root(workspace_root)
        self.eval_repo = EvalRepository(workspace_root)

    def record_eval_run(
        self,
        suite_id: str,
        structured: dict[str, object],
    ) -> EvalRun:
        """Record and return evaluation run."""
        run_id = self.eval_repo.record_eval_run(
            suite_id=suite_id,
            structured=structured,
            runtime_code_version="0.1.0",
        )

        return self.eval_repo.get_eval_run_detail(run_id) or EvalRun(
            run_id=run_id,
            suite_id=suite_id,
            timestamp="",
            status="pending",
        )

    def list_eval_runs(
        self,
        suite_id: str | None = None,
        limit: int = 30,
    ) -> list[EvalRun]:
        """List evaluation runs."""
        runs = self.eval_repo.list_eval_runs(suite_id=suite_id, limit=limit)
        return [
            EvalRun(
                run_id=run["run_id"],
                suite_id=run["suite_id"],
                timestamp=run["timestamp"],
                status=run["status"],
            )
            for run in runs
        ]


class GoldenCaseService:
    """Service for golden case management."""

    def __init__(self, workspace_root: Path):
        """Initialize golden case service."""
        self.paths = AppPaths.from_root(workspace_root)
        self.golden_repo = GoldenCaseRepository(workspace_root)

    def sync_golden_cases(self, cases: list[dict[str, object]]) -> int:
        """Sync golden cases and return count."""
        return self.golden_repo.sync_golden_cases(cases)

    def list_golden_cases(self, limit: int = 100) -> list[GoldenCase]:
        """List golden cases."""
        cases = self.golden_repo.list_golden_cases(limit=limit)
        return [
            GoldenCase(
                case_id=case["case_id"],
                query=case["query"],
                doc_id=case["doc_id"],
                expected_result=case["expected"],
                metadata=case["metadata"],
                status=case.get("status", "active"),
                created_at=case.get("created_at", ""),
            )
            for case in cases
        ]

    def load_golden_cases_from_file(self, golden_path: Path) -> list[GoldenCase]:
        """Load golden cases from file."""
        cases = self.golden_repo.load_golden_cases_from_file(golden_path)
        return [
            GoldenCase(
                case_id=case["case_id"],
                query=case["query"],
                doc_id=case["doc_id"],
                expected_result=case.get("expected_result", {}),
                metadata=case.get("metadata", {}),
                status=case.get("status", "active"),
                created_at=case.get("created_at", ""),
            )
            for case in cases
        ]


class FailureAnalysisService:
    """Service for failure analysis and debugging."""

    def __init__(self, workspace_root: Path):
        """Initialize failure analysis service."""
        self.paths = AppPaths.from_root(workspace_root)
        self.eval_repo = EvalRepository(workspace_root)

    def build_failure_analysis(
        self,
        eval_run_id: str,
        case_id: str | None = None,
    ) -> FailureAnalysis | None:
        """Build failure analysis for evaluation run."""
        # This is a simplified implementation
        # Real implementation would analyze test results and identify root causes
        return FailureAnalysis(
            eval_run_id=eval_run_id,
            case_id=case_id,
            failures=[],
            root_causes=["Analysis not yet implemented"],
            suggested_fixes=["TBD"],
        )
