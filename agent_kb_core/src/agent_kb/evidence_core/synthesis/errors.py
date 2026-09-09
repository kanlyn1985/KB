# -*- coding: utf-8 -*-
"""V0.3 合成错误模型（V0.3_ERROR_MODEL.md）。"""
from __future__ import annotations

E_SET_INVALID = "E-V03-SET-INVALID"
E_SET_MEMBER_NOT_FOUND = "E-V03-SET-MEMBER-NOT-FOUND"
E_SET_DUPLICATE = "E-V03-SET-DUPLICATE"
E_SET_TOO_LARGE = "E-V03-SET-TOO-LARGE"
E_SET_EMPTY = "E-V03-SET-EMPTY"
E_ALIGN_UNIT_MISSING = "E-V03-ALIGN-UNIT-MISSING"
E_ALIGN_INVALID = "E-V03-ALIGN-INVALID"
E_CONFLICT_CAPPED = "E-V03-CONFLICT-CAPPED"
E_SYNTHESIS_FAILED = "E-V03-SYNTHESIS-FAILED"
E_SYNTH_PROVENANCE_MISSING = "E-V03-SYNTH-PROVENANCE-MISSING"
E_SYNTH_DUPLICATE = "E-V03-SYNTH-DUPLICATE"
E_PROVIDER_FAILED = "E-V03-PROVIDER-FAILED"
E_PERSISTENCE_FAILED = "E-V03-PERSISTENCE-FAILED"


class SynthesisError(Exception):
    """带错误码的合成异常（失败不越界：不改 Evidence/authoritative/治理）。"""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


class IdempotentSynthesisHit(SynthesisError):
    """指纹命中——V0.3 语义为幂等返回（编排层捕获转返回值）。"""

    def __init__(self, fingerprint: str):
        super().__init__(E_SYNTH_DUPLICATE, f"fingerprint={fingerprint}")
        self.fingerprint = fingerprint