# -*- coding: utf-8 -*-
"""V0.1 Canonical 模型层：DB Row ↔ Domain Object ↔ Canonical JSON 零损往返。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _uj(text: str | None, default: Any) -> Any:
    return json.loads(text) if text else default


@dataclass
class Source:
    source_id: str
    source_type: str  # document/database/api/sensor/human/agent/system
    name: str
    authority_score: float | None = None
    owner: str | None = None
    access_policy_ref: str | None = None
    metadata: dict = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    def to_row(self) -> dict:
        d = asdict(self)
        d["metadata_json"] = _j(self.metadata)
        return d

    @classmethod
    def from_row(cls, row) -> "Source":
        return cls(
            source_id=row["source_id"], source_type=row["source_type"], name=row["name"],
            authority_score=row["authority_score"], owner=row["owner"],
            access_policy_ref=row["access_policy_ref"],
            metadata=_uj(row["metadata_json"], {}), created_at=row["created_at"],
            updated_at=row["updated_at"])


@dataclass
class Document:
    document_id: str
    source_id: str
    version: str
    content_hash: str  # 'sha256:<hex>'
    mime_type: str | None = None
    title: str | None = None
    effective_at: str | None = None
    ingested_at: str | None = None
    metadata: dict = field(default_factory=dict)
    created_at: str | None = None

    def to_row(self) -> dict:
        d = asdict(self)
        d["metadata_json"] = _j(self.metadata)
        return d

    @classmethod
    def from_row(cls, row) -> "Document":
        return cls(
            document_id=row["document_id"], source_id=row["source_id"],
            version=row["version"], content_hash=row["content_hash"],
            mime_type=row["mime_type"], title=row["title"],
            effective_at=row["effective_at"], ingested_at=row["ingested_at"],
            metadata=_uj(row["metadata_json"], {}), created_at=row["created_at"])


@dataclass
class Evidence:
    evidence_id: str
    document_id: str
    content: str
    evidence_type: str = "text"
    location: dict = field(default_factory=dict)  # {page?,section?,start?,end?}
    observed_at: str | None = None
    extraction_method: str = ""
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)
    content_hash: str = ""
    created_at: str | None = None

    def to_row(self) -> dict:
        loc = self.location or {}
        return {
            "evidence_id": self.evidence_id, "document_id": self.document_id,
            "location_page": loc.get("page"), "location_section": loc.get("section"),
            "location_start": loc.get("start"), "location_end": loc.get("end"),
            "content": self.content, "evidence_type": self.evidence_type,
            "observed_at": self.observed_at, "extraction_method": self.extraction_method,
            "confidence": self.confidence, "metadata_json": _j(self.metadata),
            "content_hash": self.content_hash, "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row) -> "Evidence":
        return cls(
            evidence_id=row["evidence_id"], document_id=row["document_id"],
            content=row["content"], evidence_type=row["evidence_type"],
            location={k: row[f"location_{k}"] for k in ("page", "section", "start", "end")
                      if row[f"location_{k}"] is not None},
            observed_at=row["observed_at"], extraction_method=row["extraction_method"],
            confidence=row["confidence"], metadata=_uj(row["metadata_json"], {}),
            content_hash=row["content_hash"], created_at=row["created_at"])


@dataclass
class SemanticUnit:
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
    created_at: str | None = None

    def to_row(self) -> dict:
        return {
            "unit_id": self.unit_id, "evidence_id": self.evidence_id,
            "unit_type": self.unit_type, "normalized_text": self.normalized_text,
            "entity_candidates_json": _j(self.entity_candidates),
            "relation_candidates_json": _j(self.relation_candidates),
            "temporal_parse_json": _j(self.temporal_parse) if self.temporal_parse is not None else None,
            "ontology_mapping_json": _j(self.ontology_mapping) if self.ontology_mapping is not None else None,
            "extraction_method": self.extraction_method,
            "extraction_version": self.extraction_version, "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row) -> "SemanticUnit":
        return cls(
            unit_id=row["unit_id"], evidence_id=row["evidence_id"],
            unit_type=row["unit_type"], normalized_text=row["normalized_text"],
            entity_candidates=_uj(row["entity_candidates_json"], []),
            relation_candidates=_uj(row["relation_candidates_json"], []),
            temporal_parse=_uj(row["temporal_parse_json"], None),
            ontology_mapping=_uj(row["ontology_mapping_json"], None),
            extraction_method=row["extraction_method"],
            extraction_version=row["extraction_version"], created_at=row["created_at"])


@dataclass
class KnowledgeAssertion:
    """Canonical Knowledge Unit（DM-005 / ADR-001）。"""

    assertion_id: str
    subject_ref: str
    predicate_ref: str
    object: dict  # {kind: literal|entity_ref, value?, datatype?, unit?, entity_id?}
    assertion_type: str  # extracted/observed/asserted/inferred/hypothesized
    status: str  # candidate/validated/asserted/disputed/rejected/deprecated
    confidence: float | None = None
    evidence_refs: list = field(default_factory=list)
    source_unit_refs: list = field(default_factory=list)
    provenance_ref: str | None = None
    temporal_scope: dict | None = None  # {valid_from?,valid_until?,observed_at?}
    ontology_scope: str = ""
    derivation: dict | None = None  # inferred 必填 {rule_ref,rule_version?,parent_assertions,reasoner_id,reasoner_version?}
    created_at: str | None = None
    updated_at: str | None = None

    def to_row(self) -> dict:
        o = self.object or {}
        return {
            "assertion_id": self.assertion_id, "subject_ref": self.subject_ref,
            "predicate_ref": self.predicate_ref, "object_kind": o.get("kind"),
            "object_value": None if o.get("kind") == "entity_ref" else str(o.get("value")),
            "object_datatype": o.get("datatype"), "object_unit": o.get("unit"),
            "object_entity_ref": o.get("entity_id"),
            "assertion_type": self.assertion_type, "status": self.status,
            "confidence": self.confidence,
            "evidence_refs_json": _j(self.evidence_refs),
            "source_unit_refs_json": _j(self.source_unit_refs),
            "provenance_ref": self.provenance_ref,
            "temporal_scope_json": _j(self.temporal_scope) if self.temporal_scope is not None else None,
            "ontology_scope": self.ontology_scope,
            "derivation_json": _j(self.derivation) if self.derivation is not None else None,
            "canonical_json": _j(self.canonical()),
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    def canonical(self) -> dict:
        """DM-005 完整对象（canonical_json 保真层）。"""
        d = asdict(self)
        d.pop("created_at", None)
        d.pop("updated_at", None)
        return d

    def to_canonical_json(self) -> str:
        return _j(self.canonical())

    @classmethod
    def from_row(cls, row) -> "KnowledgeAssertion":
        return cls(
            assertion_id=row["assertion_id"], subject_ref=row["subject_ref"],
            predicate_ref=row["predicate_ref"],
            object={"kind": row["object_kind"],
                    **({"value": row["object_value"], "datatype": row["object_datatype"],
                        "unit": row["object_unit"]} if row["object_kind"] == "literal" else
                       {"entity_id": row["object_entity_ref"]})},
            assertion_type=row["assertion_type"], status=row["status"],
            confidence=row["confidence"],
            evidence_refs=_uj(row["evidence_refs_json"], []),
            source_unit_refs=_uj(row["source_unit_refs_json"], []),
            provenance_ref=row["provenance_ref"],
            temporal_scope=_uj(row["temporal_scope_json"], None),
            ontology_scope=row["ontology_scope"],
            derivation=_uj(row["derivation_json"], None),
            created_at=row["created_at"], updated_at=row["updated_at"])

    @classmethod
    def from_canonical_json(cls, text: str) -> "KnowledgeAssertion":
        d = json.loads(text)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AssertionTransition:
    transition_id: str
    assertion_id: str
    previous_status: str
    new_status: str
    actor_id: str
    reason: str
    policy_version: str
    provenance_ref: str | None = None
    created_at: str | None = None

    def to_row(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row) -> "AssertionTransition":
        return cls(**{k: row[k] for k in (
            "transition_id", "assertion_id", "previous_status", "new_status",
            "actor_id", "reason", "policy_version", "provenance_ref", "created_at")})


@dataclass
class ProvenanceRecord:
    provenance_id: str
    actor_id: str
    actor_kind: str  # human/system/agent/llm
    activity: str  # import/extract/validate/promote/reason/project/migrate/dedupe
    policy_version: str
    occurred_at: str
    inputs: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str | None = None

    def to_row(self) -> dict:
        d = asdict(self)
        d["inputs_json"] = _j(self.inputs)
        d["metadata_json"] = _j(self.metadata)
        return d

    @classmethod
    def from_row(cls, row) -> "ProvenanceRecord":
        return cls(
            provenance_id=row["provenance_id"], actor_id=row["actor_id"],
            actor_kind=row["actor_kind"], activity=row["activity"],
            policy_version=row["policy_version"], occurred_at=row["occurred_at"],
            inputs=_uj(row["inputs_json"], []), metadata=_uj(row["metadata_json"], {}),
            created_at=row["created_at"])