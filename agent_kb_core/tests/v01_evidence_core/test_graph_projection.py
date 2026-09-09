# -*- coding: utf-8 -*-
"""V0.1-GRAPH-001A/001B/002：PATH B 投影 + PATH A 回填 + 投影失败不改 Canonical。

Requirement: SYS-008/019 · Invariant: INV-003/006 · Test ID: V0.1-GRAPH-001A/B, 002
"""
from __future__ import annotations

import sqlite3

import pytest

from agent_kb.evidence_core import ProjectionError
from conftest import make_candidate


def test_graph_001a_runtime_projection(stores, seeded):
    """V0.1-GRAPH-001A: validated/asserted → project_edge 成功，assertion_ref 落列。"""
    st, gp = stores["assertions"], stores["graph"]
    a = make_candidate(st, ev_ref=seeded["evidence"])
    st.transition(assertion_id=a.assertion_id, new_status="validated",
                  actor_id="system:validator", reason="ok")
    edge = gp.project_edge(assertion_id=a.assertion_id, source_ref="e:s",
                           target_ref="e:t", predicate_ref="r:p")
    row = stores["provenance"].connection.execute(
        "SELECT assertion_ref FROM graph_edges WHERE edge_id=?", (edge,)).fetchone()
    assert row["assertion_ref"] == a.assertion_id


def test_graph_001a_candidate_rejected(stores):
    """PATH B 拒绝 candidate/hypothesized（兼容性登记≠投影授权）。"""
    st, gp = stores["assertions"], stores["graph"]
    c = make_candidate(st, atype="extracted")
    h = make_candidate(st, atype="hypothesized")
    for ghost in (c, h):
        with pytest.raises(ValueError, match="E-ILLEGAL-PROJECTION"):
            gp.project_edge(assertion_id=ghost.assertion_id, source_ref="a",
                            target_ref="b", predicate_ref="r")


def test_graph_001b_legacy_backfill(db, stores, seeded):
    """V0.1-GRAPH-001B: PATH A 回填 candidate 断言 100% 完整。"""
    st, gp = stores["assertions"], stores["graph"]
    con = stores["provenance"].connection
    # 造一条 legacy 边
    con.execute("INSERT INTO graph_edges (edge_id, domain, relation_type, source_object_id,"
                " target_object_id, properties_json, evidence_ids_json, confidence, status, updated_at)"
                " VALUES ('e1','t','r:satisfy','E1','F1','{}','[]',0.8,'materialized',strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    rowid = con.execute("SELECT rowid FROM graph_edges WHERE edge_id='e1'").fetchone()[0]
    a = make_candidate(st, subject="e:E1", predicate="r:satisfy", value=None) if False else \
        st.create_candidate(subject_ref="entity:E1", predicate_ref="relation:satisfy",
                            object={"kind": "entity_ref", "entity_id": "entity:F1"},
                            assertion_type="extracted", ontology_scope="ontology:t:0.1",
                            actor_id="system:migrator")
    gp.backfill_legacy_edge(edge_rowid=rowid, assertion_id=a.assertion_id)
    integrity = gp.verify_integrity()
    assert integrity["broken_refs"] == 0
    assert integrity["backfilled"] >= 1


def test_graph_002_projection_failure_canonical_unchanged(db, stores, seeded):
    """V0.1-GRAPH-002 / INV-006: 投影失败（拒绝/约束）→ Canonical 零变更。"""
    st, gp = stores["assertions"], stores["graph"]
    a = make_candidate(st, ev_ref=seeded["evidence"])
    st.transition(assertion_id=a.assertion_id, new_status="validated",
                  actor_id="system:validator", reason="ok")
    before = st.get(a.assertion_id).canonical()
    # 失败路径 1：candidate 断言投影 → 拒绝（断言行零变更）
    c = make_candidate(st, subject="e:c")
    with pytest.raises(ValueError, match="E-ILLEGAL-PROJECTION"):
        gp.project_edge(assertion_id=c.assertion_id, source_ref="a", target_ref="b",
                        predicate_ref="r")
    # 失败路径 2：SQL 层约束失败（relation_type NULL）且带 assertion_ref —— 同样不得改断言
    db.execute("BEGIN")
    try:
        db.execute(
            "INSERT INTO graph_edges (edge_id, domain, relation_type, source_object_id,"
            " target_object_id, properties_json, evidence_ids_json, confidence, status,"
            " updated_at, assertion_ref)"
            " VALUES ('bad','t',NULL,'a','b','{}','[]',1,'projected','now',?)",
            (a.assertion_id,))
    except sqlite3.IntegrityError:
        pass
    db.rollback()
    after = st.get(a.assertion_id).canonical()
    assert before == after  # Canonical 零变更
    assert after["status"] == "validated"
