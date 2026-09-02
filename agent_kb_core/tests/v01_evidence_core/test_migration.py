# -*- coding: utf-8 -*-
"""V0.1-MIG-001/002/003：迁移、幂等、回滚。

Requirement: SYS-019 · Invariant: INV-005/006 · Test ID: V0.1-MIG-001..003
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from agent_kb.evidence_core.migration.v01_evidence_core import migrate, verify  # noqa: E402


@pytest.fixture()
def prod_like_db(tmp_path):
    """带存量 graph_edges 的临时库（模拟生产形态）；返回已关闭的 db 路径。"""
    dbp = tmp_path / "t.sqlite3"
    con = sqlite3.connect(dbp)
    con.row_factory = sqlite3.Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con).migrate()
    for i in range(5):
        con.execute(
            "INSERT INTO graph_edges (edge_id, domain, relation_type, source_object_id,"
            " target_object_id, properties_json, evidence_ids_json, confidence, status, updated_at)"
            f" VALUES ('e{i}','t','r:satisfy','R{i}','F{i}','{{}}','[]',0.8,'materialized',"
            "strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    con.commit()
    con.close()
    return dbp


def test_mig_001_backfill_100pct(prod_like_db):
    """V0.1-MIG-001 / GRAPH-001B: 存量边 → candidate 断言 → assertion_ref 100%。"""
    report = migrate(prod_like_db, apply=True)
    assert report["edges_total"] == 5
    assert report["integrity"]["broken_refs"] == 0
    assert report["integrity"]["backfilled"] == 5
    assert verify(prod_like_db)["pass"] is True


def test_mig_002_idempotent_rerun(prod_like_db):
    """V0.1-MIG-002: 第二次迁移 no-op（0 重复断言/0 损坏引用）。"""
    r1 = migrate(prod_like_db, apply=True)
    r2 = migrate(prod_like_db, apply=True, resume=True)
    assert r2["edges_total"] == 0
    assert r2["assertions_created"] == 0
    assert verify(prod_like_db)["pass"] is True
    con = sqlite3.connect(prod_like_db)
    total = con.execute("SELECT COUNT(*) FROM akb_assertions").fetchone()[0]
    con.close()
    assert total == r1["assertions_created"]


def test_mig_003_dry_run_default_no_write(prod_like_db):
    """V0.1-MIG-003: 默认 DRY-RUN 零写入。"""
    report = migrate(prod_like_db, apply=False)
    assert report["mode"].startswith("DRY-RUN")
    con = sqlite3.connect(prod_like_db)
    after = con.execute(
        "SELECT COUNT(*) FROM graph_edges WHERE assertion_ref IS NOT NULL").fetchone()[0]
    con.close()
    assert after == 0