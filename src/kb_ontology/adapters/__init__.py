"""External protocol adapters (MCP, etc.)."""

from kb_ontology.adapters.mcp import MCPTool, OntologyMCPAdapter
from kb_ontology.adapters.mcp_transport import MCPJSONRPCServer, MCPServerInfo

__all__ = [
    "MCPJSONRPCServer",
    "MCPServerInfo",
    "MCPTool",
    "OntologyMCPAdapter",
]
