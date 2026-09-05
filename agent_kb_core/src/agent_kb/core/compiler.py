from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_kb.domains.schema import DomainPack

from .documents import DocumentRecord, register_text_document
from .evidence import EvidenceBlock, build_evidence_blocks
from .facts import Fact, extract_facts
from .source_units import SourceUnit, build_source_units


@dataclass(frozen=True)
class KnowledgeCompilation:
    """Result of a generic document compilation run."""

    document: DocumentRecord
    evidence_blocks: list[EvidenceBlock]
    source_units: list[SourceUnit]
    facts: list[Fact]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": self.document.to_dict(),
            "evidence_blocks": [item.to_dict() for item in self.evidence_blocks],
            "source_units": [item.to_dict() for item in self.source_units],
            "facts": [item.to_dict() for item in self.facts],
        }

    @property
    def summary(self) -> dict[str, int]:
        return {
            "documents": 1,
            "evidence_blocks": len(self.evidence_blocks),
            "source_units": len(self.source_units),
            "facts": len(self.facts),
        }


def compile_text_document(
    text: str,
    *,
    title: str,
    domain_pack: DomainPack | None = None,
    source_type: str = "text",
    source_uri: str | None = None,
    version_label: str | None = None,
    language: str | None = None,
    metadata: dict[str, Any] | None = None,
    max_evidence_chars: int = 900,
) -> KnowledgeCompilation:
    """Compile text into generic evidence-bound knowledge objects.

    The compiler remains storage- and provider-neutral. Version and language
    metadata are carried by DocumentRecord so lifecycle adapters can manage
    multiple compiled versions without changing evidence/fact contracts.
    """

    document = register_text_document(
        text,
        title=title,
        source_type=source_type,
        source_uri=source_uri,
        version_label=version_label,
        language=language,
        metadata=metadata,
    )
    evidence_blocks = build_evidence_blocks(document, text, max_chars=max_evidence_chars)
    source_units = build_source_units(evidence_blocks)
    facts = extract_facts(source_units, domain_pack=domain_pack)
    return KnowledgeCompilation(
        document=document,
        evidence_blocks=evidence_blocks,
        source_units=source_units,
        facts=facts,
    )
