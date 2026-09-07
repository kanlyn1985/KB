# V0.8 IMPL-001 Implementation Notes — Hypothesis Runtime

- Date: 2026-09-04 · Baseline: 9ae6b92（V0.8 design）· V0.7 frozen 3df1811（零触碰
  实测）· NO-MIGRATION 路径（设计 §6 方案 a）
- 新增：agent_kb/hypothesis/（runtime.py + __init__.py——新包，frozen 零触碰）；
  tests/v08_hypothesis/test_hypothesis_runtime.py（HY-CMP-001..010）

## 行为契约（HY-CMP-001..010 全 PASS）

- **create**（001）：全字段（hypothesis_id/domain_ref/pack_ref/policy_ref/
  context_ref/statement/status=open/origin）；
- **deterministic id**（002）：hyp_id = "hyp_"+SHA256(canonical_json({statement,
  domain_ref, pack_ref, policy_ref, context_ref}))——跨实例全等；输入变→id 变；
- **idempotent duplicate**（003）：重复创建同 id + 零重复审计；
- **lifecycle**（004）：open→supported/refuted/withdrawn 全合法（transition_status
  受控原语 + withdraw_hypothesis 专用入口）；
- **invalid transition fail-close**（005）：closed（supported/refuted/withdrawn）
  无出边全拒；断言域状态（asserted/validated/inferred）设计红线禁入——
  E-V08-INVALID-TRANSITION；重复 withdraw 拒绝；
- **provenance**（006）：graph:hypothesis-create/withdraw 落 akb_provenance
  （hypothesis_id/actor/domain/context/pack/policy/from-to status）；
- **no assertion leakage**（007）：全生命周期零 akb_assertions 写入（计数实测 +
  LIKE 扫描零 hypothesis 痕迹）；
- **no graph leakage**（008）：零 kg_nodes/kg_edges 写入（计数实测）；
- **withdraw**（009）：状态重建正确（跨实例）+ 不存在 id → None（不 fabricate）；
- **frozen regression**（010）：V0.5/V0.6/V0.7 六模块零 hypothesis 感知（源码
  审计——单向依赖）+ legacy API 互斥 + 建图回归（canonical_view 不变）。

## 关键实现决策

- **存储 = provenance-only**（设计 §6 方案 a）：hypothesis 状态 = akb_provenance
  活动序列重放（graph:hypothesis-create 建态 + status/withdraw 迁移）；
- **重放排序锚**（关键修复）：provenance_id 为内容寻址 hash（非时间单调），
  occurred_at 秒级同秒有歧义——_audit 注入单调 seq 进 metadata，_load_state 按
  seq 重放（零 schema 修改，JSON 字段扩展）；
- transition_status 为 IMPL-002 Verdict 通道的受控原语（本阶段不开放自动调用）。

## P2

- get_hypothesis 全表扫描（provenance-only 路径查询面）—— EvolutionView/索引
  优化属 IMPL-003/FINAL 权衡（设计 P1 项监控中）。