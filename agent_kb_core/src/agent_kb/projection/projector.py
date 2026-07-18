from __future__ import annotations

from agent_kb.domains.schema import DomainPack
from agent_kb.projection.models import EvidenceRef, ObjectProjection


def build_terminology_projections(domain_pack: DomainPack) -> list[ObjectProjection]:
    """Project domain terminology into stable ontology-lite objects.

    MVP-1 uses domain pack terminology as the seed object registry. Later phases
    can merge evidence-derived candidates into these objects through identity
    resolution.
    """

    projections: list[ObjectProjection] = []
    for canonical_id, aliases in domain_pack.terminology.items():
        projections.append(
            ObjectProjection(
                object_id=canonical_id,
                domain=domain_pack.domain_id,
                object_type=_infer_object_type(canonical_id, domain_pack),
                canonical_name=_canonical_display_name(canonical_id, aliases),
                description="Seed object projected from domain terminology.",
                aliases=list(aliases),
                properties={
                    "source": "domain_pack.terminology",
                    "canonical_id": canonical_id,
                },
                evidence_refs=[],
                confidence=1.0,
                status="active",
            )
        )
    return projections


def project_evidence_candidate(
    *,
    domain_pack: DomainPack,
    object_id: str,
    object_type: str,
    canonical_name: str,
    evidence_id: str,
    document_id: str | None = None,
    page_no: int | None = None,
    properties: dict[str, object] | None = None,
    aliases: list[str] | None = None,
    confidence: float = 0.7,
) -> ObjectProjection:
    """Create an object projection from one extracted candidate.

    This function is intentionally generic: it does not know requirements,
    standards, OBC/DCDC, legal, finance, or any other concrete domain.
    """

    return ObjectProjection(
        object_id=object_id,
        domain=domain_pack.domain_id,
        object_type=object_type,
        canonical_name=canonical_name,
        description="Candidate projected from evidence.",
        aliases=list(aliases or []),
        properties=dict(properties or {}),
        evidence_refs=[
            EvidenceRef(
                evidence_id=evidence_id,
                document_id=document_id,
                page_no=page_no,
                support_type="derived_from",
                confidence=confidence,
            )
        ],
        confidence=confidence,
        status="candidate",
    )


def merge_projection_aliases(projections: list[ObjectProjection]) -> dict[str, list[str]]:
    """Build object_id -> aliases index for retrieval and query linking."""

    result: dict[str, list[str]] = {}
    for projection in projections:
        aliases = result.setdefault(projection.object_id, [])
        for value in [projection.canonical_name, *projection.aliases, projection.object_id]:
            text = str(value or "").strip()
            if text and text not in aliases:
                aliases.append(text)
    return result


def _infer_object_type(canonical_id: str, domain_pack: DomainPack) -> str:
    if "Parameter" in domain_pack.object_types:
        return "Parameter"
    if domain_pack.object_types:
        return next(iter(domain_pack.object_types))
    return "Concept"


def _canonical_display_name(canonical_id: str, aliases: list[str]) -> str:
    for alias in aliases:
        if any("\u4e00" <= char <= "\u9fff" for char in alias):
            return alias
    return aliases[0] if aliases else canonical_id
