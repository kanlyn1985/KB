# V0.5 Graph Provenance Spec

- Document ID: AKB-DD-V05-003 · Status: Design Baseline
- 原则：Graph 是投影——provenance 链必须保持五级连续（任务书），
  任何 Graph 元素缺失回溯链即非法（KG-01）。

## 1. Provenance 链（五级连续）

```text
Document（doc_id）
    ↓ akb_evidence.document_id
Evidence（evidence_id）
    ↓ akb_assertions.evidence_refs / akb_semantic_units.evidence_id
Assertion（assertion_id）
    ↓ Graph 投影（node_id/edge provenance_ref）
Graph Node/Edge（ent_/as_/ev_/su_/doc_/inf_ + edge id）
    ↓ derivation_json.parent_assertions（inferred）/ akb_reasoning_runs
Inference（run_id / inferred assertion_id）
```

## 2. 双向要求

- **trace back（回溯）**：任一 Node/Edge → 断言/证据/文档 的完整链
  （零孤儿：EntityNode 无 Evidence 支撑 = 违规；relates_to 边无源 Assertion = 违规）；
- **forward（下行）**：Document → 其全部 Evidence → 断言 → 投影元素
  （删除/失效传播视图）。

## 3. Audit（审计）

- Graph 元素只读：全部变更 = 重投影或治理动作，无原地改写；
- 审计事件（全部落 akb_provenance，activity 前缀 graph:）：
  graph:project（投影构建）、graph:merge / graph:split / graph:alias（identity 动作）、
  graph:invalidate（源失效级联标记）；
- 每次 audit 事件携带：触发者、源对象 id、before/after CanonicalJSON 快照
  （继承 V0.4 rule_input_snapshot 模式）；
- audit 查询：任一 Graph 元素的完整动作时序（继承 V0.4 audit_trail 模式）。

## 4. Rollback（回滚）

- 投影重建回滚：投影幂等（fingerprint 锚）——重跑投影即恢复一致状态
  （Graph 无独立事实，rollback = 重新投影，继承 V0.3/V0.4 锚语义）；
- merge/split 回滚：按 merge 记录逆操作（ENTITY_IDENTITY_SPEC §4）；
- 治理回滚（validated→disputed 等）→ Graph 级联失效标记（不物理删除）——
  rollback 后历史可审计（INV-005）；
- 回滚动作本身是治理动作（human），携带 provenance。

## 5. 失效传播模型

源 Assertion 状态变化 → 投影元素标记：
- rejected/deprecated → invalidated（查询默认排除，audit 可见）；
- disputed → flagged（查询保留 + 旗标）；
- 级联仅到直接投影元素——不跨实体传播（零连带误伤）。

## 6. 确定性

- 投影函数纯（同 DB 状态 → 同 Graph）；节点/边 id 确定性派生；
- 查询结果 canonical 排序（V0.3/V0.4 确定性约定延续）。