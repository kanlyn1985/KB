# V0.6 IMPL-003 Implementation Notes — Provenance Closure

- Date: 2026-09-04 · Baseline: ddeb22f（IMPL-002）· V0.5 frozen e7a286e（零触碰实测）·
  V0.6 design 3610c99
- 新增：agent_kb/kgraph/provenance.py（ReasoningProvenanceService +
  CandidateProvenance + ReasoningProvenanceTrace + ProvenanceClosureError）

## 行为契约（PC-CMP-001..010 全 PASS）

- **context provenance 保留**（001）：orchestration 后 context 的
  assertion→evidence→document 链完好；
- **run 可追溯**（002）：trace_run → context_id/graph_fingerprint/status/parents/
  audit_refs（graph:reason 审计引用）；
- **candidate chain**（003）：六要素 conclusion/rule_ref+version/reasoning_run_id/
  context_id/parents/status 全可解析；
- **evidence 回溯**（004）：候选 → parents 并集 → evidence 全存在；
- **document 回溯**（005）：evidence → document 全存在；
- **missing fail-closed**（006）：缺 derivation → **V0.4 schema 层 CHECK 拒绝**
  （assertion_type='inferred' ⇒ derivation_json NOT NULL——数据库级保护实测）；
  ghost run/ghost 候选/非 inferred → E-V06-PROVENANCE-MISSING / E-V06-NOT-INFERRED
  （零 fabricate）；
- **deterministic trace**（007）：同状态双查询全等；候选按 assertion_id canonical 排序；
- **rollback/error trace**（008）：failed run 的 graph:reason-failed 审计含
  context_id + E-V06-ENGINE-FAILED；verify_closure 对零候选 run closed；
- **inferred lifecycle protection**（009）：trace 只读——候选恒 candidate；
  →asserted 永禁；→validated 治理路径开放；
- **V0.5 regression**（010）：provenance 面只读——canonical_view + kg_* 四表快照
  前后零变化。

## Provenance 链（实测形态）

```text
CandidateProvenance
  candidate_assertion_id → akb_assertions(inferred, derivation_json)
    ↓ reasoning_run_id
akb_reasoning_runs（复用，零新表）
    ↓ graph:reason 审计 metadata
context_id / graph_fingerprint（→ kg_projection_runs 锚复用）
    ↓ parent_assertions
akb_assertions（evidence_refs_json 并集）
    ↓
akb_evidence → akb_documents
  + rule_ref / rule_version
```

## 复用声明

零第二套 provenance：全部经 akb_provenance（graph:reason / graph:reason-failed）
+ akb_reasoning_runs（V0.4）+ kg_projection_runs（V0.5）；服务为只读查询/校验面，
零写操作（PC-CMP-010 快照验证）。

## P2

- verify_closure 的环/深度维度在 context 构建层已控（IMPL-001 hop 上限），
  跨 run 迭代环属 IMPL-004 范围。