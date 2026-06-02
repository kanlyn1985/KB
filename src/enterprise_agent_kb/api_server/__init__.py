"""HTTP API server: HTTP request handler, route dispatch, health snapshots.

The public surface is split across focused submodules:
- `_request_handlers`: `ApiRequestHandler`, `ApiServer`, `serve_api`
- `_health_snapshots`: workspace-status aggregations (hygiene loop,
  parse risk, coverage, graph contribution, latest eval with quality)
"""
from __future__ import annotations

from ._health_snapshots import (
    _attach_hygiene_health,
    _attach_ingestion_health,
    _attach_regression_health,
    _attach_retrieval_health,
    _graph_contribution_snapshot,
    _hygiene_loop_snapshot,
    _latest_eval_with_quality,
    _latest_uncovered_priority_snapshot,
    _repair_task_status_counts_from_tasks,
    _workspace_coverage_snapshot,
    _workspace_parse_risk_snapshot,
)
from ._request_handlers import (
    ApiServer,
    serve_api,
)
# Re-export the names the test suite patches onto the api_server module.
from enterprise_agent_kb.parse_risk_actions import (  # noqa: E402,F401
    generate_parse_risk_action_plan,
    review_parse_risk_repair_tasks,
)

__all__ = [
    "ApiServer",
    "serve_api",
]
