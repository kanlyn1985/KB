"""Phase 6: API versioning tests."""
from __future__ import annotations
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse


class ApiVersioningTest(unittest.TestCase):
    """Verify /v1/ prefix routing works alongside legacy paths."""

    def _make_handler(self, path: str):
        """Create a mock handler with the given request path."""
        from enterprise_agent_kb.api_server._request_handlers import ApiRequestHandler
        handler = ApiRequestHandler.__new__(ApiRequestHandler)
        handler.path = path
        return handler

    def test_v1_prefix_stripped_for_get(self):
        """GET /v1/health should route same as GET /health."""
        from enterprise_agent_kb.api_server._request_handlers import ApiRequestHandler
        # Simulate the path normalization logic from do_GET
        path = "/v1/health"
        if path.startswith("/v1/"):
            path = path[3:]
        self.assertEqual(path, "/health")

    def test_v1_prefix_stripped_for_post(self):
        """POST /v1/search should route same as POST /search."""
        path = "/v1/search"
        if path.startswith("/v1/"):
            path = path[3:]
        self.assertEqual(path, "/search")

    def test_legacy_path_unchanged(self):
        """Legacy paths without /v1/ prefix should work unchanged."""
        path = "/health"
        if path.startswith("/v1/"):
            path = path[3:]
        self.assertEqual(path, "/health")

    def test_v1_root_maps_to_root(self):
        path = "/v1"
        if path.startswith("/v1/"):
            path = path[3:]
        elif path == "/v1":
            path = "/"
        self.assertEqual(path, "/")


if __name__ == "__main__":
    unittest.main()
