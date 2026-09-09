# -*- coding: utf-8 -*-
"""Assertion 状态机（V0.1_STATE_MACHINE.md 唯一规则来源）。"""
from __future__ import annotations

CREATE_ALLOWED_TYPES = {"extracted", "observed", "inferred", "hypothesized"}

ALL_TYPES = CREATE_ALLOWED_TYPES | {"asserted"}
ALL_STATUS = {"candidate", "validated", "asserted", "disputed", "rejected", "deprecated"}

# 合法迁移表（State Machine §3/§4；Key=(from_status, to_status) → 允许的 actor_kind）
LEGAL_TRANSITIONS: dict[tuple[str, str], set[str]] = {
    ("candidate", "validated"): {"system", "human"},       # validator 自动或人工
    ("candidate", "rejected"): {"system", "human"},
    ("validated", "asserted"): {"human"},                   # 治理跃迁，仅人工
    ("validated", "disputed"): {"human", "system"},
    ("validated", "deprecated"): {"human"},
    ("asserted", "disputed"): {"human", "system"},
    ("asserted", "deprecated"): {"human"},
    ("disputed", "asserted"): {"human"},                    # 裁决恢复
    ("disputed", "deprecated"): {"human"},
    ("disputed", "rejected"): {"human"},
}

# 创建期允许的初始状态恒为 candidate（asserted 直接创建禁止）
CREATE_STATUS = "candidate"

EVIDENCE_REQUIRED_STATUS = {"validated", "asserted", "disputed"}  # INV-001


def actor_kind_of(actor_id: str) -> str:
    """actor_id 前缀 → kind（human:/system:/llm:/agent:）。"""
    if actor_id.startswith("human:"):
        return "human"
    if actor_id.startswith("system:"):
        return "system"
    if actor_id.startswith("llm:"):
        return "llm"
    if actor_id.startswith("agent:"):
        return "agent"
    raise ValueError(f"E-ACTOR-NOT-AUTHORIZED: unknown actor prefix {actor_id!r}")


def validate_transition(
    *,
    current_status: str,
    new_status: str,
    assertion_type: str,
    actor_id: str,
    evidence_count: int,
) -> list[str]:
    """纯函数预检（can_transition / transition 共用）。返回违规码列表，空=合法。"""
    v: list[str] = []
    kind = actor_kind_of(actor_id)

    # 直接创建 asserted 在 create_candidate 层拦截；此处防迁移层伪装
    if current_status == new_status:
        v.append("E-ALREADY-IN-STATUS")
        return v
    if (current_status, new_status) not in LEGAL_TRANSITIONS:
        v.append("E-ILLEGAL-TRANSITION")
        return v
    allowed_kinds = LEGAL_TRANSITIONS[(current_status, new_status)]
    if kind not in allowed_kinds:
        v.append("E-ACTOR-NOT-AUTHORIZED")
    # INV-001：目标状态证据要求
    if new_status in EVIDENCE_REQUIRED_STATUS and evidence_count < 1:
        v.append("E-INV-001-NO-EVIDENCE")
    # INV-002 / State Machine §3：inferred 不得晋升 asserted（→validated 允许，带证据）
    if assertion_type == "inferred" and new_status == "asserted":
        v.append("E-ILLEGAL-TRANSITION: inferred cannot be promoted to asserted")
    # State Machine §3：hypothesized 只能保持 candidate；→ validated/asserted 禁止
    # （须先重新分类为 extracted/observed 再进 validation pipeline）
    if assertion_type == "hypothesized" and new_status in ("validated", "asserted"):
        v.append("E-ILLEGAL-TRANSITION: hypothesized must stay candidate "
                 "(reclassify to extracted/observed first)")
    return v


def validate_creation(assertion_type: str, derivation: dict | None) -> list[str]:
    """create_candidate 预检。"""
    v: list[str] = []
    if assertion_type not in CREATE_ALLOWED_TYPES:
        if assertion_type == "asserted":
            v.append("E-INVALID-TYPE-FOR-CREATE: asserted cannot be created directly")
        else:
            v.append(f"E-INVALID-TYPE: {assertion_type}")
    if assertion_type == "inferred":
        if not derivation:
            v.append("E-DERIVATION-MISSING")
        else:
            for key in ("rule_ref", "parent_assertions", "reasoner_id"):
                if not derivation.get(key):
                    v.append(f"E-DERIVATION-MISSING: {key} required")
    return v