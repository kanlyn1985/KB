# -*- coding: utf-8 -*-
"""VerificationTask Runtime（AKB-V08-IMPL-002；设计 docs/V0.8/ §3.2/§4）。

验证任务生命周期管理——provenance-only 存储（延续 IMPL-001 路径：akb_provenance
活动序列重放 + metadata 单调 seq 锚，零 migration/零 schema 变更）。

硬边界：
- 必须绑定已存在 hypothesis（不存在 → E-V08-HYPOTHESIS-NOT-FOUND fail-closed）；
- 零 hypothesis 状态修改（verdict 属 IMPL-003）、零 assertion 产生、零 kg_* 写入；
- lifecycle：created → running → completed | failed；running → cancelled；
  非法迁移 fail-close（E-V08-TASK-INVALID-TRANSITION）；
- deterministic：task_id = "vt_"+SHA256(canonical_json({hypothesis_id, task_type,
  spec, evidence_requirements}))——同输入同 id，零随机/零时间入 hash；
- provenance：graph:verification-task-create/start/complete/failed/cancel
  （复用 akb_provenance，零第二套审计）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from agent_kb.reasoning.models import canonical_json

TASK_STATUSES = ("created", "running", "completed", "failed", "cancelled")
ALLOWED_TASK_TRANSITIONS = {
    "created": ("running", "cancelled"),
    "running": ("completed", "failed", "cancelled"),
    "completed": (),
    "failed": (),
    "cancelled": (),
}
TASK_ACTIVITY = {
    "create": "graph:verification-task-create",
    "start": "graph:verification-task-start",
    "complete": "graph:verification-task-complete",
    "failed": "graph:verification-task-failed",
    "cancel": "graph:verification-task-cancel",
}


class VerificationTaskError(ValueError):
    """fail-closed：VerificationTask 错误。"""


@dataclass(frozen=True)
class VerificationTask:
    """immutable task 视图（provenance 快照重建）。"""
    task_id: str
    hypothesis_id: str
    task_type: str
    spec: str
    status: str
    created_by: str
    evidence_requirements: tuple


def verification_task_identity(*, hypothesis_id: str, task_type: str,
                               spec: str,
                               evidence_requirements: tuple) -> str:
    """deterministic task_id：同四元组 → 同 id（canonical JSON hash；零随机/
    零时间入 hash）。"""
    payload = {"hypothesis_id": hypothesis_id, "task_type": task_type,
               "spec": spec,
               "evidence_requirements": sorted(evidence_requirements)}
    return "vt_" + hashlib.sha256(
        canonical_json(payload).encode("utf-8")).hexdigest()[:16]


class VerificationTaskRuntime:
    """验证任务运行时（provenance-only 存储与重放；零 hypothesis 状态修改）。"""

    VALID_TASK_TYPES = ("evidence_review", "experiment", "expert_review",
                        "literature_check")

    def __init__(self, connection, hypothesis_service=None,
                 actor_id: str = "system:verification"):
        self.connection = connection
        self._hs = hypothesis_service        # HypothesisService（绑定校验复用）
        self.actor_id = actor_id

    # ---- helpers（延续 IMPL-001 seq 锚模式）----

    def _next_seq(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_provenance WHERE activity LIKE"
            " 'graph:verification-task-%'").fetchone()
        return (row["c"] if row else 0) + 1

    def _audit(self, *, activity: str, details: dict) -> str:
        from agent_kb.evidence_core.assertions import Provenance
        from agent_kb.evidence_core.state_machine import actor_kind_of
        details = dict(details)
        details["seq"] = self._next_seq()
        rec = Provenance(self.connection).record(
            actor_id=details.get("actor", self.actor_id),
            actor_kind=actor_kind_of(details.get("actor", self.actor_id)),
            activity=activity, inputs=details.get("hypothesis_ids", []),
            metadata=details)
        return rec.provenance_id

    def _validate_hypothesis_binding(self, hypothesis_id: str) -> None:
        """绑定校验：hypothesis 必须已存在（fail-closed）。"""
        if self._hs is None:
            from agent_kb.hypothesis import HypothesisService
            self._hs = HypothesisService(self.connection)
        if self._hs.get_hypothesis(hypothesis_id) is None:
            raise VerificationTaskError(
                f"E-V08-HYPOTHESIS-NOT-FOUND: {hypothesis_id}")

    def _validate_spec(self, *, task_type: str, spec: str,
                       evidence_requirements: tuple) -> None:
        if task_type not in self.VALID_TASK_TYPES:
            raise VerificationTaskError(
                f"E-V08-TASK-INVALID: task_type {task_type!r} not in"
                f" {self.VALID_TASK_TYPES}")
        if not spec or not spec.strip():
            raise VerificationTaskError(
                "E-V08-TASK-INVALID: empty spec")
        if not evidence_requirements:
            raise VerificationTaskError(
                "E-V08-TASK-INVALID: empty evidence_requirements")
        for e in evidence_requirements:
            if not e or not e.strip():
                raise VerificationTaskError(
                    "E-V08-TASK-INVALID: empty evidence requirement entry")

    # ---- 读面（provenance 序列重放，seq 排序）----

    def _load_state(self, task_id: str) -> dict | None:
        rows = []
        for r in self.connection.execute(
                "SELECT activity, metadata_json FROM akb_provenance"
                " WHERE activity LIKE 'graph:verification-task-%'"):
            m = dict(r)
            meta = json.loads(m["metadata_json"])
            if meta.get("task_id") != task_id:
                continue
            m["_seq"] = meta.get("seq", 0)
            m["_meta"] = meta
            rows.append(m)
        rows.sort(key=lambda m: m["_seq"])
        state = None
        for row in rows:
            meta = row["_meta"]
            act = row["activity"]
            if act == TASK_ACTIVITY["create"]:
                state = {"status": "created",
                         "hypothesis_id": meta.get("hypothesis_id", ""),
                         "task_type": meta.get("task_type", ""),
                         "spec": meta.get("spec", ""),
                         "evidence_requirements": tuple(
                             meta.get("evidence_requirements", [])),
                         "created_by": meta.get("actor", "")}
            elif state is not None:
                for key, activity in TASK_ACTIVITY.items():
                    if key != "create" and activity == act:
                        state["status"] = {
                            "start": "running", "complete": "completed",
                            "failed": "failed", "cancel": "cancelled"}[key]
        return state

    def get_task(self, task_id: str) -> VerificationTask | None:
        """deterministic output：同状态同重建结果；不存在 → None（不 fabricate）。"""
        if not task_id or not task_id.startswith("vt_"):
            raise VerificationTaskError(f"E-V08-TASK-INVALID: bad id {task_id!r}")
        state = self._load_state(task_id)
        if state is None:
            return None
        return VerificationTask(
            task_id=task_id, hypothesis_id=state["hypothesis_id"],
            task_type=state["task_type"], spec=state["spec"],
            status=state["status"], created_by=state["created_by"],
            evidence_requirements=tuple(state["evidence_requirements"]))

    # ---- 生命周期 ----

    def create_task(self, *, hypothesis_id: str, task_type: str, spec: str,
                    evidence_requirements: tuple,
                    actor_id: str | None = None) -> VerificationTask:
        """创建验证任务（绑定校验 fail-closed + deterministic id + 审计；幂等）。"""
        self._validate_spec(task_type=task_type, spec=spec,
                            evidence_requirements=tuple(evidence_requirements))
        self._validate_hypothesis_binding(hypothesis_id)
        tid = verification_task_identity(
            hypothesis_id=hypothesis_id, task_type=task_type, spec=spec,
            evidence_requirements=tuple(evidence_requirements))
        if self.get_task(tid) is not None:
            return self.get_task(tid)            # 幂等（零重复审计）
        actor = actor_id or self.actor_id
        self._audit(
            activity=TASK_ACTIVITY["create"],
            details={"task_id": tid, "hypothesis_ids": [hypothesis_id],
                     "hypothesis_id": hypothesis_id, "task_type": task_type,
                     "spec": spec,
                     "evidence_requirements": sorted(evidence_requirements),
                     "actor": actor, "from_status": None,
                     "to_status": "created"})
        return self.get_task(tid)

    def _transition(self, task_id: str, *, key: str, new_status: str,
                    actor_id: str) -> VerificationTask:
        state = self.get_task(task_id)
        if state is None:
            raise VerificationTaskError(
                f"E-V08-TASK-INVALID: {task_id} not found")
        if new_status not in ALLOWED_TASK_TRANSITIONS.get(state.status, ()):
            raise VerificationTaskError(
                f"E-V08-TASK-INVALID-TRANSITION: {state.status} ->"
                f" {new_status}")
        self._audit(
            activity=TASK_ACTIVITY[key],
            details={"task_id": task_id,
                     "hypothesis_ids": [state.hypothesis_id],
                     "hypothesis_id": state.hypothesis_id,
                     "from_status": state.status, "to_status": new_status,
                     "actor": actor_id,
                     "evidence_requirements": sorted(
                         state.evidence_requirements)})
        return self.get_task(task_id)

    def start_task(self, task_id: str, *, actor_id: str) -> VerificationTask:
        return self._transition(task_id, key="start", new_status="running",
                                actor_id=actor_id)

    def complete_task(self, task_id: str, *, actor_id: str) -> VerificationTask:
        return self._transition(task_id, key="complete",
                                new_status="completed", actor_id=actor_id)

    def fail_task(self, task_id: str, *, actor_id: str) -> VerificationTask:
        return self._transition(task_id, key="failed", new_status="failed",
                                actor_id=actor_id)

    def cancel_task(self, task_id: str, *, actor_id: str) -> VerificationTask:
        return self._transition(task_id, key="cancel",
                                new_status="cancelled", actor_id=actor_id)