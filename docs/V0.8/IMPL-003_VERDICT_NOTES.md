# V0.8 IMPL-003 Implementation Notes — Verdict Runtime

- Date: 2026-09-04 · Baseline: cb0fc26（IMPL-002）· V0.7 frozen 3df1811 ·
  NO-MIGRATION 路径延续（provenance-only + seq 锚）
- 新增：agent_kb/hypothesis/verdict.py（VerdictRuntime + Verdict +
  verdict_identity + VerdictError）；tests/v08_hypothesis/
  test_verdict_runtime.py（VD-CMP-001..010）；__init__ 导出追加（V0.8 阶段文件）

## 行为契约（VD-CMP-001..010 全 PASS）

- **verdict create**（001）：全字段（verdict_id/hypothesis_id/task_id/result/
  evidence_refs/reason/actor/created_seq）+ hypothesis 迁移驱动
  open→supported 实测；
- **deterministic id**（002）：verdict_id = "vrd_"+SHA256(canonical_json
  ({hypothesis_id, task_id, result, evidence_refs sorted}))——跨实例全等；
  输入变 → id 变；零时间/零随机入 hash；
- **idempotent duplicate**（003）：重复 verdict 零重复审计/零重复迁移；
- **task completed validation**（004）：未完成 task → E-V08-TASK-NOT-COMPLETED；
  ghost hypothesis → E-V08-HYPOTHESIS-NOT-FOUND；ghost task → E-V08-TASK-NOT-FOUND；
  task-hypothesis 绑定不匹配 → E-V08-VERDICT-INVALID；
- **invalid result fail-close**（005）：assertion 域结果（validated/asserted/
  inferred）+ 未知结果 → E-V08-VERDICT-INVALID；ghost/空 evidence_refs 拒绝
  （akb_evidence 存在性校验——零 fabricate）；
- **hypothesis transition**（006）：verdict 只驱动 open→supported/refuted；
  inconclusive 保持 open（裁决史记录）；supported 后幂等返回零直通；
  supported→asserted/validated/inferred 全拒（IMPL-001 红线复证）；
- **provenance**（007）：graph:hypothesis-verdict 落 akb_provenance
  （verdict_id/hypothesis_id/task_id/result/evidence_refs/actor/from-to）；
- **no leakage**（008）：零 akb_assertions/kg_nodes/kg_edges 写入（计数实测）+
  零 candidate promotion（Verdict ≠ Assertion ≠ Graph Node ≠ Promotion）；
- **replay determinism**（009）：跨实例重建一致；list_verdicts canonical 排序；
  多 verdict seq 序不串扰；不存在 → None；
- **frozen regression**（010）：V0.5/V0.6/V0.7 六 frozen 模块零 Verdict 感知
  （源码审计——单向依赖）+ legacy 互斥 + 建图回归（canonical_view 不变）。

## 关键设计落地

- 闭环贯通：Hypothesis(create) → VerificationTask(create/start/complete) →
  Verdict(supported/refuted/inconclusive) → hypothesis 状态迁移
  （经 IMPL-001 transition_status 受控原语——verdict 只能驱动 open→supported/
  refuted；inconclusive 记裁决史）；
- 全链校验：hypothesis 存在 → task 存在 → task completed → 绑定一致 →
  evidence 存在（akb_evidence 实表校验）→ result 白名单——六道 fail-closed 门；
- seq 锚延续（provenance-only 重放确定性）。

## P2

- verdict 的 evidence 校验深度 = 存在性（设计 P1 定标项默认档）——五级链回溯
  可在 EvolutionView 阶段叠加。