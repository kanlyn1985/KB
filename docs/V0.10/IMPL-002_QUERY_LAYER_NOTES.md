# V0.10 IMPL-002 Implementation Notes — Persistence Query Layer

- Date: 2026-09-04 · Baseline: ae55fee（IMPL-001）· V0.5..V0.9 frozen（零触碰实测）
- 新增：storage/query.py（ScaleQueryRuntime + QueryCursor + QueryError）；
  migrations.py（V10_QUERY_INDEX_MIGRATION version=17 追加）；storage/__init__.py
  导出；tests/v10_persist/test_v10_query.py（V10-QUERY-CMP-001..012）

## Index Verification 结论（任务书要求）

migration 16 索引审计：causal cause/effect ✓、health target/type ✓、conflict
type/status ✓；**缺失**：causal relation_type ✗、conflict severity ✗、health
(fingerprint, signal_id) 排序锚 ✗。→ **migration 17**（v10_query_indexes，
append-only 三索引）补齐；零修改 migration 16（statements 数量/内容零变更——
测试 012 零修改锚实测）。

## 行为契约（V10-QUERY-CMP-001..012 全 PASS）

- **causal query**（001/002）：list_causal_edges 全量 3 边 + cause/effect/relation
  过滤正交；
- **health history**（003）：12 信号（3 hyp×4）；时间过滤走
  akb_provenance.occurred_at JOIN（零 schema 变更）——from_time 远未来→空、
  远过去→全量；
- **conflict query**（004）：type/severity/status 过滤；
- **cursor pagination**（005）：limit=2 两页遍历无重无漏；**零 offset**；
- **cursor replay determinism**（006）：同 cursor 重放一致；
- **invalid cursor fail-close**（007）：篡改指纹/跨 query 复用/垃圾串全拒
  （E-V10-QUERY-CURSOR-INVALID——QueryCursor.decode 类型指纹校验）；
- **limit boundary**（008）：0/负数/501 超帽/非 int 全拒（E-V10-QUERY-PAGE-INVALID，
  cap=500）；500 合法；
- **deterministic ordering**（009）：causal/conflict PK ASC、health
  (fingerprint, signal_id) 联合键 ASC（migration 17 索引锚）；多次查询全等；
- **empty result**（010）：count=0+has_more=False+cursor=None 不 fabricate；
- **read-only isolation**（011）：三查询全流程 akb_assertions/kg_nodes/kg_edges/
  akb_provenance unchanged（快照实测）；
- **frozen regression**（012）：chain 1..17 + migration 16 零修改锚（11 statements）
  + 十一 frozen 模块零感知 + legacy 互斥 + 建图回归。

## Cursor Model

QueryCursor = keyset（最后一行排序键）+ 类型指纹（8 hex）——确定性序列化
（canonical JSON）+ 指纹校验（防篡改）+ kind 校验（防跨 query 复用）；
decode fail-close 三分支全实测。

## 既有测试适配（任务书授权）

- v06 contract 015 + v10 persist 001：版本上限断言 `in (15,16)`/`range(1,17)` →
  `in (15,16,17)`/`range(1,18)`——migration 17 为任务书明示授权
  （"如果缺失：只能追加 migration 17"）；语义保持（版本唯一+链完整+16 零修改）。

## P0/P1/P2

- P0 = 0
- P1 = 1（查询一致性：health 时间过滤经 LEFT JOIN akb_provenance——
  provenance_ref 缺失的行 occurred_at 为 NULL，时间过滤会排除它们；当前
  persist 面保证 provenance_ref 必填（migration CHECK），缺口关闭）
- P2 = 1（并发读风险：SQLite WAL 模式下读不阻塞写；查询层全只读零锁升级；
  跨进程并发读写一致性依赖单写者约定——V0.10 P1 延续项）
- cursor correctness = 实测锚定（005/006/007）；index 不足风险 = 已通过
  migration 17 补齐（三缺失索引全建）