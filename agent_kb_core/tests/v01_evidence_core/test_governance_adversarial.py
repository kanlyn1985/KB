# -*- coding: utf-8 -*-
"""Adversarial governance tests（AKB-V01-HARDENING-001 §3/§4）。

攻击路径 1：直 SQL 插 provenance + transitions + UPDATE status（伪造完整治理链）
攻击路径 2：伪造 actor/policy/previous/new 取得权限
攻击路径 3：操纵 provenance_ref 绕过迁移历史
DB 层守卫：migration 11（legal-pair / type-boundary / provenance-exists / provenance-pair 触发器）。
"""
from __future__ import annotations

import sqlite3

import pytest

from conftest import make_candidate


# ---- 攻击路径 1：伪造完整治理链直 SQL 晋升 ----

def test_adv1_full_fake_chain_semantics(db, seeded, stores):
    """路径1（语义裁决）：伪造完整链（provenance+transitions+UPDATE）在 DB 层的行为。

    设计裁决（STATE_MACHINE §4 / INTERFACE §2.4）：治理边界分两层——
    DB 层强制：状态对白名单 / type 边界 / provenance 存在性与一致性 / append-only 审计；
    应用层强制：actor 授权（权限矩阵）——DB 无法验证 actor 身份（SQLite 无认证主体）。
    因此"知道 schema 的直 SQL 操作者"等价于 DB 写权限持有者（等同 DBA），
    其伪造链会成功但完整留痕（provenance/transitions 行均为 append-only 审计证据）。
    本测试锁定这一语义并验证审计留痕完整。"""
    st = stores["assertions"]
    a = make_candidate(st, ev_ref=seeded["evidence"])
    db.execute(
        "INSERT INTO akb_provenance (provenance_id, actor_id, actor_kind, activity,"
        " policy_version, occurred_at) VALUES"
        " ('prov_fake','human:attacker','human','promote','policy:v0.1','2026-09-01T00:00:00Z')")
    db.execute(
        "INSERT INTO akb_assertion_transitions (transition_id, assertion_id, previous_status,"
        " new_status, actor_id, reason, policy_version, provenance_ref)"
        " VALUES ('astt_fake', ?, 'candidate', 'validated', 'human:attacker', 'fake',"
        " 'policy:v0.1', 'prov_fake')", (a.assertion_id,))
    db.execute(
        "UPDATE akb_assertions SET status='validated', provenance_ref='prov_fake'"
        " WHERE assertion_id=?", (a.assertion_id,))
    # 审计留痕完整（事后可追责）：transitions 行 + provenance 行都在
    t = db.execute("SELECT actor_id, reason FROM akb_assertion_transitions"
                   " WHERE assertion_id=?", (a.assertion_id,)).fetchall()
    assert any(r["actor_id"] == "human:attacker" for r in t)
    assert st.get(a.assertion_id).status == "validated"
    # API 层等价重放：幂等 no-op（不产生第二条审计行）；伪造晋升到 asserted 仍被权限矩阵拒
    replay = st.transition(assertion_id=a.assertion_id, new_status="validated",
                           actor_id="human:attacker", reason="replay")
    assert replay["idempotent_noop"] is True
    # 残余风险（已裁决）：持 DB 写权限者伪造 human: 前缀链可完成晋升——
    # 该风险由 DB 文件权限/部署边界防护（非 SQLite 可表达），记录于 Verification Report。


def test_adv1b_fake_provenance_insert_blocked(db, seeded, stores):
    """路径1b：transitions 引用不存在的 provenance → 11.2 触发器 ABORT。"""
    a = make_candidate(stores["assertions"], ev_ref=seeded["evidence"])
    with pytest.raises(sqlite3.Error, match="provenance"):
        db.execute(
            "INSERT INTO akb_assertion_transitions (transition_id, assertion_id,"
            " previous_status, new_status, actor_id, reason, policy_version, provenance_ref)"
            " VALUES ('astt_f2', ?, 'candidate', 'validated', 'human:x', 'r',"
            " 'policy:v0.1', 'prov_ghost')", (a.assertion_id,))


def test_adv1c_illegal_pair_blocked(db, seeded, stores):
    """路径1c：伪造非法状态对（validated→candidate / asserted→validated）→ 11.1 ABORT。"""
    a = make_candidate(stores["assertions"], ev_ref=seeded["evidence"])
    db.execute(
        "INSERT INTO akb_provenance (provenance_id, actor_id, actor_kind, activity,"
        " policy_version, occurred_at) VALUES"
        " ('prov_f3','human:x','human','promote','policy:v0.1','2026-09-01T00:00:00Z')")
    with pytest.raises(sqlite3.Error, match="illegal status pair"):
        db.execute(
            "INSERT INTO akb_assertion_transitions (transition_id, assertion_id,"
            " previous_status, new_status, actor_id, reason, policy_version, provenance_ref)"
            " VALUES ('astt_f3', ?, 'validated', 'candidate', 'human:x', 'rollback',"
            " 'policy:v0.1', 'prov_f3')", (a.assertion_id,))


# ---- 攻击路径 2：伪造 actor/治理字段 ----

def test_adv2_fake_actor_api_boundary(stores, seeded, db):
    """路径2：伪造 actor_id 的 transitions + UPDATE —— 权限在 Python 层强制；
    SQL 层伪造 actor 的链在 provenance-pair 检查下仍不能改变最终治理有效性：
    合法对+ref 一致的直 SQL 链在 DB 层允许（设计语义：DB 强制状态对与审计完整性，
    actor 授权属应用层边界），此处验证 API 层拒绝伪造权限。"""
    st = stores["assertions"]
    a = make_candidate(st, ev_ref=seeded["evidence"])
    st.transition(assertion_id=a.assertion_id, new_status="validated",
                  actor_id="system:validator", reason="ok")
    # API：system 无法 promote（权限矩阵）
    with pytest.raises(ValueError, match="E-ACTOR-NOT-AUTHORIZED"):
        st.transition(assertion_id=a.assertion_id, new_status="asserted",
                      actor_id="system:bot", reason="auto")
    # API：llm 无法 promote
    with pytest.raises(ValueError, match="E-ACTOR-NOT-AUTHORIZED"):
        st.transition(assertion_id=a.assertion_id, new_status="asserted",
                      actor_id="llm:gateway", reason="self-promote")


def test_adv2b_type_boundary_via_sql_blocked(db, seeded, stores):
    """路径2b：inferred→asserted 的伪造迁移行 → 11.1b type-boundary ABORT。"""
    st = stores["assertions"]
    inf = make_candidate(st, atype="inferred", ev_ref=seeded["evidence"],
                         derivation={"rule_ref": "R", "parent_assertions": ["x"],
                                     "reasoner_id": "r"})
    db.execute(
        "INSERT INTO akb_provenance (provenance_id, actor_id, actor_kind, activity,"
        " policy_version, occurred_at) VALUES"
        " ('prov_f4','human:x','human','promote','policy:v0.1','2026-09-01T00:00:00Z')")
    with pytest.raises(sqlite3.Error, match="type-boundary"):
        db.execute(
            "INSERT INTO akb_assertion_transitions (transition_id, assertion_id,"
            " previous_status, new_status, actor_id, reason, policy_version, provenance_ref)"
            " VALUES ('astt_f4', ?, 'candidate', 'asserted', 'human:x', 'fake',"
            " 'policy:v0.1', 'prov_f4')", (inf.assertion_id,))


def test_adv2c_hypothesized_type_boundary_via_sql(db, seeded, stores):
    """路径2c：hypothesized→validated 伪造迁移行 → type-boundary ABORT。"""
    h = make_candidate(stores["assertions"], atype="hypothesized", ev_ref=seeded["evidence"])
    db.execute(
        "INSERT INTO akb_provenance (provenance_id, actor_id, actor_kind, activity,"
        " policy_version, occurred_at) VALUES"
        " ('prov_f5','human:x','human','validate','policy:v0.1','2026-09-01T00:00:00Z')")
    with pytest.raises(sqlite3.Error, match="type-boundary"):
        db.execute(
            "INSERT INTO akb_assertion_transitions (transition_id, assertion_id,"
            " previous_status, new_status, actor_id, reason, policy_version, provenance_ref)"
            " VALUES ('astt_f5', ?, 'candidate', 'validated', 'human:x', 'fake',"
            " 'policy:v0.1', 'prov_f5')", (h.assertion_id,))


# ---- 攻击路径 3：provenance_ref 操纵 ----

def test_adv3_provenance_ref_manipulation_blocked(db, seeded, stores):
    """路径3：绕过迁移历史操纵 provenance_ref。
    - 不可变列守卫允许 provenance_ref 变更吗？provenance_ref 是受控列——
      但触发器 9.2b 要求 status 变更匹配；仅改 provenance_ref（status 不变）→
      设计允许（provenance_ref 随最近迁移更新）——
      但**清空/指向假 provenance 且无 transitions 行**的场景由 9.2b 只查 status 变更——
      严格化：status 不变时 provenance_ref 也不应被无审计改写（最小修复：新增触发器）。
    本测试验证当前行为并锁定：status 不变时改 provenance_ref 被拒（migration 11 后）。"""
    st = stores["assertions"]
    a = make_candidate(st, ev_ref=seeded["evidence"])
    with pytest.raises(sqlite3.Error):
        db.execute(
            "UPDATE akb_assertions SET provenance_ref='prov_fake' WHERE assertion_id=?",
            (a.assertion_id,))