# -*- coding: utf-8 -*-
"""V0.5 graph fixtures（in-memory db + 编译/合成/推理种子）。"""
from __future__ import annotations

import pytest

from agent_kb.kgraph import GraphProjectionService


@pytest.fixture
def db():
    con = pytest.importorskip("sqlite3").connect(":memory:", isolation_level=None)
    con.row_factory = pytest.importorskip("sqlite3").Row
    from agent_kb.storage.migrations import SchemaMigrator
    SchemaMigrator(con).migrate()
    yield con
    con.close()


@pytest.fixture
def seeded(db):
    """种子：V0.2 编译双证据（同主题参数）→ V0.3 synthesis → V0.4 推理（含 RR-04 争议）。"""
    from agent_kb.evidence_core import EvidenceStore
    from agent_kb.evidence_core.assertions import AssertionStore
    from agent_kb.evidence_core.compilation import SemanticCompiler
    from agent_kb.evidence_core.synthesis import SynthesisEngine
    db.execute("INSERT INTO akb_sources (source_id, source_type, name)"
               " VALUES ('g5', 'document', 'G5')")
    db.execute("INSERT INTO akb_documents (document_id, source_id, version, content_hash,"
               " ingested_at) VALUES ('dg5', 'g5', '1.0', 'h',"
               " strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
    store = EvidenceStore(db)
    comp = SemanticCompiler(db)
    eids = []
    for t in ["OBC 额定输入电压 265V。", "OBC 额定输入电压是 265V。"]:
        ev = store.create(document_id="dg5", content=t, extraction_method="t")
        comp.compile(ev.evidence_id, actor_id="system:compiler")
        eids.append(ev.evidence_id)
    sr = SynthesisEngine(db).synthesize(eids, actor_id="system:synth")
    ast_store = AssertionStore(db)
    # V0.4 推理：RR-03 佐证（同值）+ RR-04 矛盾旗标（异值）
    s1 = ast_store.create_candidate(
        subject_ref="OBC", predicate_ref="has_parameter",
        object={"kind": "literal", "value": "265V"}, assertion_type="extracted",
        ontology_scope="test", actor_id="system:seed", confidence=0.9,
        evidence_refs=[eids[0]])
    s2 = ast_store.create_candidate(
        subject_ref="OBC", predicate_ref="has_parameter",
        object={"kind": "literal", "value": "265V"}, assertion_type="extracted",
        ontology_scope="test", actor_id="system:seed", confidence=0.8,
        evidence_refs=[eids[1]])
    d1 = ast_store.create_candidate(
        subject_ref="MOT", predicate_ref="has_parameter",
        object={"kind": "literal", "value": "400V"}, assertion_type="extracted",
        ontology_scope="test", actor_id="system:seed", confidence=0.9,
        evidence_refs=[eids[0]])
    d2 = ast_store.create_candidate(
        subject_ref="MOT", predicate_ref="has_parameter",
        object={"kind": "literal", "value": "410V"}, assertion_type="extracted",
        ontology_scope="test", actor_id="system:seed", confidence=0.85,
        evidence_refs=[eids[1]])
    eng = ReasoningEngine(db, provider=BuiltinRuleReasoner())
    rr = eng.reason([s1.assertion_id, s2.assertion_id, d1.assertion_id, d2.assertion_id],
                    actor_id="system:reasoner", context=ReasoningContext("test"))
    return {"eids": eids, "synthesis": sr, "reasoning": rr, "store": ast_store}


from agent_kb.reasoning import BuiltinRuleReasoner, ReasoningContext, ReasoningEngine  # noqa: E402


@pytest.fixture
def projection(db, seeded):
    return GraphProjectionService().process(db)