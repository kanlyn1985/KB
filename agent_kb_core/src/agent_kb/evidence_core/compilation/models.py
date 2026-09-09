# -*- coding: utf-8 -*-
"""V0.2 编译期模型（V0.2_DATA_FLOW §2 层间契约；与 V0.1 models 风格一致）。

红线：Evidence immutable；SemanticUnit/candidates 全部为候选语义（非 authoritative）。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


def canonical_json(value) -> str:
    """CanonicalJSON（V0.1 同款约定：sort_keys + ensure_ascii=False + 紧凑分隔符）。"""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass
class TextSegment:
    segment_id: str
    span_start: int
    span_end: int
    text: str
    block_type: str = "text"


@dataclass
class NormalizedSegment:
    segment_id: str
    normalized_text: str
    normalizer_version: str
    rules_applied: list = field(default_factory=list)


@dataclass
class RawExtraction:
    """Provider 唯一出口（Schema validation 后才可进入 resolver 层）。"""
    entities_raw: list = field(default_factory=list)
    relations_raw: list = field(default_factory=list)
    temporal_expressions: list = field(default_factory=list)

    def validate(self) -> list[str]:
        v = []
        if not isinstance(self.entities_raw, list) or not isinstance(
                self.relations_raw, list) or not isinstance(self.temporal_expressions, list):
            v.append("structure must be lists")
        for e in self.entities_raw:
            if not isinstance(e, dict) or not e.get("surface_form") or "confidence" not in e:
                v.append(f"invalid entity record: {e!r}")
            elif not 0.0 <= float(e["confidence"]) <= 1.0:
                v.append(f"confidence out of range: {e.get('confidence')}")
        for r in self.relations_raw:
            if not isinstance(r, dict) or not r.get("subject_surface") or \
                    not r.get("predicate") or not r.get("object_surface"):
                v.append(f"invalid relation record: {r!r}")
            elif not 0.0 <= float(r.get("confidence", -1)) <= 1.0:
                v.append(f"relation confidence out of range: {r.get('confidence')}")
        return v


@dataclass
class EntityCandidate:
    candidate_id: str          # 'ec_0001'（run 内稳定序号）
    surface_form: str
    normalized_form: str
    entity_type: str = "unknown"
    confidence: float = 0.0
    source_span: tuple = ()
    ontology_hint: str | None = None

    def sort_key(self):
        return (self.source_span[0] if self.source_span else 0,
                self.normalized_form, self.candidate_id)


@dataclass
class RelationCandidate:
    relation_candidate_id: str  # 'rc_0001'
    subject_candidate_id: str
    predicate_candidate: str
    object_candidate_id: str
    confidence: float = 0.0
    source_span: tuple = ()
    ontology_hint: str | None = None

    def sort_key(self):
        return (self.subject_candidate_id, self.predicate_candidate,
                self.object_candidate_id, self.relation_candidate_id)


@dataclass
class TemporalParse:
    event_time: str | None = None
    valid_time: dict | None = None          # {valid_from?, valid_until?}
    observation_time: str | None = None
    document_effective_time: str | None = None
    ingestion_time: str | None = None
    conditions: list = field(default_factory=list)
    parse_status: str = "resolved"          # resolved/unresolved/failed
    raw_expressions: list = field(default_factory=list)


@dataclass
class OntologyMapping:
    concept_surface: str
    ontology_ref: str | None = None
    mapping_status: str = "candidate"       # candidate/quarantined
    confidence: float = 0.0


@dataclass
class SemanticUnitRecord:
    """akb_semantic_units 行域对象（V0.1 SemanticUnitRecord 的 V0.2 扩展）。"""
    unit_id: str
    evidence_id: str
    unit_type: str
    normalized_text: str
    entity_candidates: list = field(default_factory=list)
    relation_candidates: list = field(default_factory=list)
    temporal_parse: dict | None = None
    ontology_mapping: dict | None = None
    extraction_method: str = ""
    extraction_version: str = ""
    provenance_ref: str | None = None
    compiler_run_ref: str | None = None
    configuration_hash: str = ""
    content_fingerprint: str | None = None
    created_at: str | None = None

    def to_row(self) -> dict:
        return {
            "unit_id": self.unit_id, "evidence_id": self.evidence_id,
            "unit_type": self.unit_type, "normalized_text": self.normalized_text,
            "entity_candidates_json": canonical_json(self.entity_candidates),
            "relation_candidates_json": canonical_json(self.relation_candidates),
            "temporal_parse_json": canonical_json(self.temporal_parse)
            if self.temporal_parse is not None else None,
            "ontology_mapping_json": canonical_json(self.ontology_mapping)
            if self.ontology_mapping is not None else None,
            "extraction_method": self.extraction_method,
            "extraction_version": self.extraction_version,
            "provenance_ref": self.provenance_ref,
            "compiler_run_ref": self.compiler_run_ref,
            "configuration_hash": self.configuration_hash,
            "content_fingerprint": self.content_fingerprint,
        }


@dataclass
class CompilationRunRecord:
    """akb_compilation_runs 行域对象（run 级聚合审计实体）。"""
    run_id: str
    evidence_ids: list
    compiler_version: str
    configuration_hash: str
    ontology_version: str | None
    provider_id: str
    actor_id: str
    policy_version: str
    status: str = "running"                 # running/completed/failed/partial
    warnings: list = field(default_factory=list)
    created_at: str | None = None
    finished_at: str | None = None

    def to_row(self) -> dict:
        return {
            "run_id": self.run_id,
            "evidence_ids_json": canonical_json(self.evidence_ids),
            "compiler_version": self.compiler_version,
            "configuration_hash": self.configuration_hash,
            "ontology_version": self.ontology_version,
            "provider_id": self.provider_id,
            "actor_id": self.actor_id,
            "policy_version": self.policy_version,
            "status": self.status,
            "warnings_json": canonical_json(self.warnings),
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


@dataclass
class CompilationResult:
    run: CompilationRunRecord
    units: list = field(default_factory=list)          # list[SemanticUnitRecord]
    assertions: list = field(default_factory=list)     # list[KnowledgeAssertion]
    warnings: list = field(default_factory=list)
    fingerprint: str | None = None
    idempotent_hit: bool = False