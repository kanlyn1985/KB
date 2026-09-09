# -*- coding: utf-8 -*-
"""Verdict Runtime（AKB-V08-IMPL-003；设计 docs/V0.8/ §3.4/ARCHITECTURE §3）。

知识演化闭环：Hypothesis → VerificationTask → Verdict → hypothesis 状态迁移。

硬边界（设计 §3.4/§5）：
- result 白名单 = supported|refuted|inconclusive（validated/asserted/inferred
  禁入——E-V08-VERDICT-INVALID fail-closed）；
- 绑定校验：hypothesis 必须存在（E-V08-HYPOTHESIS-NOT-FOUND）；task 必须存在且
  completed（E-V08-TASK-NOT-COMPLETED）；evidence_refs 必须存在
  （E-V08-VERDICT-INVALID——不 fabricate）；
- 迁移只允许 open → supported|refuted（inconclusive 保持 open 记录裁决史）；
  supported → assertion/validated/kg projection 全部禁止（零直通红线）；
- Verdict ≠ Assertion ≠ Graph Node ≠ Candidate Promotion：零 akb_assertions/
  kg_nodes/kg_edges 写入；零 candidate 产生（promotion 提案属后续阶段）；
- deterministic：verdict_id = "vrd_"+SHA256(canonical_json({hypothesis_id,
  task_id, result, evidence_refs}))——同输入同 id，零时间/零随机；
- provenance：graph:hypothesis-verdict（复用 akb_provenance + seq 锚，零第二套）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from agent_kb.reasoning.models import canonical_json

VERDICT_RESULTS = ("supported", "refuted", "inconclusive")
FORBIDDEN_RESULTS = ("validated", "asserted", "inferred")


class VerdictError(ValueError):
    """fail-closed：Verdict 错误。"""


@dataclass(frozen=True)
class Verdict:
    """immutable verdict 视图（provenance 快照重建）。"""
    verdict_id: str
    hypothesis_id: str
    verification_task_id: str
    result: str
    evidence_refs: tuple
    reason: str
    actor: str
    created_seq: int


def verdict_identity(*, hypothesis_id: str, task_id: str, result: str,
                     evidence_refs: tuple) -> str:
    """deterministic verdict_id：同四元组 → 同 id（canonical JSON；零时间/零随机）。"""
    payload = {"hypothesis_id": hypothesis_id, "task_id": task_id,
               "result": result, "evidence_refs": sorted(evidence_refs)}
    return "vrd_" + hashlib.sha256(
        canonical_json(payload).encode("utf-8")).hexdigest()[:16]


class VerdictRuntime:
    """Verdict 运行时（校验 + 迁移驱动 + 审计；零直通零泄漏）。"""

    def __init__(self, connection, hypothesis_service=None,
                 task_runtime=None, actor_id: str = "system:verdict"):
        self.connection = connection
        self._hs = hypothesis_service
        self._tr = task_runtime
        self.actor_id = actor_id

    # ---- helpers（延续 seq 锚模式）----

    def _next_seq(self) -> int:
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
            activity=activity, inputs=details.get("hypothesis_ids", []),
            metadata=details)
        return rec.provenance_id

    def _services(self):
        if self._hs is None:
            from agent_kb.hypothesis import HypothesisService
            self._hs = HypothesisService(self.connection)
        if self._tr is None:
            from agent_kb.hypothesis import VerificationTaskRuntime
            self._tr = VerificationTaskRuntime(self.connection,
                                               hypothesis_service=self._hs)
        return self._hs, self._tr

    def _validate(self, *, hypothesis_id: str, task_id: str, result: str,
                  evidence_refs: tuple) -> None:
        """全链校验（fail-closed，零 fabricate）。"""
        if result not in VERDICT_RESULTS:
            raise VerdictError(
                f"E-V08-VERDICT-INVALID: result {result!r} (whitelist:"
                f" {VERDICT_RESULTS}; forbidden assertion-domain results:"
                f" {FORBIDDEN_RESULTS})")
        hs, tr = self._services()
        if hs.get_hypothesis(hypothesis_id) is None:
            raise VerdictError(
                f"E-V08-HYPOTHESIS-NOT-FOUND: {hypothesis_id}")
        task = tr.get_task(task_id)
        if task is None:
            raise VerdictError(
                f"E-V08-TASK-NOT-FOUND: {task_id}")
        if task.status != "completed":
            raise VerdictError(
                f"E-V08-TASK-NOT-COMPLETED: {task_id} is {task.status}")
        if task.hypothesis_id != hypothesis_id:
            raise VerdictError(
                f"E-V08-VERDICT-INVALID: task {task_id} bound to"
                f" {task.hypothesis_id}, not {hypothesis_id}")
        if not evidence_refs:
            raise VerdictError(
                "E-V08-VERDICT-INVALID: empty evidence_refs")
        for eid in evidence_refs:
            row = self.connection.execute(
                "SELECT 1 FROM akb_evidence WHERE evidence_id=?",
                (eid,)).fetchone()
            if row is None:
                raise VerdictError(
                    f"E-V08-VERDICT-INVALID: evidence {eid} not found"
                    " (fail-closed, no fabrication)")

    # ---- 主入口 ----

    def create_verdict(self, *, hypothesis_id: str, task_id: str,
                       result: str, evidence_refs: tuple, reason: str = "",
                       actor_id: str | None = None) -> Verdict:
        """创建 verdict → 校验 → hypothesis 迁移驱动 → 审计（幂等）。"""
        evidence_refs = tuple(evidence_refs)
        self._validate(hypothesis_id=hypothesis_id, task_id=task_id,
                       result=result, evidence_refs=evidence_refs)
        vid = verdict_identity(hypothesis_id=hypothesis_id, task_id=task_id,
                               result=result, evidence_refs=evidence_refs)
        if self.get_verdict(vid) is not None:
            return self.get_verdict(vid)        # 幂等（零重复审计/零重复迁移）
        actor = actor_id or self.actor_id
        hs, _tr = self._services()
        hyp = hs.get_hypothesis(hypothesis_id)
        # 迁移预检（inconclusive 保持 open——仅记录裁决史）
        target = result if result in ("supported", "refuted") else None
        if target is not None and hyp.status != "open":
            raise VerdictError(
                f"E-V08-VERDICT-INVALID: hypothesis {hypothesis_id} is"
                f" {hyp.status} (only open → supported/refuted allowed)")
        seq = self._next_seq()
        self._audit(
            activity="graph:hypothesis-verdict",
            details={"verdict_id": vid,
                     "hypothesis_ids": [hypothesis_id],
                     "hypothesis_id": hypothesis_id, "task_id": task_id,
                     "result": result, "evidence_refs": sorted(evidence_refs),
                     "reason": reason, "actor": actor, "seq": seq,
                     "from_status": hyp.status,
                     "to_status": target or hyp.status})
        if target is not None:
            # IMPL-001 受控迁移原语（open → supported/refuted）
            hs.transition_status(hypothesis_id, new_status=target,
                                 actor_id=actor)
        return self.get_verdict(vid)

    # ---- 读面（provenance 重放）----

    def get_verdict(self, verdict_id: str) -> Verdict | None:
        if not verdict_id or not verdict_id.startswith("vrd_"):
            raise VerdictError(f"E-V08-VERDICT-INVALID: bad id {verdict_id!r}")
        rows = []
        for r in self.connection.execute(
                "SELECT activity, metadata_json FROM akb_provenance"
                " WHERE activity = 'graph:hypothesis-verdict'"):
            meta = json.loads(r["metadata_json"])
            if meta.get("verdict_id") != verdict_id:
                continue
            rows.append(meta)
        rows.sort(key=lambda m: m.get("seq", 0))
        if not rows:
            return None
        m = rows[0]
        return Verdict(
            verdict_id=verdict_id, hypothesis_id=m["hypothesis_id"],
            verification_task_id=m["task_id"], result=m["result"],
            evidence_refs=tuple(m["evidence_refs"]), reason=m.get("reason", ""),
            actor=m.get("actor", ""), created_seq=m.get("seq", 0))

    def list_verdicts(self, hypothesis_id: str) -> list[Verdict]:
        """hypothesis 的全部 verdict（canonical 排序——by verdict_id）。"""
        out = []
        for r in self.connection.execute(
                "SELECT metadata_json FROM akb_provenance"
                " WHERE activity = 'graph:hypothesis-verdict'"):
            meta = json.loads(r["metadata_json"])
            if meta.get("hypothesis_id") != hypothesis_id:
                continue
            v = self.get_verdict(meta["verdict_id"])
            if v is not None:
                out.append(v)
        return sorted(out, key=lambda v: v.verdict_id)