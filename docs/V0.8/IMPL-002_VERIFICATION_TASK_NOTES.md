# V0.8 IMPL-002 Implementation Notes — VerificationTask Runtime

- Date: 2026-09-04 · Baseline: 9842449（IMPL-001）· V0.7 frozen 3df1811 ·
  NO-MIGRATION 路径延续（provenance-only 存储 + seq 锚重放）
- 新增：agent_kb/hypothesis/verification.py（VerificationTaskRuntime +
  VerificationTask + verification_task_identity + VerificationTaskError）；
  tests/v08_hypothesis/test_verification_task_runtime.py（VT-CMP-001..010）；
  hypothesis/__init__.py 导出追加（V0.8 阶段文件）

## 行为契约（VT-CMP-001..010 全 PASS）

- **task create**（001）：全字段（task_id/hypothesis_id/task_type/spec/status=
  created/created_by/evidence_requirements canonical 序）；
- **deterministic id**（002）：task_id = "vt_"+SHA256(canonical_json
  ({hypothesis_id, task_type, spec, evidence_requirements sorted}))——跨实例
  全等；零随机/零时间入 hash；输入变 → id 变；
- **idempotent duplicate**（003）：重复创建同 task + 零重复审计；
- **lifecycle**（004）：created→running→completed / running→failed /
  created|running→cancelled 全合法；
- **invalid transition fail-close**（005）：completed→running、failed→completed、
  cancelled→任意（start/complete/fail/cancel 四操作）全拒——
  E-V08-TASK-INVALID-TRANSITION；
- **hypothesis binding**（006）：不存在 hypothesis → E-V08-HYPOTHESIS-NOT-FOUND
  fail-closed；非法 task_type/spec/requirements → E-V08-TASK-INVALID；
- **provenance**（007）：五活动（create/start/complete/failed/cancel）全进
  akb_provenance（task_id/hypothesis_id/from-to transition/requirements/actor）；
  复用零第二套审计；
- **no leakage**（008）：全生命周期零 akb_assertions/kg_nodes 写入 + 零
  hypothesis 状态修改（IMPL-001 服务面只读引用）；
- **replay determinism**（009）：跨实例 seq 锚重放状态一致；多任务互不串扰；
  canonical ordering（evidence_requirements sorted）；不存在 → None；
- **frozen regression**（010）：V0.5/V0.6/V0.7 六 frozen 模块零 VerificationTask
  感知（源码审计——单向依赖）+ legacy API 互斥 + 建图回归（canonical_view 不变）。

## 关键实现决策

- 存储延续 IMPL-001 provenance-only + metadata 单调 seq 锚（重放排序确定性——
  provenance_id 内容寻址非时间单调的既有结论）；
- 零 hypothesis 状态修改：task 只读引用 hypothesis（绑定校验经 IMPL-001
  get_hypothesis）——verdict 属 IMPL-003；
- VALID_TASK_TYPES 白名单（evidence_review/experiment/expert_review/
  literature_check）fail-closed。

## P2

- 任务指派队列视图/陈旧度提醒属 FINAL 权衡（设计 P2 项）。