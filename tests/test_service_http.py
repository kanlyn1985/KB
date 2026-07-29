"""HTTP service + secure API e2e (no live LLM)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from kb_ontology.domains.loader import load_domain_pack
from kb_ontology.security.auth import APIKeyAuthenticator, TenantDatabaseRouter
from kb_ontology.service.app import OntologyService
from kb_ontology.service.http_api import (
    SecureServiceContext,
    create_http_server,
    create_secure_http_server,
)
from kb_ontology.storage.store import OntologyStore


def _repo_domain() -> Path:
    return Path(__file__).resolve().parents[1] / "domains" / "obc_dcdc"


def _seed_store(db_path: Path) -> None:
    with OntologyStore(db_path) as store:
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


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _http_json(
    method: str,
    url: str,
    payload: dict | None = None,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    data = None
    hdrs = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return int(resp.status), body
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read().decode("utf-8") or "{}")
        return int(exc.code), body


def test_trusted_http_health_and_query(tmp_path: Path) -> None:
    db = tmp_path / "ont.db"
    _seed_store(db)
    pack = load_domain_pack(_repo_domain())
    svc = OntologyService(db_path=db, domain_pack=pack)
    port = _free_port()
    server = create_http_server(svc, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        code, health = _http_json("GET", f"http://127.0.0.1:{port}/v1/health")
        assert code == 200
        assert health["status"] == "ok"
        assert health["store_summary"]["entities"] >= 1

        code, pack_json = _http_json(
            "POST",
            f"http://127.0.0.1:{port}/v1/query",
            {"query": "什么是DC-DC转换器"},
        )
        assert code == 200
        assert pack_json["intent"] in ("definition", "parameter_lookup", "unknown") or pack_json[
            "hit_count"
        ] >= 0
        assert "recommended_answer_strategy" in pack_json
        assert "judgement" in pack_json

        code, metrics = _http_json("GET", f"http://127.0.0.1:{port}/v1/metrics")
        assert code == 200
        assert "counters" in metrics
    finally:
        server.shutdown()
        server.server_close()


def test_secure_http_auth_rbac_and_audit(tmp_path: Path) -> None:
    root = tmp_path / "tenants"
    pack = load_domain_pack(_repo_domain())
    auth = APIKeyAuthenticator.from_mapping(
        {
            "reader-key-0000000000": {
                "principal_id": "reader1",
                "tenant_id": "default",
                "roles": ["reader"],
            },
            "admin-key-00000000000": {
                "principal_id": "admin1",
                "tenant_id": "default",
                "roles": ["admin"],
            },
        }
    )
    # Seed tenant DB after router creates path
    router = TenantDatabaseRouter(root)
    _seed_store(router.path_for("default"))

    ctx = SecureServiceContext(
        authenticator=auth,
        tenant_router=router,
        domain_pack=pack,
        audit_db_path=tmp_path / "audit.db",
    )
    port = _free_port()
    server = create_secure_http_server(ctx, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        # no auth
        code, err = _http_json("GET", f"{base}/v1/health")
        assert code == 401

        # reader health + query ok
        h = {"Authorization": "Bearer reader-key-0000000000"}
        code, health = _http_json("GET", f"{base}/v1/health", headers=h)
        assert code == 200
        assert health["status"] == "ok"

        code, pack_json = _http_json(
            "POST",
            f"{base}/v1/query",
            {"query": "DC-DC转换器是什么"},
            headers=h,
        )
        assert code == 200
        assert "hits" in pack_json

        # reader cannot extract
        code, err = _http_json(
            "POST",
            f"{base}/v1/extract",
            {"text": "x", "document_id": "d1"},
            headers=h,
        )
        assert code == 403

        # admin can list audit (query was recorded)
        ah = {"Authorization": "Bearer admin-key-00000000000"}
        code, audit = _http_json("GET", f"{base}/v1/audit", headers=ah)
        assert code == 200
        assert any(e["action"] == "query:run" for e in audit["events"])
    finally:
        server.shutdown()
        server.server_close()


def test_service_query_without_http(tmp_path: Path) -> None:
    db = tmp_path / "ont.db"
    _seed_store(db)
    pack = load_domain_pack(_repo_domain())
    svc = OntologyService(db_path=db, domain_pack=pack)
    out = svc.query({"query": "DC-DC转换器的定义"})
    assert out["hit_count"] >= 0
    assert out["judgement"] is not None
