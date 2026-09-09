# -*- coding: utf-8 -*-
"""V0.2 编译错误模型（V0.2_ERROR_MODEL.md）。"""
from __future__ import annotations

E_COMPILER_INVALID_EVIDENCE = "E-COMPILER-INVALID-EVIDENCE"
E_NORMALIZATION_FAILED = "E-NORMALIZATION-FAILED"
E_SEMANTIC_EXTRACTION_FAILED = "E-SEMANTIC-EXTRACTION-FAILED"
E_ONTOLOGY_MAPPING_FAILED = "E-ONTOLOGY-MAPPING-FAILED"
E_CANDIDATE_BUILD_FAILED = "E-CANDIDATE-BUILD-FAILED"
E_COMPILATION_NONDETERMINISTIC = "E-COMPILATION-NONDETERMINISTIC"
E_COMPILATION_DUPLICATE = "E-COMPILATION-DUPLICATE"
E_COMPILATION_PROVENANCE_MISSING = "E-COMPILATION-PROVENANCE-MISSING"


class CompilationError(Exception):
    """带错误码的编译异常（错误不能越界：不修改 Evidence/authoritative/治理）。"""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


class IdempotentHit(CompilationError):
    """fingerprint 命中——V0.2 语义为幂等返回（非错误抛出；编排层捕获转返回值）。"""

    def __init__(self, fingerprint: str):
        super().__init__(E_COMPILATION_DUPLICATE, f"fingerprint={fingerprint}")
        self.fingerprint = fingerprint