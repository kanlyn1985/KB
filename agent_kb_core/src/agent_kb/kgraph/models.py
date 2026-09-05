# -*- coding: utf-8 -*-
"""Graph Node/Edge models（确定性 id；V0.5-DD-001 §2/§3）。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from agent_kb.reasoning.models import canonical_json

GRAPH_VERSION = "v05-graph-1.0"


def node_id(node_type: str, source_id: str) -> str:
    """Node ID = SHA256(canonical_json({type, source_id, version}))——确定性派生。"""
    payload = {"type": node_type, "source_id": source_id,
               "version": GRAPH_VERSION}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:24]


def edge_id(edge_type: str, source_node: str, target_node: str) -> str:
    """Edge ID = SHA256(canonical_json({edge_type, source_node, target_node}))。"""
    payload = {"edge_type": edge_type, "source_node": source_node,
               "target_node": target_node}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:24]


# ---- Node Models（只读投影；provenance_ref 必带——KG-01）----

@dataclass(frozen=True)
class EntityNode:
    node_id: str
    canonical_id: str = ""            # ENTITY_IDENTITY_SPEC §1 确定性派生
    canonical_form: str = ""
    entity_type: str = ""
    alias: tuple = ()
    provenance_ref: str = ""          # 投影源（assertion/candidate 摘要引用）
    source_ref: str = ""


@dataclass(frozen=True)
class SemanticUnitNode:
    node_id: str
    source_id: str
    evidence_ref: str
    provenance_ref: str = ""


@dataclass(frozen=True)
class AssertionNode:
    node_id: str
    source_id: str
    subject_ref: str
    predicate_ref: str
    object_value: str
    assertion_type: str
    status: str
    confidence: float | None = None
    temporal_scope: tuple = ()        # 只读引用（V0.3 temporal semantics 不重算）
    provenance_ref: str = ""


@dataclass(frozen=True)
class EvidenceNode:
    node_id: str
    source_id: str
    content_summary: str = ""         # 不复制内容（KG-01）
    provenance_ref: str = ""


@dataclass(frozen=True)
class DocumentNode:
    node_id: str
    source_id: str
    provenance_ref: str = ""


@dataclass(frozen=True)
class InferenceNode:
    node_id: str
    source_id: str                    # reasoning run id 或 inferred assertion id
    rule_ref: str
    reasoner_id: str
    depth: int = 0
    provenance_ref: str = ""


# ---- Edge Models（方向固定；provenance_ref 必带）----

@dataclass(frozen=True)
class ExtractedFromEdge:
    edge_id: str
    source_node: str                  # SemanticUnitNode
    target_node: str                  # EvidenceNode
    provenance_ref: str = ""


@dataclass(frozen=True)
class SupportsEdge:
    edge_id: str
    source_node: str                  # AssertionNode
    target_node: str                  # EvidenceNode
    provenance_ref: str = ""


@dataclass(frozen=True)
class ContradictsEdge:
    edge_id: str
    source_node: str                  # AssertionNode（冲突方 A）
    target_node: str                  # AssertionNode（冲突方 B）
    conflict_ref: str = ""            # ConflictRecord 引用（不裁决）
    provenance_ref: str = ""


@dataclass(frozen=True)
class DerivedFromEdge:
    edge_id: str
    source_node: str                  # AssertionNode（inferred）
    target_node: str                  # AssertionNode（parent）
    rule_ref: str = ""
    provenance_ref: str = ""


@dataclass(frozen=True)
class ValidatesEdge:
    edge_id: str
    source_node: str                  # 治理动作（provenance 引用）
    target_node: str                  # AssertionNode（validated）
    provenance_ref: str = ""


@dataclass(frozen=True)
class RelatesToEdge:
    edge_id: str
    source_node: str                  # EntityNode（subject）
    target_node: str                  # EntityNode（object）——literal 走属性边语义
    predicate: str = ""
    provenance_ref: str = ""


@dataclass(frozen=True)
class GraphProjection:
    """纯数据投影容器（不可变；fingerprint 锚——KG-02 幂等重建）。"""
    nodes: tuple = ()
    edges: tuple = ()
    fingerprint: str = ""

    def canonical_digest(self) -> str:
        items = sorted(
            [n.node_id for n in self.nodes] +
            [e.edge_id for e in self.edges])
        return hashlib.sha256(canonical_json(items).encode("utf-8")).hexdigest()[:24]
