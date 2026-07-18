from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TextIO

from .mcp import AgentKBMCPAdapter


@dataclass(frozen=True)
class MCPServerInfo:
    name: str = "agent-kb-core"
    version: str = "0.5.0"


class MCPJSONRPCServer:
    """Line-delimited JSON-RPC 2.0 transport for MCP-compatible stdio use."""

    def __init__(self, adapter: AgentKBMCPAdapter, *, server_info: MCPServerInfo | None = None) -> None:
        self.adapter = adapter
        self.server_info = server_info or MCPServerInfo()

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get("id")
        method = str(message.get("method") or "")
        params = message.get("params")
        params = dict(params) if isinstance(params, dict) else {}
        if not method:
            return self._error(request_id, -32600, "invalid request")
        try:
            if method == "notifications/initialized":
                return None
            if method == "initialize":
                result = {
                    "protocolVersion": str(params.get("protocolVersion") or "2025-03-26"),
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": self.server_info.name,
                        "version": self.server_info.version,
                    },
                }
                return self._result(request_id, result)
            if method == "ping":
                return self._result(request_id, {})
            if method == "tools/list":
                return self._result(request_id, {"tools": self.adapter.list_tools()})
            if method == "tools/call":
                name = str(params.get("name") or "")
                arguments = params.get("arguments")
                payload = self.adapter.call_tool(name, dict(arguments) if isinstance(arguments, dict) else {})
                return self._result(
                    request_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                            }
                        ],
                        "structuredContent": payload,
                        "isError": False,
                    },
                )
            return self._error(request_id, -32601, f"method not found: {method}")
        except KeyError as exc:
            return self._error(request_id, -32602, str(exc))
        except Exception as exc:
            return self._error(request_id, -32000, f"{type(exc).__name__}: {exc}")

    def serve(self, input_stream: TextIO, output_stream: TextIO) -> None:
        for raw_line in input_stream:
            line = raw_line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError("JSON-RPC message must be an object")
                response = self.handle(message)
            except (json.JSONDecodeError, ValueError) as exc:
                response = self._error(None, -32700, str(exc))
            if response is not None:
                output_stream.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
                output_stream.flush()

    @staticmethod
    def _result(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": int(code), "message": str(message)},
        }
