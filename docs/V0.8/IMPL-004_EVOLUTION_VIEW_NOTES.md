# V0.8 IMPL-004 Implementation Notes — EvolutionView Runtime

- Date: 2026-09-04 · Baseline: d6ccc4c（IMPL-003）· V0.7 frozen 3df1811 ·
  NO-MIGRATION 路径延续（provenance-only 只读聚合）
- 新增：agent_kb/hypothesis/evolution.py（EvolutionViewRuntime + EvolutionView +
  TimelineEntry + EvolutionViewError）；tests/v08_hypothesis/
  test_evolution_view.py（EV-CMP-001..010）；__init__ 导出追加（V0.8 阶段文件）

## 行为契约（EV-CMP-001..010 全 PASS）

- **view create**（001）：全字段（hypothesis_id/current_status/created_seq/tasks/
  verdicts/timeline/provenance_refs/fingerprint）+ immutable（frozen dataclass
  赋值拒绝实测）；
- **deterministic fingerprint**（002）：fingerprint = "evw_"+SHA256(canonical_json
  (全视图 payload))——跨实例/双查询全等；零 timestamp/零随机入 hash；
- **complete lifecycle timeline**（003）：hypothesis-create → task-create →
  task-start → task-complete → hypothesis-verdict → hypothesis-status 全程
  覆盖 + seq 排序 + 首条恒 hypothesis-create；
- **missing fail-close**（004）：不存在 hypothesis → None（禁止 fabricate）；
  非法 id → E-V08-HYPOTHESIS-INVALID；
- **task/verdict aggregation**（005）：多 task（2）/多 verdict（supported +
  inconclusive）全聚合零遗漏；
- **provenance trace**（006）：provenance_refs 全部实存于 akb_provenance
  （零第二套数据源）；
- **ordering determinism**（007）：tasks/verdicts by id、timeline by seq、
  provenance_refs canonical——三重 canonical 序；
- **no assertion leakage**（008）：视图查询零 akb_assertions/kg_nodes/kg_edges
  写入（计数实测）+ 零 promotion；
- **replay consistency**（009）：生命周期推进视图跟随（task/verdict 增量反映 +
  状态迁移 refuted + fingerprint 变化检测）+ 双实例重放全等；
- **frozen regression**（010）：V0.5/V0.6/V0.7 六 frozen 模块零 EvolutionView
  感知（源码审计——单向依赖）+ legacy 互斥 + 建图回归（canonical_view 不变）。

## 关键设计落地

- 数据来源 = akb_provenance 活动面（graph:hypothesis-* /
  graph:verification-task-* 全活动）+ 三 runtime 既有读面（HS/TR/VR 注入或
  自建）——零新表/零 migration/零第二套审计；
- timeline = seq 锚排序（延续 IMPL-001 单调 seq 结论）；label 规范化
  （graph:verification-task-create → task-create）；
- view fingerprint 进入 provenance payload 全量（tasks/verdicts/timeline/refs）。

## P2

- list_evolution_views 全表扫描（provenance-only 路径查询面）——批量索引/
  分页属 V0.9 runtime optimization 候选（设计 P2 项延续）。