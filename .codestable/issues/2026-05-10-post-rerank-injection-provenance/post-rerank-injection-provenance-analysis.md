---
doc_type: issue-analysis
issue: 2026-05-10-post-rerank-injection-provenance
status: fixed
summary: 三个后置注入 helper 手写合并逻辑，未复用 graph-aware metadata merge
tags:
  - retrieval
  - root-cause
---

# Post-rerank Injection Provenance Analysis

## 根因

`query_api.build_query_context()` 的主候选合并使用 `_merge_runtime_hits()`，该函数会调用 `_merge_hit_metadata()` 保留 `graph_source`、`graph_path`、`relation`、`trust_tier`、`evidence_ids` 等 provenance。

但后置注入 helper 独立手写了三套合并逻辑：

- `_inject_exact_standard_hits()`
- `_inject_direct_term_definition_hits()`
- `_inject_direct_wiki_hits()`

这些 helper 在同 ID hit 被高分注入结果替换时，没有把旧 hit 的 graph metadata 合并到新 hit。

## 架构判断

这是召回层的通用合并契约问题，不能针对 CP/CC 或某个标准号单独修。所有后置注入都必须使用同一个 provenance-preserving merge contract。

## 方案

新增 `_merge_injected_hits()`：

- 允许注入 hit 以更高分数替换原 hit；
- 替换时调用 `_merge_hit_metadata()` 保留 graph provenance；
- 未替换时也把注入来源合并回已有 hit；
- 三个后置注入 helper 全部改用该 helper。
