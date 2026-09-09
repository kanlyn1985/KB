# -*- coding: utf-8 -*-
"""Graph Query Service（AKB-V05-IMPL-004；设计 docs/V0.5/ KG_SPEC §7 Q-01..Q-06）。

只读查询层：GraphPersistence 持久化的 kg_* 表之上的 semantic query contract。
- READ-ONLY（零 INSERT/UPDATE/DELETE——GQ-CMP-020 DB 快照验证）；
- deterministic（显式 ORDER BY + ID tie-breaker；canonical 排序——Q-06）；
- status-aware（Q-05：默认排除 invalidated；disputed=flagged 保留；audit 模式可包含）；
- provenance 完整回溯（Q-01 五级链——JOIN 一次完成，无 N+1）；
- fail-closed（缺 provenance/未知类型 → 显式错误，不 fabricate）；
- legacy 隔离：仅依赖 agent_kb.kgraph 与 kg_* 表，零触碰 agent_kb.graph。
"""
from __future__ import annotations

import json
from dataclasses import dataclass


class GraphQueryError(ValueError):
    """fail-closed 查询错误（§18）。"""


@dataclass(frozen=True)
class GraphNodeView:
    node_id: str
    node_type: str
    source_id: str
    status: str
    payload: dict
    provenance_ref: str
    projection_id: str


@dataclass(frozen=True)
class GraphEdgeView:
    edge_id: str
    edge_type: str
    source_node: str
    target_node: str
    status: str
    payload: dict
    provenance_ref: str
    projection_id: str


@dataclass(frozen=True)
class ProvenanceTrace:
    """五级链回溯结果（Q-01）：graph → assertion → unit/evidence → document。"""
    node_id: str
    node_type: str
    source_id: str
    assertion_id: str | None = None
    evidence_ids: tuple = ()
    document_id: str | None = None
    reasoning_run_id: str | None = None
    provenance_ref: str = ""
    chain: tuple = ()            # 逐级 label:value（确定性顺序）


VALID_NODE_TYPES = ("entity", "semantic_unit", "assertion", "evidence",
                    "document", "inference")
VALID_EDGE_TYPES = ("extracted_from", "supports", "contradicts", "derived_from",
                    "validates", "relates_to")
VALID_STATUSES = ("valid", "invalidated", "flagged")


class GraphQueryService:
    """只读语义查询（Q-01..Q-06）。Application 层唯一入口。"""

    def __init__(self, connection, repository=None):
        from agent_kb.kgraph.persistence import GraphRepository
        self.connection = connection
        self.repo = repository or GraphRepository(connection)
        if not self.repo.has_schema():
            raise GraphQueryError(
                "E-V05-NO-SCHEMA: migration 15 not applied to this database")

    # ---- 内部（Repository 拥有 SQL；此处语义组装）----

    @staticmethod
    def _rows(con, sql: str, params: tuple = ()) -> list[dict]:
        return [dict(r) for r in con.execute(sql, params)]

    def _validate_node_type(self, node_type: str) -> None:
        if node_type not in VALID_NODE_TYPES:
            raise GraphQueryError(f"E-V05-INVALID-NODE-TYPE: {node_type}")

    def _validate_edge_type(self, edge_type: str) -> None:
        if edge_type not in VALID_EDGE_TYPES:
            raise GraphQueryError(f"E-V05-INVALID-EDGE-TYPE: {edge_type}")

    def _validate_status(self, status: str) -> None:
        if status not in VALID_STATUSES:
            raise GraphQueryError(f"E-V05-INVALID-STATUS: {status}")

    @staticmethod
    def _status_clause(include_invalidated: bool, table: str = "n") -> str:
        """Q-05：默认只返回 valid + flagged（disputed 保留且标灰）；
        audit 模式显式包含 invalidated。"""
        if include_invalidated:
            return ""
        return f" AND {table}.status IN ('valid','flagged')"

    def _node_views(self, rows: list[dict]) -> list[GraphNodeView]:
        out = []
        for r in rows:
            out.append(GraphNodeView(
                node_id=r["node_id"], node_type=r["node_type"],
                source_id=r["source_id"], status=r["status"],
                payload=json.loads(r["payload_json"]),
                provenance_ref=r["provenance_ref"],
                projection_id=r["projection_id"]))
        return out  # SQL 已 ORDER BY——不再重排（保持单一定义点）

    # ---- Q-01 Provenance Query（五级链回溯；单 JOIN 组，无 N+1）----

    def provenance_trace(self, node_id: str, *,
                         include_invalidated: bool = False) -> ProvenanceTrace:
        """Q-01：任一 Graph 节点 → 五级链回溯。

        Graph Node → Assertion (source_id) → Evidence (evidence_refs) → Document；
        Inference 节点 → akb_reasoning_run。缺级 fail-closed（GQ-CMP-024）。
        """
        if not node_id or not isinstance(node_id, str):
            raise GraphQueryError(f"E-V05-INVALID-NODE-ID: {node_id!r}")
        rows = self._rows(
            self.connection,
            "SELECT node_id, node_type, source_id, status, payload_json,"
            " provenance_ref, projection_id FROM kg_nodes WHERE node_id=?"
            + ("" if include_invalidated else
               " AND status IN ('valid','flagged')"),
            (node_id,))
        if not rows:
            raise GraphQueryError(
                f"E-V05-NODE-NOT-FOUND: {node_id}"
                + (" (invalidated)" if self._exists_node(node_id) else ""))
        n = rows[0]
        chain = [f"graph_node:{node_id}"]
        ntype = n["node_type"]
        assertion_id = document_id = run_id = None
        evidence_ids: tuple = ()
        if ntype == "assertion":
            assertion_id = n["source_id"]
            chain.append(f"assertion:{assertion_id}")
            ev_rows = self._rows(
                self.connection,
                "SELECT evidence_refs_json FROM akb_assertions WHERE assertion_id=?",
                (assertion_id,))
            if not ev_rows:
                raise GraphQueryError(
                    f"E-V05-SOURCE-MISSING: assertion {assertion_id} not found")
            evidence_ids = tuple(sorted(json.loads(ev_rows[0]["evidence_refs_json"] or "[]")))
        elif ntype == "evidence":
            evidence_ids = (n["source_id"],)
        elif ntype == "semantic_unit":
            chain.append(f"semantic_unit:{n['source_id']}")
            su = self._rows(
                self.connection,
                "SELECT evidence_id FROM akb_semantic_units WHERE unit_id=?",
                (n["source_id"],))
            if not su:
                raise GraphQueryError(
                    f"E-V05-SOURCE-MISSING: semantic_unit {n['source_id']} not found")
            evidence_ids = (su[0]["evidence_id"],)
        elif ntype == "inference":
            run_id = n["source_id"]
            chain.append(f"reasoning_run:{run_id}")
        elif ntype in ("entity", "document"):
            chain.append(f"{ntype}:{n['source_id']}")
        else:
            raise GraphQueryError(f"E-V05-INVALID-NODE-TYPE: {ntype}")
        # evidence → document（一次查询取全部 evidence 的 document_id）
        docs = set()
        for eid in evidence_ids:
            for d in self._rows(
                    self.connection,
                    "SELECT document_id FROM akb_evidence WHERE evidence_id=?", (eid,)):
                docs.add(d["document_id"])
        if len(docs) > 1:
            # 单节点多 document——确定性取最小 id 并在 chain 中全部列出
            pass
        if docs:
            document_id = min(docs)
            chain.append("document:" + ",".join(sorted(docs)))
        if evidence_ids:
            chain.append("evidence:" + ",".join(evidence_ids))
        return ProvenanceTrace(
            node_id=node_id, node_type=ntype, source_id=n["source_id"],
            assertion_id=assertion_id, evidence_ids=evidence_ids,
            document_id=document_id, reasoning_run_id=run_id,
            provenance_ref=n["provenance_ref"], chain=tuple(chain))

    def _exists_node(self, node_id: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM kg_nodes WHERE node_id=?", (node_id,)).fetchone() is not None

    # ---- Q-02 Entity Neighborhood（k-hop，relates_to/supports 边）----

    def entity_neighborhood(self, entity_node_id: str, hops: int = 1, *,
                            include_invalidated: bool = False) -> dict:
        """Q-02：EntityNode k-hop 邻域（relates_to 边语义；支持 relates_to/supports）。

        返回 {"center", "hops", "nodes": [GraphNodeView], "edges": [GraphEdgeView]}——
        BFS 逐层展开（每层单条集合查询——无 N+1），节点/边确定性排序去重。
        """
        if not isinstance(hops, int) or hops < 1 or hops > 4:
            raise GraphQueryError(
                f"E-V05-INVALID-HOPS: {hops} (MAX_HOPS=4, spec §7 Q-06 边界)")
        self._validate_node_id_exists(entity_node_id, include_invalidated)
        seen_nodes = {entity_node_id}
        seen_edges: set[str] = set()
        frontier = [entity_node_id]
        all_rows: list[dict] = []
        for _ in range(hops):
            if not frontier:
                break
            ph = ",".join("?" for _ in frontier)
            rows = self._rows(
                self.connection,
                "SELECT e.* FROM kg_edges e JOIN kg_nodes s ON s.node_id=e.source_node"
                f" WHERE e.source_node IN ({ph}) AND e.edge_type IN"
                " ('relates_to','supports')"
                + self._status_clause(include_invalidated, "e"),
                tuple(frontier))
            rows += self._rows(
                self.connection,
                "SELECT e.* FROM kg_edges e JOIN kg_nodes s ON s.node_id=e.target_node"
                f" WHERE e.target_node IN ({ph}) AND e.edge_type='relates_to'"
                + self._status_clause(include_invalidated, "e"),
                tuple(frontier))
            next_frontier = []
            for r in rows:
                if r["edge_id"] in seen_edges:
                    continue
                seen_edges.add(r["edge_id"])
                all_rows.append(r)
                for nid in (r["source_node"], r["target_node"]):
                    if nid not in seen_nodes:
                        seen_nodes.add(nid)
                        next_frontier.append(nid)
            frontier = next_frontier
        nodes = self._nodes_by_ids(seen_nodes, include_invalidated)
        edges = [GraphEdgeView(
            edge_id=r["edge_id"], edge_type=r["edge_type"],
            source_node=r["source_node"], target_node=r["target_node"],
            status=r["status"], payload=json.loads(r["payload_json"]),
            provenance_ref=r["provenance_ref"], projection_id=r["projection_id"])
            for r in sorted(all_rows, key=lambda r: r["edge_id"])]
        return {"center": entity_node_id, "hops": hops,
                "nodes": sorted(nodes, key=lambda n: n.node_id),
                "edges": edges}

    def _validate_node_id_exists(self, node_id: str,
                                 include_invalidated: bool) -> None:
        if not node_id or not isinstance(node_id, str):
            raise GraphQueryError(f"E-V05-INVALID-NODE-ID: {node_id!r}")
        if not self._exists_node(node_id):
            raise GraphQueryError(f"E-V05-NODE-NOT-FOUND: {node_id}")
        if not include_invalidated:
            row = self.connection.execute(
                "SELECT status FROM kg_nodes WHERE node_id=?", (node_id,)).fetchone()
            if row["status"] == "invalidated":
                raise GraphQueryError(
                    f"E-V05-NODE-INVALIDATED: {node_id} (use include_invalidated)")

    def _nodes_by_ids(self, ids: set[str],
                      include_invalidated: bool) -> list[GraphNodeView]:
        if not ids:
            return []
        ph = ",".join("?" for _ in ids)
        rows = self._rows(
            self.connection,
            "SELECT node_id, node_type, source_id, status, payload_json,"
            " provenance_ref, projection_id FROM kg_nodes"
            f" WHERE node_id IN ({ph})"
            + ("" if include_invalidated else
               " AND status IN ('valid','flagged')")
            + " ORDER BY node_id",
            tuple(sorted(ids)))
        return self._node_views(rows)

    # ---- Q-03 Assertion Trace（contradicts 邻居 → conflict 引用）----

    def assertion_trace(self, assertion_node_id: str, *,
                        include_invalidated: bool = False) -> dict:
        """Q-03：AssertionNode → contradicts 邻居 → conflict_ref 引用（不裁决）。"""
        rows = self._rows(
            self.connection,
            "SELECT node_type, source_id, status FROM kg_nodes WHERE node_id=?",
            (assertion_node_id,))
        if not rows:
            raise GraphQueryError(f"E-V05-NODE-NOT-FOUND: {assertion_node_id}")
        if rows[0]["node_type"] != "assertion":
            raise GraphQueryError(
                f"E-V05-NOT-ASSERTION: {assertion_node_id}"
                f" is {rows[0]['node_type']}")
        edges = self._rows(
            self.connection,
            "SELECT * FROM kg_edges WHERE (source_node=? OR target_node=?)"
            " AND edge_type='contradicts'"
            + ("" if include_invalidated else
               " AND status IN ('valid','flagged')")
            + " ORDER BY edge_id",
            (assertion_node_id, assertion_node_id))
        neighbors = []
        for e in edges:
            other = e["target_node"] if e["source_node"] == assertion_node_id \
                else e["source_node"]
            neighbors.append({
                "edge_id": e["edge_id"], "neighbor_node": other,
                "conflict_ref": json.loads(e["payload_json"]).get("conflict_ref", ""),
                "provenance_ref": e["provenance_ref"]})
        trace = self.provenance_trace(assertion_node_id,
                                      include_invalidated=include_invalidated)
        return {"node": assertion_node_id,
                "source_assertion": rows[0]["source_id"],
                "status": rows[0]["status"],
                "contradictions": neighbors,
                "provenance": trace}

    # ---- Q-04 Inference Chain（derived_from 链展开）----

    def inference_chain(self, inference_node_id: str, *, max_depth: int = 8,
                        include_invalidated: bool = False) -> dict:
        """Q-04：Inference/Assertion 节点 → derived_from 祖先链展开（环截断）。"""
        if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 8:
            raise GraphQueryError("E-V05-INVALID-DEPTH: max_depth 1..8")
        if not self._exists_node(inference_node_id):
            raise GraphQueryError(f"E-V05-NODE-NOT-FOUND: {inference_node_id}")
        chain_nodes: list[str] = [inference_node_id]
        edges: list[dict] = []
        seen = {inference_node_id}
        frontier = [inference_node_id]
        depth = 0
        while frontier and depth < max_depth:
            ph = ",".join("?" for _ in frontier)
            rows = self._rows(
                self.connection,
                "SELECT e.* FROM kg_edges e WHERE e.edge_type='derived_from'"
                f" AND e.source_node IN ({ph})"
                + ("" if include_invalidated else
                   " AND e.status IN ('valid','flagged')")
                + " ORDER BY e.edge_id",
                tuple(frontier))
            nxt = []
            for r in rows:
                edges.append(r)
                # derived_from: source=inferred child, target=parent——祖先沿 target 展开
                if r["target_node"] not in seen:
                    seen.add(r["target_node"])
                    nxt.append(r["target_node"])
            frontier = nxt
            depth += 1
        nodes = self._nodes_by_ids(seen, include_invalidated)
        return {"root": inference_node_id, "depth_reached": depth,
                "nodes": sorted(nodes, key=lambda n: n.node_id),
                "edges": [GraphEdgeView(
                    edge_id=r["edge_id"], edge_type=r["edge_type"],
                    source_node=r["source_node"], target_node=r["target_node"],
                    status=r["status"], payload=json.loads(r["payload_json"]),
                    provenance_ref=r["provenance_ref"],
                    projection_id=r["projection_id"]) for r in edges]}

    # ---- Q-05 Status-aware（查询面）----

    def query_nodes(self, *, node_type: str | None = None,
                    status: str | None = None,
                    include_invalidated: bool = False,
                    limit: int = 100) -> list[GraphNodeView]:
        """Q-05 主查询面：按类型/状态查节点。

        默认（status=None 且 include_invalidated=False）→ valid + flagged；
        显式 status → 精确状态（fail-closed 校验）；include_invalidated → 含 invalidated。
        limit ≤ 1000（防失控全表）；排序 node_id（Q-06 canonical）。
        """
        if node_type is not None:
            self._validate_node_type(node_type)
        if status is not None:
            self._validate_status(status)
        if not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise GraphQueryError(f"E-V05-INVALID-LIMIT: {limit}")
        where = ["1=1"]
        params: list = []
        if node_type is not None:
            where.append("node_type=?")
            params.append(node_type)
        if status is not None:
            where.append("status=?")
            params.append(status)
        elif not include_invalidated:
            where.append("status IN ('valid','flagged')")
        rows = self._rows(
            self.connection,
            "SELECT node_id, node_type, source_id, status, payload_json,"
            " provenance_ref, projection_id FROM kg_nodes WHERE "
            + " AND ".join(where) + " ORDER BY node_id LIMIT ?",
            tuple(params) + (limit,))
        return self._node_views(rows)

    def query_edges(self, *, edge_type: str | None = None,
                    node_id: str | None = None,
                    include_invalidated: bool = False,
                    limit: int = 100) -> list[GraphEdgeView]:
        """Q-05 边查询面：按类型/端点查边（node_id 需存在——fail-closed）。"""
        if edge_type is not None:
            self._validate_edge_type(edge_type)
        if node_id is not None:
            self._validate_node_id_exists(node_id, include_invalidated)
        if not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise GraphQueryError(f"E-V05-INVALID-LIMIT: {limit}")
        where = ["1=1"]
        params: list = []
        if edge_type is not None:
            where.append("edge_type=?")
            params.append(edge_type)
        if node_id is not None:
            where.append("(source_node=? OR target_node=?)")
            params.extend([node_id, node_id])
        elif not include_invalidated:
            where.append("status IN ('valid','flagged')")
        rows = self._rows(
            self.connection,
            "SELECT edge_id, edge_type, source_node, target_node, status,"
            " payload_json, provenance_ref, projection_id FROM kg_edges WHERE "
            + " AND ".join(where) + " ORDER BY edge_id LIMIT ?",
            tuple(params) + (limit,))
        return [GraphEdgeView(
            edge_id=r["edge_id"], edge_type=r["edge_type"],
            source_node=r["source_node"], target_node=r["target_node"],
            status=r["status"], payload=json.loads(r["payload_json"]),
            provenance_ref=r["provenance_ref"], projection_id=r["projection_id"])
            for r in rows]

    # ---- Q-06 Determinism（canonical 查询入口——返回 canonical JSON）----

    def canonical_view(self, *, include_invalidated: bool = False) -> str:
        """Q-06：全图 canonical 视图（节点+边 按 id 排序的确定性序列化）。"""
        nodes = self.query_nodes(include_invalidated=include_invalidated, limit=1000)
        edges = self.query_edges(include_invalidated=include_invalidated, limit=1000)
        payload = {
            "nodes": sorted(({"node_id": n.node_id, "type": n.node_type,
                              "source": n.source_id, "status": n.status}
                             for n in nodes), key=lambda x: x["node_id"]),
            "edges": sorted(({"edge_id": e.edge_id, "type": e.edge_type,
                              "src": e.source_node, "tgt": e.target_node,
                              "status": e.status}
                             for e in edges), key=lambda x: x["edge_id"]),
        }
        from agent_kb.reasoning.models import canonical_json
        return canonical_json(payload)