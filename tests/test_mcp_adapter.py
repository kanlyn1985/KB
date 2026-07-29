"""MCP adapter + JSON-RPC transport tests."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from kb_ontology.adapters.mcp import OntologyMCPAdapter
from kb_ontology.adapters.mcp_transport import MCPJSONRPCServer
from kb_ontology.domains.loader import load_domain_pack
from kb_ontology.service.app import OntologyService
from kb_ontology.storage.store import OntologyStore


def _repo_domain() -> Path:
    return Path(__file__).resolve().parents[1] / "domains" / "obc_dcdc"


def _seed(db: Path) -> None:
    with OntologyStore(db) as store:
        ent = store.upsert_entity("Product", "DC-DC转换器", "obc_dcdc")
        store.upsert_attribute(ent.id, "description", "车载直流变换器", "string")
        store.add_evidence(
            ref_type="entity",
            ref_id=ent.id,
            document_id="doc1",
            text_span="DC-DC转换器用于车载电源",
            location="§1",
            confidence=0.9,
        )


def test_mcp_list_and_call_tools(tmp_path: Path) -> None:
    db = tmp_path / "ont.db"
    _seed(db)
    pack = load_domain_pack(_repo_domain())
    svc = OntologyService(db_path=db, domain_pack=pack)
    adapter = OntologyMCPAdapter(svc)

    tools = adapter.list_tools()
    names = {t["name"] for t in tools}
    assert "kb_ontology_query" in names
    assert "kb_ontology_health" in names
    assert "kb_ontology_extract" in names
    assert "kb_ontology_metrics" in names

    health = adapter.call_tool("kb_ontology_health", {})
    assert health["status"] == "ok"
    assert health["store_summary"]["entities"] >= 1

    pack_json = adapter.call_tool(
        "kb_ontology_query", {"query": "什么是DC-DC转换器"}
    )
    assert "judgement" in pack_json
    assert "recommended_answer_strategy" in pack_json

    metrics = adapter.call_tool("kb_ontology_metrics", {})
    assert "counters" in metrics


def test_mcp_jsonrpc_stdio_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "ont.db"
    _seed(db)
    pack = load_domain_pack(_repo_domain())
    svc = OntologyService(db_path=db, domain_pack=pack)
    server = MCPJSONRPCServer(OntologyMCPAdapter(svc))

    init = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26"},
        }
    )
    assert init is not None
    assert init["result"]["serverInfo"]["name"] == "kb-ontology"

    listed = server.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    )
    assert listed is not None
    assert len(listed["result"]["tools"]) >= 4

    called = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "kb_ontology_health",
                "arguments": {},
            },
        }
    )
    assert called is not None
    assert called["result"]["isError"] is False
    assert "structuredContent" in called["result"]
    assert called["result"]["structuredContent"]["status"] == "ok"

    # notifications produce no response
    assert (
        server.handle(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        )
        is None
    )

    unknown = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "nope", "arguments": {}},
        }
    )
    assert unknown is not None
    assert "error" in unknown

    # line server
    inp = StringIO(
        '{"jsonrpc":"2.0","id":9,"method":"ping","params":{}}\n'
    )
    out = StringIO()
    server.serve(inp, out)
    line = out.getvalue().strip()
    assert '"result"' in line
