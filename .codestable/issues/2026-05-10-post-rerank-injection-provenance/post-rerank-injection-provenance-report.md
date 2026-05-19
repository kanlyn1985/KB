---
doc_type: issue-report
issue: 2026-05-10-post-rerank-injection-provenance
status: fixed
summary: 后置 direct 注入替换同 ID hit 时丢失 graph provenance
tags:
  - retrieval
  - graph
  - provenance
---

# Post-rerank Injection Provenance Report

## 现象

Graph contribution dashboard 显示 graph 候选会产生，但部分查询 top 结果里 `graph_source=false`。抽样发现 definition 查询中，graph 候选和 direct term definition 可能指向同一个 fact。

## 影响

当后置注入命中同一个 fact/wiki 且分数更高时，原 graph hit 会被普通 direct hit 替换，导致：

- `rerank_explanations[*].graph_source` 被误记为 false；
- graph contribution 被低估；
- graph path、relation、trust tier 等解释元数据丢失。

## 非根因

这不是某个查询 alias 不足，也不是 graph 没接入。根因在召回编排层的 hit 合并契约不一致。
