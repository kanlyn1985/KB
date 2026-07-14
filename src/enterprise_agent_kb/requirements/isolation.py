"""Phase 6: Multi-project isolation guard.

Provides project-scoped access verification for requirement resources.
When a caller provides a project_id context, get_* methods verify that the
resource belongs to that project, raising PermissionError on mismatch.

This prevents cross-project data leakage when a user from project A tries
to access project B's ECO/baseline/approval by guessing IDs.
"""
from __future__ import annotations

from typing import Any


def assert_project_scope(resource: dict[str, Any], expected_project_id: str, resource_type: str, resource_id: str) -> None:
    """Verify that a resource belongs to the expected project.

    Raises PermissionError if the resource's project_id does not match.
    Does nothing if the resource has no project_id (shared resources).
    """
    resource_project = resource.get("project_id")
    if resource_project is not None and resource_project != expected_project_id:
        raise PermissionError(
            f"{resource_type} '{resource_id}' belongs to project '{resource_project}', "
            f"not '{expected_project_id}' (cross-project access denied)"
        )
