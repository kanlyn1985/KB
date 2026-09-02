# -*- coding: utf-8 -*-
"""V0.1-AST-006/007：Transition 审计与原子性。

Requirement: SYS-006 · Invariant: INV-005 · Test ID: V0.1-AST-006/007
"""
from __future__ import annotations

import sqlite3

import pytest

from conftest import make_candidate


def test_ast_006_audit_row_per_transition(stores, seeded):
    """V0.1-AST-006 / INV-005: 每次合法迁移恰一行审计，含全部治理字段。"""
    st = stores["assertions"]
    a = make_candidate(st, ev_ref=seeded["evidence"])
    st.transition(assertion_id=a.assertion_id, new_status="validated",
                  actor_id="system:validator", reason="ok")
    st.transition(assertion_id=a.assertion_id, new_status="asserted",
                  actor_id="human:r", reason="approved")
    rows = stores["provenance"].connection.execute(
        "SELECT * FROM akb_assertion_transitions WHERE assertion_id = ? ORDER BY created_at",
        (a.assertion_id,)).fetchall()
    assert len(rows) == 2
    assert rows[0]["previous_status"] == "candidate" and rows[0]["new_status"] == "validated"
    assert rows[1]["previous_status"] == "validated" and rows[1]["new_status"] == "asserted"
    assert all(r["actor_id"] and r["reason"] and r["policy_version"] for r in rows)


def test_ast_006b_audit_append_only(stores, seeded):
    """INV-005: 审计行 UPDATE/DELETE 直写 → 触发器 ABORT。"""
    st = stores["assertions"]
    a = make_candidate(st, ev_ref=seeded["evidence"])
    st.transition(assertion_id=a.assertion_id, new_status="validated",
                  actor_id="system:validator", reason="ok")
    tid = stores["provenance"].connection.execute(
        "SELECT transition_id FROM akb_assertion_transitions").fetchone()["transition_id"]
    with pytest.raises(sqlite3.Error, match="append-only"):
        stores["provenance"].connection.execute(
            "UPDATE akb_assertion_transitions SET reason='tampered' WHERE transition_id=?", (tid,))
    with pytest.raises(sqlite3.Error, match="append-only"):
        stores["provenance"].connection.execute(
            "DELETE FROM akb_assertion_transitions WHERE transition_id=?", (tid,))


def test_ast_006c_evidence_append_only(stores, seeded):
    """INV-005: akb_evidence 行 UPDATE/DELETE 直写 → ABORT。"""
    with pytest.raises(sqlite3.Error, match="append-only"):
        stores["provenance"].connection.execute(
            "UPDATE akb_evidence SET content='tampered' WHERE evidence_id=?",
            (seeded["evidence"],))
    with pytest.raises(sqlite3.Error, match="append-only"):
        stores["provenance"].connection.execute(
            "DELETE FROM akb_evidence WHERE evidence_id=?", (seeded["evidence"],))


def test_ast_007_transition_atomicity(stores, seeded):
    """V0.1-AST-007: 迁移原子性——事务回滚后零孤儿（status 零变更/无孤儿行）。"""
    st = stores["assertions"]
    a = make_candidate(st, ev_ref=seeded["evidence"])
    con = stores["provenance"].connection
    con.execute("BEGIN")
    st.transition(assertion_id=a.assertion_id, new_status="validated",
                  actor_id="system:validator", reason="in-txn")
    # 回滚前确认事务内生效
    assert st.get(a.assertion_id).status == "validated"
    con.rollback()
    # 回滚后：status 复原、无孤儿 transitions/provenance
    assert st.get(a.assertion_id).status == "candidate"
    orphans_t = con.execute(
        "SELECT COUNT(*) FROM akb_assertion_transitions WHERE assertion_id=?",
        (a.assertion_id,)).fetchone()[0]
    assert orphans_t == 0


def test_ast_007b_direct_sql_status_update_blocked(db, seeded, stores):
    """INV-005 / 任务书 §16: 直接 SQL UPDATE status 绕过 API → 触发器 FAIL。"""
    a = make_candidate(stores["assertions"], ev_ref=seeded["evidence"])
    with pytest.raises(sqlite3.Error, match="assertion_transitions"):
        db.execute("UPDATE akb_assertions SET status='asserted' WHERE assertion_id=?",
                   (a.assertion_id,))
    # 不可变列同理
    with pytest.raises(sqlite3.Error, match="immutable"):
        db.execute("UPDATE akb_assertions SET subject_ref='hacked' WHERE assertion_id=?",
                   (a.assertion_id,))


def test_ast_007c_reason_required(stores):
    """迁移 reason 必填（审计完整性）。"""
    a = make_candidate(stores["assertions"], ev_ref=None)
    with pytest.raises(ValueError, match="E-INVALID-REASON"):
        st = stores["assertions"]
        st.transition(assertion_id=a.assertion_id, new_status="rejected",
                      actor_id="human:t", reason="")