from __future__ import annotations

from typing import Any


def build_openapi_spec(*, title: str = "Agent KB Core API", version: str = "0.4.0") -> dict[str, Any]:
    security = [{"bearerAuth": []}]
    simple_response = lambda description: {"200": {"description": description}}
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
                        "idempotency_key": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["text"],
                },
                "LegalHoldRequest": {
                    "type": "object",
                    "properties": {
                        "logical_document_id": {"type": "string"},
                        "reason": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["logical_document_id", "reason"],
                },
                "RetentionRequest": {
                    "type": "object",
                    "properties": {
                        "policy_id": {"type": "string"},
                        "retain_days": {"type": "integer", "minimum": 0},
                        "statuses": {"type": "array", "items": {"type": "string"}},
                        "dry_run": {"type": "boolean"},
                    },
                },
            },
        },
        "paths": {
            "/v1/health": {"get": {"security": security, "responses": simple_response("Service health")}},
            "/v1/query": {
                "post": {
                    "security": security,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/QueryRequest"}}},
                    },
                    "responses": simple_response("Evidence-grounded query result"),
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
            "/v1/documents": {"get": {"security": security, "responses": simple_response("Tenant documents")}},
            "/v1/feedback": {"post": {"security": security, "responses": {"201": {"description": "Feedback recorded"}}}},
            "/v1/jobs/index": {"post": {"security": security, "responses": {"202": {"description": "Index job accepted"}}}},
            "/v1/jobs/{job_id}": {
                "get": {
                    "security": security,
                    "parameters": [{"name": "job_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": simple_response("Background job state"),
                }
            },
            "/v1/metrics": {"get": {"security": security, "responses": simple_response("Metrics snapshot")}},
            "/v1/audit": {"get": {"security": security, "responses": simple_response("Tenant audit events")}},
            "/v1/admin/workers": {"get": {"security": security, "responses": simple_response("Active worker registry")}},
            "/v1/admin/worker-once": {"post": {"security": security, "responses": simple_response("Worker iteration result")}},
            "/v1/admin/backup": {"post": {"security": security, "responses": {"201": {"description": "Verified and replicated backup"}}}},
            "/v1/admin/purge": {"post": {"security": security, "responses": simple_response("Document purge and vector cleanup")}},
            "/v1/admin/legal-holds": {
                "post": {
                    "security": security,
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/LegalHoldRequest"}}},
                    },
                    "responses": {"201": {"description": "Legal hold placed"}},
                }
            },
            "/v1/admin/legal-holds/release": {"post": {"security": security, "responses": simple_response("Legal hold released")}},
            "/v1/admin/retention": {
                "post": {
                    "security": security,
                    "requestBody": {
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/RetentionRequest"}}},
                    },
                    "responses": simple_response("Retention evaluation or execution"),
                }
            },
        },
    }
