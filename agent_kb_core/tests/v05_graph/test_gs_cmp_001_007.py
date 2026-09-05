# -*- coding: utf-8 -*-
"""GS-CMP-001..007（AKB-V05-IMPL-001：Graph Schema 基础层验收）。"""
from __future__ import annotations

from collections import Counter

from agent_kb.kgraph import (
    GraphProjectionService,
    node_id as nid,
    edge_id as eid,
)
from agent_kb.kgraph.models import (
    AssertionNode,
    ContradictsEdge,
    DerivedFromEdge,
    EntityNode,
    EvidenceNode,
    ExtractedFromEdge,
    InferenceNode,
    RelatesToEdge,
    SemanticUnitNode,
    SupportsEdge,
)
from agent_kb.reasoning.models import canonical_json


def _by_type(projection):
    return Counter(type(n).__name__ for n in projection.nodes)


def _edges_of(projection, cls):
    return [e for e in projection.edges if isinstance(e, cls)]


def test_gs_cmp_001_node_projection(db, seeded, projection):
    """GS-CMP-001：六类 Node 投影（Document/Evidence/SemanticUnit/Assertion/Entity/
    Inference）数量与 id 确定性。"""
    counts = _by_type(projection)
    assert counts["DocumentNode"] == 1
    assert counts["EvidenceNode"] == len(seeded["eids"])
    assert counts["SemanticUnitNode"] >= len(seeded["eids"])   # 编译产出 unit
    assert counts["AssertionNode"] >= 2                        # synthesis + seeds + inferred
    assert counts["EntityNode"] >= 1                           # identity 簇
    assert counts["InferenceNode"] == 1                        # 一个 reasoning run
    # id 确定性：node_id 函数重算一致
    assert nid("document", "dg5") == nid("document", "dg5")
    # 零重复 node id
    ids = [n.node_id for n in projection.nodes]
    assert len(ids) == len(set(ids))


def test_gs_cmp_002_edge_projection(db, seeded, projection):
    """GS-CMP-002：六类 Edge 投影（extracted_from/supports/contradicts/derived_from/
    validates/relates_to）。"""
    assert _edges_of(projection, ExtractedFromEdge), "extracted_from missing"
    assert _edges_of(projection, SupportsEdge), "supports missing"
    assert _edges_of(projection, DerivedFromEdge), "derived_from missing (inferred)"
    assert _edges_of(projection, ContradictsEdge), "contradicts missing (RR-04)"
    assert _edges_of(projection, RelatesToEdge), "relates_to missing"
    # validates：治理动作存在时投影（govern:validate）——本 seed 无治理，跳过不 fail，
    # 但 edge 类型必须可构造（模型存在性由 import 断言）
    from agent_kb.kgraph import ValidatesEdge  # noqa: F401
    # 零重复 edge id
    ids = [e.edge_id for e in projection.edges]
    assert len(ids) == len(set(ids))


def test_gs_cmp_003_deterministic_id(db, seeded):
    """GS-CMP-003：node/edge id 确定性——同输入重算全等；异输入必异；跨服务实例一致。"""
    assert nid("assertion", "ast_1") == nid("assertion", "ast_1")
    assert nid("assertion", "ast_1") != nid("assertion", "ast_2")
    assert nid("assertion", "ast_1") != nid("evidence", "ast_1")     # type 参与派生
    assert eid("supports", "n1", "n2") == eid("supports", "n1", "n2")
    assert eid("supports", "n1", "n2") != eid("supports", "n2", "n1")  # 方向参与
    assert eid("supports", "n1", "n2") != eid("derived_from", "n1", "n2")
    # 跨服务实例：同 db 双 service → 全投影全等
    p1 = GraphProjectionService().process(db)
    p2 = GraphProjectionService().process(db)
    assert p1.fingerprint == p2.fingerprint
    assert canonical_json([n.node_id for n in p1.nodes]) == \
        canonical_json([n.node_id for n in p2.nodes])
    assert canonical_json([e.edge_id for e in p1.edges]) == \
        canonical_json([e.edge_id for e in p2.edges])


def test_gs_cmp_004_idempotent_rebuild(db, seeded):
    """GS-CMP-004：幂等重建——同状态双跑同 Graph；无状态变化时 fingerprint 稳定。"""
    s1 = GraphProjectionService().process(db)
    s2 = GraphProjectionService().process(db)
    s3 = GraphProjectionService().process(db)
    assert s1.fingerprint == s2.fingerprint == s3.fingerprint
    assert len(s1.nodes) == len(s2.nodes) == len(s3.nodes)
    assert len(s1.edges) == len(s2.edges) == len(s3.edges)


def test_gs_cmp_005_provenance_preservation(db, seeded, projection):
    """GS-CMP-005：provenance 保持——任一节点/边可回溯源对象（KG-01 零孤儿面）。"""
    # 全部节点带 provenance_ref
    for n in projection.nodes:
        assert n.provenance_ref, f"{type(n).__name__} missing provenance"
    # 全部边带 provenance_ref
    for e in projection.edges:
        assert e.provenance_ref, f"{type(e).__name__} missing provenance"
    # supports 边 target 可回溯真实 evidence id（node_id 反查源）
    ev_sources = {n.source_id for n in projection.nodes
                  if isinstance(n, EvidenceNode)}
    assert ev_sources == set(seeded["eids"])
    # derived_from 边源是真实 inferred 断言
    for e in _edges_of(projection, DerivedFromEdge):
        src = next(n for n in projection.nodes if n.node_id == e.source_node)
        assert src.assertion_type == "inferred"


def test_gs_cmp_006_contradiction_projection_no_resolution(db, seeded, projection):
    """GS-CMP-006：矛盾投影不裁决——contradicts 边保留双方 + conflict_ref 引用，
    无任何 resolved/winner 字段（治理裁决不属 Graph 职责）。"""
    ce = _edges_of(projection, ContradictsEdge)
    assert ce, "RR-04 disputed assertion must project contradicts edge"
    for e in ce:
        assert e.conflict_ref.startswith("RR-04:")
        assert not hasattr(e, "resolved") and not hasattr(e, "winner")
    # 双方节点都存在（不丢边）
    node_ids = {n.node_id for n in projection.nodes}
    for e in ce:
        assert e.source_node in node_ids and e.target_node in node_ids


def test_gs_cmp_007_inferred_lifecycle_unchanged(db, seeded):
    """GS-CMP-007：inferred 生命周期不变——恒 candidate；inferred→asserted 仍禁；
    Graph 投影不改变源状态（零 DB 写）。"""
    from agent_kb.evidence_core.state_machine import validate_transition
    for a in seeded["reasoning"]["assertions"]:
        assert a.status == "candidate" and a.assertion_type == "inferred"
        v = validate_transition(current_status="candidate", new_status="asserted",
                                assertion_type="inferred", actor_id="human:reviewer",
                                evidence_count=1)
        assert any("E-ILLEGAL-TRANSITION" in x for x in v)
    # 投影零 DB 写：投影前后 assertion/run 状态不变
    before = db.execute("SELECT status, COUNT(*) c FROM akb_assertions"
                        " GROUP BY status ORDER BY status").fetchall()
    GraphProjectionService().process(db)
    after = db.execute("SELECT status, COUNT(*) c FROM akb_assertions"
                       " GROUP BY status ORDER BY status").fetchall()
    assert [tuple(r) for r in before] == [tuple(r) for r in after]
    # 投影后 fingerprint 稳定（无写入副作用）
    p1 = GraphProjectionService().process(db)
    p2 = GraphProjectionService().process(db)
    assert p1.fingerprint == p2.fingerprint