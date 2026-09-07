# -*- coding: utf-8 -*-
"""CausalProjection Runtime（AKB-V09-IMPL-001；设计 docs/V0.9/ §3/ARCHITECTURE §3）。

因果投影只读运行时：因果谓词断言（causes/caused_by/enables/prevents）之上
派生独立 CausalProjection（零 kg_*/零 akb_assertions 写入）。

MIGRATION DECISION（IMPL-001）：**NO MIGRATION**——本阶段只实现 projection
runtime；投影以内存 immutable 对象 + graph:causal-projection-create 审计快照
（akb_provenance metadata）存在。migration 16（akb_causal_edges）验证结论：
仅在因果边需要跨进程索引查询（IMPL-002 KnowledgeHealth 批量信号/IMPL-003
ConflictRuntime 检测）时必要——留给 IMPL-002/003 任务书决策；单次投影/查询
场景 provenance-only + 内存重投影完全可行（本阶段实测）。

因果边界五律实现：
1. CausalRelation ≠ Assertion——CausalEdge 零 akb_assertions 写入（断言内容
   经 V0.4 既有通道产生，本 runtime 只读消费）；
2. CausalProjection ≠ Graph Mutation——零 kg_nodes/kg_edges 写入；
3. Projection rebuildable——同（断言快照 + 因果规格）→ 同 projection_id/
   fingerprint（canonical JSON）；
4. Unknown causal relation fail-close——未知 relation_type/无效端点/缺
   provenance 全拒（E-V09-CAUSAL-INVALID，零 fabricate）。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from agent_kb.reasoning.models import canonical_json

CAUSAL_RELATION_TYPES = ("causes", "caused_by", "enables", "prevents")
CAUSAL_PREDICATES = ("causes", "caused_by", "enables", "prevents")


class CausalProjectionError(ValueError):
    """fail-closed：因果投影错误。"""


@dataclass(frozen=True)
class CausalEdge:
    """immutable 因果边（源 = 因果谓词断言；零独立事实地位）。"""
    causal_id: str
    source_ref: str
    target_ref: str
    relation_type: str
    condition_refs: tuple = ()
    mechanism_ref: str = ""
    confidence: float = 0.0
    provenance_refs: tuple = ()
    status: str = "valid"


@dataclass(frozen=True)
class CausalProjection:
    """immutable 因果投影（零写入面——纯派生视图）。"""
    projection_id: str
    source_snapshot: str
    causal_edges: tuple
    fingerprint: str
    generated_at: str


def causal_edge_identity(*, source_ref: str, target_ref: str,
                         relation_type: str, condition_refs: tuple,
                         mechanism_ref: str, assertion_id: str) -> str:
    """deterministic causal_id：同六元组 → 同 id（canonical JSON）。"""
    payload = {"source_ref": source_ref, "target_ref": target_ref,
               "relation_type": relation_type,
               "condition_refs": sorted(condition_refs),
               "mechanism_ref": mechanism_ref,
               "assertion_id": assertion_id}
    return "ce_" + hashlib.sha256(
        canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def snapshot_identity(assertions: list) -> str:
    """断言快照 identity：canonical（assertion_id 集合的确定性摘要）。"""
    ids = sorted(a["assertion_id"] if isinstance(a, dict) else a
                 for a in assertions)
    return "snap_" + hashlib.sha256(
        canonical_json(ids).encode("utf-8")).hexdigest()[:16]


class CausalProjectionRuntime:
    """因果投影运行时（只读派生；零 kg_*/零 assertions 写入）。"""

    def __init__(self, connection, actor_id: str = "system:causal"):
        self.connection = connection
        self.actor_id = actor_id

    # ---- helpers ----

    def _audit(self, *, activity: str, details: dict) -> str:
        from agent_kb.evidence_core.assertions import Provenance
        from agent_kb.evidence_core.state_machine import actor_kind_of
        details = dict(details)
        row = self.connection.execute(
            "SELECT COUNT(*) c FROM akb_provenance WHERE activity LIKE"
            " 'graph:causal-%'").fetchone()
        details["seq"] = (row["c"] if row else 0) + 1
        rec = Provenance(self.connection).record(
            actor_id=details.get("actor", self.actor_id),
            actor_kind=actor_kind_of(details.get("actor", self.actor_id)),
            activity=activity, inputs=details.get("domains", []),
            metadata=details)
        return rec.provenance_id

    def _load_causal_assertions(self) -> list[dict]:
        """加载因果谓词断言（V0.5 只读面——零状态过滤放宽：invalidated 排除）。"""
        rows = [dict(r) for r in self.connection.execute(
            "SELECT assertion_id, subject_ref, predicate_ref, object_value,"
            " object_entity_ref, status, confidence, provenance_ref"
            " FROM akb_assertions WHERE predicate_ref IN"
            f" ({','.join('?' for _ in CAUSAL_PREDICATES)})",
            CAUSAL_PREDICATES)]
        # V0.5 状态语义：invalidated 排除（rejected/deprecated）
        return [r for r in rows if r["status"] not in ("rejected", "deprecated")]

    # ---- 主入口 ----

    def project(self, *, actor_id: str | None = None) -> CausalProjection:
        """从因果谓词断言全量派生 CausalProjection（幂等：同库状态同投影）。"""
        assertions = self._load_causal_assertions()
        snap = snapshot_identity(assertions)
        edges: list[CausalEdge] = []
        for a in assertions:
            # fail-closed：缺 provenance / 无效端点
            if not a["provenance_ref"]:
                raise CausalProjectionError(
                    f"E-V09-CAUSAL-INVALID: assertion {a['assertion_id']}"
                    " missing provenance")
            src = a["subject_ref"]
            tgt = a["object_entity_ref"] or a["object_value"]
            if not src or not tgt:
                raise CausalProjectionError(
                    f"E-V09-CAUSAL-INVALID: assertion {a['assertion_id']}"
                    " invalid endpoint")
            rel = a["predicate_ref"]
            if rel not in CAUSAL_RELATION_TYPES:
                raise CausalProjectionError(
                    f"E-V09-CAUSAL-INVALID: unknown relation {rel!r} on"
                    f" {a['assertion_id']}")
            edges.append(CausalEdge(
                causal_id=causal_edge_identity(
                    source_ref=src, target_ref=tgt, relation_type=rel,
                    condition_refs=(), mechanism_ref="",
                    assertion_id=a["assertion_id"]),
                source_ref=src, target_ref=tgt, relation_type=rel,
                condition_refs=(), mechanism_ref="",
                confidence=a["confidence"] or 0.0,
                provenance_refs=(a["provenance_ref"],),
                status="valid" if a["status"] in ("candidate", "validated",
                                                  "asserted") else
                        ("flagged" if a["status"] == "disputed" else "valid")))
        edges = tuple(sorted(edges, key=lambda e: e.causal_id))
        fingerprint = hashlib.sha256(canonical_json(
            [{"id": e.causal_id, "src": e.source_ref, "tgt": e.target_ref,
              "rel": e.relation_type, "status": e.status} for e in
             edges]).encode("utf-8")).hexdigest()[:16]
        projection_id = "cpr_" + hashlib.sha256(
            canonical_json({"snapshot": snap,
                            "fingerprint": fingerprint}).encode("utf-8")
        ).hexdigest()[:16]
        projection = CausalProjection(
            projection_id=projection_id, source_snapshot=snap,
            causal_edges=edges, fingerprint=fingerprint,
            generated_at=f"snapshot:{snap}")   # 无时间戳——快照锚即生成标识
        actor = actor_id or self.actor_id
        self._audit(
            activity="graph:causal-projection-create",
            details={"projection_id": projection_id,
                     "domains": sorted({e.source_ref for e in edges}),
                     "source_snapshot": snap, "fingerprint": fingerprint,
                     "causal_edge_count": len(edges),
                     "causal_edges": [e.causal_id for e in edges],
                     "actor": actor})
        return projection

    # ---- 只读查询面 ----

    def query_causal(self, projection: CausalProjection, *,
                     effect_ref: str | None = None) -> list[CausalEdge]:
        """因果边查询（canonical 排序；按 effect 过滤可选）。"""
        out = [e for e in projection.causal_edges
               if effect_ref is None or e.target_ref == effect_ref]
        return sorted(out, key=lambda e: e.causal_id)