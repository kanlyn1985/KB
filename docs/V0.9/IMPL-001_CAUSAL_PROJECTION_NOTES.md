# V0.9 IMPL-001 Implementation Notes — CausalProjection Runtime

- Date: 2026-09-04 · Baseline: dc15ec5（V0.9 design）· V0.5..V0.8 frozen（零触碰
  实测）· **MIGRATION DECISION: NO MIGRATION**（本阶段）
- 新增：agent_kb/causal/（projection.py + __init__.py——新包，frozen 零触碰）；
  tests/v09_causal/test_causal_projection.py（CP-CMP-001..010）

## 行为契约（CP-CMP-001..010 全 PASS）

- **create projection**（001）：因果谓词断言（causes/caused_by/enables/prevents）
  → CausalProjection（projection_id/source_snapshot/causal_edges/fingerprint/
  generated_at=快照锚非时间戳）；
- **deterministic identity**（002）：projection_id = "cpr_"+SHA256(canonical
  ({snapshot, fingerprint}))；causal_id = "ce_"+SHA256(canonical 六元组)——
  同库状态双投影全等；新断言 → fingerprint 变；
- **same snapshot rebuild**（003）：同（断言快照+因果规格）→ 同 projection_id/
  causal_ids（Rule 3 rebuildable 实测）；
- **invalid relation reject**（004）：非因果谓词不进投影（白名单加载面）；
  relation 白名单 fail-close 语义；
- **missing provenance fail-close**（005）：①schema 层：V0.4 INV-005 触发器
  拒绝 provenance_ref 变更（frozen 保护实测——比 runtime 校验更强）；
  ②runtime 层：空 provenance 断言视图 → E-V09-CAUSAL-INVALID（零 fabricate）；
- **causal ≠ assertion**（006）：投影全流程 akb_assertions unchanged（快照实测）；
- **projection ≠ graph mutation**（007）：零 kg_nodes/kg_edges 写入（计数+快照
  实测——Rule 2，多层语义架构假设验证成立）；
- **provenance audit**（008）：graph:causal-projection-create 落 akb_provenance
  （projection_id/snapshot/fingerprint/edge count——复用零第二套）；
- **immutable projection**（009）：CausalProjection/CausalEdge frozen dataclass
  赋值拒绝实测；
- **frozen regression**（010）：V0.5..V0.8 十个 frozen 模块零 CausalProjection
  感知（源码审计——单向依赖）+ legacy 互斥 + 建图回归（canonical_view 不变）。

## MIGRATION DECISION（任务书要求的验证结论）

**NO MIGRATION（本阶段）**。理由：IMPL-001 只实现 projection runtime——投影以
内存 immutable 对象存在 + graph:causal-projection-create 审计快照（akb_provenance
metadata 携带 projection_id/snapshot/fingerprint/edges），单次投影/查询场景
provenance-only 完全可行（本阶段实测）。
migration 16（akb_causal_edges）**留给 IMPL-002/003 任务书决策**：仅当因果边需要
跨进程持久索引查询（KnowledgeHealth 批量信号/ConflictRuntime 检测）时必要——
与设计 §6 判断一致（基数 10^3-10^4 时 JOIN 推导不可行）。

## P2

- 因果边基数增长后内存投影的查询效率（IMPL-002 决策联动）。