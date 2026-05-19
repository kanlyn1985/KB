---
doc_type: issue-report
issue: 2026-05-10-user-query-eval-clarification-contract
status: fixed
summary: user query retrieval eval 将 clarification 查询误判为 retrieval 失败
tags:
  - regression
  - clarification
  - eval
---

# User Query Eval Clarification Contract Report

## 现象

当前版本 user query retrieval eval 运行 8 条真实查询时，唯一失败是 `CC是什么意思`：

- 实际 query type：`clarification`
- 旧 case 期望：`definition`
- 旧评测继续检查 `retrieval_must_hit=["连接确认功能"]`

## 影响

澄清机制已经是正确行为，但评测仍按普通召回 case 计算 recall/MRR，导致回归闭环把正确的 clarification 判成失败。

## 非根因

这不是查询链路回退，也不是 CC 解释没召回。根因是评测契约没有表达“非召回型澄清结果”。
