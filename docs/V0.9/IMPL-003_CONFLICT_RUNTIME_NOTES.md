# V0.9 IMPL-003 Implementation Notes — ConflictRuntime v2

- Date: 2026-09-04 · Baseline: 382aa33（IMPL-002）· V0.5..V0.8 frozen（零触碰实测）·
  **MIGRATION DECISION: NO MIGRATION 维持**（快照检测模型）
- 新增：agent_kb/conflict/（runtime.py + __init__.py——新包，frozen 零触碰）；
  tests/v09_conflict/test_conflict_runtime.py（CF-CMP-001..010）

## 行为契约（CF-CMP-001..010 全 PASS）

- **basic creation**（001）：同 subject+predicate 不同值 →
  ASSERTION_VALUE_CONFLICT（status=open 零 resolution 语义）；
- **deterministic conflict_id**（002）：conflict_id = "cf_"+SHA256(canonical_json
  ({conflict_type, source_refs sorted, target_refs, snapshot}))——跨实例全等 +
  单元级复算 + 输入变化检测；
- **same snapshot rebuild**（003）：同投影/库面 → 同 fingerprint 集；
- **value conflict detection**（004）：同 subject+predicate 不同 object 值 →
  记录（values 清单进 metadata）；单值零记录；
- **causal mechanism conflict detection**（005）：同 effect 多因果源 →
  CAUSAL_MECHANISM_CONFLICT（消费 CausalProjection——causal_refs 全 ce_ 前缀 +
  detection=condition-set-mutual-exclusion）；
- **unknown type rejection**（006）：非白名单 fail-close（E-V09-CONFLICT-INVALID）；
  白名单类型正常；坏 id 读面拒绝；
- **conflict ≠ mutation**（007）：检测全流程 akb_assertions/kg_nodes/kg_edges
  unchanged（快照实测——Conflict ≠ Resolution ≠ Truth ≠ Mutation）；
- **provenance audit**（008）：graph:conflict-detect 落 akb_provenance
  （conflicts/snapshot/fingerprint——复用零第二套）；
- **immutable + idempotent**（009）：frozen dataclass 赋值拒绝 + 同状态重复检测
  零重复审计（幂等——与 projection/health 一致）；
- **frozen regression**（010）：V0.5..V0.8 十 frozen 模块零字符串感知 + V0.9
  IMPL-001/002 模块零语义 import（单向依赖保持；docstring 文字引用不算依赖）+
  legacy 互斥 + 建图回归（canonical_view 不变）。

## 冲突类型白名单（三型）

1. ASSERTION_VALUE_CONFLICT——同语义目标不同值（V0.3 值冲突语义延续）；
2. CAUSAL_MECHANISM_CONFLICT——同 effect 多因果源/互斥机制（消费
   CausalProjection；condition-set-mutual-exclusion 确定性判定，文本语义比对
   DEFERRED——设计 P1 项）；
3. DOMAIN_SCOPE_CONFLICT——同概念不同 ontology_scope。

## MIGRATION DECISION

**NO MIGRATION 维持**：ConflictRuntime 为快照检测模型（同状态同记录集），
graph:conflict-detect 审计快照足够；akb_conflicts 表无需创建——仅当冲突历史
索引/趋势分析需求出现时按设计 §3 P2 项评估。

## 关键实现决策

- 检测确定性：同投影/库面 → 同记录集（fingerprint 集稳定）；
- 幂等审计：同状态重复检测（同 snapshot+同冲突集）零重复审计——
  last_fingerprints 快照比对；
- severity 规则：值冲突 2 值=medium/>2=high；机制冲突 2 源=medium/>2=high；
  domain scope=low。

## P1/P2

- P1 延续：conflict detection scalability（全表扫描）/causal mechanism
  equivalence precision（文本语义比对 DEFERRED）；
- P2：conflict history indexing/conflict trend analytics。