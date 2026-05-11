---
doc_type: issue-fix-note
issue: 2026-05-10-standard-anchor-topic-resolution
status: fixed
summary: 标准号查询现在用精确 standard/document seed，并限制 graph 标准关系
tags:
  - retrieval
  - graph
  - fix
---

# Standard Anchor Topic Resolution Fix Note

## 修复

- `src/enterprise_agent_kb/topic_resolution.py`
  - 新增标准号锚点识别和归一化匹配。
  - 标准号 `standard_lookup/lifecycle_lookup` 只解析 `standard`、`document` 实体。
  - `_compact_topic_text()` 增加 `+` 归一化，支持 `GBT+40432-2021.pdf` 这类文件名。
- `src/enterprise_agent_kb/graph_retrieval.py`
  - 标准号 lifecycle 查询只允许 `references_standard`、`replaces_standard`。
  - 标准号 standard/lifecycle 查询不追加 weak `relates_to_term`。
- `tests/test_query_repair_regression.py`
  - 增加标准号 topic resolution 精确锚点回归。
  - 增加标准号 lifecycle graph relation 准入回归。

## 验证

命令：

`C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py::test_topic_resolution_uses_exact_standard_anchor_for_lifecycle_query tests/test_query_repair_regression.py::test_graph_retrieval_does_not_use_process_edges_for_standard_lifecycle_query tests/test_query_repair_regression.py::test_topic_resolution_keeps_software_architecture_activity_in_aspice_domain tests/test_query_repair_regression.py::test_topic_resolution_uses_process_activity_alias_for_software_architecture_analysis -q -m integration`

结果：

`4 passed`

手工上下文验证：

- topic entities: `GB/T 40432—2021`, `DOC-000009:GBT+40432-2021.pdf`
- graph relations: `references_standard`
- context contains `DOC-000009`, `GB/T 40432—2021`, `2022-03-01`
