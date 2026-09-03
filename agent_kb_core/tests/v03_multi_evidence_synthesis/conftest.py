# -*- coding: utf-8 -*-
"""V0.3 测试公共 fixture。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent_kb_core" / "src"))
sys.path.insert(0, str(ROOT / "agent_kb_core" / "tests"))

import sqlite3  # noqa: E402

from agent_kb.storage.migrations import SchemaMigrator  # noqa: E402
from agent_kb.evidence_core import EvidenceStore  # noqa: E402
from agent_kb.evidence_core.compilation import SemanticCompiler  # noqa: E402
from agent_kb.evidence_core.synthesis import SynthesisEngine  # noqa: E402


@pytest.fixture()
def db():
    con = sqlite3.connect(":memory:", isolation_level=None)
    con.row_factory = sqlite3.Row
    SchemaMigrator(con).migrate()
    yield con
    con.close()


@pytest.fixture()
def compiled_evidence(db):
    """3 条已编译 evidence（同主题多证据）。"""
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('s1', 'document', 'S1')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at, effective_at) VALUES ('d1', 's1', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'), '2026-01-01T00:00:00Z')")
    store = EvidenceStore(db)
    comp = SemanticCompiler(db)
    texts = ["OBC 额定输入电压 265V。", "OBC 额定输入电压是 265V。",
             "OBC 额定输入电压 265V 待机功耗小于 5W。"]
    eids = []
    for t in texts:
        ev = store.create(document_id="d1", content=t, extraction_method="t")
        comp.compile(ev.evidence_id, actor_id="system:compiler")
        eids.append(ev.evidence_id)
    return {"evidence_ids": eids, "engine": SynthesisEngine(db), "store": store,
            "compiler": comp, "db": db}