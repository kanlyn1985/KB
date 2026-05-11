---
doc_type: issue-report
issue: 2026-05-10-retrieval-run-code-version-boundary
status: fixed
summary: retrieval_runs 无代码版本边界导致 dashboard 混合新旧召回行为
tags:
  - regression
  - retrieval
  - dashboard
---

# Retrieval Run Code Version Boundary Report

## 现象

Graph/topic 修复后，closed-loop dashboard 仍显示旧的 graph lost samples，例如修复前的标准号运行仍以 `graph_candidate_count=16` 出现在最近 500 条统计中。

## 影响

修复是否生效无法从 dashboard 直接判断，因为新旧代码产生的 retrieval run 被混入同一个窗口。

## 非根因

这不是 graph 修复无效，也不是 rerank 权重仍错误。根因是 `retrieval_runs` 缺少代码版本维度。
