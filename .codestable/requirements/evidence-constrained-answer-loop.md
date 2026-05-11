---
doc_type: requirement
slug: evidence-constrained-answer-loop
pitch: 让答案受证据和规则约束，歧义问题先问清楚。
status: current
last_reviewed: 2026-05-09
implemented_by:
  - query-chain-architecture
tags:
  - answer
  - evidence
  - ambiguity
  - llm-boundary
---

# 证据约束答案闭环

## 用户故事

- 作为提问者，我希望答案引用正确证据，而不是 LLM 根据相似词自由发挥。
- 作为标准文档使用者，我希望短缩写问题先澄清语境，而不是被系统强行猜测。
- 作为系统维护者，我希望 evidence judge 只在候选集合内裁判，不越权生成事实。

## 为什么需要

KB1 面向标准和工程知识，错误答案比没有答案更危险。答案层必须把 LLM 限制在查询规划、证据裁判和表达辅助上，最终事实来自规则校验后的候选证据。

## 怎么解决

系统先构建 query context，再通过 evidence shape 和 evidence judge 判断证据是否足够。答案策略根据 query_type 和 evidence_judgement 选择输出模式；短缩写定义问题先返回 clarification options。

## 边界

- 不在候选 evidence/fact 之外编造答案。
- 无合法候选 ID 时不能判定 sufficient。
- 直接答案需要清洗渲染残留，但 supporting evidence 的原始展示清洗属于单独链路。
