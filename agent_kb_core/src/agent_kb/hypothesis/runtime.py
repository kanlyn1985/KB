# -*- coding: utf-8 -*-
"""Hypothesis Runtime（AKB-V08-IMPL-001；设计 docs/V0.8/ V0.8_DESIGN §3.1）。

独立 hypothesis 生命周期——hypothesis ≠ inference ≠ assertion：
- 存储 = provenance-only（akb_provenance 审计事实 + metadata 快照——NO MIGRATION
  路径，设计 §6 方案 a）；零 akb_assertions 写入、零 kg_* 写入；
- 状态机：open → supported | refuted | withdrawn（open 起，closed 不可再变）；
  禁止 inferred/validated/asserted（这三种属 assertion 域——设计红线）；
- deterministic：hypothesis_id = "hyp_"+SHA256(canonical_json({statement,
  domain_ref, pack_ref, policy_ref, context_ref}))——同输入同 id；
- provenance：graph:hypothesis-create / graph:hypothesis-withdraw（复用
  akb_provenance，零第二套系统）；
- fail-closed：非法状态迁移/空字段/重复迁移 → E-V08-* 显式错误。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from agent_kb.reasoning.models import canonical_json

HYPOTHESIS_STATUSES = ("open", "supported", "refuted", "withdrawn")
FORBIDDEN_STATUSES = ("inferred", "validated", "asserted")   # 设计红线：禁入域
ALLOWED_TRANSITIONS = {
    "open": ("supported", "refuted", "withdrawn"),
    # closed 状态（supported/refuted/withdrawn）无出边——fail-closed
    "supported": (),
    "refuted": (),
    "withdrawn": (),
}


class HypothesisError(ValueError):
    """fail-closed：Hypothesis lifecycle 错误。"""


@dataclass(frozen=True)
class Hypothesis:
    """immutable hypothesis 视图（provenance 快照重建）。"""
    hypothesis_id: str
    domain_ref: str
    pack_ref: str
    policy_ref: str
    context_ref: str
    statement: str
    status: str
    origin: str
    created_by: str


def hypothesis_identity(*, statement: str, domain_ref: str, pack_ref: str,
                        policy_ref: str, context_ref: str) -> str:
    """deterministic hypothesis_id：同五元组 → 同 id（canonical JSON hash）。"""
    payload = {"statement": statement, "domain_ref": domain_ref,
               "pack_ref": pack_ref, "policy_ref": policy_ref,
               "context_ref": context_ref}
    return "hyp_" + hashlib.sha256(
        canonical_json(payload).encode("utf-8")).hexdigest()[:16]


class HypothesisService:
    """Hypothesis 生命周期服务（provenance-only 存储；零 assertion/graph 写入）。"""

    def __init__(self, connection, actor_id: str = "system:hypothesis"):
        self.connection = connection
        self.actor_id = actor_id

    # ---- helpers ----

    def _next_seq(self) -> int:
        """单调序号（本连接累计 hypothesis 活动数）——重放排序锚
        （provenance_id 为内容寻址非时间单调，occurred_at 秒级同秒有歧义）。"""
        row = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_provenance WHERE activity LIKE"
            " 'graph:hypothesis-%'").fetchone()
        return (row["c"] if row else 0) + 1

    def _audit(self, *, activity: str, details: dict) -> str:
        from agent_kb.evidence_core.assertions import Provenance
        from agent_kb.evidence_core.state_machine import actor_kind_of
        details = dict(details)
        details["seq"] = self._next_seq()
        rec = Provenance(self.connection).record(
            actor_id=details.get("actor", self.actor_id),
            actor_kind=actor_kind_of(details.get("actor", self.actor_id)),
            activity=activity, inputs=details.get("domains", []),
            metadata=details)
        return rec.provenance_id

    def _validate_refs(self, *, domain_ref: str, pack_ref: str,
                       policy_ref: str, context_ref: str) -> None:
        if not domain_ref or not domain_ref.strip():
            raise HypothesisError("E-V08-HYPOTHESIS-INVALID: empty domain_ref")
        if not pack_ref or not pack_ref.strip():
            raise HypothesisError("E-V08-HYPOTHESIS-INVALID: empty pack_ref")
        if not policy_ref or not policy_ref.strip():
            raise HypothesisError("E-V08-HYPOTHESIS-INVALID: empty policy_ref")
        if not context_ref or not context_ref.strip():
            raise HypothesisError(
                "E-V08-HYPOTHESIS-INVALID: empty context_ref (origin=reasoning"
                " requires traceable context)")

    # ---- 读面（provenance 重建）----

    def _load_state(self, hypothesis_id: str) -> dict | None:
        """从 akb_provenance 重建 hypothesis 当前状态（活动序列重放）。"""
        # provenance_id 为内容寻址（非时间单调）——按 occurred_at 时间序 +
        # provenance_id tie-breaker 稳定重放（V0.5 metadata 面先例一致）
        rows = []
        for r in self.connection.execute(
                "SELECT activity, metadata_json FROM akb_provenance"
                " WHERE activity LIKE 'graph:hypothesis-%'"):
            m = dict(r)
            meta = json.loads(m["metadata_json"])
            m["_seq"] = meta.get("seq", 0)
            rows.append(m)
        rows.sort(key=lambda m: m["_seq"])
        state = None
        for row in rows:
            m = json.loads(row["metadata_json"])
            if m.get("hypothesis_id") != hypothesis_id:
                continue
            if row["activity"] == "graph:hypothesis-create":
                state = {"status": "open", "statement": m.get("statement", ""),
                         "domain_ref": m.get("domain_ref", ""),
                         "pack_ref": m.get("pack_ref", ""),
                         "policy_ref": m.get("policy_ref", ""),
                         "context_ref": m.get("context_ref", ""),
                         "origin": m.get("origin", ""),
                         "created_by": m.get("actor", "")}
            elif row["activity"] == "graph:hypothesis-withdraw":
                if state is not None:
                    state["status"] = "withdrawn"
            elif row["activity"] == "graph:hypothesis-status":
                if state is not None:
                    state["status"] = m.get("to_status", state["status"])
        return state

    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis | None:
        """deterministic output：同状态同 id 同重建结果。"""
        if not hypothesis_id or not hypothesis_id.startswith("hyp_"):
            raise HypothesisError(
                f"E-V08-HYPOTHESIS-INVALID: bad id {hypothesis_id!r}")
        state = self._load_state(hypothesis_id)
        if state is None:
            return None
        return Hypothesis(
            hypothesis_id=hypothesis_id, domain_ref=state["domain_ref"],
            pack_ref=state["pack_ref"], policy_ref=state["policy_ref"],
            context_ref=state["context_ref"], statement=state["statement"],
            status=state["status"], origin=state["origin"],
            created_by=state["created_by"])

    # ---- 主入口 ----

    def create_hypothesis(self, *, statement: str, domain_ref: str,
                          pack_ref: str, policy_ref: str, context_ref: str,
                          origin: str = "human",
                          actor_id: str | None = None) -> Hypothesis:
        """创建 hypothesis（deterministic id + graph:hypothesis-create 审计；
        重复创建幂等返回既有 hypothesis）。"""
        if not statement or not statement.strip():
            raise HypothesisError("E-V08-HYPOTHESIS-INVALID: empty statement")
        if origin not in ("reasoning", "human"):
            raise HypothesisError(
                f"E-V08-HYPOTHESIS-INVALID: origin {origin!r} not in"
                " ('reasoning','human')")
        self._validate_refs(domain_ref=domain_ref, pack_ref=pack_ref,
                            policy_ref=policy_ref, context_ref=context_ref)
        hid = hypothesis_identity(statement=statement, domain_ref=domain_ref,
                                  pack_ref=pack_ref, policy_ref=policy_ref,
                                  context_ref=context_ref)
        existing = self.get_hypothesis(hid)
        if existing is not None:
            return existing                     # 幂等（零重复审计）
        actor = actor_id or self.actor_id
        self._audit(
            activity="graph:hypothesis-create",
            details={"hypothesis_id": hid, "actor": actor,
                     "domains": [domain_ref], "domain_ref": domain_ref,
                     "pack_ref": pack_ref, "policy_ref": policy_ref,
                     "context_ref": context_ref, "statement": statement,
                     "origin": origin})
        return self.get_hypothesis(hid)

    def withdraw_hypothesis(self, hypothesis_id: str, *,
                            actor_id: str) -> Hypothesis:
        """open → withdrawn（human 动作；graph:hypothesis-withdraw 审计）。
        非 open 状态 fail-closed（closed 无出边）。"""
        state = self.get_hypothesis(hypothesis_id)
        if state is None:
            raise HypothesisError(
                f"E-V08-HYPOTHESIS-INVALID: {hypothesis_id} not found")
        if "withdrawn" not in ALLOWED_TRANSITIONS.get(state.status, ()):
            raise HypothesisError(
                f"E-V08-INVALID-TRANSITION: {state.status} -> withdrawn"
                " (closed hypothesis has no outgoing transitions)")
        self._audit(
            activity="graph:hypothesis-withdraw",
            details={"hypothesis_id": hypothesis_id, "actor": actor_id,
                     "domains": [state.domain_ref],
                     "domain_ref": state.domain_ref,
                     "pack_ref": state.pack_ref,
                     "policy_ref": state.policy_ref,
                     "context_ref": state.context_ref,
                     "from_status": state.status, "to_status": "withdrawn"})
        return self.get_hypothesis(hypothesis_id)

    def transition_status(self, hypothesis_id: str, *, new_status: str,
                          actor_id: str) -> Hypothesis:
        """open → supported | refuted（verdict 驱动迁移——IMPL-002 Verdict 通道；
        本阶段提供受控迁移原语 + fail-closed 校验）。"""
        if new_status not in HYPOTHESIS_STATUSES:
            raise HypothesisError(
                f"E-V08-INVALID-TRANSITION: {new_status!r} not a hypothesis"
                f" status (forbidden assertion-domain statuses:"
                f" {FORBIDDEN_STATUSES})")
        state = self.get_hypothesis(hypothesis_id)
        if state is None:
            raise HypothesisError(
                f"E-V08-HYPOTHESIS-INVALID: {hypothesis_id} not found")
        if new_status not in ALLOWED_TRANSITIONS.get(state.status, ()):
            raise HypothesisError(
                f"E-V08-INVALID-TRANSITION: {state.status} -> {new_status}")
        self._audit(
            activity="graph:hypothesis-status",
            details={"hypothesis_id": hypothesis_id, "actor": actor_id,
                     "domains": [state.domain_ref],
                     "domain_ref": state.domain_ref,
                     "pack_ref": state.pack_ref, "policy_ref": state.policy_ref,
                     "context_ref": state.context_ref,
                     "from_status": state.status, "to_status": new_status})
        return self.get_hypothesis(hypothesis_id)