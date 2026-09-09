# -*- coding: utf-8 -*-
"""V0.10 Persistence Adapter（AKB-V10-IMPL-001；设计 docs/V0.10/ §2/ARCHITECTURE）。

三 runtime（causal/health/conflict）的持久化基础层——API 零破坏（只新增
persist_* 方法集合，runtime identity 算法零修改）。

MIGRATION 16：akb_causal_edges / akb_health_signals / akb_conflict_records
（append-only 三新表——V0.10_DESIGN §3；零修改既有表；rollback = drop 可重建）。

原则：
- deterministic identity 零新算法——persist 对象携带 runtime 已派生的
  causal_id/health_id/conflict_id/fingerprint（零重算）；
- idempotent：同 id 重复 persist 零重复写入（INSERT OR IGNORE 语义 +
  first_write 标志）；
- transaction/rollback：每 persist 单事务（异常 → ROLLBACK TO SAVEPOINT）；
- 零 kg_*/akb_assertions/akb_provenance schema 写入。
"""
from __future__ import annotations

import json

from agent_kb.reasoning.models import canonical_json


class PersistError(ValueError):
    """fail-closed：持久化错误。"""


class ScalePersistenceRuntime:
    """V0.10 持久化基础层（三 runtime 共用模式——零新 identity 算法）。"""

    def __init__(self, connection, actor_id: str = "system:scale-persist"):
        self.connection = connection
        self.actor_id = actor_id

    # ---- helpers ----

    def _require_migration16(self) -> None:
        row = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND"
            " name='akb_causal_edges'").fetchone()
        if row is None:
            raise PersistError(
                "E-V10-PERSIST-INVALID: migration 16 not applied")

    def _validated_write(self, *, table: str, obj_id: str,
                         insert_sql: str, params: tuple) -> bool:
        """单事务幂等写入（first_write 标志；异常 ROLLBACK TO SAVEPOINT）。"""
        self._require_migration16()
        # 幂等检查（按主键）
        pk_col = {"akb_causal_edges": "causal_edge_id",
                  "akb_health_signals": "signal_id",
                  "akb_conflict_records": "conflict_id"}[table]
        dup = self.connection.execute(
            f"SELECT 1 FROM {table} WHERE {pk_col}=?", (obj_id,)).fetchone()
        if dup is not None:
            return False                          # 已存在——零重复写入
        sp = f"sp_v10persist_{obj_id[:12]}"
        self.connection.execute(f"SAVEPOINT {sp}")
        try:
            self.connection.execute(insert_sql, params)
            self.connection.execute(f"RELEASE {sp}")
            return True                           # first_write
        except Exception:
            self.connection.execute(f"ROLLBACK TO {sp}")
            self.connection.execute(f"RELEASE {sp}")
            raise

    # ---- 1. causal edges ----

    def persist_causal_edges(self, projection, *,
                             actor_id: str | None = None) -> dict:
        """CausalProjection.causal_edges → akb_causal_edges（幂等批量）。

        assertion 锚解析：CausalEdge.provenance_refs[0] = 源断言的
        provenance_ref（IMPL-001 语义）——按 provenance_ref 反查
        akb_assertions.assertion_id（FK 合法实体要求）；反查失败 fail-closed。
        """
        written = 0
        for e in projection.causal_edges:
            prov = e.provenance_refs[0] if e.provenance_refs else None
            if not prov:
                raise PersistError(
                    f"E-V10-PERSIST-INVALID: edge {e.causal_id} missing"
                    " provenance anchor")
            arow = self.connection.execute(
                "SELECT assertion_id FROM akb_assertions WHERE"
                " provenance_ref=?", (prov,)).fetchone()
            if arow is None:
                raise PersistError(
                    f"E-V10-PERSIST-INVALID: edge {e.causal_id} provenance"
                    f" {prov} resolves to no assertion (FK anchor missing)")
            first = self._validated_write(
                table="akb_causal_edges", obj_id=e.causal_id,
                insert_sql=(
                    "INSERT INTO akb_causal_edges (causal_edge_id, cause_ref,"
                    " effect_ref, relation_type, condition_refs_json,"
                    " mechanism_ref, assertion_id, status, confidence,"
                    " provenance_ref, fingerprint) VALUES"
                    " (?,?,?,?,?,?,?,?,?,?,?)"),
                params=(e.causal_id, e.source_ref, e.target_ref,
                        e.relation_type,
                        canonical_json(list(e.condition_refs)),
                        e.mechanism_ref, arow["assertion_id"],
                        e.status, e.confidence, prov,
                        projection.fingerprint))
            written += 1 if first else 0
        return {"projection_id": projection.projection_id,
                "fingerprint": projection.fingerprint,
                "edges_total": len(projection.causal_edges),
                "edges_written": written}

    # ---- 2. health signals ----

    def persist_health_signals(self, health, *,
                               actor_id: str | None = None) -> dict:
        """KnowledgeHealth.signals → akb_health_signals（幂等批量）。"""
        written = 0
        for s in health.signals:
            sid = f"{health.health_id}:{s['type']}"
            first = self._validated_write(
                table="akb_health_signals", obj_id=sid,
                insert_sql=(
                    "INSERT INTO akb_health_signals (signal_id, target_ref,"
                    " target_type, signal_type, value, detail, health_id,"
                    " provenance_ref, computed_snapshot, fingerprint) VALUES"
                    " (?,?,?,?,?,?,?,?,?,?)"),
                params=(sid, health.target_ref, health.target_type,
                        s["type"], s["value"], s.get("detail", ""),
                        health.health_id,
                        health.provenance_refs[0]
                        if health.provenance_refs else "",
                        health.health_id, health.fingerprint))
            written += 1 if first else 0
        return {"health_id": health.health_id,
                "signals_total": len(health.signals),
                "signals_written": written}

    # ---- 3. conflict records ----

    def persist_conflict_records(self, records, *,
                                 actor_id: str | None = None) -> dict:
        """ConflictRecord 列表 → akb_conflict_records（幂等批量）。"""
        written = 0
        for r in records:
            first = self._validated_write(
                table="akb_conflict_records", obj_id=r.conflict_id,
                insert_sql=(
                    "INSERT INTO akb_conflict_records (conflict_id,"
                    " conflict_type, source_refs_json, target_refs_json,"
                    " severity, status, evidence_refs_json, fingerprint,"
                    " created_from_snapshot, provenance_ref) VALUES"
                    " (?,?,?,?,?,?,?,?,?,?)"),
                params=(r.conflict_id, r.conflict_type,
                        canonical_json(list(r.source_refs)),
                        canonical_json(list(r.target_refs)), r.severity,
                        r.status, canonical_json(list(r.evidence_refs)),
                        r.fingerprint, r.created_from_snapshot,
                        r.evidence_refs[0] if r.evidence_refs else
                        r.fingerprint))
            written += 1 if first else 0
        return {"conflicts_total": len(records),
                "conflicts_written": written}