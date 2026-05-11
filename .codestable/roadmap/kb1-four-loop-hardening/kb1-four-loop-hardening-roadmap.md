---
doc_type: roadmap
slug: kb1-four-loop-hardening
status: active
created: 2026-05-09
last_reviewed: 2026-05-09
tags:
  - kb1
  - four-loop
  - regression
  - quality
---

# KB1 四闭环强化 Roadmap

## 1. 背景

KB1 当前已经具备文档入库、结构化召回、证据约束答案和回归评测的基础能力，但历史文档分散在 `docs/`，CodeStable 新结构下缺少统一的需求、规划、feature 和开发指南入口。后续继续修查询链路时，需要先让开发流程本身可追踪。

## 2. 范围与明确不做

本 roadmap 覆盖四个闭环的工程化强化：

- 入库闭环：source_units、coverage report、parse risk。
- 召回闭环：query rewrite、retrieval_runs、graph/routing/rerank 调试。
- 答案闭环：evidence shape、evidence judge、answer policy、clarification。
- 回归闭环：golden cases、eval results、failure analysis、repair tasks。

明确不做：

- 不重建数据库，不做破坏性 schema reset。
- 不把旧 `docs/` 历史文档批量移动到 `.codestable/`。
- 不引入分布式依赖。
- 不让 LLM 绕过规则校验直接决定最终事实。

## 3. 模块拆分

| 模块 | 职责 |
|---|---|
| Ingestion Coverage | 把 document 到 source_units 的覆盖情况变成可审计指标。 |
| Retrieval Quality | 把 query 到 context 的每次召回变成可复盘运行记录。 |
| Evidence Answer | 把 context 到 direct answer 的证据形状、候选约束和答案策略固定下来。 |
| Regression Governance | 把 golden suite、eval runs、failure analysis 和 repair tasks 接成闭环。 |
| Developer Workflow | 把需求、规划、feature、issue、架构和指南放入 CodeStable 结构。 |

## 4. 接口契约

### 4.1 数据对象契约

```text
source_units(unit_id, doc_id, page_no, block_id, unit_type, text, normalized_text, importance, expected_knowledge_type, status)
retrieval_runs(run_id, query, query_type, doc_scope, retrieved_evidence_ids, reranked_ids, scores, metadata, created_at)
golden_cases(case_id, doc_id, assert_mode, query, must_hit, negative_expected, expected_pages, expected_sections, status, source)
eval_runs(eval_run_id, suite_id, started_at, config_hash, code_version, result_summary)
eval_results(eval_run_id, case_id, passed, failure_reason, retrieved_items, answer, metrics)
```

### 4.2 查询上下文契约

`build_query_context()` 返回对象必须保留：

- `rewrite`
- `query_expansion`
- `advanced_query_plan`
- `retrieval_rewrite`
- `topic_resolution`
- `retrieval_plan`
- `retrieval_run_id`
- `evidence_judgement`

### 4.3 答案契约

`answer_query()` 返回对象必须保留：

- `answer_mode`
- `confidence_score`
- `direct_answer`
- `supporting_facts`
- `supporting_evidence`
- `clarification_required`
- `context.evidence_judgement`

短缩写歧义命中时，`clarification_required=true`，选项必须包含 `option_id`、`label`、`description`、`example_query`。

## 5. 子 Feature 清单

| 状态 | 子 feature | 说明 |
|---|---|---|
| done | codestable-development-docs | 补齐 CodeStable 新结构下的需求、架构、规划、issue 和开发者指南。 |
| done | failure-analysis-workbench | 在 Workbench 中把失败归因、期望命中和实际召回做成可操作页面。 |
| done | evidence-display-sanitization | 统一 supporting evidence 展示清洗，避免 HTML 渲染残留。 |
| done | query-context-clarification-contract | 定义 query-context 对短缩写歧义是否返回 clarification context。 |
| done | golden-case-auto-promotion | 把真实查询失败或测试失败纳入 golden case 草稿和激活流程。 |
| done | graph-contribution-dashboard | 量化 graph 候选是否进入最终 top rerank，暴露 rerank 后丢失风险。 |

## 6. 排期

1. 先完成开发文档补齐，作为后续所有修复的记录入口。
2. 再补 Workbench Failure Analysis，降低后续人工定位成本。
3. 再处理 evidence 展示清洗和 query-context clarification contract。
4. 推进 golden case 自动沉淀。
5. 补 graph contribution dashboard，证明 graph 候选是否真正进入召回结果。

## 7. 观察项

- 当前 dashboard 仍有 warn/fail，需要按 Failure Analysis 分组继续处理。
- Supporting evidence 原始片段和 direct answer 清洗边界需要单独定义。
- Graph 已参与候选增强，dashboard 现在能显示 request/candidate/retention/lost；后续应按 `by_query_type` 决定是否调整 rerank 特征。

## 变更日志

- 2026-05-09：创建 roadmap，补齐四闭环强化的规划入口。
- 2026-05-10：增加 graph-contribution-dashboard，补齐 graph 贡献度可观测性。
