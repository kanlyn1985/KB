# -*- coding: utf-8 -*-
"""InferredProposal / ReasoningContext / fingerprint（V0.4 DD-002/003）。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

RULE_SET_VERSION = "v04-rules-v1"


def canonical_json(value) -> str:
    """与 V0.2/V0.3 同款 canonical JSON（确定性序列化）。"""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def reasoning_fingerprint(parent_ids: list[str], reasoner_id: str,
                          rule_version: str, configuration_hash: str) -> str:
    """ReasoningFingerprint（DD-002 §3）：parent sorted + reasoner + rules + config。"""
    payload = {"parent_assertion_ids": sorted(parent_ids), "reasoner_id": reasoner_id,
               "rule_version": rule_version, "configuration_hash": configuration_hash}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass
class ReasoningContext:
    """推理上下文（DD-001 §3）：ontology 范围 + 规则参数（strict deterministic）。"""
    ontology_scope: str = ""
    configuration: dict = field(default_factory=dict)
    max_depth: int = 8                 # DC-06

    def configuration_hash(self) -> str:
        return hashlib.sha256(canonical_json({
            "ontology_scope": self.ontology_scope,
            "configuration": self.configuration,
            "max_depth": self.max_depth,
        }).encode("utf-8")).hexdigest()[:16]


@dataclass
class InferredProposal:
    """Provider 输出的结构化提案（未落库；DD-001 §4）。"""
    proposal_id: str
    subject_ref: str
    predicate_ref: str
    object: dict
    rule_ref: str                       # "<rule_id>@<rule_version>"
    parent_assertions: list[str]        # parent assertion_id（非空，DC-01）
    reasoner_id: str
    rule_input_snapshot: str            # CanonicalJSON（DC-04）
    confidence_basis: dict = field(default_factory=dict)
    confidence: float | None = None

    def validate(self) -> list[str]:
        """schema validation（malformed → 拒绝；DD-001 §3）。"""
        v = []
        if not self.proposal_id:
            v.append("E-V04-PROPOSAL-MALFORMED: proposal_id missing")
        if not self.subject_ref or not self.predicate_ref or not self.object:
            v.append("E-V04-PROPOSAL-MALFORMED: triple incomplete")
        if not self.rule_ref:
            v.append("E-V04-PROPOSAL-MALFORMED: rule_ref missing")
        if not self.parent_assertions:
            v.append("E-V04-PROPOSAL-MALFORMED: parent_assertions empty (INV-002)")
        if not self.reasoner_id:
            v.append("E-V04-PROPOSAL-MALFORMED: reasoner_id missing")
        if not self.rule_input_snapshot:
            v.append("E-V04-PROPOSAL-MALFORMED: rule_input_snapshot missing")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            v.append("E-V04-PROPOSAL-MALFORMED: confidence out of range")
        return v