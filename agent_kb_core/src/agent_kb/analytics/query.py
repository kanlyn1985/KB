# -*- coding: utf-8 -*-
"""V0.12 Analytics Query & Report Retrieval Layer（AKB-V12-IMPL-002）。

KnowledgeMetricReport 的 deterministic 查询/检索层——报告源唯一 =
akb_provenance（activity = graph:analytics-report-create）。

原则：
- cursor-based keyset pagination（复用 V0.10/0.11 模式；禁止 OFFSET）；
- cursor = canonical JSON + fingerprint 校验 + query binding（跨 query 复用
  拒绝）；
- ordering 固定 report_id ASC（零 created time/memory order/DB natural）；
- metric filter 白名单（五项——未知 metric fail-close）；
- READ-ONLY：查询零写面（不触发 create_report、零 proposal/task 桥）；
- Migration 19 NOT REQUIRED 维持（provenance metadata 即报告源）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from agent_kb.reasoning.models import canonical_json
from agent_kb.analytics.runtime import METRIC_WHITELIST

PAGE_LIMIT_MAX = 500
CURSOR_KIND = "analytics_report_query"


class AnalyticsQueryError(ValueError):
    """fail-closed：Analytics 查询错误。"""


@dataclass(frozen=True)
class AnalyticsQueryCursor:
    """deterministic cursor（keyset + 指纹校验 + query binding）。"""
    last_key: str
    fingerprint: str

    @staticmethod
    def encode(last_key: str) -> str:
        payload = {"kind": CURSOR_KIND, "last_key": last_key}
        return hashlib.sha256(canonical_json(payload).encode("utf-8")
                              ).hexdigest()[:8] + "." + canonical_json(payload)

    @staticmethod
    def decode(raw: str) -> str:
        if not raw or "." not in raw:
            raise AnalyticsQueryError(
                f"E-V12-QUERY-CURSOR-INVALID: malformed cursor {raw!r}")
        fp, body = raw.split(".", 1)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AnalyticsQueryError(
                "E-V12-QUERY-CURSOR-INVALID: invalid JSON payload") from exc
        if not isinstance(payload, dict) or payload.get("kind") != CURSOR_KIND:
            raise AnalyticsQueryError(
                "E-V12-QUERY-CURSOR-INVALID: wrong cursor kind (query"
                " binding violated)")
        check = hashlib.sha256(canonical_json(payload).encode("utf-8")
                               ).hexdigest()[:8]
        if check != fp:
            raise AnalyticsQueryError(
                "E-V12-QUERY-CURSOR-INVALID: fingerprint mismatch (tampered)")
        last_key = payload.get("last_key")
        if not isinstance(last_key, str) or not last_key:
            raise AnalyticsQueryError(
                "E-V12-QUERY-CURSOR-INVALID: empty last_key")
        return last_key


@dataclass(frozen=True)
class AnalyticsReportPage:
    """immutable 分页结果。"""
    items: tuple
    next_cursor: str | None
    has_more: bool


class AnalyticsQueryRuntime:
    """报告检索运行时（只读——零写面零桥接）。"""

    def __init__(self, connection):
        self.connection = connection

    def _load_rows(self) -> list[dict]:
        """唯一报告源：akb_provenance（graph:analytics-report-create）。"""
        rows = []
        for r in self.connection.execute(
                "SELECT provenance_id, metadata_json FROM akb_provenance"
                " WHERE activity = 'graph:analytics-report-create'"):
            meta = json.loads(r["metadata_json"])
            names = meta.get("metric_names", [])
            rows.append({"report_id": meta["report_id"],
                         "scope": meta.get("scope", ""),
                         "fingerprint": meta.get("fingerprint", ""),
                         "metric_names": tuple(sorted(names)),
                         "provenance_id": r["provenance_id"]})
        return rows

    def list_reports(self, *, scope: str | None = None,
                     metric: str | None = None, cursor: str | None = None,
                     limit: int = 100) -> AnalyticsReportPage:
        """确定性报告分页（report_id ASC；scope/metric 过滤白名单 fail-close）。"""
        if not isinstance(limit, int) or limit < 1 or limit > PAGE_LIMIT_MAX:
            raise AnalyticsQueryError(
                f"E-V12-QUERY-PAGE-INVALID: limit {limit!r} out of range"
                f" (1..{PAGE_LIMIT_MAX})")
        if metric is not None and metric not in METRIC_WHITELIST:
            raise AnalyticsQueryError(
                f"E-V12-QUERY-INVALID: metric {metric!r} not in whitelist"
                f" {METRIC_WHITELIST}")
        rows = self._load_rows()
        if scope is not None:
            rows = [r for r in rows if r["scope"] == scope]
        if metric is not None:
            rows = [r for r in rows if metric in r["metric_names"]]
        rows.sort(key=lambda r: r["report_id"])     # 固定 ordering
        if cursor is not None:
            last_key = AnalyticsQueryCursor.decode(cursor)
            rows = [r for r in rows if r["report_id"] > last_key]
        page = rows[:limit]
        has_more = len(rows) > limit
        next_cursor = AnalyticsQueryCursor.encode(
            page[-1]["report_id"]) if has_more and page else None
        return AnalyticsReportPage(items=tuple(page), next_cursor=next_cursor,
                                   has_more=has_more)