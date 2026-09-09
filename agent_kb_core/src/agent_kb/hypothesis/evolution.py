# -*- coding: utf-8 -*-
"""EvolutionView Runtime（AKB-V08-IMPL-004；设计 docs/V0.8/ ARCHITECTURE §4）。

知识演化只读审计视图：Hypothesis → VerificationTask(s) → Verdict(s) →
Provenance 完整生命周期聚合。

硬边界：
- READ-ONLY：零 akb_assertions/kg_nodes/kg_edges 写入；零 promotion；
  EvolutionView ≠ Assertion ≠ Graph Node ≠ Knowledge Promotion；
- 数据来源 = akb_provenance + HypothesisRuntime/VerificationTaskRuntime/
  VerdictRuntime 既有读面（零新表/零 migration/零第二套审计）；
- deterministic：view fingerprint = "evw_"+SHA256(canonical_json(全视图))——
  同状态同 fingerprint；canonical/stable ordering；零 timestamp/零随机入 hash；
- 不存在 hypothesis → None（禁止 fabricate）；seq 排序 timeline。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from agent_kb.reasoning.models import canonical_json


class EvolutionViewError(ValueError):
    """fail-closed：EvolutionView 错误。"""


@dataclass(frozen=True)
class TimelineEntry:
    """timeline 单条（seq 排序；label:activity + 关键字段）。"""
    seq: int
    label: str
    actor: str = ""
    detail: str = ""


@dataclass(frozen=True)
class EvolutionView:
    """immutable 只读演化视图。"""
    hypothesis_id: str
    current_status: str
    created_seq: int
    tasks: tuple
    verdicts: tuple
    timeline: tuple
    provenance_refs: tuple
    fingerprint: str


class EvolutionViewRuntime:
    """演化视图运行时（只读聚合；零写入）。"""

    def __init__(self, connection, hypothesis_service=None,
                 task_runtime=None, verdict_runtime=None):
        self.connection = connection
        self._hs = hypothesis_service
        self._tr = task_runtime
        self._vr = verdict_runtime

    # ---- helpers ----

    def _services(self):
        if self._hs is None:
            from agent_kb.hypothesis import HypothesisService
            self._hs = HypothesisService(self.connection)
        if self._tr is None:
            from agent_kb.hypothesis import VerificationTaskRuntime
            self._tr = VerificationTaskRuntime(self.connection,
                                               hypothesis_service=self._hs)
        if self._vr is None:
            from agent_kb.hypothesis import VerdictRuntime
            self._vr = VerdictRuntime(self.connection,
                                      hypothesis_service=self._hs,
                                      task_runtime=self._tr)
        return self._hs, self._tr, self._vr

    @staticmethod
    def view_fingerprint(view_payload: dict) -> str:
        """deterministic view fingerprint（canonical JSON；零 timestamp/零随机）。"""
        return "evw_" + hashlib.sha256(
            canonical_json(view_payload).encode("utf-8")).hexdigest()[:16]

    # ---- 主查询 ----

    def get_evolution_view(self, hypothesis_id: str) -> EvolutionView | None:
        """完整生命周期聚合（不存在 → None，禁止 fabricate）。"""
        if not hypothesis_id or not hypothesis_id.startswith("hyp_"):
            raise EvolutionViewError(
                f"E-V08-HYPOTHESIS-INVALID: bad id {hypothesis_id!r}")
        hs, tr, vr = self._services()
        hyp = hs.get_hypothesis(hypothesis_id)
        if hyp is None:
            return None
        # tasks：provenance 重放面扫描（task 创建活动绑定本 hypothesis）
        tasks = []
        for r in self.connection.execute(
                "SELECT metadata_json FROM akb_provenance WHERE activity ="
                " 'graph:verification-task-create'"):
            meta = json.loads(r["metadata_json"])
            if meta.get("hypothesis_id") != hypothesis_id:
                continue
            t = tr.get_task(meta["task_id"])
            if t is not None:
                tasks.append(t)
        tasks = tuple(sorted(tasks, key=lambda t: t.task_id))
        # verdicts（既有读面）
        verdicts = tuple(sorted(vr.list_verdicts(hypothesis_id),
                                key=lambda v: v.verdict_id))
        # timeline：全 hypothesis/task/verdict 活动 seq 排序
        entries = []
        for r in self.connection.execute(
                "SELECT provenance_id, activity, actor_id, metadata_json"
                " FROM akb_provenance WHERE activity LIKE"
                " 'graph:hypothesis-%' OR activity LIKE"
                " 'graph:verification-task-%'"):
            meta = json.loads(r["metadata_json"])
            related = (meta.get("hypothesis_id") == hypothesis_id or
                       meta.get("hypothesis_ids") == [hypothesis_id])
            if not related:
                continue
            label = r["activity"].replace("graph:", "").replace(
                "verification-task-", "task-")
            entries.append(TimelineEntry(
                seq=meta.get("seq", 0), label=label,
                actor=r["actor_id"], detail=meta.get("to_status", "")))
        entries.sort(key=lambda e: e.seq)
        # provenance_refs（related 活动的 provenance_id——再扫一次取 id）
        prov_refs = []
        for r in self.connection.execute(
                "SELECT provenance_id, metadata_json FROM akb_provenance"
                " WHERE activity LIKE 'graph:hypothesis-%' OR activity LIKE"
                " 'graph:verification-task-%'"):
            meta = json.loads(r["metadata_json"])
            if (meta.get("hypothesis_id") == hypothesis_id or
                    meta.get("hypothesis_ids") == [hypothesis_id]):
                prov_refs.append(r["provenance_id"])
        prov_refs = tuple(sorted(prov_refs))
        payload = {
            "hypothesis_id": hypothesis_id,
            "current_status": hyp.status,
            "created_seq": min((e.seq for e in entries), default=0),
            "tasks": [t.task_id for t in tasks],
            "verdicts": [v.verdict_id for v in verdicts],
            "timeline": [(e.seq, e.label, e.actor, e.detail)
                         for e in entries],
            "provenance_refs": list(prov_refs),
        }
        return EvolutionView(
            hypothesis_id=hypothesis_id, current_status=hyp.status,
            created_seq=min((e.seq for e in entries), default=0),
            tasks=tasks, verdicts=verdicts, timeline=tuple(entries),
            provenance_refs=prov_refs,
            fingerprint=self.view_fingerprint(payload))

    def list_evolution_views(self) -> list[EvolutionView]:
        """全部 hypothesis 的视图（canonical 排序——by hypothesis_id）。"""
        ids = []
        for r in self.connection.execute(
                "SELECT metadata_json FROM akb_provenance WHERE activity ="
                " 'graph:hypothesis-create'"):
            hid = json.loads(r["metadata_json"]).get("hypothesis_id")
            if hid and hid not in ids:
                ids.append(hid)
        views = [self.get_evolution_view(h) for h in sorted(set(ids))]
        return [v for v in views if v is not None]