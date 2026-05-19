---
doc_type: issue-report
issue: 2026-05-11-corpus-definition-term-retrieval-shape
status: confirmed
severity: P1
summary: corpus eval 中定义类查询返回 parameter_definition 形状而非目标 term_definition
tags:
  - retrieval
  - corpus-eval
  - evidence-shape
---

# Corpus Definition Term Retrieval Shape Issue Report

## 1. 问题现象

运行 corpus retrieval eval 时，定义类样例 `传导充电是什么意思` 未命中目标术语定义形状。评测期望返回 `term_definition`，但实际 context 的 evidence shape 为 `parameter_definition`，case 失败为 `evidence_shape_mismatch`。

失败样例：

- `case_id`: `CORPUS-DOC-000003-DEFINITION-10-082-904340101E`
- `query`: `传导充电是什么意思`
- `coverage_unit_id`: `DOC-000003:definition:10:08297070E9CA`
- `expected_doc_id`: `DOC-000003`
- `expected_query_type`: `definition`
- `expected_evidence_shape`: `term_definition`

## 2. 复现步骤

1. 在项目根目录 `E:\AI_Project\opencode_workspace\KB1` 执行：
   `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base run-corpus-retrieval-eval --generation-limit-per-type 3 --case-limit 9 --limit 10 --output-dir output\acceptance-corpus-eval`
2. 打开生成的 `output\acceptance-corpus-eval\corpus_retrieval_eval_2026-05-11.md`。
3. 观察到 `CORPUS-DOC-000003-DEFINITION-10-082-904340101E` 失败，失败类型为 `evidence_shape_mismatch`。

复现频率：稳定。最近一次 eval run 为 `EVAL-53F27F7968FE2A5E`，结果 `8 passed / 1 failed`。

## 3. 期望 vs 实际

**期望行为**：定义类查询 `传导充电是什么意思` 应召回目标文档中的术语定义 source unit，并让 evidence shape 与 `term_definition` 匹配。

**实际行为**：查询被判定为 `definition`，但最终 context 的 evidence shape 为 `parameter_definition`，corpus case 因形状不匹配失败。

## 4. 环境信息

- 涉及模块 / 功能：corpus retrieval eval、query context、topic resolution、retrieval/rerank、evidence shape judgement。
- 相关文件 / 函数：待阶段 2 根因分析确认。
- 运行环境：本地 dev，`knowledge_base`。
- 其他上下文：该失败由验收 `corpus-scale-eval` 时真实库小批量评测发现。

## 5. 严重程度

**P1** — 该问题说明定义类查询在真实语料上存在系统性召回/形状判定风险，会影响 corpus eval 建立全局基线，也可能影响用户直接查询术语定义。

## 备注

本报告只记录现象。根因需要在阶段 2 通过代码和数据链路分析确认，不能只针对 `传导充电` 这个 query 硬修。
