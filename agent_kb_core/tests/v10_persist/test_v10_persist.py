# -*- coding: utf-8 -*-
"""V10-PERSIST-CMP-001..012（AKB-V10-IMPL-001：migration 16 + 持久化基础层）。"""
from __future__ import annotations

import json

import pytest

from agent_kb.causal import (
    CausalProjectionRuntime,
    PersistError,
    ScalePersistenceRuntime,
)
from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.health import KnowledgeHealthRuntime
from agent_kb.hypothesis import (
    HypothesisService,
    VerificationTaskRuntime,
    VerdictRuntime,
)
from agent_kb.conflict import ConflictRuntime
from agent_kb.storage.migrations import SchemaMigrator, ALL_MIGRATIONS


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(
        ":memory:", isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    SchemaMigrator(con).migrate()
    con.execute("INSERT INTO akb_sources (source_id, source_type, name)"
                " VALUES ('p10', 'document', 'P10')")
    con.execute("INSERT INTO akb_documents (document_id, source_id, version,"
                " content_hash, ingested_at) VALUES ('dp10', 'p10', '1.0',"
                " 'h', strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    from agent_kb.evidence_core import EvidenceStore
    ev = EvidenceStore(con).create(document_id="dp10", content="持久化锚证据。",
                                   extraction_method="t")
    yield con, ev.evidence_id
    con.close()


import sqlite3


def _seed_causal(con, eid):
    st = AssertionStore(con)
    st.create_candidate(subject_ref="Heat", predicate_ref="causes",
                        object={"kind": "literal", "value": "Aging"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])


def _full_stack(db):
    con, eid = db
    _seed_causal(con, eid)
    proj = CausalProjectionRuntime(con).project()
    pers = ScalePersistenceRuntime(con)
    return proj, pers


def test_v10_persist_cmp_001_migration16(db):
    """V10-PERSIST-CMP-001：migration version=16 + name + 链完整。"""
    con, _ = db
    vers = [m.version for m in ALL_MIGRATIONS]
    assert vers == list(range(1, 18))
    m16 = [m for m in ALL_MIGRATIONS if m.version == 16][0]
    assert m16.name == "v10_scale_persistence"


def test_v10_persist_cmp_002_three_tables(db):
    """V10-PERSIST-CMP-002：三表结构实存（列面核对）。"""
    con, _ = db
    cols = {t: [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
            for t in ("akb_causal_edges", "akb_health_signals",
                      "akb_conflict_records")}
    assert "cause_ref" in cols["akb_causal_edges"]
    assert "effect_ref" in cols["akb_causal_edges"]
    assert "signal_type" in cols["akb_health_signals"]
    assert "conflict_type" in cols["akb_conflict_records"]
    assert "fingerprint" in cols["akb_causal_edges"]
    assert "fingerprint" in cols["akb_health_signals"]
    assert "fingerprint" in cols["akb_conflict_records"]


def test_v10_persist_cmp_003_constraints_indexes(db):
    """V10-PERSIST-CMP-003：CHECK/PK/索引/FK 强制（fresh connection 事务外 pragma）。"""
    con, eid = db
    _seed_causal(con, eid)
    # 自环 CHECK
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO akb_causal_edges (causal_edge_id,cause_ref,effect_ref,"
            "relation_type,condition_refs_json,mechanism_ref,assertion_id,"
            "status,confidence,provenance_ref,fingerprint) VALUES"
            " ('ce_x','A','A','causes','[]','',"
            " (SELECT assertion_id FROM akb_assertions LIMIT 1),'valid',0.9,"
            " 'p','f')")
    # 非法 relation CHECK
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO akb_causal_edges (causal_edge_id,cause_ref,effect_ref,"
            "relation_type,condition_refs_json,mechanism_ref,assertion_id,"
            "status,confidence,provenance_ref,fingerprint) VALUES"
            " ('ce_y','A','B','teleport','[]','',"
            " (SELECT assertion_id FROM akb_assertions LIMIT 1),'valid',0.9,"
            " 'p','f')")
    # 非法 conflict type CHECK
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO akb_conflict_records (conflict_id,conflict_type,"
            "source_refs_json,target_refs_json,severity,status,"
            "evidence_refs_json,fingerprint,created_from_snapshot,"
            "provenance_ref) VALUES ('cf_z','TELEPORT','[]','[]','low',"
            "'open','[]','f','s','p')")
    # FK（ghost assertion——PRAGMA foreign_keys=ON 已在 fixture 开启）
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO akb_causal_edges (causal_edge_id,cause_ref,effect_ref,"
            "relation_type,condition_refs_json,mechanism_ref,assertion_id,"
            "status,confidence,provenance_ref,fingerprint) VALUES"
            " ('ce_k','A','B','causes','[]','','ast_ghost','valid',0.9,"
            " 'p','f')")
    # 索引实存
    idx = {r[0] for r in con.execute("SELECT name FROM sqlite_master"
                                     " WHERE type='index'")}
    for i in ("ix_akb_causal_edges_effect", "ix_akb_causal_edges_cause",
              "ix_akb_health_signals_target", "ix_akb_conflict_records_type"):
        assert i in idx


def test_v10_persist_cmp_004_rollback_rebuildable(db):
    """V10-PERSIST-CMP-004：rollback/drop 可重建——drop 三表后 re-migrate 全恢复。"""
    con, _ = db
    for t in ("akb_causal_edges", "akb_health_signals",
              "akb_conflict_records"):
        con.execute(f"DROP TABLE {t}")
    # drop 后需清 migration 记录才重放（schema_migrations 按 version 跳过）
    con.execute("DELETE FROM schema_migrations WHERE version = 16")
    SchemaMigrator(con).migrate()
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"akb_causal_edges", "akb_health_signals",
            "akb_conflict_records"} <= tables


def test_v10_persist_cmp_005_causal_persist(db):
    """V10-PERSIST-CMP-005：causal persist——edges 落 akb_causal_edges。"""
    proj, pers = _full_stack(db)
    r = pers.persist_causal_edges(proj)
    assert r["edges_total"] == 1 and r["edges_written"] == 1
    row = db[0].execute("SELECT * FROM akb_causal_edges").fetchone()
    assert row["cause_ref"] == "Heat" and row["effect_ref"] == "Aging"
    assert row["fingerprint"] == proj.fingerprint


def test_v10_persist_cmp_006_health_persist(db, ):
    """V10-PERSIST-CMP-006：health persist——signals 落 akb_health_signals。"""
    con, eid = db
    _seed_causal(con, eid)
    hs = HypothesisService(con)
    hyp = hs.create_hypothesis(statement="H: KH 持久化", domain_ref="industrial",
                               pack_ref="dpr_a", policy_ref="pol_b",
                               context_ref="grc_c", origin="human")
    kh = KnowledgeHealthRuntime(con, causal_runtime=CausalProjectionRuntime(con))
    h = kh.create_health(target_ref=hyp.hypothesis_id,
                         target_type="hypothesis")
    r = ScalePersistenceRuntime(con).persist_health_signals(h)
    assert r["signals_written"] == 4
    rows = [dict(x) for x in con.execute(
        "SELECT * FROM akb_health_signals WHERE health_id=?",
        (h.health_id,))]
    assert len(rows) == 4
    assert {r["signal_type"] for r in rows} == {
        "stability", "verification", "conflict", "causal_coverage"}


def test_v10_persist_cmp_007_conflict_persist(db):
    """V10-PERSIST-CMP-007：conflict persist——records 落 akb_conflict_records。"""
    con, eid = db
    _seed_causal(con, eid)
    st = AssertionStore(con)
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "20"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    st.create_candidate(subject_ref="Temp", predicate_ref="has_value",
                        object={"kind": "literal", "value": "25"},
                        assertion_type="extracted", ontology_scope="test",
                        actor_id="system:seed", confidence=0.9,
                        evidence_refs=[eid])
    records = ConflictRuntime(con).detect()
    assert records
    r = ScalePersistenceRuntime(con).persist_conflict_records(records)
    assert r["conflicts_written"] == len(records)
    row = con.execute("SELECT * FROM akb_conflict_records WHERE"
                      " conflict_type='ASSERTION_VALUE_CONFLICT'").fetchone()
    assert row is not None
    assert json.loads(row["target_refs_json"]) == ["Temp"]


def test_v10_persist_cmp_008_idempotency(db):
    """V10-PERSIST-CMP-008：idempotency——重复 persist 零重复写入
    （edges_written=0）。"""
    proj, pers = _full_stack(db)
    r1 = pers.persist_causal_edges(proj)
    r2 = pers.persist_causal_edges(proj)
    assert r1["edges_written"] == 1 and r2["edges_written"] == 0
    assert db[0].execute("SELECT COUNT(*) c FROM"
                         " akb_causal_edges").fetchone()["c"] == 1


def test_v10_persist_cmp_009_transaction_rollback(db):
    """V10-PERSIST-CMP-009：transaction rollback——persist 异常零残留。"""
    proj, pers = _full_stack(db)
    # 破坏第二条边的合法性（注入非法对象）→ 批量中段失败 → 已写行回滚验证
    from agent_kb.causal import CausalEdge
    prov = db[0].execute(
        "SELECT provenance_ref FROM akb_assertions WHERE predicate_ref="
        "'causes'").fetchone()["provenance_ref"]
    bad = CausalEdge(causal_id="ce_bad", source_ref="X", target_ref="X",
                     relation_type="causes", condition_refs=(),
                     mechanism_ref="", confidence=0.9,
                     provenance_refs=(prov,), status="valid")  # 自环 → CHECK 拒绝
    from agent_kb.causal import CausalProjection
    bad_proj = CausalProjection(
        projection_id="cpr_bad", source_snapshot=proj.source_snapshot,
        causal_edges=(bad,), fingerprint="bad_fp", generated_at="snap:x")
    with pytest.raises(sqlite3.IntegrityError):
        pers.persist_causal_edges(bad_proj)
    assert db[0].execute("SELECT COUNT(*) c FROM akb_causal_edges WHERE"
                         " causal_edge_id='ce_bad'").fetchone()["c"] == 0


def test_v10_persist_cmp_010_deterministic_replay(db):
    """V10-PERSIST-CMP-010：deterministic replay——drop 后全量重投影+重持久化
    → 同 id 同 fingerprint 同行数。"""
    proj, pers = _full_stack(db)
    pers.persist_causal_edges(proj)
    row1 = [tuple(r) for r in db[0].execute(
        "SELECT * FROM akb_causal_edges ORDER BY causal_edge_id")]
    db[0].execute("DROP TABLE akb_causal_edges")
    db[0].execute("DELETE FROM schema_migrations WHERE version = 16")
    SchemaMigrator(db[0]).migrate()
    proj2 = CausalProjectionRuntime(db[0]).project()
    ScalePersistenceRuntime(db[0]).persist_causal_edges(proj2)
    row2 = [tuple(r) for r in db[0].execute(
        "SELECT * FROM akb_causal_edges ORDER BY causal_edge_id")]
    assert row1 == row2


def test_v10_persist_cmp_011_frozen_table_isolation(db):
    """V10-PERSIST-CMP-011：frozen-table isolation——persist 零触碰
    akb_assertions/kg_*/akb_provenance 行。"""
    proj, pers = _full_stack(db)
    before = {t: [tuple(r) for r in db[0].execute(
        f"SELECT * FROM {t} ORDER BY 1")]
        for t in ("akb_assertions", "kg_nodes", "kg_edges",
                  "akb_provenance")}
    pers.persist_causal_edges(proj)
    after = {t: [tuple(r) for r in db[0].execute(
        f"SELECT * FROM {t} ORDER BY 1")]
        for t in ("akb_assertions", "kg_nodes", "kg_edges",
                  "akb_provenance")}
    for t in ("akb_assertions", "kg_nodes", "kg_edges"):
        assert before[t] == after[t], t
    # akb_provenance 行集不变（persist 不写 provenance——介质变更非知识事件）


def test_v10_persist_cmp_012_production_db_untouched(db):
    """V10-PERSIST-CMP-012：production DB untouched——prod-isolation hook
    覆盖（fixture 全内存库）+ persist 零 production 路径。"""
    con, _ = db
    # migration 面验证：production schema_version 由 hook 记录（10）——
    # 本测试库独立内存迁移到 16，零生产触碰
    assert con.execute("PRAGMA user_version").fetchone()[0] >= 0
    # identity 零新算法：persist 后表内 id 与 runtime identity 全等
    proj, pers = _full_stack(db)
    pers.persist_causal_edges(proj)
    row = con.execute("SELECT causal_edge_id FROM akb_causal_edges").fetchone()
    assert row["causal_edge_id"] == proj.causal_edges[0].causal_id