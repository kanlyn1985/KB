"""MCP tool surface over OntologyService (copy-adapted from agent_kb_core)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kb_ontology.service.app import OntologyService


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


class OntologyMCPAdapter:
    """Stable list_tools / call_tool for stdio or HTTP MCP transports."""

    def __init__(self, service: OntologyService) -> None:
        self.service = service

    def list_tools(self) -> list[dict[str, Any]]:
        return [tool.to_dict() for tool in _TOOLS]

    def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = dict(arguments or {})
        if name == "kb_ontology_query":
            return self.service.query(payload)
        if name == "kb_ontology_extract":
            return self.service.extract(payload)
        if name == "kb_ontology_health":
            return self.service.health().to_dict()
        if name == "kb_ontology_metrics":
            return self.service.metrics_snapshot()
        raise KeyError(f"unknown MCP tool: {name}")


_TOOLS: tuple[MCPTool, ...] = (
    MCPTool(
        name="kb_ontology_query",
        description=(
            "Understand a natural-language question against the ontology store "
            "and return a structured ContextPack (hits, evidence, judgement, strategy)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "use_llm_understanding": {"type": "boolean"},
                "use_llm_judgement": {"type": "boolean"},
            },
            "required": ["query"],
        },
    ),
    MCPTool(
        name="kb_ontology_extract",
        description=(
            "Extract Entity/Attribute/Relation from clean document text into the "
            "ontology store using the configured Domain Pack and LLM."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "document_id": {"type": "string"},
                "max_tokens": {"type": "integer", "minimum": 256, "maximum": 16000},
            },
            "required": ["text"],
        },
    ),
    MCPTool(
        name="kb_ontology_health",
        description="Read service health, package version, and ontology table counts.",
        input_schema={"type": "object", "properties": {}},
    ),
    MCPTool(
        name="kb_ontology_metrics",
        description="Read in-process counters and duration summaries.",
        input_schema={"type": "object", "properties": {}},
    ),
)
