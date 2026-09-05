# -*- coding: utf-8 -*-
"""V0.4 Reasoner Core fixtures（in-memory db + 种子断言）。"""
from __future__ import annotations

import pytest

from agent_kb.evidence_core.assertions import AssertionStore
from agent_kb.storage.migrations import SchemaMigrator
from agent_kb.reasoning import (
    BuiltinRuleReasoner,
    ReasoningContext,
    ReasoningEngine,
)


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    SchemaMigrator(con).migrate()
    yield con
    con.close()


@pytest.fixture
def seeded(db):
    """种子 parent 断言：extracted 两条（rule 通道）+ before 链 + 同 pred 同/异值。"""
    store = AssertionStore(db)
    made = {}

    def mk(key, subj, pred, value, kind="literal", atype="extracted", conf=0.9):
        a = store.create_candidate(
            subject_ref=subj, predicate_ref=pred,
            object={"kind": kind, "value": value}, assertion_type=atype,
            ontology_scope="test", actor_id="system:seed", confidence=conf)
        made[key] = a
        return a

    mk("sat", "Pump-A", "satisfies_rule", "RuleX")
    mk("req", "", "rule_requires", "Inspection")
    mk("ab", "A", "before", "B")
    mk("bc", "B", "before", "C")
    mk("same1", "OBC", "has_parameter", "265V", conf=0.9)
    mk("same2", "OBC", "has_parameter", "265V", conf=0.8)
    mk("diff1", "MOT", "has_parameter", "400V", conf=0.9)
    mk("diff2", "MOT", "has_parameter", "410V", conf=0.85)
    return {"store": store, "made": made, "db": db}


@pytest.fixture
def engine(db):
    return ReasoningEngine(db, provider=BuiltinRuleReasoner())


@pytest.fixture
def ctx():
    return ReasoningContext(ontology_scope="test")