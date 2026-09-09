# -*- coding: utf-8 -*-
"""GraphProjectionService（V0.5-DD-001 §4/§7）——纯函数投影。

输入：既有 Assertion/Evidence/SemanticUnit/Inference（只读快照）；
输出：GraphProjection（不可变）；
约束：pure / deterministic / idempotent / **no database write**（KG-01/02）。
"""
from __future__ import annotations

import hashlib
import json

from agent_kb.kgraph.identity import EntityIdentityResolver
from agent_kb.kgraph.models import (
    GRAPH_VERSION,
    AssertionNode,
    ContradictsEdge,
    DerivedFromEdge,
    DocumentNode,
    EvidenceNode,
    ExtractedFromEdge,
    GraphProjection,
    EntityNode,
    InferenceNode,
    RelatesToEdge,
    SemanticUnitNode,
    SupportsEdge,
    ValidatesEdge,
    edge_id,
    node_id,
)
from agent_kb.reasoning.models import canonical_json

# V0.4/V0.1 治理冲突面（contradicts 投影源——ConflictRecord 语义，不裁决）
CONFLICT_PREDICATE_HINTS = ("__DISPUTED__",)


class GraphProjectionService:
    """纯函数投影服务（零 DB 写）。

    process(db) 只读查询既有对象 → GraphProjection；
    同 DB 状态双跑 → fingerprint 全等（GS-CMP-004）。
    """

    def __init__(self, identity_resolver: EntityIdentityResolver | None = None):
        self.identity = identity_resolver or EntityIdentityResolver()

    # ---- helpers（只读）----

    @staticmethod
    def _rows(db, sql: str, params: tuple = ()) -> list[dict]:
        return [dict(r) for r in db.execute(sql, params)]

    @staticmethod
    def _obj_value(o: dict) -> str:
        return str(o.get("value") if o.get("value") is not None
                   else o.get("entity_id") or "")

    # ---- 主入口 ----

    def process(self, db) -> GraphProjection:
        nodes: list = []
        edges: list = []

        # 1) Documents / Evidence / SemanticUnits
        docs = self._rows(db, "SELECT document_id FROM akb_documents ORDER BY document_id")
        for d in docs:
            nodes.append(DocumentNode(node_id=node_id("document", d["document_id"]),
                                      source_id=d["document_id"],
                                      provenance_ref=d["document_id"]))
        evids = self._rows(db, "SELECT evidence_id, document_id FROM akb_evidence"
                               " ORDER BY evidence_id")
        for e in evids:
            nodes.append(EvidenceNode(node_id=node_id("evidence", e["evidence_id"]),
                                      source_id=e["evidence_id"],
                                      provenance_ref=e["evidence_id"]))
            edges.append(ExtractedFromEdge(  # SemanticUnit 端稍后挂
                edge_id="", source_node="", target_node=node_id("evidence",
                                                                e["evidence_id"]),
                provenance_ref=e["evidence_id"]))
        # evidence→document 支撑边（extracted_from 语义：unit→evidence 在下面挂）
        sus = self._rows(db, "SELECT unit_id, evidence_id FROM akb_semantic_units"
                             " ORDER BY unit_id")
        for su in sus:
            nodes.append(SemanticUnitNode(
                node_id=node_id("semantic_unit", su["unit_id"]),
                source_id=su["unit_id"], evidence_ref=su["evidence_id"],
                provenance_ref=su["unit_id"]))
            en_id = node_id("evidence", su["evidence_id"])
            edges.append(ExtractedFromEdge(
                edge_id=edge_id("extracted_from", node_id("semantic_unit", su["unit_id"]),
                                en_id),
                source_node=node_id("semantic_unit", su["unit_id"]),
                target_node=en_id, provenance_ref=su["unit_id"]))

        # 2) Assertions（candidate/validated/inferred 投影；hypothesized 不投影——DD-001 §3）
        asserts = self._rows(db, "SELECT assertion_id, subject_ref, predicate_ref,"
                                 " object_kind, object_value, object_entity_ref,"
                                 " assertion_type, status, confidence,"
                                 " evidence_refs_json, source_unit_refs_json,"
                                 " temporal_scope_json, derivation_json"
                                 " FROM akb_assertions ORDER BY assertion_id")
        ent_members: list[dict] = []
        for a in asserts:
            if a["assertion_type"] == "hypothesized":
                continue
            o = {"value": a["object_value"], "entity_id": a["object_entity_ref"]}
            an_id = node_id("assertion", a["assertion_id"])
            nodes.append(AssertionNode(
                node_id=an_id, source_id=a["assertion_id"],
                subject_ref=a["subject_ref"], predicate_ref=a["predicate_ref"],
                object_value=self._obj_value(o), assertion_type=a["assertion_type"],
                status=a["status"], confidence=a["confidence"],
                temporal_scope=(a["temporal_scope_json"] or "",),
                provenance_ref=a["assertion_id"]))
            # supports 边（evidence_refs）
            for eid in sorted(json.loads(a["evidence_refs_json"] or "[]")):
                ev_id = node_id("evidence", eid)
                edges.append(SupportsEdge(
                    edge_id=edge_id("supports", an_id, ev_id),
                    source_node=an_id, target_node=ev_id,
                    provenance_ref=a["assertion_id"]))
            # derived_from 边（inferred → parent）
            if a["assertion_type"] == "inferred" and a["derivation_json"]:
                d = json.loads(a["derivation_json"])
                for pid in sorted(d.get("parent_assertions") or []):
                    edges.append(DerivedFromEdge(
                        edge_id=edge_id("derived_from", an_id,
                                        node_id("assertion", pid)),
                        source_node=an_id, target_node=node_id("assertion", pid),
                        rule_ref=d.get("rule_ref", ""),
                        provenance_ref=a["assertion_id"]))
            # entity 成员（identity 候选）
            ent_members.append({
                "normalized_form": a["subject_ref"], "entity_type": "subject",
                "evidence_id": (json.loads(a["evidence_refs_json"] or "[]") or [""])[0],
                "candidate_id": a["assertion_id"]})
            obj_ent = a["object_entity_ref"] or self._obj_value(o)
            if obj_ent:
                ent_members.append({
                    "normalized_form": obj_ent, "entity_type": "object",
                    "evidence_id": (json.loads(a["evidence_refs_json"] or "[]") or [""])[0],
                    "candidate_id": a["assertion_id"]})

        # 3) Entity 节点（identity 层 L1 精确簇）+ relates_to 边
        clusters = {c["canonical_id"]: c for c in self.identity.resolve_clusters(ent_members)}
        form_to_cluster: dict[tuple, str] = {}
        for cid, c in clusters.items():
            nodes.append(EntityNode(
                node_id=node_id("entity", cid), canonical_id=cid,
                canonical_form=c["canonical_form"], entity_type=c["entity_type"],
                alias=tuple(c["aliases"]), provenance_ref=cid, source_ref=cid))
            for m in c["members"]:
                form_to_cluster[(m.get("normalized_form") or "", m.get("entity_type") or "")] = cid
        for a in asserts:
            if a["assertion_type"] == "hypothesized" or not a["subject_ref"]:
                continue
            s_cid = form_to_cluster.get((a["subject_ref"], "subject"))
            o_ent = a["object_entity_ref"] or self._obj_value(
                {"value": a["object_value"], "entity_id": a["object_entity_ref"]})
            o_cid = form_to_cluster.get((o_ent, "object"))
            if s_cid and o_cid and a["assertion_type"] in ("extracted", "observed",
                                                           "inferred", "validated"):
                sn = node_id("entity", s_cid)
                on = node_id("entity", o_cid)
                if sn != on:
                    edges.append(RelatesToEdge(
                        edge_id=edge_id(f"relates_to:{a['predicate_ref']}", sn, on),
                        source_node=sn, target_node=on,
                        predicate=a["predicate_ref"],
                        provenance_ref=a["assertion_id"]))

        # 4) Inference 节点（reasoning runs——表存在时；migration 14 已在测试库）
        has_runs = db.execute("SELECT name FROM sqlite_master WHERE type='table'"
                              " AND name='akb_reasoning_runs'").fetchone() is not None
        if has_runs:
            for rr in self._rows(db, "SELECT run_id, rule_version, reasoner_id"
                                     " FROM akb_reasoning_runs ORDER BY run_id"):
                nodes.append(InferenceNode(
                    node_id=node_id("inference", rr["run_id"]), source_id=rr["run_id"],
                    rule_ref=rr["rule_version"], reasoner_id=rr["reasoner_id"],
                    provenance_ref=rr["run_id"]))

        # 5) contradicts 边（__DISPUTED__ 值断言的 RR-04 语义投影——不裁决）
        disputed = [a for a in asserts
                    if a["object_value"] == "__DISPUTED__" and a["status"] == "candidate"]
        for a in disputed:
            d = json.loads(a["derivation_json"]) if a["derivation_json"] else {}
            for pid in sorted(d.get("parent_assertions") or []):
                edges.append(ContradictsEdge(
                    edge_id=edge_id("contradicts", node_id("assertion", a["assertion_id"]),
                                    node_id("assertion", pid)),
                    source_node=node_id("assertion", a["assertion_id"]),
                    target_node=node_id("assertion", pid),
                    conflict_ref=f"RR-04:{a['assertion_id']}",
                    provenance_ref=a["assertion_id"]))

        # 6) validates 边（govern:validate 审计投影）
        if has_runs or True:
            try:
                gov_rows = self._rows(db, "SELECT provenance_id, inputs_json,"
                                          " metadata_json FROM akb_provenance"
                                          " WHERE activity='govern:validate'"
                                          " ORDER BY provenance_id")
            except Exception:
                gov_rows = []
            for g in gov_rows:
                meta = json.loads(g["metadata_json"] or "{}")
                aid = meta.get("assertion_id")
                if aid:
                    edges.append(ValidatesEdge(
                        edge_id=edge_id("validates", g["provenance_id"],
                                        node_id("assertion", aid)),
                        source_node=g["provenance_id"],
                        target_node=node_id("assertion", aid),
                        provenance_ref=g["provenance_id"]))

        # 清理占位边（evidence 循环里的空壳）
        edges = [e for e in edges if getattr(e, "edge_id", "")]
        # 确定性：节点/边按 id 排序去重
        seen_nodes, uniq_nodes = set(), []
        for n in sorted(nodes, key=lambda n: n.node_id):
            if n.node_id not in seen_nodes:
                seen_nodes.add(n.node_id)
                uniq_nodes.append(n)
        seen_edges, uniq_edges = set(), []
        for e in sorted(edges, key=lambda e: e.edge_id):
            if e.edge_id not in seen_edges:
                seen_edges.add(e.edge_id)
                uniq_edges.append(e)
        fp = hashlib.sha256(canonical_json(
            [n.node_id for n in uniq_nodes] +
            [e.edge_id for e in uniq_edges]).encode("utf-8")).hexdigest()[:24]
        return GraphProjection(nodes=tuple(uniq_nodes), edges=tuple(uniq_edges),
                               fingerprint=fp)
