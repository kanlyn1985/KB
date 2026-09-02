# -*- coding: utf-8 -*-
"""V0.1 幂等性集中测试（任务书 §23）：migration/evidence create/backfill 重复安全。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from agent_kb.evidence_core.migration.v01_evidence_core import migrate, verify  # noqa: E402


def test_idempotency_evidence_create(db, seeded):
    stores = None
    from agent_kb.evidence_core import EvidenceStore
    es = EvidenceStore(db)
    ids = [es.create(document_id="doc_t1", content="X", extraction_method="f").evidence_id
           for _ in range(3)]
    assert len(set(ids)) == 1  # 三次创建同一 id


def test_idempotency_migration_double_run(tmp_path):
    import sqlite3
    from agent_kb.storage.migrations import SchemaMigrator
    dbp = tmp_path / "t.sqlite3"
    con = sqlite3.connect(dbp)
    con.row_factory = sqlite3.Row
    SchemaMigrator(con).migrate()
    con.execute("INSERT INTO graph_edges (edge_id, domain, relation_type, source_object_id,"
                " target_object_id, properties_json, evidence_ids_json, confidence, status, updated_at)"
                " VALUES ('e0','t','r','A','B','{}','[]',1,'materialized',"
                "strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    con.commit()
    con.close()
    r1 = migrate(dbp, apply=True)
    n_assert = r1["assertions_created"]
    r2 = migrate(dbp, apply=True, resume=True)
    assert r2["assertions_created"] == 0
    assert verify(dbp)["pass"] is True
    # 断言总数不翻倍
    con = sqlite3.connect(dbp)
    total = con.execute("SELECT COUNT(*) FROM akb_assertions").fetchone()[0]
    con.close()
    assert total == n_assert