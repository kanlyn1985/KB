# -*- coding: utf-8 -*-
"""V0.3 Multi-Evidence Semantic Synthesis Core（设计基线：v0.3-multi-evidence-synthesis/）。"""
from agent_kb.evidence_core.synthesis.evidence_set import (
    MAX_SET_SIZE,
    SYNTHESIS_VERSION,
    EvidenceSetManager,
    evidence_set_fingerprint,
)
from agent_kb.evidence_core.synthesis.errors import (
    E_ALIGN_UNIT_MISSING,
    E_SET_DUPLICATE,
    E_SET_MEMBER_NOT_FOUND,
    E_SYNTH_DUPLICATE,
    E_SYNTH_PROVENANCE_MISSING,
    IdempotentSynthesisHit,
    SynthesisError,
)
from agent_kb.evidence_core.synthesis.models import (
    ConflictRecord,
    ConflictSet,
    SourceWeight,
    canonical_json,
)
from agent_kb.evidence_core.synthesis.synthesizer import (
    SynthesisEngine,
    synthesis_fingerprint,
)

__all__ = [
    "MAX_SET_SIZE", "SYNTHESIS_VERSION", "EvidenceSetManager", "evidence_set_fingerprint",
    "SynthesisEngine", "synthesis_fingerprint", "SynthesisError", "IdempotentSynthesisHit",
    "ConflictRecord", "ConflictSet", "SourceWeight", "canonical_json",
    "E_ALIGN_UNIT_MISSING", "E_SET_DUPLICATE", "E_SET_MEMBER_NOT_FOUND",
    "E_SYNTH_DUPLICATE", "E_SYNTH_PROVENANCE_MISSING",
]