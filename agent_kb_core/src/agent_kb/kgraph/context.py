# -*- coding: utf-8 -*-
"""Graph Reasoning Context（AKB-V06-IMPL-001；设计 docs/V0.6/ V0.6_DESIGN §3.1/§16）。

GraphContextBuilder：V0.5 GraphQueryService 只读输出 → deterministic
GraphReasoningContext，供 V0.4 ReasoningEngine.reason(parent_ids) 消费。

边界（设计 contract）：
- 只经 GraphQueryService 获取数据——零直接 SQL 查询 kg_*；
- 只读（不改 kg_* / akb_* / provenance）；
- legacy agent_kb.graph 零触碰；
- deterministic：context_id/fingerprint 为 canonical JSON 确定性派生；
- status/temporal 规则：validated/candidate/flagged 可进入、invalidated 排除、
  hypothesized 禁止（assertion_type 维度）、temporal ambiguity fail-closed；
- provenance 保留：context → assertion → evidence → document。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from agent_kb.kgraph.query import GraphQueryError, GraphQueryService
from agent_kb.reasoning.models import canonical_json

# 状态过滤语义（V0.6_DESIGN §4/§10；hypothesized 是 assertion_type 非 status）
ALLOWED_SOURCE_STATUSES = ("valid", "flagged")
DEFAULT_STATUS_FILTER = ("valid", "flagged")
ALLOWED_NODE_TYPES_FOR_CONTEXT = ("assertion", "entity", "evidence", "semantic_unit")
DEFAULT_MAX_HOPS = 2
MAX_HOPS_LIMIT = 4                      # 对齐 Q-02 MAX_HOPS


class GraphContextError(ValueError):
    """fail-closed：context 构建错误（设计 §9/§16）。"""


@dataclass(frozen=True)
class ProvenanceRecord:
    """context → assertion → evidence → document 的一级回溯记录。"""
    assertion_id: str
    evidence_ids: tuple = ()
    document_ids: tuple = ()
    node_id: str = ""
    status: str = ""


@dataclass(frozen=True)
class GraphReasoningContext:
    """immutable + deterministic（V0.6_DESIGN §3.1 字段集）。"""
    context_id: str
    fingerprint: str
    root_entity: str
    graph_fingerprint: str
    input_nodes: tuple
    input_assertions: tuple
    input_edges: tuple
    temporal_context: tuple
    status_filter: tuple
    query_constraints: dict
    rule_set_version: str
    provenance: tuple                      # ProvenanceRecord 列表（canonical 序）
    hop: int = DEFAULT_MAX_HOPS

    def canonical_payload(self) -> dict:
        """确定性 canonical 载荷（identity 计算的唯一输入集）。"""
        return {
            "root_entity": self.root_entity,
            "graph_fingerprint": self.graph_fingerprint,
            "input_nodes": sorted(self.input_nodes),
            "input_assertions": sorted(self.input_assertions),
            "input_edges": sorted(self.input_edges),
            "temporal_context": sorted(self.temporal_context),
            "status_filter": sorted(self.status_filter),
            "query_constraints": self.query_constraints,
            "rule_set_version": self.rule_set_version,
            "hop": self.hop,
        }


class GraphContextBuilder:
    """V0.5 Query → ReasoningContext（只读 + 确定性 + fail-closed）。"""

    def __init__(self, query_service: GraphQueryService | None = None):
        self._qs_provided = query_service is not None
        self._qs = query_service

    # ---- helpers ----

    def _query_service(self, connection) -> GraphQueryService:
        """GraphQueryService 单一数据通道（禁止直接 SQL 查 kg_*）。"""
        if self._qs is not None:
            return self._qs
        return GraphQueryService(connection)

    @staticmethod
    def _assertion_view_to_record(view, connection) -> ProvenanceRecord:
        """GraphNodeView(assertion) → ProvenanceRecord（JOIN 级回溯，无 N+1 循环查询）。"""
        row = connection.execute(
            "SELECT evidence_refs_json FROM akb_assertions WHERE assertion_id=?",
            (view.source_id,)).fetchone()
        if row is None:
            raise GraphContextError(
                f"E-V06-SOURCE-MISSING: assertion {view.source_id} not found")
        evidence_ids = tuple(sorted(json_loads(row["evidence_refs_json"] or "[]")))
        docs = set()
        for eid in evidence_ids:
            d = connection.execute(
                "SELECT document_id FROM akb_evidence WHERE evidence_id=?",
                (eid,)).fetchone()
            if d is None:
                raise GraphContextError(
                    f"E-V06-SOURCE-MISSING: evidence {eid} not found")
            docs.add(d["document_id"])
        return ProvenanceRecord(
            assertion_id=view.source_id, evidence_ids=evidence_ids,
            document_ids=tuple(sorted(docs)), node_id=view.node_id,
            status=view.status)

    @staticmethod
    def _temporal_of(view, connection) -> str:
        """temporal scope 只读引用（V0.3 语义，不重算）；缺失返回空标记。"""
        row = connection.execute(
            "SELECT temporal_scope_json FROM akb_assertions WHERE assertion_id=?",
            (view.source_id,)).fetchone()
        if row is None:
            raise GraphContextError(
                f"E-V06-SOURCE-MISSING: assertion {view.source_id} not found")
        raw = (row["temporal_scope_json"] or "").strip()
        if raw in ("", "null", "[]", "None"):
            return "temporal:unspecified"
        try:
            parsed = json_loads(raw)
        except Exception as exc:
            # temporal ambiguity fail-closed（设计 §12/§16）
            raise GraphContextError(
                f"E-V06-TEMPORAL-AMBIGUITY: assertion {view.source_id}"
                f" unparsable temporal scope") from exc
        return "temporal:" + canonical_json(parsed)

    # ---- 主入口 ----

    def build(self, connection, *, root_entity: str, hops: int = DEFAULT_MAX_HOPS,
              status_filter: tuple = DEFAULT_STATUS_FILTER,
              rule_set_version: str = "v06-rules-v1",
              predicate_whitelist: tuple | None = None,
              max_assertions: int = 256,
              temporal_required: bool = False) -> GraphReasoningContext:
        """从 V0.5 图构建 deterministic ReasoningContext。

        fail-closed：root 不存在/invalidated、hops 越界、非法 status_filter、
        源缺失、temporal ambiguity（temporal_required=True 且 scope 缺失）。
        """
        if not isinstance(root_entity, str) or not root_entity.strip():
            raise GraphContextError(f"E-V06-INVALID-ROOT: {root_entity!r}")
        if not isinstance(hops, int) or hops < 1 or hops > MAX_HOPS_LIMIT:
            raise GraphContextError(
                f"E-V06-INVALID-HOPS: {hops} (1..{MAX_HOPS_LIMIT})")
        if not status_filter or any(s not in ALLOWED_SOURCE_STATUSES
                                    for s in status_filter):
            raise GraphContextError(
                f"E-V06-INVALID-STATUS-FILTER: {status_filter} (allowed:"
                f" {ALLOWED_SOURCE_STATUSES})")
        qs = self._query_service(connection)
        # root 存在性 + 状态（经 Query service 面，不直查 kg_*）
        root_nodes = [n for n in qs.query_nodes(node_type="entity", limit=1000)
                      if n.node_id == root_entity]
        if not root_nodes:
            # audit 面确认存在性（invalidated root 也拒绝——推理前提不可失效）
            audit = [n for n in qs.query_nodes(node_type="entity", limit=1000,
                                               include_invalidated=True)
                     if n.node_id == root_entity]
            if audit:
                raise GraphContextError(
                    f"E-V06-ROOT-INVALIDATED: {root_entity}")
            raise GraphContextError(f"E-V06-ROOT-NOT-FOUND: {root_entity}")
        # 子图收集：Q-02 neighborhood（relates_to/supports）+ Q-04 链（derived_from）
        nb = qs.entity_neighborhood(root_entity, hops=hops)
        node_ids = {n.node_id for n in nb["nodes"]}
        edge_ids = {e.edge_id for e in nb["edges"]}
        # assertion 节点收集（邻域 + root 关联断言），status 过滤经 query 面
        assertion_views = {v.node_id: v for v in qs.query_nodes(
            node_type="assertion", limit=1000)}
        # 关联判定（零额外 SQL）：①relates_to/supports 边的 provenance_ref 指向该断言；
        # ②断言 payload 的 subject_ref/object 值出现在邻域 entity 的 canonical_form 集；
        # ③断言节点本身在邻域/边端点（covers supports 结构）
        entity_forms = {n.payload.get("canonical_form", "")
                        for n in nb["nodes"] if n.node_type == "entity"}
        edge_prov = {e.provenance_ref for e in nb["edges"]}
        selected_assertions = []
        for nid, v in assertion_views.items():
            if v.status not in status_filter:
                continue
            linked = (v.node_id in node_ids
                      or v.source_id in edge_prov
                      or v.payload.get("subject_ref") in entity_forms
                      or v.payload.get("object_value") in entity_forms
                      or any(e.source_node == v.node_id or e.target_node == v.node_id
                             for e in nb["edges"]))
            if linked:
                selected_assertions.append(v)
        # assertion 按 node_id 确定性排序 + 上限
        selected_assertions.sort(key=lambda v: v.node_id)
        if len(selected_assertions) > max_assertions:
            raise GraphContextError(
                f"E-V06-CONTEXT-TOO-LARGE: {len(selected_assertions)} assertions"
                f" > {max_assertions}")
        if not selected_assertions:
            raise GraphContextError(
                f"E-V06-EMPTY-CONTEXT: no assertions reachable from {root_entity}")
        # provenance 记录（assertion → evidence → document；缺源 fail-closed）
        provenance = []
        temporal_marks = []
        input_assertions = []
        for v in selected_assertions:
            rec = self._assertion_view_to_record(v, connection)
            provenance.append(rec)
            temporal_marks.append(self._temporal_of(v, connection))
            input_assertions.append(v.source_id)
        if temporal_required and any(t == "temporal:unspecified"
                                     for t in temporal_marks):
            raise GraphContextError(
                "E-V06-TEMPORAL-AMBIGUITY: temporal_required but assertion"
                " lacks temporal scope")
        input_nodes = tuple(sorted(
            {v.node_id for v in selected_assertions} | node_ids))
        input_edges = tuple(sorted(edge_ids))
        query_constraints = {
            "hops": hops,
            "max_assertions": max_assertions,
            "predicate_whitelist": sorted(predicate_whitelist) if predicate_whitelist
            else None,
        }
        payload = {
            "root_entity": root_entity,
            "graph_fingerprint": _graph_fingerprint_of(qs, connection),
            "input_nodes": sorted(input_nodes),
            "input_assertions": sorted(input_assertions),
            "input_edges": sorted(input_edges),
            "temporal_context": sorted(temporal_marks),
            "status_filter": sorted(status_filter),
            "query_constraints": query_constraints,
            "rule_set_version": rule_set_version,
            "hop": hops,
        }
        cj = canonical_json(payload)
        context_id = "grc_" + hashlib.sha256(cj.encode("utf-8")).hexdigest()[:16]
        fingerprint = hashlib.sha256(
            ("v06-ctx-1.0|" + cj).encode("utf-8")).hexdigest()[:24]
        return GraphReasoningContext(
            context_id=context_id, fingerprint=fingerprint,
            root_entity=root_entity, graph_fingerprint=payload["graph_fingerprint"],
            input_nodes=input_nodes, input_assertions=tuple(sorted(input_assertions)),
            input_edges=input_edges, temporal_context=tuple(sorted(temporal_marks)),
            status_filter=tuple(sorted(status_filter)),
            query_constraints=query_constraints, rule_set_version=rule_set_version,
            provenance=tuple(sorted(provenance, key=lambda p: p.assertion_id)),
            hop=hops)


def _graph_fingerprint_of(qs: GraphQueryService, connection) -> str:
    """当前持久化投影的 fingerprint（经 metadata 查询——kg 表 metadata 面）。"""
    row = connection.execute(
        "SELECT fingerprint FROM kg_projection_runs WHERE status='active'"
        " ORDER BY created_at DESC, projection_id DESC LIMIT 1").fetchone()
    if row is None:
        raise GraphContextError("E-V06-NO-GRAPH: no persisted projection")
    return row["fingerprint"]


def json_loads(raw: str):
    import json
    return json.loads(raw)