# V0.10 IMPL-001 Implementation Notes — Migration 16 & Persistence Foundation

- Date: 2026-09-04 · Baseline: 6640ecf（V0.10 design）· V0.5..V0.9 frozen（零触碰
  实测——唯一非 V0.10 新产物修改 = migrations.py append-only 追加 + v06 contract
  015 版本上限适配）
- 新增：migrations.py（V10_SCALE_PERSISTENCE_MIGRATION version=16 追加）；
  causal/persistence.py（ScalePersistenceRuntime + PersistError）；
  tests/v10_persist/test_v10_persist.py（V10-PERSIST-CMP-001..012）

## Migration 16（v10_scale_persistence，append-only 三新表）

- **akb_causal_edges**：causal_edge_id PK / cause_ref / effect_ref（自环 CHECK
  cause≠effect）/ relation_type CHECK 四值 / condition_refs_json /
  mechanism_ref / assertion_id FK→akb_assertions / status CHECK 三值 /
  confidence CHECK 0..1 / provenance_ref NOT NULL / fingerprint + 三索引
  （effect/cause/fingerprint）；
- **akb_health_signals**：signal_id PK / target_ref / target_type CHECK 三值 /
  signal_type CHECK 四值 / value CHECK ≥0 / detail / health_id /
  provenance_ref / computed_snapshot / fingerprint + 三索引；
- **akb_conflict_records**：conflict_id PK / conflict_type CHECK 三值 /
  source_refs_json / target_refs_json / severity CHECK 三值 / status CHECK
  三值（open/reviewed/dismissed——零 resolution）/ evidence_refs_json /
  fingerprint / created_from_snapshot / provenance_ref + 二索引；
- 全部 IF NOT EXISTS；零修改既有表；实测：自环/relation/type CHECK enforced、
  FK（事务外 pragma）enforced、幂等重放 OK。

## Persistence Adapter（ScalePersistenceRuntime——API 零破坏）

- persist_causal_edges：projection.causal_edges → akb_causal_edges；**assertion
  锚解析**：CausalEdge.provenance_refs[0] = 源断言 provenance_ref → 反查
  akb_assertions.assertion_id（FK 合法实体）；反查失败 fail-closed
  （E-V10-PERSIST-INVALID）；
- persist_health_signals：四信号 → akb_health_signals（signal_id =
  health_id:signal_type）；persist_conflict_records：records →
  akb_conflict_records；
- 幂等：按主键查重，零重复写入（edges_written 标志）；单事务 + SAVEPOINT
  回滚（011 异常零残留实测）；identity 零新算法（runtime 已派生 id 直接落表）；
- persist 零写 provenance（介质变更非知识事件——设计 ARCHITECTURE §2）。

## CONTRACT-CMP-015 适配说明（V0.10 设计授权）

v06 contract 015 的 versions[-1]==15 上限断言随 migration 16 授权适配为
`in (15, 16)`——语义保持（版本唯一 + 链完整 + 零修改既有表）；docstring 记录
授权来源。

## P0/P1/P2

- P0 = 0
- P1 = 1（并发写锁语义：SQLite 单写者模型——同 connection 串行即可；跨进程
  场景需显式串行化说明，实现期任务书继续）
- P2 = 1（constraint 缺口评估：akb_health_signals 的 target FK 未加（target 可
  为 assertion/entity/hypothesis 三态——多态 FK 不可表达，应用层校验已实现）；
  migration 风险 = 0（append-only 实测））