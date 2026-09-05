# -*- coding: utf-8 -*-
"""Graph Persistence（AKB-V05-IMPL-003；设计 docs/V0.5/）。

GraphPersistenceService：将 GraphProjectionService 的投影持久化到 kg_* 表
（migration 15）。

- 纯投影消费方（不修改 Evidence/Assertion/Document/Inference——KG-01）；
- deterministic/idempotent：同 projection 重复 persist → 零新增（fingerprint 锚）；
- transaction atomic：nodes/edges/metadata 同 SAVEPOINT，失败全回滚；
- invalidation：rejected/deprecated → invalidated、disputed → flagged、
  hypothesized 不投影（GP-CMP-014..017）；
- provenance：复用 akb_provenance（activity=graph:persist），零第二套系统；
- rebuild：drop → re-project → re-persist → 同 fingerprint（KG-02）。
"""
from __future__ import annotations

import json
import uuid

from agent_kb.kgraph.models import GraphProjection
from agent_kb.reasoning.models import canonical_json


class GraphPersistenceError(ValueError):
    """fail-closed 持久化错误（§21）。"""


class GraphRepository:
    """kg_* 表数据库操作层（SQL 唯一归属地）。"""

    def __init__(self, connection):
        self.connection = connection

    def has_schema(self) -> bool:
        return self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name='kg_nodes'").fetchone() is not None

    def find_projection_by_fingerprint(self, fingerprint: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM kg_projection_runs WHERE fingerprint=?",
            (fingerprint,)).fetchone()
        return dict(row) if row else None

    def insert_projection(self, *, projection_id: str, graph_version: str,
                          fingerprint: str, source_digest: str, node_count: int,
                          edge_count: int, actor_id: str, status: str = "active") -> None:
        self.connection.execute(
            "INSERT INTO kg_projection_runs (projection_id, graph_version, fingerprint,"
            " source_digest, node_count, edge_count, actor_id, status)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (projection_id, graph_version, fingerprint, source_digest, node_count,
             edge_count, actor_id, status))

    def supersede_projection(self, projection_id: str) -> None:
        self.connection.execute(
            "UPDATE kg_projection_runs SET status='superseded' WHERE projection_id=?",
            (projection_id,))

    def insert_node(self, *, node_id: str, node_type: str, source_id: str,
                    projection_id: str, status: str, payload: dict,
                    provenance_ref: str) -> None:
        self.connection.execute(
            "INSERT INTO kg_nodes (node_id, node_type, source_id, projection_id,"
            " status, payload_json, provenance_ref) VALUES (?,?,?,?,?,?,?)",
            (node_id, node_type, source_id, projection_id, status,
             canonical_json(payload), provenance_ref))

    def insert_edge(self, *, edge_id: str, edge_type: str, source_node: str,
                    target_node: str, projection_id: str, status: str,
                    payload: dict, provenance_ref: str) -> None:
        self.connection.execute(
            "INSERT INTO kg_edges (edge_id, edge_type, source_node, target_node,"
            " projection_id, status, payload_json, provenance_ref)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (edge_id, edge_type, source_node, target_node, projection_id, status,
             canonical_json(payload), provenance_ref))

    def log_invalidation(self, *, invalidation_id: str, node_id: str,
                         reason_status: str, graph_status: str, actor_id: str) -> None:
        self.connection.execute(
            "INSERT INTO kg_invalidation_log (invalidation_id, node_id, reason_status,"
            " graph_status, actor_id) VALUES (?,?,?,?,?)",
            (invalidation_id, node_id, reason_status, graph_status, actor_id))

    def node_status(self, node_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT status FROM kg_nodes WHERE node_id=?", (node_id,)).fetchone()
        return row["status"] if row else None

    def counts(self) -> dict:
        return {"nodes": self.connection.execute(
                    "SELECT COUNT(*) c FROM kg_nodes").fetchone()["c"],
                "edges": self.connection.execute(
                    "SELECT COUNT(*) c FROM kg_edges").fetchone()["c"],
                "projections": self.connection.execute(
                    "SELECT COUNT(*) c FROM kg_projection_runs").fetchone()["c"]}


class GraphPersistenceService:
    """持久化服务：projection → kg_* 表（事务原子 + 幂等 + fail-closed）。"""

    NODE_TYPE_MAP = {
        "DocumentNode": "document", "EvidenceNode": "evidence",
        "SemanticUnitNode": "semantic_unit", "AssertionNode": "assertion",
        "EntityNode": "entity", "InferenceNode": "inference",
    }
    EDGE_TYPE_MAP = {
        "ExtractedFromEdge": "extracted_from", "SupportsEdge": "supports",
        "ContradictsEdge": "contradicts", "DerivedFromEdge": "derived_from",
        "ValidatesEdge": "validates", "RelatesToEdge": "relates_to",
    }
    # 源断言状态 → graph 状态（§16/§9；hypothesized 不投影——上游已排除）
    STATUS_MAP = {
        "candidate": "valid", "validated": "valid", "asserted": "valid",
        "rejected": "invalidated", "deprecated": "invalidated",
        "disputed": "flagged",
    }

    def __init__(self, connection, repository: GraphRepository | None = None,
                 provenance=None):
        from agent_kb.evidence_core.assertions import Provenance
        self.connection = connection
        self.repo = repository or GraphRepository(connection)
        self.provenance = provenance or Provenance(connection)

    # ---- helpers ----

    def _node_payload(self, n) -> dict:
        from dataclasses import asdict, is_dataclass
        if is_dataclass(n):
            d = asdict(n)
            d.pop("node_id", None)
            return d
        return {"value": str(n)}

    def _edge_payload(self, e) -> dict:
        from dataclasses import asdict, is_dataclass
        if is_dataclass(e):
            d = asdict(e)
            d.pop("edge_id", None)
            return d
        return {"value": str(e)}

    def _graph_status_for(self, n) -> str:
        """节点级 graph status：源断言状态映射；非断言节点恒 valid。"""
        st = getattr(n, "status", None)
        if st is None:
            return "valid"
        return self.STATUS_MAP.get(st, "valid")

    def _audit(self, *, actor_id: str, activity: str, details: dict) -> str:
        from agent_kb.evidence_core.state_machine import actor_kind_of
        rec = self.provenance.record(
            actor_id=actor_id, actor_kind=actor_kind_of(actor_id), activity=activity,
            inputs=details.get("node_ids", []), metadata=details)
        return rec.provenance_id

    # ---- 主入口 ----

    def persist(self, projection: GraphProjection, *, actor_id: str = "system:kgraph",
                rebuild: bool = False) -> dict:
        """持久化一个 projection（事务原子；fingerprint 幂等）。

        - 同 fingerprint 已存在 → 幂等命中（零新增，GP-CMP-009/010）；
        - 新 fingerprint → supersede 旧 active 投影 + 写 nodes/edges/metadata；
        - 任一步失败 → SAVEPOINT 回滚（GP-CMP-011..013）。
        """
        if not projection.nodes:
            raise GraphPersistenceError("E-V05-EMPTY-PROJECTION")
        if not projection.fingerprint:
            raise GraphPersistenceError("E-V05-PROJECTION-NO-FINGERPRINT")
        if not self.repo.has_schema():
            raise GraphPersistenceError(
                "E-V05-NO-SCHEMA: migration 15 not applied to this database")
        hit = self.repo.find_projection_by_fingerprint(projection.fingerprint)
        if hit is not None:
            counts = self.repo.counts()
            return {"accepted": False, "idempotent_hit": True,
                    "projection_id": hit["projection_id"],
                    "fingerprint": projection.fingerprint,
                    "nodes": counts["nodes"], "edges": counts["edges"]}
        sp = f"sp_kgp_{uuid.uuid4().hex[:12]}"
        self.connection.execute(f"SAVEPOINT {sp}")
        try:
            projection_id = f"kgp_{uuid.uuid4().hex[:16]}"
            source_digest = projection.canonical_digest()
            # supersede 旧 active 投影（逻辑替换——不物理删除，§17）
            for old in self._rows(
                    self.connection,
                    "SELECT projection_id FROM kg_projection_runs WHERE status='active'"):
                self.repo.supersede_projection(old["projection_id"])
            self.repo.insert_projection(
                projection_id=projection_id, graph_version="v05-graph-1.0",
                fingerprint=projection.fingerprint, source_digest=source_digest,
                node_count=len(projection.nodes), edge_count=len(projection.edges),
                actor_id=actor_id)
            invalidations: list[dict] = []
            for n in projection.nodes:
                ntype = self.NODE_TYPE_MAP.get(type(n).__name__)
                if ntype is None:
                    raise GraphPersistenceError(
                        f"E-V05-INVALID-NODE: {type(n).__name__}")
                if not getattr(n, "provenance_ref", ""):
                    raise GraphPersistenceError(
                        f"E-V05-NO-PROVENANCE: node {n.node_id}")
                status = self._graph_status_for(n)
                if status not in ("valid", "invalidated", "flagged"):
                    raise GraphPersistenceError(
                        f"E-V05-INVALID-STATUS: {status}")
                src_id = getattr(n, "source_id", None) or getattr(n, "source_ref", "")\
                    or getattr(n, "canonical_id", "")
                self.repo.insert_node(
                    node_id=n.node_id, node_type=ntype, source_id=src_id,
                    projection_id=projection_id, status=status,
                    payload=self._node_payload(n),
                    provenance_ref=n.provenance_ref)
                if status in ("invalidated", "flagged"):
                    # reason 必须是源断言的真实状态（rejected/deprecated/disputed）——
                    # 不得从 graph_status 反推（fail-closed 语义，GP-CMP-014）
                    reason = getattr(n, "status", "") or ""
                    if reason not in ("rejected", "deprecated", "disputed"):
                        raise GraphPersistenceError(
                            f"E-V05-INVALID-INVALIDATION: {reason}")
                    inv_id = f"kgi_{uuid.uuid4().hex[:16]}"
                    self.repo.log_invalidation(
                        invalidation_id=inv_id, node_id=n.node_id,
                        reason_status=reason, graph_status=status, actor_id=actor_id)
                    invalidations.append({"node_id": n.node_id, "reason": reason})
            node_ids = {n.node_id for n in projection.nodes}
            for e in projection.edges:
                etype = self.EDGE_TYPE_MAP.get(type(e).__name__)
                if etype is None:
                    raise GraphPersistenceError(
                        f"E-V05-INVALID-EDGE: {type(e).__name__}")
                if e.source_node not in node_ids or e.target_node not in node_ids:
                    raise GraphPersistenceError(
                        f"E-V05-DANGLING-EDGE: {e.edge_id} endpoints not in"
                        " projection")
                if not getattr(e, "provenance_ref", ""):
                    raise GraphPersistenceError(
                        f"E-V05-NO-PROVENANCE: edge {e.edge_id}")
                self.repo.insert_edge(
                    edge_id=e.edge_id, edge_type=etype, source_node=e.source_node,
                    target_node=e.target_node, projection_id=projection_id,
                    status="valid", payload=self._edge_payload(e),
                    provenance_ref=e.provenance_ref)
            prov_id = self._audit(
                actor_id=actor_id, activity="graph:project",
                details={"projection_id": projection_id,
                         "fingerprint": projection.fingerprint,
                         "node_count": len(projection.nodes),
                         "edge_count": len(projection.edges),
                         "invalidations": invalidations, "rebuild": rebuild})
            self.connection.execute(f"RELEASE {sp}")
            return {"accepted": True, "idempotent_hit": False,
                    "projection_id": projection_id, "fingerprint": projection.fingerprint,
                    "nodes": len(projection.nodes), "edges": len(projection.edges),
                    "invalidations": invalidations, "provenance_ref": prov_id}
        except Exception:
            self.connection.execute(f"ROLLBACK TO {sp}")
            self.connection.execute(f"RELEASE {sp}")
            raise

    @staticmethod
    def _rows(db, sql: str) -> list[dict]:
        return [dict(r) for r in db.execute(sql)]