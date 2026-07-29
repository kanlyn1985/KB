"""LLM-powered ontology extraction engine."""

from kb_ontology.extraction.extractor import (
    ExtractionResult,
    ExtractedEntity,
    ExtractedRelation,
    extract_document,
)
from kb_ontology.extraction.schema_prompt import build_schema_description

__all__ = [
    "ExtractionResult",
    "ExtractedEntity",
    "ExtractedRelation",
    "build_schema_description",
    "extract_document",
]
