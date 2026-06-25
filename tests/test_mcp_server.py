from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.ingest import register_document


WORKDIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = WORKDIR / "src" / "enterprise_agent_kb" / "schema.sql"


@pytest.mark.unit
def test_mcp_server_initialize_and_tools_list() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "enterprise_agent_kb.cli", "--root", "knowledge_base", "serve-mcp"],
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
def _has_doc(filename_stem: str) -> bool:
    """Check whether a document with the given filename stem exists in the KB."""
    try:
        from test_helpers import resolve_doc_id_by_filename
        return bool(resolve_doc_id_by_filename(filename_stem, ".pdf"))
    except Exception:
        return False


@pytest.mark.skipif(
    not _has_doc("18487.1"),
    reason="18487.1.pdf not in current knowledge_base",
)
def test_mcp_server_tools_call_answer_query() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "enterprise_agent_kb.cli", "--root", "knowledge_base", "serve-mcp"],
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
def test_mcp_server_tools_call_build_document_exposes_coverage(tmp_path: Path) -> None:
    workspace = tmp_path / "knowledge_base"
    initialize_workspace(workspace, SCHEMA_PATH)
    source = tmp_path / "sample_standard.md"
    source.write_text(
        "\n".join(
            [
                "# 示例标准文档",
                "",
                "GB/T 99999.1—2025",
                "",
                "## 3 术语和定义",
                "#### 3.1.1",
                "## 控制导引电路 control pilot circuit",
                "设计用于电动汽车和供电设备之间信号传输或通信的电路。",
            ]
        ),
        encoding="utf-8",
    )
    registered = register_document(workspace, source)
    proc = subprocess.Popen(
        [sys.executable, "-m", "enterprise_agent_kb.cli", "--root", str(workspace), "serve-mcp"],
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
                        "arguments": {"doc_id": registered.doc_id},
                    },
                }
            )
            + "\n"
        )
        proc.stdin.flush()
        response = json.loads(proc.stdout.readline())
        assert response["id"] == 4
        payload = json.loads(response["result"]["content"][0]["text"])
        assert payload["doc_id"] == registered.doc_id
        assert payload["coverage_source_unit_count"] >= 1
        assert payload["coverage_summary_path"].endswith(".summary.json")
        assert payload["coverage_report_path"].endswith(".coverage_report.md")
        assert payload["ingestion_acceptance"]["status"] in {"passed", "warn", "failed"}
        assert payload["ingestion_acceptance"]["json_path"].endswith(".ingestion_acceptance.json")
    finally:
        proc.terminate()
        proc.wait(timeout=5)
