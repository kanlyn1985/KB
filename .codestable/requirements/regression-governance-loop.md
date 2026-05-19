---
doc_type: requirement
slug: regression-governance-loop
pitch: 让每次修复都进入 golden suite，避免系统越改越乱。
status: current
last_reviewed: 2026-05-13
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
- 作为知识库维护者，我希望系统能从 source_units 自动抽样评测，不必等用户问到才发现全局召回缺口。
- 作为系统维护者，我希望 golden 自动生成有统一的候选合约、置信分级和激活门，避免 corpus eval、coverage promotion 和 failure draft 各自为政。

## 为什么需要

查询链路会持续变化，如果失败案例不进入 golden suite，修一个问题可能破坏另一个问题。回归闭环让系统优化从拍脑袋调 prompt 变成可追踪的失败归因和质量趋势。

## 怎么解决

系统维护 golden_cases、eval_runs、eval_results 和 repair_tasks。每次运行评测后生成指标和 Failure Analysis，修复完成后把结果写回文档和测试。

除人工 golden suite 外，系统还支持 corpus scale eval：从 `source_units` 确定性生成 definition、parameter、process_activity 查询样例，保留 coverage unit、期望 query type、证据形状和 must-hit 锚点，再通过 `run-corpus-retrieval-eval` 写入 eval 闭环。corpus eval 不自动等同于高置信人工 golden；它用于发现全局质量缺口，并把失败交给 Failure Analysis 或 issue 流程归因。大规模 corpus eval 必须支持分批运行，每个批次记录自己的 eval run 和 evaluation window，但不能因为只运行子集就废弃同一 case file 中未运行的 golden case。

Golden Generation v1 的目标是统一自动生成入口：把 `source_units`、coverage gaps、eval failures 和后续 ontology gaps 生成的候选都表达为带 origin、confidence tier、assertion contract、trace 和 readiness 的候选对象。只有通过 activation gate 的候选才能进入 active golden；其余候选保留为 corpus_eval、draft、review_required 或 blocked。

## 边界

- 不要求所有历史失败一次性修完。
- 不把 deselected 视为失败；它表示 pytest 过滤条件之外的测试被跳过。
- 评测结果只是质量信号，根因仍需结合代码和数据链路分析。
- 不从错误召回结果反推 expected contract；自动生成 case 的断言只能来自 source unit 和已有结构化字段。
- 自动生成不等于自动激活；没有稳定断言、证据形状或语义锚点的候选必须阻断或进入人工审核。
