"""OpenAPI and MCP adapter contracts."""

from .mcp import AgentKBMCPAdapter, MCPTool
from .openapi import build_openapi_spec

__all__ = ["AgentKBMCPAdapter", "MCPTool", "build_openapi_spec"]
