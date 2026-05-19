---
doc_type: issue-analysis
issue: 2026-05-10-retrieval-run-code-version-boundary
status: fixed
summary: 召回闭环记录缺少 code_version，无法按修复版本隔离指标
tags:
  - root-cause
  - schema
---

# Retrieval Run Code Version Boundary Analysis

## 根因

`eval_runs` 已有 `code_version`，但 `retrieval_runs` 没有。closed-loop dashboard 的 graph contribution 只能按时间取最近 N 条，无法区分修复前和修复后的运行。

这会导致两个问题：

- 修复刚完成时，历史失败样本继续影响 retention/lost 指标。
- Failure Analysis 看到的 lost samples 可能来自旧代码，不应该指导当前代码继续改。

## 方案

- 对 `retrieval_runs` 做 additive schema change：新增 `code_version TEXT`。
- `record_retrieval_run()` 写入当前 runtime code version。
- 旧库访问时自动 `ALTER TABLE` 补列，不做 reset。
- graph contribution dashboard 返回：
  - `current_code_version`
  - `current_code_version_runs`
  - `stale_or_unknown_runs`
  - `code_version_counts`
- 召回健康检查在旧版本/未知版本样本占多数时提示 `retrieval_runs_mixed_code_versions`。
