# V0.6 IMPL-002 Implementation Notes — Graph Reasoning Orchestrator

- Date: 2026-09-04 · Baseline: 7b17625（IMPL-001）· V0.5 frozen e7a286e（零触碰实测）·
  V0.6 design 3610c99
- 新增：agent_kb/kgraph/orchestrator.py（GraphReasoningOrchestrator +
  OrchestrationTrace + GraphOrchestrationError）

## 行为契约（OC-CMP-001..010 全 PASS）

- **context 输入**（001）：只接受 GraphReasoningContext；非 context 类型 →
  E-V06-INVALID-CONTEXT；结果携带 context_id；
- **engine 复用**（002）：零新 ReasoningEngine——默认构造 V0.4
  ReasoningEngine+BuiltinRuleReasoner；外部 V0.4 实例注入时原样复用
  （orch.engine is my_engine）；零 LLM（默认 provider deterministic）；
- **deterministic candidates**（003）：同 context 双 run → 同 fingerprint +
  同候选集；幂等经 V0.4 fingerprint 锚（第二次 run 命中既有 run 零新候选）；
- **derivation chain**（004）：候选 derivation 六键齐全
  （rule_ref/parent_assertions/reasoner_id/rule_input_snapshot/confidence_basis/
  depth）+ reasoning_run_id 关联 run；parent 断言全部可回溯 akb_assertions；
- **provenance**（005）：graph:reason 审计落 akb_provenance（context_id/
  graph_fingerprint/parent_assertions/candidates）；trace.provenance 携带
  (candidate × parent) 推导对；context 自身链（IMPL-001）完好；
- **candidate lifecycle**（006）：候选恒 assertion_type=inferred + status=candidate；
  candidate→validated 治理路径开放（无 ILLEGAL 拒绝）；
- **inferred 保护**（007）：inferred→asserted 永久禁止（V0.4 硬门延续）；
  orchestrator 零晋升动作（全库零 asserted 的 inferred）；
- **failure fail-closed**（008）：engine 崩溃（V0.4 runs.fail+re-raise 语义）→
  编排层捕获转 failed result + graph:reason-failed 审计 + 零候选；深度越界
  （hop > MAX_DERIVATION_DEPTH=4）→ E-V06-DEPTH-OVERFLOW；
- **no LLM**（009）：源码审计零 LLM/网络调用；默认 provider deterministic；
- **V0.5 regression**（010）：编排后 canonical_view 不变（候选不入 V0.5 图）；
  kg_* 四表快照零变化；akb_provenance 仅新增 graph:reason 审计（预期语义）。

## 关键设计落地

- ReasoningContext 桥接：GraphReasoningContext → V0.4 ReasoningContext
  （ontology_scope="v06-graph" + configuration={context_id, graph_fingerprint,
  hop, status_filter, rule_set_version}）→ 进入 V0.4 fingerprint 计算流；
- 深度独立定义：MAX_DERIVATION_DEPTH=4（≠ Q-04 query depth 8）；
  MAX_CANDIDATES_PER_RUN=1024（爆炸控制）；
- V0.4 crash 语义桥接：engine re-raise → 编排层 catch → failed result
  （审计不外泄异常）。

## P2

- 环检测/深度控制依赖 V0.4 engine 既有机制 + hop 上限（候选集层面的图遍历环
  截断在 IMPL-001 邻域面已控；多跳链式推理（run→re-project→run）的迭代环检测
  属 IMPL-003/004 范围）。