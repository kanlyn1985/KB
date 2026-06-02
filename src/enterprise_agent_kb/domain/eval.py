"""Evaluation and testing domain models.

This module contains pure domain concepts for evaluation runs,
golden cases, and test results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class EvalRun:
    """Evaluation run domain model."""
    run_id: str
    suite_id: str
    timestamp: str
    status: str = "pending"
    metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_complete(self) -> bool:
        """Check if evaluation run is complete."""
        return self.status == "complete"


@dataclass
class RetrievalRun:
    """Retrieval run domain model."""
    run_id: str
    query: str
    timestamp: str
    hit_count: int
    status: str = "success"
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class GoldenCase:
    """Golden test case domain model."""
    case_id: str
    query: str
    doc_id: str
    expected_result: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "active"
    created_at: str = ""

    def is_active(self) -> bool:
        """Check if golden case is active."""
        return self.status == "active"


@dataclass
class SourceUnit:
    """Source unit domain model."""
    unit_id: str
    doc_id: str
    unit_type: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FailureRecord:
    """Test failure domain model."""
    case_id: str
    failure_type: str
    actual_result: dict[str, Any]
    expected_result: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)


@dataclass
class FailureAnalysis:
    """Failure analysis result."""
    eval_run_id: str
    case_id: str | None
    failures: list[FailureRecord] = field(default_factory=list)
    root_causes: list[str] = field(default_factory=list)
    suggested_fixes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
