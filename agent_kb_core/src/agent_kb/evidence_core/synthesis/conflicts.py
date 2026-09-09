# -*- coding: utf-8 -*-
"""ConflictDetector（7 类；capped 语义；零静默丢弃）。

## Conflict Provenance Contract（AKB-V03-IMPL-003 定案）

全部 ConflictRecord 字段从拥有该语义的原始对象生成：

- source_evidence_ids ← members 的 evidence_id（Evidence 层身份）
- unit_ids            ← members 的 unit_id（SemanticUnit 层身份）
- candidate_id        → 只允许出现在 sides/member detail（细粒度 provenance），
                        **禁止冒充 unit_ids**
- detection_method    ← 每类冲突的稳定规则编号（CONF-001..006 + 006-STATE）
- audit_timestamp     ← detect(audit_ts=...) 调用参数（不入语义/指纹）
- provider_id         ← 参与 provider（builtin 为 None）

统一经 _provenance_from_members() 生成——禁止复制粘贴式手工构造导致字段错位。
"""
from __future__ import annotations

from agent_kb.evidence_core.synthesis.models import ConflictRecord, ConflictSet

MAX_CONFLICTS = 128


def _provenance_from_members(members: list[dict]) -> tuple[list[str], list[str]]:
    """(source_evidence_ids, unit_ids)——显式按语义字段生成，防字段错位。"""
    return (sorted({m["evidence_id"] for m in members if m.get("evidence_id")}),
            sorted({m["unit_id"] for m in members if m.get("unit_id")}))


class ConflictDetector:
    def __init__(self, max_conflicts: int = MAX_CONFLICTS, provider_id: str | None = None):
        self.max_conflicts = max_conflicts
        self.provider_id = provider_id

    def detect(self, alignment, units: list[dict], audit_ts: str | None = None) -> ConflictSet:
        cs = ConflictSet()
        # unit 语义索引（显式 evidence_id → unit_id 集合；单位所有权来自 SemanticUnit 行）
        units_of: dict[str, set] = {}
        for u in units:
            units_of.setdefault(u["evidence_id"], set()).add(u["unit_id"])
        # 1) VALUE_CONFLICT（CONF-001）：同 relation 簇内 object_value 不同
        for rc in alignment.relation_clusters:
            values = {}
            for m in rc.members:
                v = m.get("object_value")
                if v is not None:
                    values.setdefault(str(v), []).append(m)
            if len(values) > 1:
                sides = [{"value": v, "members": ms} for v, ms in sorted(values.items())]
                ev_ids, u_ids = _provenance_from_members(rc.members)
                cs.conflicts.append(ConflictRecord(
                    conflict_type="VALUE_CONFLICT",
                    source_evidence_ids=ev_ids, unit_ids=u_ids,
                    conflicting_fields=["object_value"],
                    detection_method="CONF-001",
                    confidence=0.9, provider_id=self.provider_id,
                    sides=sides, audit_timestamp=audit_ts))
        # 2) ONTOLOGY_CONFLICT（CONF-002）：同实体簇内不同 ontology_ref
        for ec in alignment.entity_clusters:
            refs = {}
            for m in ec.members:
                if m.get("ontology_ref"):
                    refs.setdefault(m["ontology_ref"], []).append(m)
            if len(refs) > 1:
                all_members = [m for ms in refs.values() for m in ms]
                ev_ids, u_ids = _provenance_from_members(all_members)
                cs.conflicts.append(ConflictRecord(
                    conflict_type="ONTOLOGY_CONFLICT",
                    source_evidence_ids=ev_ids, unit_ids=u_ids,
                    conflicting_fields=["ontology_ref"],
                    detection_method="CONF-002", confidence=0.85,
                    provider_id=self.provider_id,
                    sides=[{"ontology_ref": r, "members": ms} for r, ms in sorted(refs.items())],
                    audit_timestamp=audit_ts))
        # 3) TEMPORAL_CONFLICT（CONF-003）——scope = 真实矛盾双方（V03-IMPL-004 修复：
        #    原 scope=全部 units 夹带无关成员）。sides 保留 evidence_id/unit_id/valid_from/
        #    valid_until（§12：不只 aggregate）。
        ta = alignment.temporal_alignment or {}
        c_members = ta.get("contradiction_members") or []
        if c_members:
            ev_ids, u_ids = _provenance_from_members(c_members)
            sides = []
            for m in c_members:
                key = (m["evidence_id"], m.get("unit_id"))
                if key not in {(s["evidence_id"], s.get("unit_id")) for s in sides}:
                    sides.append({"evidence_id": m["evidence_id"],
                                  "unit_id": m.get("unit_id"),
                                  "valid_from": m.get("valid_from"),
                                  "valid_until": m.get("valid_until")})
            cs.conflicts.append(ConflictRecord(
                conflict_type="TEMPORAL_CONFLICT",
                source_evidence_ids=ev_ids, unit_ids=u_ids,
                conflicting_fields=["valid_time"], detection_method="CONF-003",
                confidence=0.8, provider_id=self.provider_id,
                sides=sides, audit_timestamp=audit_ts))
        # 4) SOURCE_CONFLICT（CONF-004）：同事实簇内多 source_type 互斥
        cluster_members = [m for rcl in alignment.relation_clusters for m in rcl.members]
        stypes = {}
        stype_of = {u["evidence_id"]: (u.get("source_type") or "unknown") for u in units}
        for m in cluster_members:
            stypes.setdefault(stype_of.get(m["evidence_id"], "unknown"), []).append(m)
        if len(stypes) > 1:
            all_members = [m for ms in stypes.values() for m in ms]
            ev_ids, u_ids = _provenance_from_members(all_members)
            cs.conflicts.append(ConflictRecord(
                conflict_type="SOURCE_CONFLICT",
                source_evidence_ids=ev_ids, unit_ids=u_ids,
                conflicting_fields=["source_type"], detection_method="CONF-004",
                confidence=0.7, provider_id=self.provider_id,
                sides=[{"source_type": st,
                        "members": sorted(ms, key=lambda m: m["evidence_id"])}
                       for st, ms in sorted(stypes.items())],
                audit_timestamp=audit_ts))
        # 5) IDENTITY_CONFLICT（CONF-005）：同簇内 entity_type 分歧（confidence>0.7）
        for ec in alignment.entity_clusters:
            types = {}
            for m in ec.members:
                if m.get("entity_type") and float(m.get("confidence") or 0) > 0.7:
                    types.setdefault(m["entity_type"], []).append(m)
            if len(types) > 1:
                all_members = [m for ms in types.values() for m in ms]
                ev_ids, u_ids = _provenance_from_members(all_members)
                cs.conflicts.append(ConflictRecord(
                    conflict_type="IDENTITY_CONFLICT",
                    source_evidence_ids=ev_ids, unit_ids=u_ids,
                    conflicting_fields=["entity_type"], detection_method="CONF-005",
                    confidence=0.75, provider_id=self.provider_id,
                    sides=[{"entity_type": t, "members": ms} for t, ms in sorted(types.items())],
                    audit_timestamp=audit_ts))
        # 6) STATE_CONFLICT（CONF-006-STATE）：直接消费 state contradiction 自带 provenance
        #    （Defect §6：不经 relation cluster 间接反推）
        for st in getattr(alignment, "state_contradictions", []) or []:
            st_members = st.get("members") or st.get("sides") or []
            if st_members and "unit_id" not in st_members[0]:
                # 旧结构 sides 无 unit_id——由 cluster members 补（contradiction 自带优先）
                st = dict(st)
                by_eid = {m["evidence_id"]: m for m in
                          next((c["members"] for c in
                                [dict(x) for x in alignment.state_clusters or []]
                                if c.get("cluster_id") == st.get("cluster_id")), [])}
                for s in st["sides"]:
                    if not s.get("unit_id") and s.get("evidence_id") in by_eid:
                        s["unit_id"] = by_eid[s["evidence_id"]]["unit_id"]
            ev_ids, u_ids = _provenance_from_members(
                [{"evidence_id": s.get("evidence_id"), "unit_id": s.get("unit_id")}
                 for s in st["sides"]])
            cs.conflicts.append(ConflictRecord(
                conflict_type="STATE_CONFLICT",
                source_evidence_ids=ev_ids, unit_ids=u_ids,
                conflicting_fields=["valid_time", "object_value"],
                detection_method="CONF-006-STATE",
                confidence=0.85, provider_id=self.provider_id,
                sides=st["sides"], audit_timestamp=audit_ts))
        # 7) RELATION_CONFLICT（CONF-007-RELATION）：谓词互斥对
        #    规则编号定案：STATE=CONF-006-STATE，RELATION=CONF-007-RELATION
        #    （原 CONF-006 与 STATE 后缀语义易混——本轮起稳定编号，兼容旧 CONF-006 值读取方
        #    由 detection_method 前缀 CONF-006* 判断的调用方不受影响）
        rel_pairs: dict[tuple, set] = {}
        for rc in alignment.relation_clusters:
            key = (rc.subject_cluster, rc.object_cluster)
            rel_pairs.setdefault(key, set()).add(rc.predicate)
        for key, preds in sorted(rel_pairs.items()):
            if {"has_parameter", "constrained_by"} <= preds:
                members = [m for rcl in alignment.relation_clusters
                           for m in rcl.members
                           if (rcl.subject_cluster, rcl.object_cluster) == key]
                ev_ids, u_ids = _provenance_from_members(members)
                cs.conflicts.append(ConflictRecord(
                    conflict_type="RELATION_CONFLICT",
                    source_evidence_ids=ev_ids, unit_ids=u_ids,
                    conflicting_fields=["predicate"], detection_method="CONF-007-RELATION",
                    confidence=0.7, provider_id=self.provider_id,
                    sides=[{"predicates": sorted(preds)}], audit_timestamp=audit_ts))
        cs.unresolved_count = len(cs.conflicts)
        if len(cs.conflicts) > self.max_conflicts:
            cs.capped = True
            cs.conflicts = cs.conflicts[:self.max_conflicts]
        return cs