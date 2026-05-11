---
doc_type: issue-fix-note
issue: 2026-05-10-post-rerank-injection-provenance
status: fixed
summary: 后置 direct 注入现在统一保留 graph provenance
tags:
  - retrieval
  - graph
  - fix
---

# Post-rerank Injection Provenance Fix Note

## 修复

- `src/enterprise_agent_kb/query_api.py`
  - 新增 `_merge_injected_hits()`。
  - `_inject_exact_standard_hits()`、`_inject_direct_term_definition_hits()`、`_inject_direct_wiki_hits()` 改为复用统一合并契约。
  - `rerank_explanations.graph_relation` 兼容读取 hit 内部的 `relation` 字段。
- `tests/test_query_repair_regression.py`
  - 新增 `test_injected_hit_merge_preserves_graph_provenance_on_replacement()`。

## 验证

命令：

`C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py -q -k "injected_hit_merge or cc_resistance or answer_query_defines_short_cc_acronym or answer_query_asks_for_clarification_on_ambiguous_cc"`

结果：

`4 passed, 50 deselected`

命令：

`C:\Python314\python.exe -m py_compile src\enterprise_agent_kb\query_api.py`

结果：通过。

## 后续

Graph contribution dashboard 之后的 `graph_retention_rate` 会更接近真实贡献。若仍存在 `graph_lost_after_rerank_dominates`，下一步应分析 query_type 维度的 rerank 特征，而不是继续修 provenance。
