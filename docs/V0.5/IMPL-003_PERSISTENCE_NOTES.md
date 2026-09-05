# V0.5 IMPL-003 Implementation Notes — Graph Persistence

- Date: 2026-09-04 · Baseline: 28721cc（IMPL-002）→ 本实现 · 设计基线 f5e28dd（frozen，语义未改）
- 关联：V0.5-IMPL-004 STOP 报告（c2f6fa3）确认的 persistence 缺口由本实现补齐

## 1. Migration 15（append-only；migration 14 零修改）

`V05_GRAPH_PERSISTENCE_MIGRATION`（version=15, name=v05_graph_persistence）：

| 表 | 用途 | 关键列 |
|---|---|---|
| kg_projection_runs | 投影构建元数据（fingerprint 幂等锚） | projection_id PK / graph_version / fingerprint **UNIQUE** / source_digest / node_count / edge_count / actor_id / status(active/superseded) / created_at |
| kg_nodes | 六类节点持久化 | node_id PK / node_type CHECK(6 类) / source_id / projection_id FK / status CHECK(valid/invalidated/flagged) / payload_json / provenance_ref |
| kg_edges | 六类边持久化 | edge_id PK / edge_type CHECK(6 类) / source_node→kg_nodes FK / target_node→kg_nodes FK / projection_id FK / status / payload_json / provenance_ref |
| kg_invalidation_log | 失效审计（§17 不物理删除） | invalidation_id PK / node_id FK / reason_status CHECK(rejected/deprecated/disputed) / graph_status CHECK(invalidated/flagged) / actor_id / created_at |

索引：node_type/source/projection、edge_type/src/tgt/projection、fingerprint unique、
invalidation node。全部 IF NOT EXISTS——幂等重放 PASS。

## 2. Architecture（边界分工）

```text
GraphProjectionService（What should the graph contain? — 零 DB 写）
        ↓ GraphProjection（frozen dataclass + fingerprint）
GraphPersistenceService（Persist this graph — 事务/幂等/失效映射/审计）
        ↓
GraphRepository（Database operations — kg_* SQL 唯一归属地）
        ↓
kg_* tables（migration 15）
```

SQL 全部收敛在 GraphRepository；projection/persistence 层零裸 SQL。

## 3. Persistence 生命周期

1. `persist(projection, actor_id=, rebuild=False)`；
2. fingerprint 幂等检查——命中即返回 `idempotent_hit=True`（零新增：nodes/edges/
   projections/provenance 全不重复，GP-CMP-009/010）；
3. SAVEPOINT 原子域：supersede 旧 active 投影（逻辑替换，不 DELETE）→ 写 metadata →
   写 nodes（状态映射 + provenance 必填校验 + invalidation log）→ 写 edges
   （端点存在性校验——不依赖连接级 FK，fail-closed）→ `graph:project` 审计
   （akb_provenance 复用）→ RELEASE；
4. 任一步失败 → ROLLBACK TO SAVEPOINT → pre-operation state（GP-CMP-011..013）。

## 4. Status / Invalidation 语义（§16）

| 源断言状态 | graph status | kg_invalidation_log.reason_status |
|---|---|---|
| candidate / validated / asserted | valid | —（不记录） |
| rejected | invalidated | rejected |
| deprecated | invalidated | deprecated |
| disputed | flagged（不删除） | disputed |
| hypothesized | 不投影（上游排除） | — |

invalidation 的 reason_status 一律取**源断言真实状态**（不从 graph_status 反推）；
非 rejected/deprecated/disputed 的失效请求 → E-V05-INVALID-INVALIDATION 拒绝。

## 5. Provenance（§18）

复用 akb_provenance（activity=`graph:project`；IMPL-002 治理事实继续经
`graph:entity-*` 落同一 provenance 表——零第二套系统）。回溯链（GP-CMP-018..021 实测）：

```text
kg_nodes.source_id → akb_assertions → (evidence_refs) → akb_evidence
                    → akb_evidence.document_id → akb_documents
kg_edges(supports).target → kg_nodes(evidence) → akb_evidence
kg_nodes(inference).source_id → akb_reasoning_runs
```

## 6. Determinism / Rebuild（§14/§15）

- node/edge id 复用 IMPL-001 确定性派生（SHA256 over canonical JSON）——零随机 UUID 入
  identity；projection_id/invalidation_id 为运行期记录标识，不参与 identity/fingerprint；
- fingerprint = projection canonical digest（无时间戳/PID/机器数据）；
  kg_projection_runs.fingerprint UNIQUE；
- rebuild = 重新投影 → persist → fingerprint 命中幂等（GP-CMP-022..024）；
  determinism 语义 = **同一数据库状态 → 同 IDs/同 fingerprint/同 raw storage**
  （事件溯源 source_id 跨库不重放——GP-CMP-006/007/023 按此语义锚定）。

## 7. Tests

GP-CMP-001..025（25 项，tests/v05_graph/test_graph_persistence.py）全 PASS：
schema×2 / persistence×3 / identity×3 / idempotency×2 / atomicity×3（故障注入回滚）/
status×4（rejected/deprecated/disputed/hypothesized）/ provenance×4（全链回溯）/
rebuild×3 / legacy isolation×1。v05_graph 全套 48 项（GS 7 + ER 16 + GP 25）PASS。

## 8. Legacy Isolation

`agent_kb.graph`（V0.1）零触碰：API 面互斥（GP-CMP-025）+ graph_edges 表零变化 +
test_phase6/7 回归 PASS（见回归记录）。