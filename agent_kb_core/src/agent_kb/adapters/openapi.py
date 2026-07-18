from __future__ import annotations

from typing import Any


def build_openapi_spec(*, title: str = "Agent KB Core API", version: str = "0.3.0") -> dict[str, Any]:
    security = [{"bearerAuth": []}]
    return {
        "openapi": "3.1.0",
        "info": {"title": title, "version": version},
        "servers": [{"url": "/"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"},
            },
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                        "detail": {"type": "string"},
                        "request_id": {"type": "string"},
                    },
                    "required": ["error"],
                },
                "QueryRequest": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "minLength": 1},
                        "top_k": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "required": ["query"],
                },
                "IndexRequest": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "minLength": 1},
                        "title": {"type": "string"},
                        "logical_document_id": {"type": "string"},
                        "version_label": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["text"],
                },
            },
        },
        "paths": {
            "/v1/health": {
                "get": {
                    "security": security,
                    "responses": {"200": {"description": "Service health"}},
                }
            },
            "/v1/query": {
                "post": {
                    "security": security,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/QueryRequest"}}},
                    },
                    "responses": {"200": {"description": "Evidence-grounded query result"}},
                }
            },
            "/v1/index": {
                "post": {
                    "security": security,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/IndexRequest"}}},
                    },
                    "responses": {"201": {"description": "Indexed document version"}},
                }
            },
            "/v1/documents": {
                "get": {
                    "security": security,
                    "responses": {"200": {"description": "Tenant-scoped documents"}},
                }
            },
            "/v1/feedback": {
                "post": {
                    "security": security,
                    "responses": {"201": {"description": "Feedback recorded"}},
                }
            },
            "/v1/jobs/index": {
                "post": {
                    "security": security,
                    "responses": {"202": {"description": "Index job accepted"}},
                }
            },
            "/v1/admin/backup": {
                "post": {
                    "security": security,
                    "responses": {"201": {"description": "Verified database backup"}},
                }
            },
            "/v1/admin/purge": {
                "post": {
                    "security": security,
                    "responses": {"200": {"description": "Transactional document purge"}},
                }
            },
            "/v1/metrics": {
                "get": {
                    "security": security,
                    "responses": {"200": {"description": "Process metrics snapshot"}},
                }
            },
        },
    }
