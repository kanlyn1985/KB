# -*- coding: utf-8 -*-
"""V0.2 Semantic Compilation 测试公共 fixture。"""
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


@pytest.fixture()
def db():
    con = sqlite3.connect(":memory:", isolation_level=None)
    con.row_factory = sqlite3.Row
    SchemaMigrator(con).migrate()
    yield con
    con.close()


@pytest.fixture()
def seeded(db):
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('src_t', 'document', 'T')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash, ingested_at)"
               " VALUES ('doc_t1', 'src_t', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    es = EvidenceStore(db)
    ev = es.create(document_id="doc_t1",
                   content="OBC 额定输入电压 265V。\n输入滤波电容 22uF。",
                   extraction_method="fixture")
    return {"evidence": ev, "evidence_id": ev.evidence_id}


@pytest.fixture()
def compiler(db):
    return SemanticCompiler(db)