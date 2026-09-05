"""Generic document compilation core.

Phase 2 starts the generic ingestion/compiler boundary:

Document -> EvidenceBlock -> SourceUnit -> Fact

The core stays domain-neutral. Domain packs can enrich extraction by providing
terminology and object schemas, but the compiler must still work without any
specific domain pack.
"""

from .compiler import KnowledgeCompilation, compile_text_document
from .documents import DocumentRecord, register_text_document
from .evidence import EvidenceBlock, build_evidence_blocks
from .facts import Fact, extract_facts
from .source_units import SourceUnit, build_source_units

__all__ = [
    "DocumentRecord",
    "EvidenceBlock",
    "Fact",
    "KnowledgeCompilation",
    "SourceUnit",
    "build_evidence_blocks",
    "build_source_units",
    "compile_text_document",
    "extract_facts",
    "register_text_document",
]
