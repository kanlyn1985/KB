# V0.4 Derivation Chain Spec

- Document ID: AKB-DD-V04-003 · Status: Design Baseline
- 继承：INV-002（derived 不静默覆盖/完整 derivation）+ INV-004（Evidence 可溯）+
  V0.2 E-CANDIDATE-BUILD-FAILED（缺 derivation 拒绝）先例。

## 1. Derivation Chain 定义

```text
Inferred Assertion (n-th order)
    ↓ derivation_json.parent_assertions
Parent Assertions (n-1)  ∈ {extracted, observed, inferred(更早 run), validated}
    ↓ evidence_refs / source_unit_refs
SemanticUnit[]
    ↓ evidence_id
Evidence[]
    ↓ document_id
Document[]
```

## 2. Chain 完备性规则

DC-01 每个 inferred 的 parent_assertions 非空且全部存在于 akb_assertions
      （不存在的 parent → E-V04-PARENT-NOT-FOUND，提案拒绝）；
DC-02 环检测：parent 链不得成环（含自引用）——run 内新产 inferred 不得作为同 run
      后继提案的 parent（一阶限定）；跨 run 链允许（深度记录 derivation.depth）；
DC-03 derivation_json 六键完备：rule_ref / parent_assertions / reasoner_id /
      rule_input_snapshot / confidence_basis / （可选）synthesis_run_id——
      前三键缺一 = P0 级拒绝（继承 V0.2 校验）；
DC-04 rule_input_snapshot = CanonicalJSON(parent 断言的语义摘要)——审计可回放
      "当时推理看到了什么"（parent 后续被 disputed 不影响历史快照——INV-005）；
DC-05 evidence_refs = parent 并集（零缺失——V03-REQ-014 精神跨层延续）；
DC-06 depth 记录：derivation.depth = max(parent.depth) + 1（extracted/observed=0）；
      MAX_DEPTH（默认 8）超限 → E-V04-DEPTH-EXCEEDED（防失控链）。

## 3. 反向追踪查询

`trace_inference_chain(assertion_id)`（V0.4 实现期交付）：
递归展开 parent 链至根（extracted/observed），输出：
- 全部祖先断言（按代分层）；
- 每跳的 rule_ref/reasoner_id/snapshot 摘要；
- 汇聚的 Evidence/Document 全集；
- 环/缺失检测报告。

确定性：同断言两次 trace 结果等价（V0.3 CMP-025 先例延续）。

## 4. Chain 与治理的交互

- parent 被 rejected → 其 inferred 子女**不自动失效**（INV-005 历史完整），
  但 trace 报告标注"parent rejected"——治理复核入口；
- parent 被 disputed → 同上（不自动传播状态——状态变更只走治理）。

## 5. Provenance 双链

- 断言级：akb_provenance(activity=infer, inputs=[run_id])；
- run 级：akb_reasoning_runs（含 parent_ids 快照）；
- 汇合：trace_candidate_synthesis 同款模式扩展（activity=infer 分支）。