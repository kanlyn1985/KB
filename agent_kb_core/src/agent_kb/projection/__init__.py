"""Ontology-lite object projection."""

from .models import EvidenceRef, ObjectProjection, ObjectRelation
from .projector import build_terminology_projections, merge_projection_aliases, project_evidence_candidate

__all__ = [
    "EvidenceRef",
    "ObjectProjection",
    "ObjectRelation",
    "build_terminology_projections",
    "merge_projection_aliases",
    "project_evidence_candidate",
]
