# -*- coding: utf-8 -*-
"""V0.10 Persistence Query Layer（AKB-V10-IMPL-002；设计 ARCHITECTURE §3）。

migration 16/17 三表之上的 deterministic、cursor-based、read-only 查询面。

原则：
- cursor-based pagination（禁止 offset——深分页一致性）；cursor = keyset
  （最后一行的排序键）+ 类型指纹校验（防跨 query 复用/篡改——fail-close）；
- deterministic ordering：causal/conflict 按 PK ASC；health 按
  (fingerprint, signal_id) ASC（migration 17 索引锚）；
- read-only：零 INSERT/UPDATE/DELETE 面；零 identity 算法修改；
- health 时间过滤：from_time/to_time 走 akb_provenance.occurred_at JOIN
  （零 schema 变更——provenance_ref 关联）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from agent_kb.reasoning.models import canonical_json

PAGE_LIMIT_MAX = 500


class QueryError(ValueError):
    """fail-closed：查询层错误（含非法 cursor）。"""


@dataclass(frozen=True)
class QueryCursor:
    """deterministic cursor（keyset + 类型指纹校验）。"""
    query_kind: str
    last_key: str
    fingerprint: str

    def encode(self) -> str:
        payload = {"kind": self.query_kind, "last_key": self.last_key}
        return hashlib.sha256(canonical_json(payload).encode("utf-8")
                              ).hexdigest()[:8] + "." + canonical_json(payload)

    @classmethod
    def decode(cls, raw: str, *, expected_kind: str) -> "QueryCursor":
        if not raw or "." not in raw:
            raise QueryError(f"E-V10-QUERY-CURSOR-INVALID: {raw!r}")
        fp, body = raw.split(".", 1)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise QueryError(
                f"E-V10-QUERY-CURSOR-INVALID: malformed payload") from exc
        kind = payload.get("kind")
        last_key = payload.get("last_key")
        if kind != expected_kind:
            raise QueryError(
                f"E-V10-QUERY-CURSOR-INVALID: cursor kind {kind!r} not"
                f" usable for {expected_kind!r} (no cross-query reuse)")
        check = hashlib.sha256(canonical_json(payload).encode("utf-8")
                               ).hexdigest()[:8]
        if check != fp:
            raise QueryError(
                "E-V10-QUERY-CURSOR-INVALID: fingerprint mismatch")
        if not isinstance(last_key, str) or not last_key:
            raise QueryError(
                "E-V10-QUERY-CURSOR-INVALID: empty last_key")
        return cls(query_kind=kind, last_key=last_key, fingerprint=fp)


def _encode_cursor(kind: str, last_key: str) -> str:
    return QueryCursor(query_kind=kind, last_key=last_key,
                       fingerprint=hashlib.sha256(canonical_json(
                           {"kind": kind, "last_key": last_key}).encode(
                           "utf-8")).hexdigest()[:8]).encode()


def _normalize_limit(limit) -> int:
    if not isinstance(limit, int) or limit < 1:
        raise QueryError(
            f"E-V10-QUERY-PAGE-INVALID: limit {limit!r} must be int >= 1")
    if limit > PAGE_LIMIT_MAX:
        raise QueryError(
            f"E-V10-QUERY-PAGE-INVALID: limit {limit} exceeds cap"
            f" {PAGE_LIMIT_MAX}")
    return limit


class ScaleQueryRuntime:
    """只读查询面（三表 cursor 分页；零写入零 identity 修改）。"""

    def __init__(self, connection):
        self.connection = connection

    def _require_tables(self, *tables: str) -> None:
        for t in tables:
            row = self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND"
                f" name='{t}'").fetchone()
            if row is None:
                raise QueryError(
                    f"E-V10-QUERY-INVALID: table {t} missing (migration"
                    " 16 not applied)")

    # ---- 1. causal edges ----

    def list_causal_edges(self, *, snapshot_id: str | None = None,
                          cause_ref: str | None = None,
                          effect_ref: str | None = None,
                          relation: str | None = None,
                          cursor: str | None = None,
                          limit: int = 100) -> dict:
        self._require_tables("akb_causal_edges")
        limit = _normalize_limit(limit)
        where, params = ["1=1"], []
        if snapshot_id is not None:
            where.append("fingerprint = ?")
            params.append(snapshot_id)
        if cause_ref is not None:
            where.append("cause_ref = ?")
            params.append(cause_ref)
        if effect_ref is not None:
            where.append("effect_ref = ?")
            params.append(effect_ref)
        if relation is not None:
            where.append("relation_type = ?")
            params.append(relation)
        if cursor is not None:
            cur = QueryCursor.decode(cursor, expected_kind="causal_edges")
            where.append("causal_edge_id > ?")
            params.append(cur.last_key)
        wsql = " AND ".join(where)
        rows = [dict(r) for r in self.connection.execute(
            f"SELECT * FROM akb_causal_edges WHERE {wsql}"
            f" ORDER BY causal_edge_id ASC LIMIT ?", (*params, limit + 1))]
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = _encode_cursor(
            "causal_edges", rows[-1]["causal_edge_id"]) if has_more and rows \
            else None
        return {"kind": "causal_edges", "items": rows,
                "count": len(rows), "has_more": has_more,
                "next_cursor": next_cursor}

    # ---- 2. health signals ----

    def list_health_signals(self, *, target_ref: str | None = None,
                            signal_type: str | None = None,
                            from_time: str | None = None,
                            to_time: str | None = None,
                            cursor: str | None = None,
                            limit: int = 100) -> dict:
        self._require_tables("akb_health_signals")
        limit = _normalize_limit(limit)
        where, params = ["1=1"], []
        if target_ref is not None:
            where.append("hs.target_ref = ?")
            params.append(target_ref)
        if signal_type is not None:
            where.append("hs.signal_type = ?")
            params.append(signal_type)
        if from_time is not None or to_time is not None:
            # 时间语义 = 产生该 health 的 provenance occurred_at（JOIN 只读面）
            if from_time is not None:
                where.append("p.occurred_at >= ?")
                params.append(from_time)
            if to_time is not None:
                where.append("p.occurred_at <= ?")
                params.append(to_time)
        if cursor is not None:
            cur = QueryCursor.decode(cursor, expected_kind="health_signals")
            where.append("(hs.fingerprint > ? OR (hs.fingerprint = ? AND"
                         " hs.signal_id > ?))")
            params.extend([cur.last_key.split("|", 1)[0],
                           cur.last_key.split("|", 1)[0],
                           cur.last_key.split("|", 1)[1]
                           if "|" in cur.last_key else ""])
        wsql = " AND ".join(where)
        rows = [dict(r) for r in self.connection.execute(
            f"SELECT hs.*, p.occurred_at AS occurred_at FROM"
            f" akb_health_signals hs LEFT JOIN akb_provenance p ON"
            f" p.provenance_id = hs.provenance_ref WHERE {wsql}"
            f" ORDER BY hs.fingerprint ASC, hs.signal_id ASC LIMIT ?",
            (*params, limit + 1))]
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = _encode_cursor(
                "health_signals",
                f"{last['fingerprint']}|{last['signal_id']}")
        return {"kind": "health_signals", "items": rows,
                "count": len(rows), "has_more": has_more,
                "next_cursor": next_cursor}

    # ---- 3. conflict records ----

    def list_conflicts(self, *, conflict_type: str | None = None,
                       severity: str | None = None,
                       status: str | None = None,
                       cursor: str | None = None,
                       limit: int = 100) -> dict:
        self._require_tables("akb_conflict_records")
        limit = _normalize_limit(limit)
        where, params = ["1=1"], []
        if conflict_type is not None:
            where.append("conflict_type = ?")
            params.append(conflict_type)
        if severity is not None:
            where.append("severity = ?")
            params.append(severity)
        if status is not None:
            where.append("status = ?")
            params.append(status)
        if cursor is not None:
            cur = QueryCursor.decode(cursor, expected_kind="conflict_records")
            where.append("conflict_id > ?")
            params.append(cur.last_key)
        wsql = " AND ".join(where)
        rows = [dict(r) for r in self.connection.execute(
            f"SELECT * FROM akb_conflict_records WHERE {wsql}"
            f" ORDER BY conflict_id ASC LIMIT ?", (*params, limit + 1))]
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = _encode_cursor(
            "conflict_records", rows[-1]["conflict_id"]) if has_more and rows \
            else None
        return {"kind": "conflict_records", "items": rows,
                "count": len(rows), "has_more": has_more,
                "next_cursor": next_cursor}