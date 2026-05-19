---
doc_type: feature-design
feature: 2026-05-17-parse-risk-attribution
status: approved
summary: 为 parse risk 增加自动归因和行动建议
requirement: parse-quality-loop
tags:
  - parsing
  - diagnostics
  - parse-quality
---

# Parse Risk Attribution Design

## 0. 需求摘要

目标：解析质量闭环不只展示风险页，还要判断下一步应该修 parser/provider、selection、抽取链路、人工复核，还是补测试覆盖。

## 1. 归因类型

```text
provider_quality_issue
selection_rule_issue
extraction_chain_issue
review_only
test_coverage_gap
```

## 2. 挂载点

归因挂在 `doc_diagnostics.parse_quality`。原因是 document diagnostics 同时能读取 pages、quality report、evidence、source_units、facts、coverage 和 parse_views，是当前最完整的只读诊断层。

## 3. 验收契约

- 每个 parse risk page 输出 `attribution` 和 `recommended_action`。
- 文档级输出 `attribution_counts` 和 `recommended_actions`。
- Workbench 能显示归因摘要。
- 不让 LLM 做归因。
- 不新增破坏性 schema。
