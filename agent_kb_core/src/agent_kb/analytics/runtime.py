# -*- coding: utf-8 -*-
"""V0.12 Knowledge Analytics Runtime（AKB-V12-IMPL-001；设计 docs/V0.12/）。

第八层（观察/理解层）：七层 frozen 产物 → 确定性聚合 → KnowledgeMetricReport。

三不变量：Observation ≠ Truth（零 assertion/flag/status 写入）·
Proposal ≠ Decision（报告↛proposal/task 零自动桥）· Human = Final authority。

Metric 白名单（禁止扩展——扩展需新任务书）：
  M001 knowledge_growth——assertion/node/edge 计数（禁止解释原因）
  M002 knowledge_drift——lifecycle change/evolution event 计数（只描述量，
       禁止 drift→correction）
  M003 governance_efficiency——created proposals / completed reviews 比例
       （禁止评价 human decision 正确性）
  M004 proposal_resolution_rate——proposal lifecycle 分布（禁止
       accepted=truth/rejected=false 推断）
  M005 causal_coverage_trend——causal projection count / knowledge size
       （禁止 more-causal=better 推断）

Identity：analytics_report_identity = "anr_"+SHA256(canonical_json(
  {scope, metrics}))——canonical JSON/sorted keys/round(4)/零 timestamp/random。
Storage：report 走 akb_provenance metadata（graph:analytics-report-create）
  ——migration 19 NOT REQUIRED（即时聚合可重算；触发条件已记录）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from agent_kb.reasoning.models import canonical_json

METRIC_WHITELIST = ("knowledge_growth", "knowledge_drift",
                    "governance_efficiency", "proposal_resolution_rate",
                    "causal_coverage_trend")
SCOPES = ("global",)
SCHEMA_VERSION = 1


class AnalyticsError(ValueError):
    """fail-closed：Analytics 错误。"""


@dataclass(frozen=True)
class KnowledgeMetricReport:
    """immutable 度量报告（观察 only——零执行语义）。"""
    report_id: str
    scope: str
    metrics: tuple                     # {"metric","value","detail"} canonical 序
    metric_count: int
    generated_from: str
    fingerprint: str
    schema_version: int


def analytics_report_identity(*, scope: str, metrics: tuple) -> str:
    """deterministic report_id：canonical JSON + sorted keys + round(4)
    （零 uuid/timestamp/random/memory address）。"""
    canon = sorted(
        ({"metric": m["metric"], "value": round(m["value"], 4),
          "detail": m["detail"]} for m in metrics),
        key=lambda x: x["metric"])
    payload = {"scope": scope, "metrics": canon}
    return "anr_" + hashlib.sha256(
        canonical_json(payload).encode("utf-8")).hexdigest()[:16]


class KnowledgeAnalyticsRuntime:
    """分析运行时（只读聚合——纯函数；零 mutation 零学习零推断）。"""

    def __init__(self, connection, actor_id: str = "system:analytics"):
        self.connection = connection
        self.actor_id = actor_id

    def _audit(self, *, activity: str, details: dict) -> str:
        from agent_kb.evidence_core.assertions import Provenance
        from agent_kb.evidence_core.state_machine import actor_kind_of
        details = dict(details)
        row = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_provenance WHERE activity LIKE"
            " 'graph:analytics-%'").fetchone()
        details["seq"] = (row["c"] if row else 0) + 1
        rec = Provenance(self.connection).record(
            actor_id=details.get("actor", self.actor_id),
            actor_kind=actor_kind_of(details.get("actor", self.actor_id)),
            activity=activity, inputs=details.get("targets", []),
            metadata=details)
        return rec.provenance_id

    # ---- 五 metrics（全部只读聚合——纯函数）----

    def _m_knowledge_growth(self) -> dict:
        n_a = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
        n_n = self.connection.execute(
            "SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"]
        n_e = self.connection.execute(
            "SELECT COUNT(*) c FROM kg_edges").fetchone()["c"]
        return {"metric": "knowledge_growth", "value": float(n_a),
                "detail": f"assertions={n_a};nodes={n_n};edges={n_e}"}

    def _m_knowledge_drift(self) -> dict:
        row = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_provenance WHERE activity LIKE"
            " 'transition:%'").fetchone()
        ev_count = row["c"] if row else 0
        return {"metric": "knowledge_drift", "value": float(ev_count),
                "detail": f"lifecycle_transitions={ev_count}"}

    def _m_governance_efficiency(self) -> dict:
        created = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_provenance WHERE activity ="
            " 'graph:maintenance-proposal-create'").fetchone()["c"]
        completed = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_provenance WHERE activity LIKE"
            " 'graph:verification-task-complete'").fetchone()["c"]
        ratio = (completed / created) if created else 0.0
        return {"metric": "governance_efficiency", "value": round(ratio, 4),
                "detail": f"proposals={created};completed_reviews={completed}"}

    def _m_proposal_resolution_rate(self) -> dict:
        counts = {"created": 0, "running": 0, "completed": 0, "failed": 0,
                  "cancelled": 0}
        for r in self.connection.execute(
                "SELECT metadata_json FROM akb_provenance WHERE activity ="
                " 'graph:verification-task-create'"):
            m = json.loads(r["metadata_json"])
            counts["created"] += 1
        for act, st in (("graph:verification-task-start", "running"),
                        ("graph:verification-task-complete", "completed"),
                        ("graph:verification-task-failed", "failed"),
                        ("graph:verification-task-cancel", "cancelled")):
            counts[st] = self.connection.execute(
                f"SELECT COUNT(*) c FROM akb_provenance WHERE activity ="
                f" '{act}'").fetchone()["c"]
        dist = ";".join(f"{k}={v}" for k, v in sorted(counts.items()))
        rate = round(counts["completed"] / max(1, counts["created"]), 4)
        return {"metric": "proposal_resolution_rate", "value": rate,
                "detail": f"lifecycle:{dist}"}

    def _m_causal_coverage_trend(self) -> dict:
        n_edges = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_causal_edges").fetchone()["c"]
        n_a = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_assertions").fetchone()["c"]
        ratio = round(n_edges / n_a, 4) if n_a else 0.0
        return {"metric": "causal_coverage_trend", "value": ratio,
                "detail": f"causal_edges={n_edges};assertions={n_a}"}

    # ---- 主入口 ----

    def create_report(self, *, scope: str = "global",
                      actor_id: str | None = None) -> KnowledgeMetricReport:
        """五 metric 白名单聚合（幂等：同库状态同 report + 零重复审计）。"""
        if scope not in SCOPES:
            raise AnalyticsError(
                f"E-V12-ANALYTICS-INVALID: scope {scope!r} not in {SCOPES}")
        metrics = tuple(sorted([
            self._m_knowledge_growth(), self._m_knowledge_drift(),
            self._m_governance_efficiency(), self._m_proposal_resolution_rate(),
            self._m_causal_coverage_trend(),
        ], key=lambda m: m["metric"]))
        report_id = analytics_report_identity(scope=scope, metrics=metrics)
        existing = self.get_report(report_id)
        if existing is not None:
            return existing                    # 幂等（零重复审计）
        fp_payload = {"report_id": report_id, "scope": scope,
                      "metrics": [dict(m) for m in metrics]}
        fingerprint = hashlib.sha256(
            canonical_json(fp_payload).encode("utf-8")).hexdigest()[:16]
        actor = actor_id or self.actor_id
        # metrics 摘要（payload 粒度——报告内容锚）
        metric_names = sorted(m["metric"] for m in metrics)
        self._audit(
            activity="graph:analytics-report-create",
            details={"targets": [scope], "report_id": report_id,
                     "scope": scope, "metric_names": metric_names,
                     "metrics": [dict(m) for m in metrics],
                     "fingerprint": fingerprint,
                     "generated_from": "snapshot:current", "actor": actor})
        return KnowledgeMetricReport(
            report_id=report_id, scope=scope, metrics=metrics,
            metric_count=len(metrics), generated_from="snapshot:current",
            fingerprint=fingerprint, schema_version=SCHEMA_VERSION)

    # ---- 读面（provenance 重放）----

    def get_report(self, report_id: str) -> KnowledgeMetricReport | None:
        if not report_id or not report_id.startswith("anr_"):
            raise AnalyticsError(
                f"E-V12-ANALYTICS-INVALID: bad id {report_id!r}")
        rows = []
        for r in self.connection.execute(
                "SELECT provenance_id, metadata_json FROM akb_provenance"
                " WHERE activity = 'graph:analytics-report-create'"):
            meta = json.loads(r["metadata_json"])
            if meta.get("report_id") != report_id:
                continue
            rows.append((meta, r["provenance_id"]))
        rows.sort(key=lambda x: x[0].get("seq", 0))
        if not rows:
            return None
        m, prov = rows[0]
        return KnowledgeMetricReport(
            report_id=report_id, scope=m["scope"],
            metrics=tuple(m["metrics"]), metric_count=len(m["metrics"]),
            generated_from=m.get("generated_from", ""),
            fingerprint=m["fingerprint"], schema_version=m.get(
                "schema_version", SCHEMA_VERSION))

    def list_reports(self, *, cursor: str | None = None,
                     limit: int = 100) -> dict:
        """只读分页（V0.10/0.11 keyset cursor 模式复用）。"""
        if not isinstance(limit, int) or limit < 1 or limit > 500:
            raise AnalyticsError(
                f"E-V12-ANALYTICS-INVALID: limit {limit!r} out of range"
                " (1..500)")
        rows = []
        for r in self.connection.execute(
                "SELECT provenance_id, metadata_json FROM akb_provenance"
                " WHERE activity = 'graph:analytics-report-create'"):
            meta = json.loads(r["metadata_json"])
            rows.append({"report_id": meta["report_id"],
                         "scope": meta["scope"],
                         "fingerprint": meta["fingerprint"],
                         "metric_names": meta.get("metric_names", [])})
        rows.sort(key=lambda r: r["report_id"])
        if cursor is not None:
            fp, body = cursor.split(".", 1) if "." in cursor else ("", "")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise AnalyticsError(
                    "E-V12-ANALYTICS-INVALID: cursor malformed") from exc
            if (not isinstance(payload, dict) or
                    payload.get("kind") != "analytics_reports"):
                raise AnalyticsError(
                    "E-V12-ANALYTICS-INVALID: cursor kind mismatch")
            check = hashlib.sha256(canonical_json(payload).encode(
                "utf-8")).hexdigest()[:8]
            if check != fp:
                raise AnalyticsError(
                    "E-V12-ANALYTICS-INVALID: cursor fingerprint mismatch")
            last = payload.get("last_key", "")
            rows = [r for r in rows if r["report_id"] > last]
        page = rows[:limit]
        has_more = len(rows) > limit
        next_cursor = None
        if has_more and page:
            payload = {"kind": "analytics_reports",
                       "last_key": page[-1]["report_id"]}
            next_cursor = hashlib.sha256(canonical_json(payload).encode(
                "utf-8")).hexdigest()[:8] + "." + canonical_json(payload)
        return {"kind": "analytics_reports", "items": page,
                "count": len(page), "has_more": has_more,
                "next_cursor": next_cursor}