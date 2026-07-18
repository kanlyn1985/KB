from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_kb.service.api import AgentKBService


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": dict(self.input_schema),
        }


class AgentKBMCPAdapter:
    """Small MCP tool surface over the application service.

    Transport framing is intentionally outside Core. This adapter exposes
    stable `list_tools` and `call_tool` operations usable by stdio or HTTP MCP
    transports.
    """

    def __init__(self, service: AgentKBService) -> None:
        self.service = service

    def list_tools(self) -> list[dict[str, Any]]:
        return [tool.to_dict() for tool in _TOOLS]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(arguments or {})
        if name == "agent_kb_query":
            return self.service.query(payload)
        if name == "agent_kb_index":
            return self.service.index(payload)
        if name == "agent_kb_documents":
            return {"documents": self.service.documents(include_deleted=bool(payload.get("include_deleted", False)))}
        if name == "agent_kb_feedback":
            return self.service.feedback(payload)
        if name == "agent_kb_health":
            return self.service.health().to_dict()
        raise KeyError(f"unknown MCP tool: {name}")


_TOOLS: tuple[MCPTool, ...] = (
    MCPTool(
        name="agent_kb_query",
        description="Query the evidence-grounded knowledge compiler and return a structured context pack.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["query"],
        },
    ),
    MCPTool(
        name="agent_kb_index",
        description="Compile and index one text document version.",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "title": {"type": "string"},
                "logical_document_id": {"type": "string"},
                "version_label": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["text"],
        },
    ),
    MCPTool(
        name="agent_kb_documents",
        description="List logical documents and versions.",
        input_schema={
            "type": "object",
            "properties": {"include_deleted": {"type": "boolean"}},
        },
    ),
    MCPTool(
        name="agent_kb_feedback",
        description="Attach explicit feedback to a retrieval run.",
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "rating": {"type": "integer"},
                "comment": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["run_id", "rating"],
        },
    ),
    MCPTool(
        name="agent_kb_health",
        description="Read service health, schema version, and store counts.",
        input_schema={"type": "object", "properties": {}},
    ),
)
