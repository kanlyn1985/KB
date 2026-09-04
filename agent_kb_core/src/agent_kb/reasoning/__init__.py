# -*- coding: utf-8 -*-
"""V0.4 Reasoner Core（AKB-V04-IMPL-001）。

设计基线：docs/V0.4/（25a13f7）。
- ReasonerProvider Protocol（provider neutrality，R-04）
- BuiltinRuleReasoner（RR-01..04，strict deterministic）
- ReasoningEngine skeleton（parent selection/环检测/fingerprint/create_candidate 唯一边界）
- InferredProposal model（schema validation）

边界：不改 V0.3 frozen code；不执行 migration 14；不写 production DB；
inferred 恒 candidate；inferred→asserted 永久禁止（State Machine 继承）。
"""
from agent_kb.reasoning.models import (
    InferredProposal,
    ReasoningContext,
    reasoning_fingerprint,
)
from agent_kb.reasoning.provider import ReasonerProvider
from agent_kb.reasoning.builtin_rules import BuiltinRuleReasoner, RULE_SET_VERSION
from agent_kb.reasoning.engine import ReasoningEngine
from agent_kb.reasoning.repository import (
    InferenceTraceService,
    ReasoningRunRepository,
)

__all__ = [
    "InferredProposal", "ReasoningContext", "reasoning_fingerprint",
    "ReasonerProvider", "BuiltinRuleReasoner", "RULE_SET_VERSION",
    "ReasoningEngine", "ReasoningRunRepository", "InferenceTraceService",
]