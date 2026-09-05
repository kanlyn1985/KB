# -*- coding: utf-8 -*-
"""ReasonerProvider Protocol（DD-001 §3；provider neutrality R-04）。"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ReasonerProvider(Protocol):
    """推理提供者协议。

    - 内置：BuiltinRuleReasoner（strict deterministic）；
    - 外部/LLM：stochastic but traceable（后阶段；必须可给出 rule_input_snapshot）。
    Provider 不得接触 create_candidate/治理 API——落库由 ReasoningEngine 编排执行。
    """

    def reasoner_id(self) -> str: ...

    def rule_version(self) -> str: ...

    def infer(self, parent_assertions: list, context) -> list: ...