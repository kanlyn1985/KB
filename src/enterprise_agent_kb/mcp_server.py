from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from .agent_tools import run_agent_query
from .answer_api import answer_query
from .pipeline import run_document_pipeline
from .query_api import build_query_context
from .retrieval import search_knowledge_base


ToolHandler = Callable[[Path, dict[str, Any]], Any]


def run_mcp_stdio(workspace_root: Path) -> None:
    handlers: dict[str, ToolHandler] = {
        "search": _tool_search,
        "query_context": _tool_query_context,
        "answer_query": _tool_answer_query,
        "agent_query": _tool_agent_query,
        "build_document": _tool_build_document,
    }

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
            )
            continue

        message_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "enterprise-agent-kb",
                        "version": "0.1.0",
                    },
                    "capabilities": {
                        "tools": {},
                    },
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": _tool_descriptors()}
            elif method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments", {})
                if name not in handlers:
                    raise ValueError(f"unknown tool: {name}")
                payload = handlers[name](workspace_root, arguments)
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(payload, ensure_ascii=False),
                        }
                    ]
                }
            else:
                raise ValueError(f"unsupported method: {method}")

            _write_message({"jsonrpc": "2.0", "id": message_id, "result": result})
        except Exception as exc:
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "error": {"code": -32000, "message": str(exc)},
                }
            )


def _write_message(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _tool_descriptors() -> list[dict[str, Any]]:
    return [
        {
            "name": "search",
            "description": "Search evidence, facts, and wiki pages.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        },
        {
            "name": "query_context",
            "description": "Build structured retrieval context.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
        },
        {
            "name": "answer_query",
            "description": "Build a structured answer from the knowledge base.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
        },
        {
            "name": "agent_query",
            "description": "Run a lightweight multi-hop agent query.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
        },
        {
            "name": "build_document",
            "description": "Run the full pipeline for a registered document.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                },
                "required": ["doc_id"],
            },
        },
    ]


def _tool_search(workspace_root: Path, arguments: dict[str, Any]) -> Any:
    query = str(arguments.get("query", "")).strip()
    limit = int(arguments.get("limit", 10))
    return {"results": search_knowledge_base(workspace_root, query, limit=limit)}


def _tool_query_context(workspace_root: Path, arguments: dict[str, Any]) -> Any:
    query = str(arguments.get("query", "")).strip()
    limit = int(arguments.get("limit", 8))
    return build_query_context(workspace_root, query, limit=limit)


def _tool_answer_query(workspace_root: Path, arguments: dict[str, Any]) -> Any:
    query = str(arguments.get("query", "")).strip()
    limit = int(arguments.get("limit", 8))
    return answer_query(workspace_root, query, limit=limit)


def _tool_agent_query(workspace_root: Path, arguments: dict[str, Any]) -> Any:
    query = str(arguments.get("query", "")).strip()
    limit = int(arguments.get("limit", 8))
    result = run_agent_query(workspace_root, query, limit=limit)
    return {
        "query": result.query,
        "plan": result.plan,
        "tool_results": result.tool_results,
        "final_answer": result.final_answer,
    }


def _tool_build_document(workspace_root: Path, arguments: dict[str, Any]) -> Any:
    doc_id = str(arguments.get("doc_id", "")).strip()
    result = run_document_pipeline(workspace_root, doc_id)
    return result.__dict__
