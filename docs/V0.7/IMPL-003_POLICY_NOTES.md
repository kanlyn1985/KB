# V0.7 IMPL-003 Implementation Notes — ReasoningPolicy Runtime

- Date: 2026-09-04 · Baseline: 50be33e（IMPL-002）· V0.6 frozen b317c6e ·
  V0.5 frozen e7a286e（零触碰实测）
- 新增：agent_kb/policy/（runtime.py + __init__.py——新包，frozen 零触碰）；
  tests/v07_policy/test_reasoning_policy.py（POLICY-CMP-001..010）

## 行为契约（POLICY-CMP-001..010 全 PASS）

- **policy load**（001）：activate → policy_ref（"pol_"+SHA256）+ 幂等语义
  （同 policy_id+version 重复激活零重复审计）；
- **schema validation**（002）：空 id/version、未注册规则引用、未知域预算、
  depth/candidates 超上限、load_order 越集、非法 status_filter 全拒绝
  （E-V07-POLICY-INVALID）；合法收紧（空 order、低预算）正向通过；
- **deterministic policy_id**（003）：policy_ref = "pol_"+SHA256(canonical_json
  ({policy_id, version, enabled_rules, per_domain_budgets, load_order, depth,
  candidates, status_filter}))——跨实例全等；内容变化 → ref 变；
- **version conflict handling**（004）：同 policy 多版本共存（list/get 最新）；
- **enable/disable semantics**（005）：check_enabled 按 package@version 精确匹配
  （flow-rules@1.0.0 启用 ≠ flow-rules@2.0.0）；
- **budget enforcement**（006）：apply_budgets per-domain 预算执行——超限
  E-V07-BUDGET-EXCEEDED fail-closed / 界内放行 / 未声明域回退全局 max_candidates；
- **provenance**（007）：graph:reason-policy 落 akb_provenance（enabled_rules/
  budgets/depth/candidates/before-after 快照）；重复激活零重复审计；
- **reasoning integration**（008）：policy 版本入 V0.4 configuration →
  configuration_hash 反映 policy（确定性隔离实测）；check_enabled 门控语义贯通；
  V0.6 全链路行为不变；
- **deterministic replay**（009）：同策略跨实例激活同 ref + 预算判定全等；
- **frozen regression**（010）：V0.6 orchestrator/context 零 policy 感知
  （单向依赖：policy→kgraph/reasoning/rules，frozen 不感知）+ legacy 零引用。

## 关键设计落地

- Policy 只能收紧不能放宽：max_derivation_depth ≤ 4、max_candidates ≤ 1024
  （V0.6 frozen 上限硬校验）；
- status_filter 白名单 = valid/flagged（invalidated/hypothesized 无法经 policy
  进入推理面）；
- before/after 快照进审计（policy 激活事件完整可追溯）。

## P2

- load_order 与 provider 注入顺序的交互执行（编排侧批量注入）属 IMPL-004/
  实现期后续——本阶段 check_enabled/apply_budgets 单点语义已锚定。