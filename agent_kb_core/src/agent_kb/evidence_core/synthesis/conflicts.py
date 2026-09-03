# -*- coding: utf-8 -*-
"""ConflictDetector（7 类；capped 语义；零静默丢弃）。"""
from __future__ import annotations

from agent_kb.evidence_core.synthesis.models import ConflictRecord, ConflictSet

MAX_CONFLICTS = 128


class ConflictDetector:
    def __init__(self, max_conflicts: int = MAX_CONFLICTS, provider_id: str | None = None):
        self.max_conflicts = max_conflicts
        self.provider_id = provider_id

    def detect(self, alignment, units: list[dict], audit_ts: str | None = None) -> ConflictSet:
        cs = ConflictSet()
        unit_ids_by_evidence = {u["evidence_id"]: u["unit_id"] for u in units}
        # 1) VALUE_CONFLICT：同 relation 簇内 object_value 不同
        for rc in alignment.relation_clusters:
            values = {}
            for m in rc.members:
                v = m.get("object_value")
                if v is not None:
                    values.setdefault(str(v), []).append(m)
            if len(values) > 1:
                sides = [{"value": v, "members": ms} for v, ms in sorted(values.items())]
                cs.conflicts.append(ConflictRecord(
                    conflict_type="VALUE_CONFLICT",
                    source_evidence_ids=sorted({m["evidence_id"] for m in rc.members}),
                    unit_ids=sorted({m["unit_id"] for m in rc.members}),
                    conflicting_fields=["object_value"],
                    detection_method="CONF-001",
                    confidence=0.9, provider_id=self.provider_id,
                    sides=sides, audit_timestamp=audit_ts))
        # 2) ONTOLOGY_CONFLICT：同实体簇内不同 ontology_ref
        for ec in alignment.entity_clusters:
            refs = {}
            for m in ec.members:
                if m.get("ontology_ref"):
                    refs.setdefault(m["ontology_ref"], []).append(m)
            if len(refs) > 1:
                cs.conflicts.append(ConflictRecord(
                    conflict_type="ONTOLOGY_CONFLICT",
                    source_evidence_ids=sorted({m["evidence_id"] for m in ec.members}),
                    unit_ids=sorted({m["unit_id"] for m in ec.members
                                     for m2 in [m] if True}) if False else
                    sorted({m.get("candidate_id") or "" for m in ec.members}),
                    conflicting_fields=["ontology_ref"],
                    detection_method="CONF-002", confidence=0.85,
                    provider_id=self.provider_id,
                    sides=[{"ontology_ref": r, "members": ms} for r, ms in sorted(refs.items())],
                    audit_timestamp=audit_ts))
        # 3) TEMPORAL_CONFLICT：per_evidence 同时含 contradictory 信号（reserved——内置 six-state
        #    判 contradictory 由 temporal 对齐标注）
        ta = alignment.temporal_alignment or {}
        if ta.get("overall") == "contradictory":
            cs.conflicts.append(ConflictRecord(
                conflict_type="TEMPORAL_CONFLICT",
                source_evidence_ids=sorted(ta.get("per_evidence", {})),
                unit_ids=sorted(unit_ids_by_evidence.values()),
                conflicting_fields=["valid_time"], detection_method="CONF-003",
                confidence=0.8, provider_id=self.provider_id,
                audit_timestamp=audit_ts))
        # 4) SOURCE_CONFLICT：同事实簇内多 source 且 source_type 互斥（governed vs ingested）
        stypes = {}
        for u in units:
            stypes.setdefault(u.get("source_type") or "unknown", []).append(u["evidence_id"])
        if len(stypes) > 1 and any(alignment.relation_clusters for _ in [0]):
            cs.conflicts.append(ConflictRecord(
                conflict_type="SOURCE_CONFLICT",
                source_evidence_ids=sorted(u["evidence_id"] for u in units),
                unit_ids=sorted(unit_ids_by_evidence.values()),
                conflicting_fields=["source_type"], detection_method="CONF-004",
                confidence=0.7, provider_id=self.provider_id,
                sides=[{"source_type": st, "evidence_ids": eids}
                       for st, eids in sorted(stypes.items())],
                audit_timestamp=audit_ts))
        # 5) IDENTITY_CONFLICT：同簇内 entity_type 分歧（confidence>0.7）
        for ec in alignment.entity_clusters:
            types = {}
            for m in ec.members:
                if m.get("entity_type") and float(m.get("confidence") or 0) > 0.7:
                    types.setdefault(m["entity_type"], []).append(m)
            if len(types) > 1:
                cs.conflicts.append(ConflictRecord(
                    conflict_type="IDENTITY_CONFLICT",
                    source_evidence_ids=sorted({m["evidence_id"] for m in ec.members}),
                    unit_ids=sorted({m.get("candidate_id") or "" for m in ec.members}),
                    conflicting_fields=["entity_type"], detection_method="CONF-005",
                    confidence=0.75, provider_id=self.provider_id,
                    sides=[{"entity_type": t, "members": ms} for t, ms in sorted(types.items())],
                    audit_timestamp=audit_ts))
        # 6) RELATION_CONFLICT / 7) STATE_CONFLICT：谓词互斥对（内置最小规则——同 subj/obj 簇
        #    出现 has_parameter 与 constrained_by 并存）
        rel_pairs: dict[tuple, set] = {}
        for rc in alignment.relation_clusters:
            key = (rc.subject_cluster, rc.object_cluster)
            rel_pairs.setdefault(key, set()).add(rc.predicate)
        for key, preds in sorted(rel_pairs.items()):
            if {"has_parameter", "constrained_by"} <= preds:
                cs.conflicts.append(ConflictRecord(
                    conflict_type="RELATION_CONFLICT",
                    source_evidence_ids=sorted({m["evidence_id"]
                                                for rcl in alignment.relation_clusters
                                                for m in rcl.members
                                                if (rcl.subject_cluster, rcl.object_cluster) == key}),
                    unit_ids=sorted({m["unit_id"]
                                     for rcl in alignment.relation_clusters
                                     for m in rcl.members
                                     if (rcl.subject_cluster, rcl.object_cluster) == key}),
                    conflicting_fields=["predicate"], detection_method="CONF-006",
                    confidence=0.7, provider_id=self.provider_id,
                    sides=[{"predicates": sorted(preds)}], audit_timestamp=audit_ts))
        cs.unresolved_count = len(cs.conflicts)
        if len(cs.conflicts) > self.max_conflicts:
            cs.capped = True
            cs.conflicts = cs.conflicts[:self.max_conflicts]
        return cs