# -*- coding: utf-8 -*-
"""Graph-aware Reasoning Orchestrator（AKB-V06-IMPL-002；设计 docs/V0.6/ §16/§3.3）。

GraphReasoningOrchestrator：GraphReasoningContext（IMPL-001）→ V0.4
ReasoningEngine.reason(parent_ids) 复用调用 → candidates + derivation trace。

硬边界（设计 contract）：
- 零新 ReasoningEngine——唯一引擎 = agent_kb.reasoning.ReasoningEngine；
- 零 LLM 依赖——provider 只接 deterministic ReasonerProvider；
- 只产 candidate——零 validate/approve/promote（inferred→asserted 禁令延续）；
- provenance 全链：candidate → run → context → assertions → evidence → documents；
- deterministic：同 context + 同 graph state + 同 rule version → 同 candidate 集
  （V0.4 fingerprint 幂等锚复用）。
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field

from agent_kb.kgraph.context import GraphContextError, GraphReasoningContext
from agent_kb.reasoning import (
    BuiltinRuleReasoner,
    ReasoningContext as V04ReasoningContext,
    ReasoningEngine,
)
from agent_kb.reasoning.models import canonical_json

# 设计 §10：推理深度独立定义（≠ query depth 8）
MAX_DERIVATION_DEPTH = 4
MAX_CANDIDATES_PER_RUN = 1024


class GraphOrchestrationError(ValueError):
    """fail-closed：编排错误（设计 §9/§16）。"""


@dataclass(frozen=True)
class OrchestrationTrace:
    """derivation trace：context → run → candidates → parent provenance。"""
    context_id: str
    run_id: str | None
    engine_fingerprint: str | None
    candidate_assertion_ids: tuple
    parent_assertion_ids: tuple
    provenance: tuple            # (candidate_id, parent_assertion_id) 推导对
    idempotent_hit: bool = False


class GraphReasoningOrchestrator:
    """Context → V0.4 Engine → Candidates（编排层，零推理语义）。"""

    def __init__(self, connection, engine: ReasoningEngine | None = None,
                 actor_id: str = "system:graph-reasoner"):
        if engine is None:
            # 复用 V0.4 默认引擎（deterministic BuiltinRuleReasoner——零 LLM）
            self.engine = ReasoningEngine(connection,
                                          provider=BuiltinRuleReasoner())
        else:
            self.engine = engine
        self.connection = connection
        self.actor_id = actor_id

    # ---- helpers ----

    def _v04_context(self, ctx: GraphReasoningContext) -> V04ReasoningContext:
        """GraphReasoningContext → V0.4 ReasoningContext（configuration_hash 对齐）。"""
        cfg = {
            "context_id": ctx.context_id,
            "graph_fingerprint": ctx.graph_fingerprint,
            "hop": ctx.hop,
            "status_filter": sorted(ctx.status_filter),
            "rule_set_version": ctx.rule_set_version,
        }
        return V04ReasoningContext(ontology_scope="v06-graph", configuration=cfg)

    def _depth_guard(self, ctx: GraphReasoningContext) -> None:
        hop = ctx.query_constraints.get("hops", ctx.hop)
        if hop > MAX_DERIVATION_DEPTH:
            raise GraphOrchestrationError(
                f"E-V06-DEPTH-OVERFLOW: hop {hop} > max_derivation_depth "
                f"{MAX_DERIVATION_DEPTH}")

    def _audit(self, *, activity: str, details: dict) -> str:
        from agent_kb.evidence_core.assertions import Provenance
        from agent_kb.evidence_core.state_machine import actor_kind_of
        rec = Provenance(self.connection).record(
            actor_id=self.actor_id, actor_kind=actor_kind_of(self.actor_id),
            activity=activity, inputs=details.get("parent_assertions", []),
            metadata=details)
        return rec.provenance_id

    # ---- 主入口 ----

    def run(self, ctx: GraphReasoningContext, *,
            include_trace: bool = True) -> dict:
        """执行一次 graph-aware reasoning（deterministic；幂等经 V0.4 锚）。

        返回 ReasoningResult：{run_id, context_id, candidates, warnings, errors,
        fingerprint, status, trace?}。
        """
        if not isinstance(ctx, GraphReasoningContext):
            raise GraphOrchestrationError("E-V06-INVALID-CONTEXT: not a"
                                          " GraphReasoningContext")
        self._depth_guard(ctx)
        if not ctx.input_assertions:
            raise GraphOrchestrationError(
                "E-V06-EMPTY-CONTEXT: no input assertions")
        v04_ctx = self._v04_context(ctx)
        try:
            result = self.engine.reason(list(ctx.input_assertions),
                                        actor_id=self.actor_id, context=v04_ctx)
        except Exception as exc:
            # V0.4 crash 语义：runs.fail + re-raise——编排层捕获转 failed result
            # （fail-closed 不外泄异常；审计留痕）
            prov_id = self._audit(
                activity="graph:reason-failed",
                details={"context_id": ctx.context_id,
                         "parent_assertions": sorted(ctx.input_assertions),
                         "errors": [f"E-V06-ENGINE-FAILED: {exc}"]})
            return {"run_id": None, "context_id": ctx.context_id,
                    "candidates": [], "warnings": [],
                    "errors": [f"E-V06-ENGINE-FAILED: {exc}"],
                    "fingerprint": None, "status": "failed",
                    "provenance_ref": prov_id}
        if not result.get("ok", True):
            prov_id = self._audit(
                activity="graph:reason-failed",
                details={"context_id": ctx.context_id,
                         "parent_assertions": sorted(ctx.input_assertions),
                         "errors": result.get("errors", [])})
            return {"run_id": None, "context_id": ctx.context_id,
                    "candidates": [], "warnings": result.get("warnings", []),
                    "errors": result.get("errors", []),
                    "fingerprint": None, "status": "failed",
                    "provenance_ref": prov_id}
        new_ids = [a.assertion_id for a in result.get("assertions", [])]
        if len(new_ids) > MAX_CANDIDATES_PER_RUN:
            raise GraphOrchestrationError(
                f"E-V06-CANDIDATE-EXPLOSION: {len(new_ids)} > "
                f"{MAX_CANDIDATES_PER_RUN}")
        status = "completed"
        if result.get("warnings"):
            status = "partial"
        trace = None
        prov_id = None
        if include_trace:
            provenance_pairs = tuple(
                (cid, pid) for cid in new_ids
                for pid in sorted(ctx.input_assertions))
            prov_id = self._audit(
                activity="graph:reason",
                details={"context_id": ctx.context_id,
                         "run_id": result.get("run_id"),
                         "candidate_assertions": new_ids,
                         "parent_assertions": sorted(ctx.input_assertions),
                         "graph_fingerprint": ctx.graph_fingerprint,
                         "rule_set_version": ctx.rule_set_version})
            trace = OrchestrationTrace(
                context_id=ctx.context_id, run_id=result.get("run_id"),
                engine_fingerprint=result.get("fingerprint"),
                candidate_assertion_ids=tuple(new_ids),
                parent_assertion_ids=tuple(sorted(ctx.input_assertions)),
                provenance=provenance_pairs,
                idempotent_hit=result.get("idempotent", False))
        return {"run_id": result.get("run_id"), "context_id": ctx.context_id,
                "candidates": result.get("assertions", []),
                "warnings": result.get("warnings", []),
                "errors": result.get("errors", []),
                "fingerprint": result.get("fingerprint"), "status": status,
                "provenance_ref": prov_id, "trace": trace}