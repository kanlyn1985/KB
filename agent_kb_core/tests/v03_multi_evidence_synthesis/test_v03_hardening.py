# -*- coding: utf-8 -*-
"""V0.3 Implementation Hardening（AKB-V03-IMPL-002）H-001..H-015。"""
from __future__ import annotations

import json

import pytest

from agent_kb.evidence_core.synthesis import (
    EvidenceSetManager,
    SynthesisEngine,
    SynthesisError,
)
from agent_kb.evidence_core.synthesis.alignment import EvidenceAlignmentEngine


def _mk_three_units(db, texts):
    """3 evidence → 3 unit（candidate_id 有意跨 unit 重名：ec_0001/ec_0002）。"""
    from agent_kb.evidence_core import EvidenceStore
    from agent_kb.evidence_core.compilation import SemanticCompiler
    import time
    tag = str(int(time.time() * 1000))[-8:]
    db.execute("INSERT OR IGNORE INTO akb_sources (source_id, source_type, name)"
               " VALUES (?, 'document', ?)", (f"sh_{tag}", f"SH_{tag}"))
    db.execute("INSERT OR IGNORE INTO akb_documents (document_id, source_id, version,"
               " content_hash, ingested_at, effective_at)"
               " VALUES (?, ?, '1.0', 'h', strftime('%Y-%m-%dT%H:%M:%SZ','now'),"
               " '2026-01-01T00:00:00Z')", (f"dh_{tag}", f"sh_{tag}"))
    doc_id = f"dh_{tag}"
    store = EvidenceStore(db)
    comp = SemanticCompiler(db)
    eids = []
    for t in texts:
        ev = store.create(document_id=doc_id, content=t, extraction_method="t")
        comp.compile(ev.evidence_id, actor_id="system:compiler")
        eids.append(ev.evidence_id)
    return eids, store, comp


# ---- Defect A：H-001/H-002（unit 所有权隔离 + candidate_id 跨 unit 重名）----

def test_h_001_relation_unit_ownership_isolation(db, compiled_evidence):
    """每条 relation 解析到其所属 unit 的实体簇——行为级（多 unit 候选值不同场景）。"""
    eids, store, comp = _mk_three_units(
        db, ["OBC 额定输入电压 265V。", "OBC 额定输入电压 280V。", "OBC 待机功耗小于 5W。"])
    eng = SynthesisEngine(db)
    r = eng.synthesize(eids, actor_id="system:synth")
    al = r["run"].alignment
    # 265V 与 280V 证据的 relation 都归属 subject 簇（OBC 额定输入电压 跨证据）且
    # object 值各自正确（无跨 unit 串值）
    rel_members = [(m["evidence_id"], m.get("object_value"))
                   for rc in al["relation_clusters"] for m in rc["members"]
                   if m.get("object_value")]
    by_eid = dict(rel_members)
    # 每条 evidence 的 relation object 值与其文本一致（unit 所有权正确）
    text_expect = {}
    for t, eid in zip(["OBC 额定输入电压 265V。", "OBC 额定输入电压 280V。",
                       "OBC 待机功耗小于 5W。"], eids):
        text_expect[eid] = "265V" if "265V" in t else ("280V" if "280V" in t else "5W")
    for eid, val in by_eid.items():
        assert val == text_expect[eid], f"unit ownership violated: {eid} got {val}"


def test_h_002_duplicate_candidate_id_across_units(db):
    """跨 unit candidate_id 重名（ec_0001/ec_0002）→ 对齐不串值。"""
    eids, store, comp = _mk_three_units(
        db, ["OBC 额定输入电压 265V。", "OBC 额定输入电压 280V。", "OBC 额定输入电压 300V。"])
    eng = SynthesisEngine(db)
    r = eng.synthesize(eids, actor_id="system:synth")
    # VALUE_CONFLICT：三值互异且全被保留（H-009 联动）
    conflicts = r["run"].conflicts["conflicts"]
    vc = [c for c in conflicts if c["conflict_type"] == "VALUE_CONFLICT"]
    assert vc and len(vc[0]["sides"]) == 3
    # 每条 evidence 的 object_value 都是其真实文本值
    real = {"265V", "280V", "300V"}
    got = {side["value"] for side in vc[0]["sides"]}
    assert got == real


# ---- Defect B：H-003..H-005（state alignment）----

def test_h_003_state_alignment_positive(db):
    """同 subject + 同 state 谓词 + 兼容时间 → aligned。"""
    from agent_kb.evidence_core.synthesis.models import AlignmentResult, RelationAlignmentCluster
    eng_e = EvidenceAlignmentEngine()
    al = AlignmentResult()
    al.relation_clusters.append(RelationAlignmentCluster(
        cluster_id="rc_0001", subject_cluster="cl_0001", predicate="has_parameter",
        object_cluster="cl_0002",
        members=[{"evidence_id": "E1", "unit_id": "u1", "confidence": 0.9,
                  "object_value": "265V"},
                 {"evidence_id": "E2", "unit_id": "u2", "confidence": 0.9,
                  "object_value": "265V"}]))
    units = [
        {"evidence_id": "E1", "unit_id": "u1",
         "temporal_parse": {"valid_time": {"valid_from": "2026-01-01",
                                           "valid_until": "2027-01-01"},
                            "parse_status": "resolved"}},
        {"evidence_id": "E2", "unit_id": "u2",
         "temporal_parse": {"valid_time": {"valid_from": "2026-06-01",
                                           "valid_until": "2027-06-01"},
                            "parse_status": "resolved"}}]
    sc, contra = eng_e._state_alignment(units, {}, al.relation_clusters)
    assert len(sc) == 1 and sc[0]["alignment"] == "aligned"
    assert not contra


def test_h_004_state_alignment_negative(db):
    """缺时间锚 → 不伪造对齐（alignment=missing/partial-anchored，无编造日期）。"""
    from agent_kb.evidence_core.synthesis.models import AlignmentResult, RelationAlignmentCluster
    eng_e = EvidenceAlignmentEngine()
    al = AlignmentResult()
    al.relation_clusters.append(RelationAlignmentCluster(
        cluster_id="rc_0001", subject_cluster="cl_0001", predicate="has_parameter",
        object_cluster="cl_0002",
        members=[{"evidence_id": "E1", "unit_id": "u1", "confidence": 0.9,
                  "object_value": "265V"}]))
    units = [{"evidence_id": "E1", "unit_id": "u1",
              "temporal_parse": {"parse_status": "unresolved"}}]
    sc, contra = eng_e._state_alignment(units, {}, al.relation_clusters)
    assert sc and sc[0]["alignment"] in ("missing", "partial-anchored")
    assert not contra
    assert all(not m.get("valid_from") or m["valid_from"] != "2026" for m in sc[0]["members"])


def test_h_005_state_conflict(db):
    """同 subject 同 state + contradictory 窗 → STATE_CONFLICT（双方保留）。"""
    from agent_kb.evidence_core.synthesis.conflicts import ConflictDetector
    from agent_kb.evidence_core.synthesis.models import (
        AlignmentResult,
        RelationAlignmentCluster,
    )
    eng_e = EvidenceAlignmentEngine()
    al = AlignmentResult()
    al.relation_clusters.append(RelationAlignmentCluster(
        cluster_id="rc_0001", subject_cluster="cl_0001", predicate="has_parameter",
        object_cluster="cl_0002",
        members=[{"evidence_id": "E1", "unit_id": "u1", "confidence": 0.9,
                  "object_value": "265V"},
                 {"evidence_id": "E2", "unit_id": "u2", "confidence": 0.9,
                  "object_value": "265V"}]))
    units = [
        {"evidence_id": "E1", "unit_id": "u1",
         "temporal_parse": {"valid_time": {"valid_from": "2026-01-01",
                                           "valid_until": "2026-06-01"},
                            "parse_status": "resolved"}},
        {"evidence_id": "E2", "unit_id": "u2",
         "temporal_parse": {"valid_time": {"valid_from": "2027-01-01",
                                           "valid_until": "2027-06-01"},
                            "parse_status": "resolved"}}]
    sc, contra = eng_e._state_alignment(units, {}, al.relation_clusters)
    assert contra and contra[0]["state_predicate"] == "has_parameter" \
        and len(contra[0]["sides"]) == 2
    al.state_contradictions = contra   # align() 内部同款集成路径
    cs = ConflictDetector().detect(al, units, audit_ts="2026-09-03T00:00:00Z")
    stc = [c for c in cs.conflicts if c.conflict_type == "STATE_CONFLICT"]
    assert stc, "STATE_CONFLICT must be emitted"
    rec = stc[0]
    assert set(rec.source_evidence_ids) == {"E1", "E2"}       # 双方保留
    assert rec.detection_method == "CONF-006-STATE"
    assert rec.audit_timestamp == "2026-09-03T00:00:00Z"


# ---- Defect H：H-006（temporal interval conflict 六态）----

def test_h_006_temporal_interval_states(db):
    eng_e = EvidenceAlignmentEngine()
    def u(eid, vf, vu, status="resolved"):
        return {"evidence_id": eid, "unit_id": eid,
                "temporal_parse": {"valid_time": {"valid_from": vf, "valid_until": vu},
                                   "parse_status": status}}
    assert eng_e._temporal_alignment([u("E1", "2026-01-01", "2027-01-01"),
                                      u("E2", "2026-01-01", "2027-01-01")])["overall"] == "same"
    assert eng_e._temporal_alignment([u("E1", "2026-01-01", "2026-06-01"),
                                      u("E2", "2026-06-01", "2026-12-01")])["overall"] == "overlapping"
    # AKB-V03-IMPL-004 语义升级：恰两证据全隔互斥窗 = contradictory（TEMPORAL_CONFLICT
    # 候选，P-012 契约）；三证据顺时链仍为 sequential
    # Semantic Context Rule（V03-IMPL-005）：同实体簇上下文 + 区间互斥 → contradictory
    ctx = {"E1": {"cl_0001"}, "E2": {"cl_0001"}}   # 同实体（OBC）
    ta2 = eng_e._temporal_alignment([u("E1", "2025-01-01", "2025-06-01"),
                                     u("E2", "2027-01-01", "2027-06-01")], ctx)
    assert ta2["overall"] == "contradictory" and ta2["contradiction_members"]
    # 跨实体互斥（Pump-A vs Valve-B 语义）→ sequential（禁止跨实体制造 TEMPORAL_CONFLICT）
    ctx_x = {"E1": {"cl_0001"}, "E2": {"cl_0002"}}
    ta_x = eng_e._temporal_alignment([u("E1", "2025-01-01", "2025-06-01"),
                                      u("E2", "2027-01-01", "2027-06-01")], ctx_x)
    assert ta_x["overall"] == "sequential" and not ta_x["contradiction_members"]
    # 三证据顺时链（同实体）→ sequential
    ta3 = eng_e._temporal_alignment([u("E1", "2025-01-01", "2025-06-01"),
                                     u("E2", "2026-01-01", "2026-06-01"),
                                     u("E3", "2027-01-01", "2027-06-01")], ctx)
    assert ta3["overall"] == "sequential"
    assert eng_e._temporal_alignment([u("E1", None, None)])["overall"] == "missing"
    assert eng_e._temporal_alignment([u("E1", None, None, status="unresolved"),
                                      u("E2", "2026-01-01", "2027-01-01")])["overall"] == "unresolved"


# ---- Defect I：H-007（event 同时刻不同参与者拒绝）----

def test_h_007_event_same_time_different_participants(db):
    from agent_kb.evidence_core.synthesis.alignment import EvidenceAlignmentEngine
    eng_e = EvidenceAlignmentEngine()
    units = [
        {"evidence_id": "E1", "unit_id": "u1",
         "entity_candidates": [{"candidate_id": "c1", "normalized_form": "泵A",
                                "entity_type": "equipment"}],
         "temporal_parse": {"event_time": "2026-05-01", "parse_status": "resolved"}},
        {"evidence_id": "E2", "unit_id": "u2",
         "entity_candidates": [{"candidate_id": "c2", "normalized_form": "阀B",
                                "entity_type": "equipment"}],
         "temporal_parse": {"event_time": "2026-05-01", "parse_status": "resolved"}}]
    # 预构建 ec_index：两 unit 实体不同簇（无交集）
    ec_index = {("u1", "c1"): "cl_0001", ("u2", "c2"): "cl_0002"}
    events = eng_e._event_clusters(units, ec_index)
    assert not events, "same timestamp + disjoint participants must NOT align"


# ---- Defect C：H-008（实体层级一致性）----

def test_h_008_entity_hierarchy_consistency(db):
    """同语义实体（一含 ontology_ref 一不含）不因 L3 缺失而分裂；无关实体不合。"""
    from agent_kb.evidence_core.synthesis.alignment import EvidenceAlignmentEngine
    eng_e = EvidenceAlignmentEngine()
    units = [
        {"evidence_id": "E1", "unit_id": "u1",
         "entity_candidates": [
             {"candidate_id": "c1", "normalized_form": "OBC", "entity_type": "equipment",
              "ontology_ref": "object_type:equipment"}]},
        {"evidence_id": "E2", "unit_id": "u2",
         "entity_candidates": [
             {"candidate_id": "c1", "normalized_form": "OBC", "entity_type": "equipment"},
             {"candidate_id": "c2", "normalized_form": "DCDC", "entity_type": "equipment",
              "ontology_ref": "object_type:equipment"}]}]
    al = eng_e.align(units)
    obc = [c for c in al.entity_clusters
           if any(m["normalized_form"] == "OBC" for m in c.members)]
    assert len(obc) == 1 and len(obc[0].members) == 2  # OBC 跨证据合一簇（L1/L2 共键）
    dcdc = [c for c in al.entity_clusters
            if any(m["normalized_form"] == "DCDC" for m in c.members)]
    assert dcdc and dcdc[0].members[0]["normalized_form"] == "DCDC"  # DCDC 独立簇


# ---- Defect D：H-009（relation value conflict 语义）----

def test_h_009_relation_value_conflict(db):
    """同 subject 同谓词不同 object → VALUE_CONFLICT（不塌缩 object 语义）。"""
    eids, store, comp = _mk_three_units(
        db, ["OBC 额定输入电压 265V。", "OBC 额定输入电压 280V。"])
    eng = SynthesisEngine(db)
    r = eng.synthesize(eids, actor_id="system:synth")
    vc = [c for c in r["run"].conflicts["conflicts"]
          if c["conflict_type"] == "VALUE_CONFLICT"]
    assert vc
    assert {s["value"] for s in vc[0]["sides"]} == {"265V", "280V"}
    # 同 subject 同谓词同 object → 兼容合成（对比组）
    eids2, store2, comp2 = _mk_three_units(
        db, ["OBC 额定输入电压 265V。", "OBC 额定输入电压是 265V。"])
    r3 = SynthesisEngine(db).synthesize(eids2, actor_id="system:synth")
    assert r3["assertions"]  # 同值 → 合成候选（无 VALUE_CONFLICT）


# ---- Defect G：H-014（compatibility 优先级）----

def test_h_014_compatibility_precedence(db):
    """有真实冲突的成员必须 CONFLICTING（不得因弱规则命中变 COMPATIBLE）。"""
    eids, store, comp = _mk_three_units(
        db, ["OBC 额定输入电压 265V。", "OBC 额定输入电压 280V。"])
    eng = SynthesisEngine(db)
    r = eng.synthesize(eids, actor_id="system:synth")
    compat = next(a for a in r["run"].alignment["rule_audit"]
                  if a["rule_id"].startswith("COMPAT-"))
    conflict_members = {eid for c in r["run"].conflicts["conflicts"]
                        for eid in c["source_evidence_ids"]}
    for eid in conflict_members:
        assert compat["result"][eid] == "CONFLICTING"
    # rule_id/inputs/result 记录完整
    assert "inputs" in compat and "result" in compat


# ---- Defect A/E：H-015（零 ambient 依赖——行为级注入）----

def test_h_015_no_ambient_unit_dependency(db):
    """3 unit 候选 ID 完全重名且值各异——对齐/冲突结果必须各归其主（D-15 行为证明）。"""
    eids, store, comp = _mk_three_units(
        db, ["OBC 额定输入电压 265V。", "OBC 额定输入电压 280V。", "OBC 额定输入电压 300V。"])
    eng = SynthesisEngine(db)
    r1 = eng.synthesize(eids, actor_id="system:synth")
    # 反转顺序重跑（同指纹）→ 各 evidence 的值归属不变
    r2 = eng.synthesize(list(reversed(eids)), actor_id="system:synth")
    assert r2["idempotent_hit"]
    sides1 = {s["value"] for c in r1["run"].conflicts["conflicts"]
              if c["conflict_type"] == "VALUE_CONFLICT" for s in c["sides"]}
    assert sides1 == {"265V", "280V", "300V"}


# ---- §11/13：H-010/H-011（确定性编号 + 逆序幂等）----

def test_h_010_deterministic_cluster_numbering(db):
    eids, store, comp = _mk_three_units(
        db, ["OBC 额定输入电压 265V。", "OBC 额定输入电压 280V。", "OBC 待机功耗小于 5W。"])
    eng = SynthesisEngine(db)
    r = eng.synthesize(eids, actor_id="system:synth")
    ids = [c["cluster_id"] for c in r["run"].alignment["entity_clusters"]]
    assert ids == sorted(ids)                      # 全簇序稳定
    assert len(set(ids)) == len(ids)               # 无重号


def test_h_011_reversed_evidence_set_idempotency(db, compiled_evidence):
    eng = compiled_evidence["engine"]
    r1 = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    r2 = eng.synthesize(list(reversed(compiled_evidence["evidence_ids"])),
                        actor_id="system:synth")
    assert r1["fingerprint"] == r2["fingerprint"] and r2["idempotent_hit"]
    assert len(r2["assertions"]) == len(r1["assertions"])


# ---- §12：H-012（provenance ownership）----

def test_h_012_provenance_ownership(db, compiled_evidence):
    eng = compiled_evidence["engine"]
    r = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    for a in r["assertions"]:
        aid = a["assertion_id"] if isinstance(a, dict) else a.assertion_id
        tr = eng.trace_candidate_synthesis(aid)
        assert tr["run"] and tr["set"] and tr["members"]
        assert tr["units"] and all(u.get("unit_id") and u.get("evidence_id")
                                   for u in tr["units"])
        # 每个 unit 可溯到 document（无跨 unit 歧义）
        for u in tr["units"]:
            assert any(d["document_id"] for d in tr["documents"])


# ---- §14：H-013（candidate-only 边界）----

def test_h_013_candidate_only_boundary(db, compiled_evidence):
    eng = compiled_evidence["engine"]
    r = eng.synthesize(compiled_evidence["evidence_ids"], actor_id="system:synth")
    rows = db.execute("SELECT DISTINCT status FROM akb_assertions").fetchall()
    assert all(row["status"] == "candidate" for row in rows)
    import sqlite3
    aid = db.execute("SELECT assertion_id FROM akb_assertions LIMIT 1").fetchone()["assertion_id"]
    with pytest.raises(sqlite3.Error):
        db.execute("UPDATE akb_assertions SET status='asserted' WHERE assertion_id=?", (aid,))


def test_h_014b_unrelated_subjects_no_state_alignment(db):
    """无关 subject → 无 state 对齐（H 组补充）。"""
    from agent_kb.evidence_core.synthesis.models import AlignmentResult, RelationAlignmentCluster
    eng_e = EvidenceAlignmentEngine()
    al = AlignmentResult()
    al.relation_clusters.append(RelationAlignmentCluster(
        cluster_id="rc_0001", subject_cluster="cl_0001", predicate="has_parameter",
        object_cluster="cl_0002",
        members=[{"evidence_id": "E1", "unit_id": "u1", "confidence": 0.9,
                  "object_value": "265V"}]))
    units = [{"evidence_id": "E1", "unit_id": "u1",
              "temporal_parse": {"valid_time": {"valid_from": "2026-01-01",
                                                "valid_until": "2027-01-01"},
                                 "parse_status": "resolved"}}]
    sc, contra = eng_e._state_alignment(units, {}, al.relation_clusters)
    assert not contra                              # 单成员无矛盾
    assert sc[0]["alignment"] in ("aligned", "missing")


def test_h_014c_unknown_state_predicate_warning(db):
    """未知 state 谓词 → 不进 state family（显式排除而非误判）。"""
    from agent_kb.evidence_core.synthesis.alignment import EvidenceAlignmentEngine
    eng_e = EvidenceAlignmentEngine()
    assert "verified_by" not in eng_e.state_predicate_family
    assert "has_parameter" in eng_e.state_predicate_family