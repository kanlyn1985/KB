# V0.9 IMPL-002 Implementation Notes — KnowledgeHealth Runtime

- Date: 2026-09-04 · Baseline: 9977c13（IMPL-001）· V0.5..V0.8 frozen（零触碰实测）·
  **MIGRATION DECISION: NO MIGRATION 维持**
- 新增：agent_kb/health/（runtime.py + __init__.py——新包，frozen 零触碰）；
  tests/v09_health/test_knowledge_health.py（KH-CMP-001..010）

## 行为契约（KH-CMP-001..010 全 PASS）

- **create health**（001）：全字段（health_id/target_ref/target_type/signals 四类/
  score/status/provenance_refs/fingerprint）+ 0..1 score + healthy/watch/degraded；
- **deterministic identity**（002）：health_id = "khs_"+SHA256(canonical_json
  ({target, target_type, snapshot, signals}))——跨实例全等；
- **same snapshot rebuild**（003）：同（target+snapshot+causal+provenance）→
  同 health_id；
- **stability signal**（004）：V0.4 transition 审计计数（活动名
  "transition:<from>-><to>"动态 + assertion_id 在 inputs_json 列）——变更越多
  stability 越低（单调递减实测）；
- **verification signal**（005）：hypothesis/verdict 关联（statement 文本含
  target 名——确定性文本关联）；verdict 记录后信号值上升；
- **causal coverage signal**（006）：目标在 CausalProjection 中的边数
  （IMPL-001 读面）；
- **conflict signal**（007 同组）：V0.3 flagged（disputed）断言读取——零自动产生；
- **health ≠ mutation**（007）：akb_assertions/kg_nodes/kg_edges unchanged
  （快照实测——Health ≠ Truth ≠ Mutation）；
- **provenance audit**（008）：graph:knowledge-health-create 落 akb_provenance
  （health_id/target/signals/score/fingerprint——复用零第二套）；
- **immutable**（009）：frozen dataclass 赋值拒绝 + 重复 create 零重复审计；
- **frozen regression**（010）：V0.5..V0.9causal 十一个 frozen 模块零感知（源码
  审计——单向依赖）+ legacy 互斥 + 建图回归（canonical_view 不变）。

## MIGRATION DECISION（重新评估结论）

**NO MIGRATION 维持**。依据：健康信号为单次只读聚合（同状态同报告），
graph:knowledge-health-create 审计快照已满足当前消费面（单目标查询）；跨进程
历史趋势查询（信号时序对比）当前无消费方。migration 16（akb_health_signals）
继续留给出现历史趋势消费方的任务书决策（IMPL-003 ConflictRuntime 检测基数
评估时复核）。

## 关键实现决策

- stability 信号的数据源实锚：V0.4 transition 审计活动名为动态
  "transition:<from>-><to>"且 assertion_id 在 inputs_json 列（探针实测后对齐）；
- verification 关联语义 = verdict 的 hypothesis statement 文本含 target 名
  （确定性文本关联——IMPL-003 EvolutionView 可叠加更精确回溯）；
- score 加权聚合：0.3*stability + 0.3*verification + 0.2*(1-conflict) +
  0.2*coverage（round 4）——阈值 healthy≥0.7/watch≥0.4。

## P2

- 信号时序趋势视图（需 health signals 历史消费方）——migration 16 决策联动。