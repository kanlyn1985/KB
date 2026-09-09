# -*- coding: utf-8 -*-
"""V0.1 Evidence Core 测试公共 fixture（内存库 + 已应用迁移）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent_kb_core" / "src"))

from agent_kb.evidence_core import (  # noqa: E402
    AssertionStore,
    EvidenceStore,
    GraphProjection,
    Provenance,
)
from agent_kb.storage.migrations import SchemaMigrator  # noqa: E402

POLICY = "policy:v0.1"


@pytest.fixture()
def db():
    con = __import__("sqlite3").connect(":memory:", isolation_level=None)  # autocommit：事务由测试显式控制
    con.row_factory = __import__("sqlite3").Row
    SchemaMigrator(con).migrate()
    # legacy evidence 表（KB1 编译器建表；V0.1 测试模拟生产形态）
    con.execute("""
        CREATE TABLE IF NOT EXISTS evidence (
            evidence_id TEXT PRIMARY KEY,
            document_id TEXT,
            page_no INTEGER,
            snippet TEXT,
            confidence REAL,
            updated_at TEXT
        )
    """)
    yield con
    con.close()


@pytest.fixture()
def seeded(db):
    """source + document + evidence 种子数据。"""
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('src_t', 'document', '测试源')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash, ingested_at)"
               " VALUES ('doc_t1', 'src_t', '1.0', 'sha256:seed',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    es = EvidenceStore(db)
    ev = es.create(document_id="doc_t1", content="OBC 额定输入电压 85-265VAC",
                   extraction_method="fixture")
    return {"source": "src_t", "document": "doc_t1", "evidence": ev.evidence_id}


@pytest.fixture()
def stores(db):
    return {"evidence": EvidenceStore(db), "assertions": AssertionStore(db),
            "provenance": Provenance(db), "graph": GraphProjection(db)}


def make_candidate(store, subject="e:s", predicate="r:p", value="v", actor="human:t",
                   ev_ref=None, atype="extracted", derivation=None):
    return store.create_candidate(
        subject_ref=subject, predicate_ref=predicate,
        object={"kind": "literal", "value": value},
        assertion_type=atype, ontology_scope="ontology:t:0.1", actor_id=actor,
        evidence_refs=[ev_ref] if isinstance(ev_ref, str) else (ev_ref or []),
        derivation=derivation)