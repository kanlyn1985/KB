# -*- coding: utf-8 -*-
"""AKB V0.1 Evidence Core（Canonical Knowledge 层）。

设计基线：docs/architecture/detailed-design/v0.1-evidence-core/
治理语义：INV-001..010（docs/architecture/INVARIANT_REGISTRY_V1.0.md）
"""
from agent_kb.evidence_core.models import (
    Document,
    Evidence,
    KnowledgeAssertion,
    ProvenanceRecord,
    SemanticUnit,
    Source,
    AssertionTransition,
)
from agent_kb.evidence_core.ids import mint_id
from agent_kb.evidence_core.store import EvidenceStore, LegacyEvidenceResolver
from agent_kb.evidence_core.assertions import (
    AssertionStore,
    AssertionValidator,
    Provenance,
)
from agent_kb.evidence_core.graph import GraphProjection, ProjectionError
from agent_kb.evidence_core import state_machine

__all__ = [
    "Source", "Document", "Evidence", "SemanticUnit",
    "KnowledgeAssertion", "AssertionTransition", "ProvenanceRecord",
    "mint_id", "EvidenceStore", "LegacyEvidenceResolver",
    "AssertionStore", "AssertionValidator", "Provenance",
    "GraphProjection", "ProjectionError", "state_machine",
]