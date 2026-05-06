from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


WORKDIR = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_mcp_server_initialize_and_tools_list() -> None:
    proc = subprocess.Popen(
        ["python", "-m", "enterprise_agent_kb.cli", "--root", "knowledge_base", "serve-mcp"],
        cwd=WORKDIR,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        assert proc.stdin is not None
        assert proc.stdout is not None

        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n")
        proc.stdin.flush()
        initialize_response = json.loads(proc.stdout.readline())
        assert initialize_response["id"] == 1
        assert initialize_response["result"]["serverInfo"]["name"] == "enterprise-agent-kb"

        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n")
        proc.stdin.flush()
        list_response = json.loads(proc.stdout.readline())
        assert list_response["id"] == 2
        tools = list_response["result"]["tools"]
        names = {tool["name"] for tool in tools}
        assert {"search", "query_context", "answer_query", "agent_query", "build_document"} <= names
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.mark.unit
def test_mcp_server_tools_call_answer_query() -> None:
    proc = subprocess.Popen(
        ["python", "-m", "enterprise_agent_kb.cli", "--root", "knowledge_base", "serve-mcp"],
        cwd=WORKDIR,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        assert proc.stdin is not None
        assert proc.stdout is not None

        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n")
        proc.stdin.flush()
        _ = json.loads(proc.stdout.readline())

        proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "answer_query",
                        "arguments": {"query": "什么是控制导引电路？", "limit": 4},
                    },
                }
            )
            + "\n"
        )
        proc.stdin.flush()
        response = json.loads(proc.stdout.readline())
        assert response["id"] == 3
        content = response["result"]["content"][0]["text"]
        payload = json.loads(content)
        assert "direct_answer" in payload
        assert "控制导引电路" in payload["direct_answer"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.mark.unit
def test_mcp_server_tools_call_build_document_exposes_coverage() -> None:
    proc = subprocess.Popen(
        ["python", "-m", "enterprise_agent_kb.cli", "--root", "knowledge_base", "serve-mcp"],
        cwd=WORKDIR,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        assert proc.stdin is not None
        assert proc.stdout is not None

        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n")
        proc.stdin.flush()
        _ = json.loads(proc.stdout.readline())

        proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "build_document",
                        "arguments": {"doc_id": "DOC-000003"},
                    },
                }
            )
            + "\n"
        )
        proc.stdin.flush()
        response = json.loads(proc.stdout.readline())
        assert response["id"] == 4
        payload = json.loads(response["result"]["content"][0]["text"])
        assert payload["doc_id"] == "DOC-000003"
        assert payload["coverage_source_unit_count"] >= 1
        assert payload["coverage_summary_path"].endswith(".summary.json")
        assert payload["coverage_report_path"].endswith(".coverage_report.md")
    finally:
        proc.terminate()
        proc.wait(timeout=5)
