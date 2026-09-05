# -*- coding: utf-8 -*-
"""V0.5 Knowledge Graph Schema 基础层（AKB-V05-IMPL-001；设计 docs/V0.5/）。

命名空间说明：agent_kb.graph 为 V0.1 legacy 提取/存储适配层（frozen 侧）——
V0.5 Knowledge Graph Layer 使用独立命名空间 agent_kb.kgraph，零触碰 legacy。

- Node/Edge models（6+6，确定性 id）
- GraphProjectionService（纯函数投影：同 DB 状态 → 同 Graph；零 DB 写）
- EntityIdentityResolver（canonical id 派生——merge/persistence 属 IMPL-002/003）

边界：V0.4 frozen behavior 不变；temporal semantics 不变；inferred→asserted 永禁；
零 migration 执行；零 production DB。
"""
from agent_kb.kgraph.models import (
    AssertionNode,
    ContradictsEdge,
    DerivedFromEdge,
    DocumentNode,
    EvidenceNode,
    ExtractedFromEdge,
    GraphProjection,
    InferenceNode,
    RelatesToEdge,
    SemanticUnitNode,
    SupportsEdge,
    ValidatesEdge,
    edge_id,
    node_id,
)
from agent_kb.kgraph.projection import GraphProjectionService
from agent_kb.kgraph.identity import (
    EntityGovernanceService,
    EntityIdentityResolver,
    MergeCandidate,
)

__all__ = [
    "AssertionNode", "DocumentNode", "DerivedFromEdge", "ContradictsEdge",
    "EvidenceNode", "ExtractedFromEdge", "GraphProjection", "InferenceNode",
    "RelatesToEdge", "SemanticUnitNode", "SupportsEdge", "ValidatesEdge",
    "edge_id", "node_id", "GraphProjectionService", "EntityIdentityResolver",
    "EntityGovernanceService", "MergeCandidate",
]
