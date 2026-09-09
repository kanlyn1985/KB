"""OpenAPI, MCP, and generated-client adapter contracts."""

from .client_codegen import generate_python_client
from .mcp import AgentKBMCPAdapter, MCPTool
from .mcp_transport import MCPJSONRPCServer, MCPServerInfo
from .openapi import build_openapi_spec

__all__ = [
    "AgentKBMCPAdapter",
    "MCPJSONRPCServer",
    "MCPServerInfo",
    "MCPTool",
    "build_openapi_spec",
    "generate_python_client",
]
