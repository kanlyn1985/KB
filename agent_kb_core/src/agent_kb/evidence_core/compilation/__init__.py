# -*- coding: utf-8 -*-
"""V0.2 Semantic Compilation Core（设计基线：docs/architecture/detailed-design/v0.2-semantic-compilation/）。"""
from agent_kb.evidence_core.compilation.compiler import (
    COMPILER_VERSION,
    CandidateAssertionBuilder,
    SemanticCompiler,
    compilation_fingerprint,
    configuration_hash,
)
from agent_kb.evidence_core.compilation.errors import (
    E_CANDIDATE_BUILD_FAILED,
    E_COMPILER_INVALID_EVIDENCE,
    E_COMPILATION_DUPLICATE,
    E_COMPILATION_PROVENANCE_MISSING,
    E_NORMALIZATION_FAILED,
    E_ONTOLOGY_MAPPING_FAILED,
    E_SEMANTIC_EXTRACTION_FAILED,
    CompilationError,
    IdempotentHit,
)
from agent_kb.evidence_core.compilation.models import (
    CompilationResult,
    CompilationRunRecord,
    EntityCandidate,
    NormalizedSegment,
    OntologyMapping,
    RawExtraction,
    RelationCandidate,
    SemanticUnitRecord,
    TemporalParse,
    TextSegment,
    canonical_json,
)
from agent_kb.evidence_core.compilation.normalizer import Preprocessor, SemanticNormalizer
from agent_kb.evidence_core.compilation.providers import (
    BuiltinRuleExtractor,
    FakeSemanticCompilerProvider,
    SemanticCompilerProvider,
    validate_provider_output,
)

__all__ = [
    "COMPILER_VERSION", "SemanticCompiler", "CandidateAssertionBuilder",
    "compilation_fingerprint", "configuration_hash", "canonical_json",
    "SemanticCompilerProvider", "BuiltinRuleExtractor", "FakeSemanticCompilerProvider",
    "validate_provider_output", "Preprocessor", "SemanticNormalizer",
    "CompilationResult", "CompilationRunRecord", "EntityCandidate", "RelationCandidate", "TemporalParse", "RawExtraction", "NormalizedSegment", "TextSegment",
    "OntologyMapping", "SemanticUnitRecord",
    "CompilationError", "IdempotentHit",
    "E_CANDIDATE_BUILD_FAILED", "E_COMPILER_INVALID_EVIDENCE", "E_COMPILATION_DUPLICATE", "E_COMPILATION_PROVENANCE_MISSING",
    "E_NORMALIZATION_FAILED", "E_ONTOLOGY_MAPPING_FAILED", "E_SEMANTIC_EXTRACTION_FAILED",
]