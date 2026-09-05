# -*- coding: utf-8 -*-
"""V0.1-AST-005：非法迁移拒绝（状态机矩阵全负例）。

Requirement: SYS-006 · Invariant: INV-002/005/008 · Test ID: V0.1-AST-005
"""
from __future__ import annotations

import pytest

from conftest import make_candidate


def test_ast_005_validated_to_candidate_rejected(stores, seeded):
    """INV-005: validated→candidate 回退禁止（历史不可逆）。"""
    st = stores["assertions"]
    a = make_candidate(st, ev_ref=seeded["evidence"])
    st.transition(assertion_id=a.assertion_id, new_status="validated",
                  actor_id="system:validator", reason="ok")
    with pytest.raises(ValueError, match="E-ILLEGAL-TRANSITION"):
        st.transition(assertion_id=a.assertion_id, new_status="candidate",
                      actor_id="human:r", reason="rollback try")


def test_ast_005b_rejected_is_terminal(stores):
    """rejected → any 禁止。"""
    st = stores["assertions"]
    a = make_candidate(st)
    st.transition(assertion_id=a.assertion_id, new_status="rejected",
                  actor_id="system:validator", reason="bad content")
    with pytest.raises(ValueError, match="E-ILLEGAL-TRANSITION"):
        st.transition(assertion_id=a.assertion_id, new_status="asserted",
                      actor_id="human:r", reason="try")


def test_ast_005c_unauthorized_actor_rejected(stores, seeded):
    """权限矩阵：validated→asserted 仅 human；system 尝试 → E-ACTOR-NOT-AUTHORIZED。"""
    st = stores["assertions"]
    a = make_candidate(st, ev_ref=seeded["evidence"])
    st.transition(assertion_id=a.assertion_id, new_status="validated",
                  actor_id="system:validator", reason="ok")
    with pytest.raises(ValueError, match="E-ACTOR-NOT-AUTHORIZED"):
        st.transition(assertion_id=a.assertion_id, new_status="asserted",
                      actor_id="system:auto", reason="auto promote")


def test_ast_005d_conflict_flow(stores, seeded):
    """合法链抽查：asserted→disputed（system:conflict-detector）→ asserted（human 裁决）。"""
    st = stores["assertions"]
    a = make_candidate(st, ev_ref=seeded["evidence"])
    st.transition(assertion_id=a.assertion_id, new_status="validated",
                  actor_id="system:validator", reason="ok")
    st.transition(assertion_id=a.assertion_id, new_status="asserted",
                  actor_id="human:r", reason="approved")
    st.transition(assertion_id=a.assertion_id, new_status="disputed",
                  actor_id="system:conflict-detector", reason="conflicting evidence")
    r = st.transition(assertion_id=a.assertion_id, new_status="asserted",
                      actor_id="human:judge", reason="resolved in favor")
    assert r["new_status"] == "asserted"


def test_ast_005e_g016_conflict_detection(stores, seeded):
    """Golden G016 支撑：同 S-P 多 object → list_conflicts 检出。"""
    st = stores["assertions"]
    make_candidate(st, subject="e:eff", predicate="r:max", value="97%", ev_ref=seeded["evidence"])
    make_candidate(st, subject="e:eff", predicate="r:max", value="95%", ev_ref=seeded["evidence"])
    conflicts = st.list_conflicts("e:eff", "r:max")
    assert len(conflicts) == 2
    # 无冲突场景
    make_candidate(st, subject="e:solo", predicate="r:max", value="50%", ev_ref=seeded["evidence"])
    assert st.list_conflicts("e:solo", "r:max") == []