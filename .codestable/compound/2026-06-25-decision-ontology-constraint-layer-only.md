---
doc_type: decision
category: constraint
slug: ontology-constraint-layer-only
title: Ontology 只作约束/校验层，不生成事实
date: 2026-06-25
sprint: sprint2-ontology-and-bugfix
status: accepted
related_adr: docs/ontology/adr/0003-ontology-constraint-layer-only.md
tags: [ontology, constraint, evidence-constrained, architecture]
---

# Decision: Ontology 只作约束/校验层，不生成事实

> 完整 ADR：`docs/ontology/adr/0003-ontology-constraint-layer-only.md`

## 决定

`kb1_ontology` 接入主系统时是**只读约束 / 校验 / 召回辅助层**，硬约束：

1. **不生成事实**：输出字段名只用 `signal` / `constraint` / `check` / `validation`，绝不叫 `evidence` / `fact` / `source_truth`。
2. **不绕过 `evidence_judge`**：答案事实仍只来自经 `evidence_judge` 裁决的证据候选。
3. **Sprint 2 不改答案**：`changed_retrieval` / `changed_answer` 恒为 `False`；guard post-check 只出 warning，不改写 `direct_answer`。
4. **adapter 不调 LLM**：实体检测走规则 + ontology.db 查表；ontology 自带 LLM 的 router/decomposer 不接入主链路。
5. **不引入 OWL/RDF / 重图数据库**：只读 `ontology.db`（SQLite，只读模式）。
6. **`ontology.db` 非主事实库**：主事实库仍为 `knowledge.db`。

## 为什么

KB1 核心不变式：**每个答案事实都经 `evidence_judge` 在带证据候选上裁决**，绝不由 LLM 或辅助知识层裁决。Ontology 首次接入（Sprint 2 前 fully isolated）必须保住这条不变式。

## 考虑过的替代方案

- **主动召回过滤**（ontology 按 entity-type 过滤/重排召回候选）：Sprint 2 否决，因改检索排序（违反 `changed_retrieval=False`）且可能在裁决前丢弃有效证据。留 Sprint 3 评估。
- **事实源接入**（ontology 直接注入答案事实）：**永久否决**，违反核心不变式。

## 后果

- 安全性 by construction：`ontology.db` 损坏/缺失时主链路不受影响（adapter 返回空 signal + errors，永不抛异常）。
- Sprint 2 答案质量不受 ontology 影响（`answer_changed_by_ontology=False`）。本 Sprint ontology 价值是 plumbing / 可观测性 / 回归安全，不是答案提升。
- Sprint 3 可在**独立 ADR + 不回归 eval 基线证据**前提下放宽约束 3（允许 ontology 作*候选增强通道*影响检索，类似 graph）。约束 1/2/4/6 **永久**。
- 可观测字段：`ontology_post_check_status`、`ontology_post_checks`；`answer_changed_by_ontology` 是必须保持 `false` 的金丝雀。

## 关联

- ADR：`docs/ontology/adr/0003-ontology-constraint-layer-only.md`
- 实现：`src/enterprise_agent_kb/ontology_adapter.py`、`answer_api._compose_final_answer`
- Feature design：`.codestable/features/2026-06-25-ontology-shadow-guard-adapter/ontology-shadow-guard-adapter-design.md`
