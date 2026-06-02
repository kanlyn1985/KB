"""Fact extraction from parsed documents.

The public surface is split across focused submodules: `_extract_cover`
(cover-page metadata), `_extract_terms` (term/definition extraction),
`_extract_process` (process/type-relation extraction), and `_fact_payloads`
(payload construction + main orchestrator). The split preserves the
historical surface so external callers don't notice.
"""
from __future__ import annotations

from ._extract_cover import (
    _extract_cover_metadata,
    _extract_doc_metadata,
    _sanitize_payload,
)
from ._extract_terms import _extract_term_definitions
from ._fact_payloads import (
    FactsBuildResult,
    _definition_has_publishable_signal,
    _ensure_evidence_chains,
    _insert_metadata_facts,
    build_facts_for_document,
)

__all__ = [
    "FactsBuildResult",
    "build_facts_for_document",
]
