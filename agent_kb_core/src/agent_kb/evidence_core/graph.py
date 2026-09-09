# -*- coding: utf-8 -*-
"""Graph projection（V0.1）：PATH A Migration Backfill / PATH B Runtime Projection 严格分离。"""
from __future__ import annotations

import sqlite3

PROJECTION_ALLOWED_STATUS = {"validated", "asserted"}  # PATH B 唯一准入


class ProjectionError(RuntimeError):
    pass


class GraphProjection:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def project_edge(self, *, assertion_id: str, source_ref: str, target_ref: str,
                     predicate_ref: str, domain: str = "obc_dcdc",
                     actor_id: str = "system:projector",
                     properties: dict | None = None) -> str:
        """PATH B — Runtime Projection：仅 validated/asserted 可进入（V0.1-GRAPH-001A）。"""
        row = self.connection.execute(
            "SELECT status, confidence FROM akb_assertions WHERE assertion_id = ?",
            (assertion_id,)).fetchone()
        if row is None:
            raise LookupError(f"E-NOT-FOUND: {assertion_id}")
        if row["status"] not in PROJECTION_ALLOWED_STATUS:
            raise ValueError(
                f"E-ILLEGAL-PROJECTION: status={row['status']} not projectable "
                f"(PATH B requires {'/'.join(sorted(PROJECTION_ALLOWED_STATUS))})")
        from agent_kb.evidence_core.ids import mint_id
        edge_id = f"edge_{mint_id('provenance')[5:]}"  # 复用铸造器生成非语义后缀
        try:
            self.connection.execute(
                "INSERT INTO graph_edges (edge_id, domain, relation_type, source_object_id,"
                " target_object_id, properties_json, evidence_ids_json, confidence, status,"
                " updated_at, assertion_ref)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'projected', strftime('%Y-%m-%dT%H:%M:%SZ','now'), ?)",
                (edge_id, domain, predicate_ref, source_ref, target_ref,
                 __import__("json").dumps(properties or {}, ensure_ascii=False),
                 "[]", row["confidence"] if row["confidence"] is not None else 1.0, assertion_id))
        except sqlite3.Error as exc:  # 投影失败 → 回滚本操作，Canonical 零变更（INV-006）
            raise ProjectionError(f"E-PROJECTION-FAILED: {exc}") from exc
        return edge_id

    def backfill_legacy_edge(self, *, edge_rowid: int, assertion_id: str) -> None:
        """PATH A — Migration Backfill：legacy 边 ↔ candidate 断言兼容性链接
        （仅迁移脚本调用；不做状态检查——candidate 合法，MIGRATION_PLAN §3）。"""
        cur = self.connection.execute(
            "UPDATE graph_edges SET assertion_ref = ? WHERE rowid = ?",
            (assertion_id, edge_rowid))
        if cur.rowcount != 1:
            raise LookupError(f"E-NOT-FOUND: graph_edges rowid={edge_rowid}")

    def verify_integrity(self) -> dict:
        """assertion_ref 完整性巡检。"""
        total, linked, broken = self.connection.execute(
            "SELECT COUNT(*),"
            " SUM(assertion_ref IS NOT NULL),"
            " SUM(assertion_ref IS NOT NULL AND NOT EXISTS"
            "     (SELECT 1 FROM akb_assertions a WHERE a.assertion_id = graph_edges.assertion_ref))"
            " FROM graph_edges").fetchone()
        return {"total_edges": total, "backfilled": linked or 0, "broken_refs": broken or 0}