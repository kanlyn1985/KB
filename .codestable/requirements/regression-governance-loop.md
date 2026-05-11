---
doc_type: requirement
slug: regression-governance-loop
pitch: 让每次修复都进入 golden suite，避免系统越改越乱。
status: current
last_reviewed: 2026-05-09
implemented_by:
  - closed-loop-architecture
tags:
  - regression
  - golden-cases
  - failure-analysis
---

# 回归治理闭环

## 用户故事

- 作为开发者，我希望每个修复都有测试和记录，而不是靠记忆判断有没有退化。
- 作为项目负责人，我希望看到 new failures、fixed failures 和 stable pass rate，而不是只看单次测试输出。
- 作为调试者，我希望失败能归因到 parse_missing、retrieval_miss、rerank_wrong 或 answer_policy_wrong。

## 为什么需要

查询链路会持续变化，如果失败案例不进入 golden suite，修一个问题可能破坏另一个问题。回归闭环让系统优化从拍脑袋调 prompt 变成可追踪的失败归因和质量趋势。

## 怎么解决

系统维护 golden_cases、eval_runs、eval_results 和 repair_tasks。每次运行评测后生成指标和 Failure Analysis，修复完成后把结果写回文档和测试。

## 边界

- 不要求所有历史失败一次性修完。
- 不把 deselected 视为失败；它表示 pytest 过滤条件之外的测试被跳过。
- 评测结果只是质量信号，根因仍需结合代码和数据链路分析。
