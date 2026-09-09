# -*- coding: utf-8 -*-
"""V0.1-AST-001/002/003/004：candidate 创建、Evidence Gate、derived isolation。

Requirement: SYS-004/005/006 · Invariant: INV-001/002 · Test ID: V0.1-AST-001..004
"""
from __future__ import annotations

import pytest

from conftest import make_candidate


def test_ast_001_candidate_creation(stores, seeded):
    """V0.1-AST-001: 四种可创建类型均落 candidate。"""
    st = stores["assertions"]
    ev = seeded["evidence"]
    for atype in ("extracted", "observed", "hypothesized"):
        a = make_candidate(st, subject=f"e:{atype}", atype=atype)
        assert a.status == "candidate"
    inf = make_candidate(st, subject="e:inf", atype="inferred",
                         derivation={"rule_ref": "R1", "parent_assertions": ["ast_x"],
                                     "reasoner_id": "reasoner_v1"})
    assert inf.status == "candidate" and inf.derivation["rule_ref"] == "R1"


def test_ast_001b_direct_asserted_creation_forbidden(stores):
    """V0.1-AST-001 负例：asserted 直接创建禁止。"""
    with pytest.raises(ValueError, match="E-INVALID-TYPE-FOR-CREATE"):
        make_candidate(stores["assertions"], atype="asserted")


def test_ast_002_no_evidence_no_validated(stores):
    """V0.1-AST-002 / INV-001: 无证据 → validated 拒绝，status 保持 candidate。"""
    st = stores["assertions"]
    a = make_candidate(st)
    with pytest.raises(ValueError, match="E-INV-001-NO-EVIDENCE"):
        st.transition(assertion_id=a.assertion_id, new_status="validated",
                      actor_id="system:validator", reason="try")
    assert st.get(a.assertion_id).status == "candidate"  # 不得自动 reject


def test_ast_003_valid_evidence_validated(stores, seeded):
    """V0.1-AST-003 / INV-001: 有证据 → validated（validator actor 自动门）。"""
    st = stores["assertions"]
    a = make_candidate(st, ev_ref=seeded["evidence"])
    r = st.transition(assertion_id=a.assertion_id, new_status="validated",
                      actor_id="system:validator", reason="evidence verified")
    assert r["new_status"] == "validated"
    # 幂等：重复 transition 同状态 → no-op
    r2 = st.transition(assertion_id=a.assertion_id, new_status="validated",
                       actor_id="system:validator", reason="again")
    assert r2["idempotent_noop"] is True


def test_ast_004_derived_requires_derivation(stores):
    """V0.1-AST-004 / INV-002: inferred 无 derivation → 拒绝（API+DB 双层）。"""
    with pytest.raises(ValueError, match="E-DERIVATION-MISSING"):
        make_candidate(stores["assertions"], atype="inferred")
    # 缺字段
    with pytest.raises(ValueError, match="E-DERIVATION-MISSING: reasoner_id"):
        make_candidate(stores["assertions"], atype="inferred",
                       derivation={"rule_ref": "R", "parent_assertions": []})


def test_ast_004b_inferred_cannot_be_promoted(stores, seeded):
    """V0.1-AST-004 负例 / INV-002: inferred → asserted 禁止。"""
    st = stores["assertions"]
    inf = make_candidate(st, atype="inferred", ev_ref=seeded["evidence"],
                         derivation={"rule_ref": "R1", "parent_assertions": ["ast_x"],
                                     "reasoner_id": "r1"})
    r = st.transition(assertion_id=inf.assertion_id, new_status="validated",
                      actor_id="system:validator", reason="deduced")
    assert r["new_status"] == "validated"
    with pytest.raises(ValueError, match="inferred cannot be promoted"):
        st.transition(assertion_id=inf.assertion_id, new_status="asserted",
                      actor_id="human:reviewer", reason="try")


def test_ast_004c_hypothesized_boundary(stores, seeded):
    """任务书 §13 / State Machine §3: hypothesized 只能 candidate；→validated 禁止。"""
    st = stores["assertions"]
    h = make_candidate(st, atype="hypothesized", ev_ref=seeded["evidence"])
    assert h.status == "candidate"
    with pytest.raises(ValueError, match="E-ILLEGAL-TRANSITION"):
        st.transition(assertion_id=h.assertion_id, new_status="validated",
                      actor_id="system:validator", reason="try")
    with pytest.raises(ValueError, match="E-ILLEGAL-TRANSITION"):
        st.transition(assertion_id=h.assertion_id, new_status="asserted",
                      actor_id="human:r", reason="try")