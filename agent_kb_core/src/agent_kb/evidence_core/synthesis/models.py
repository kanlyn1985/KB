# -*- coding: utf-8 -*-
"""V0.3 合成期模型（derived runtime 结构；canonical 持久化仅 Set/Run）。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


def canonical_json(value) -> str:
    """CanonicalJSON（V0.1 同款约定）。"""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass
class EntityAlignmentCluster:
    cluster_id: str                       # cl_0001（按最小 (evidence_id, candidate_id) 稳定编号）
    members: list = field(default_factory=list)   # [{evidence_id, candidate_id, normalized_form, ontology_ref}]
    representative: str = ""              # 簇代表 normalized_form


@dataclass
class RelationAlignmentCluster:
    cluster_id: str
    subject_cluster: str
    predicate: str
    object_cluster: str
    members: list = field(default_factory=list)   # [{evidence_id, unit_id, confidence, object_value}]


@dataclass
class ConflictRecord:
    conflict_type: str                    # 7 类
    source_evidence_ids: list = field(default_factory=list)
    unit_ids: list = field(default_factory=list)
    conflicting_fields: list = field(default_factory=list)
    detection_method: str = ""            # 规则号
    confidence: float = 0.0
    provenance_ref: str | None = None
    provider_id: str | None = None
    sides: list = field(default_factory=list)     # 各方完整记录（永不丢弃）
    audit_timestamp: str | None = None


@dataclass
class ConflictSet:
    conflicts: list = field(default_factory=list)
    capped: bool = False
    unresolved_count: int = 0


@dataclass
class SourceWeight:
    evidence_id: str
    authority: float = 0.0
    reliability: float = 0.5
    recency: float = 0.5
    document_version: float = 0.5
    evidence_quality: float = 0.5
    corroboration: float = 0.0
    weight: float = 0.0                   # Σ(维度×权重策略)，round 4


@dataclass
class AlignmentResult:
    entity_clusters: list = field(default_factory=list)
    relation_clusters: list = field(default_factory=list)
    event_clusters: list = field(default_factory=list)
    state_clusters: list = field(default_factory=list)
    temporal_alignment: dict | None = None
    compatibility: dict = field(default_factory=dict)   # evidence_id → 五级
    rule_audit: list = field(default_factory=list)      # [{rule_id, inputs, result}]
    warnings: list = field(default_factory=list)


@dataclass
class SynthesisRunRecord:
    run_id: str
    set_id: str
    members: list
    synthesis_version: str
    configuration_hash: str
    provider_id: str
    actor_id: str
    policy_version: str
    status: str = "running"               # running/completed/failed/partial/capped
    alignment: dict | None = None
    conflicts: dict | None = None
    weights: list = field(default_factory=list)
    fingerprint: str | None = None
    warnings: list = field(default_factory=list)
    created_at: str | None = None
    finished_at: str | None = None

    def to_row(self) -> dict:
        return {
            "run_id": self.run_id, "set_id": self.set_id,
            "members_json": canonical_json(self.members),
            "synthesis_version": self.synthesis_version,
            "configuration_hash": self.configuration_hash,
            "provider_id": self.provider_id, "actor_id": self.actor_id,
            "policy_version": self.policy_version, "status": self.status,
            "alignment_json": canonical_json(self.alignment) if self.alignment is not None else None,
            "conflicts_json": canonical_json(self.conflicts) if self.conflicts is not None else None,
            "weights_json": canonical_json(self.weights),
            "fingerprint": self.fingerprint,
            "warnings_json": canonical_json(self.warnings),
            "created_at": self.created_at, "finished_at": self.finished_at,
        }