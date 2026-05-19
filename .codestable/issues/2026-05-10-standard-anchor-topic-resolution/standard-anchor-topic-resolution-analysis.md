---
doc_type: issue-analysis
issue: 2026-05-10-standard-anchor-topic-resolution
status: fixed
summary: 标准号锚点未进入 topic entity type 和 graph relation 准入
tags:
  - retrieval
  - root-cause
---

# Standard Anchor Topic Resolution Analysis

## 根因

`topic_resolution._entity_types_for_query_type()` 对 `lifecycle_lookup` 只检索 `process` 实体。标准号查询中 `GB/T` 片段会匹配到过程实体 alias，例如控制导引过程里的 `GB/T 20234.3`，导致 seed entity 漂移。

修正 topic seed 后还存在第二层问题：`graph_retrieval` 对 `lifecycle_lookup` 允许 `has_process`。当 seed 是文档实体时，`has_process` 会拉出整篇文档的过程/章节事实，不适合“实施日期/发布日期/标准号”查询。

## 方案

- topic resolution 识别标准号锚点。
- `standard_lookup/lifecycle_lookup` 含标准号锚点时，只检索 `standard` 和 `document` entity type。
- 标准号锚点必须在实体 canonical name、description 或 alias 中精确归一化匹配。
- `lifecycle_lookup` 含标准号锚点时，graph strong relations 限定为 `references_standard`、`replaces_standard`。
- `standard_lookup/lifecycle_lookup` 含标准号锚点时，不再追加 weak `relates_to_term`。
