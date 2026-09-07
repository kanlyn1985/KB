# -*- coding: utf-8 -*-
"""KnowledgeHealth Runtime（AKB-V09-IMPL-002；设计 docs/V0.9/ §4/ARCHITECTURE §4）。

知识健康只读观察层：Knowledge → Health Analyzer → KnowledgeHealth。
Health ≠ Truth ≠ Mutation——零知识修改、零 promotion、零 assertion/graph 写入。

四类信号（只读）：
1. stability     ——provenance history 变更频率（transition 审计计数）
2. verification  ——hypothesis/task/verdict 验证记录关联（V0.8 读面）
3. conflict      ——existing conflict 标注读取（V0.3 flagged 断言；零自动产生）
4. causal_coverage ——CausalProjection 中该目标是否具因果上下文（IMPL-001 读面）

MIGRATION DECISION（IMPL-002）：**NO MIGRATION 维持**——健康信号为单次只读
聚合（同状态同报告），graph:knowledge-health-create 审计快照足够；跨进程历史
趋势查询（信号时序对比）当前无消费方——migration 16（akb_health_signals）继续
留给出现历史趋势消费方时的任务书决策。

deterministic：health_id = "khs_"+SHA256(canonical_json({target, snapshot,
signals}))——同输入同 id；零 timestamp/零 random/零 runtime ordering。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from agent_kb.reasoning.models import canonical_json


class KnowledgeHealthError(ValueError):
    """fail-closed：KnowledgeHealth 错误。"""


@dataclass(frozen=True)
class KnowledgeHealth:
    """immutable 健康视图（只读信号聚合——零知识修改语义）。"""
    health_id: str
    target_ref: str
    target_type: str
    signals: tuple                # {"type","value","detail"} canonical 序
    score: float                  # 0..1 确定性聚合（信号加权和）
    status: str                   # "healthy" | "watch" | "degraded"
    provenance_refs: tuple
    fingerprint: str


class KnowledgeHealthRuntime:
    """健康信号运行时（只读聚合；零写入）。"""

    SIGNAL_TYPES = ("stability", "verification", "conflict", "causal_coverage")

    def __init__(self, connection, causal_runtime=None,
                 actor_id: str = "system:health"):
        self.connection = connection
        self._cr = causal_runtime
        self.actor_id = actor_id

    # ---- helpers ----

    def _audit(self, *, activity: str, details: dict) -> str:
        from agent_kb.evidence_core.assertions import Provenance
        from agent_kb.evidence_core.state_machine import actor_kind_of
        details = dict(details)
        row = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_provenance WHERE activity LIKE"
            " 'graph:knowledge-health-%'").fetchone()
        details["seq"] = (row["c"] if row else 0) + 1
        rec = Provenance(self.connection).record(
            actor_id=details.get("actor", self.actor_id),
            actor_kind=actor_kind_of(details.get("actor", self.actor_id)),
            activity=activity, inputs=details.get("targets", []),
            metadata=details)
        return rec.provenance_id

    @staticmethod
    def _score(signals: tuple) -> float:
        """确定性健康分：加权聚合（0..1；stability/verification/causal/逆冲突）。"""
        vals = {s["type"]: s["value"] for s in signals}
        stability = vals.get("stability", 1.0)          # 1=稳定
        verification = min(vals.get("verification", 0.0), 1.0)
        conflict = vals.get("conflict", 0.0)            # 0=无冲突
        coverage = min(vals.get("causal_coverage", 0.0), 1.0)
        score = (0.3 * stability + 0.3 * verification +
                 0.2 * (1.0 - conflict) + 0.2 * coverage)
        return round(score, 4)

    @staticmethod
    def _status(score: float) -> str:
        if score >= 0.7:
            return "healthy"
        if score >= 0.4:
            return "watch"
        return "degraded"

    # ---- 信号计算（全部只读）----

    def _stability_signal(self, assertion_id: str) -> dict:
        """变更频率：该断言相关 transition 审计计数（0 次=最稳定 1.0）。"""
        # V0.4 transition 审计：活动名 "transition:<from>-><to>"（动态）、
        # assertion_id 在 inputs_json 列（record 的 inputs 参数）
        row = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_provenance WHERE activity LIKE"
            " 'transition:%' AND inputs_json LIKE ?",
            (f'%{assertion_id}%',)).fetchone()
        count = row["c"] if row else 0
        value = 1.0 / (1.0 + count)     # 单调递减：变更越多越不稳定
        return {"type": "stability", "value": round(value, 4),
                "detail": f"transitions={count}"}

    def _verification_signal(self, target_ref: str) -> dict:
        """验证记录关联：target 相关 hypothesis 的 verdict 数（V0.8 读面）。
        关联语义：verdict 的 hypothesis statement 文本含 target 名
        （确定性文本关联——target_ref=assertion_id 时取 subject 值维度）。"""
        hs = None
        try:
            from agent_kb.hypothesis import HypothesisService
            hs = HypothesisService(self.connection)
        except Exception:
            hs = None
        n = 0
        for r in self.connection.execute(
                "SELECT metadata_json FROM akb_provenance WHERE activity ="
                " 'graph:hypothesis-verdict'"):
            m = json.loads(r["metadata_json"])
            hid = m.get("hypothesis_id", "")
            matched = target_ref == hid
            if not matched and hs is not None:
                hyp = hs.get_hypothesis(hid)
                if hyp is not None and target_ref in hyp.statement:
                    matched = True
            if matched:
                n += 1
        return {"type": "verification", "value": n, "detail": f"verdicts={n}"}

    def _conflict_signal(self, target_ref: str) -> dict:
        """existing conflict：V0.3 flagged 断言读取（零自动产生）。"""
        row = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_assertions WHERE status='disputed'"
            " AND (subject_ref=? OR object_value=?)",
            (target_ref, target_ref)).fetchone()
        n = row["c"] if row else 0
        return {"type": "conflict", "value": n, "detail": f"flagged={n}"}

    def _causal_coverage_signal(self, target_ref: str,
                                projection) -> dict:
        """因果上下文覆盖：目标在 CausalProjection 中的边数。"""
        n = len([e for e in projection.causal_edges
                 if e.source_ref == target_ref or e.target_ref == target_ref])
        return {"type": "causal_coverage", "value": n,
                "detail": f"causal_edges={n}"}

    # ---- 主入口 ----

    def create_health(self, *, target_ref: str, target_type: str = "assertion",
                      causal_projection=None,
                      actor_id: str | None = None) -> KnowledgeHealth:
        """聚合四信号 → KnowledgeHealth（幂等：同状态同 id，零重复审计）。"""
        if not target_ref or not target_ref.strip():
            raise KnowledgeHealthError(
                f"E-V09-HEALTH-INVALID: empty target_ref")
        if target_type not in ("assertion", "entity", "hypothesis"):
            raise KnowledgeHealthError(
                f"E-V09-HEALTH-INVALID: target_type {target_type!r}")
        # 断言存在性（fail-closed——target_type=assertion 时）
        if target_type == "assertion":
            row = self.connection.execute(
                "SELECT 1 FROM akb_assertions WHERE assertion_id=?",
                (target_ref,)).fetchone()
            if row is None:
                raise KnowledgeHealthError(
                    f"E-V09-HEALTH-INVALID: assertion {target_ref} not found")
        # causal projection（注入或即时生成）
        if causal_projection is None:
            if self._cr is None:
                from agent_kb.causal import CausalProjectionRuntime
                self._cr = CausalProjectionRuntime(self.connection)
            causal_projection = self._cr.project()
        # 快照 identity（同输入锚）
        snap = hashlib.sha256(canonical_json({
            "target_ref": target_ref, "target_type": target_type,
            "causal_fingerprint": causal_projection.fingerprint,
            "signal_inputs": True}).encode("utf-8")).hexdigest()[:16]
        signals_raw = [
            self._stability_signal(target_ref),
            self._verification_signal(target_ref),
            self._conflict_signal(target_ref),
            self._causal_coverage_signal(target_ref, causal_projection),
        ]
        signals = tuple(sorted(signals_raw, key=lambda s: s["type"]))
        score = self._score(signals)
        health_id = "khs_" + hashlib.sha256(canonical_json({
            "target_ref": target_ref, "target_type": target_type,
            "snapshot": snap, "signals": signals}).encode("utf-8")
        ).hexdigest()[:16]
        existing = self.get_health(health_id)
        if existing is not None:
            return existing                     # 幂等（零重复审计）
        fingerprint = hashlib.sha256(canonical_json({
            "health_id": health_id, "score": score,
            "status": self._status(score)}).encode("utf-8")).hexdigest()[:16]
        # provenance_refs：目标相关审计（存在的 provenance_id）
        prov_refs = []
        for r in self.connection.execute(
                "SELECT provenance_id, metadata_json FROM akb_provenance"
                " WHERE activity LIKE 'graph:hypothesis-%' OR activity LIKE"
                " 'graph:verification-task-%'"):
            if target_ref in r["metadata_json"]:
                prov_refs.append(r["provenance_id"])
        prov_refs = tuple(sorted(prov_refs))
        actor = actor_id or self.actor_id
        self._audit(
            activity="graph:knowledge-health-create",
            details={"health_id": health_id, "targets": [target_ref],
                     "target_ref": target_ref, "target_type": target_type,
                     "signals": signals, "score": score,
                     "status": self._status(score), "fingerprint": fingerprint,
                     "snapshot": snap, "actor": actor})
        return KnowledgeHealth(
            health_id=health_id, target_ref=target_ref,
            target_type=target_type, signals=signals, score=score,
            status=self._status(score), provenance_refs=prov_refs,
            fingerprint=fingerprint)

    def get_health(self, health_id: str) -> KnowledgeHealth | None:
        """provenance 重放重建（不存在 → None 不 fabricate）。"""
        if not health_id or not health_id.startswith("khs_"):
            raise KnowledgeHealthError(f"E-V09-HEALTH-INVALID: bad id {health_id!r}")
        rows = []
        for r in self.connection.execute(
                "SELECT provenance_id, metadata_json FROM akb_provenance"
                " WHERE activity = 'graph:knowledge-health-create'"):
            meta = json.loads(r["metadata_json"])
            if meta.get("health_id") != health_id:
                continue
            rows.append((meta, r["provenance_id"]))
        rows.sort(key=lambda x: x[0].get("seq", 0))
        if not rows:
            return None
        m, _pid = rows[0]
        return KnowledgeHealth(
            health_id=health_id, target_ref=m["target_ref"],
            target_type=m["target_type"],
            signals=tuple(m["signals"]), score=m["score"],
            status=m["status"],
            provenance_refs=tuple(sorted(m.get("provenance_refs", []))),
            fingerprint=m["fingerprint"])