---
doc_type: feature-acceptance
feature: 2026-05-11-corpus-scale-eval
status: accepted
summary: source_units 驱动的 corpus retrieval eval 已接入 eval 闭环，并能暴露全局召回缺口
tags:
  - regression
  - retrieval
  - coverage
  - acceptance
---

# Corpus Scale Eval Acceptance

> 阶段：阶段 3（验收闭环）
> 验收日期：2026-05-11
> 关联方案 doc：`.codestable/features/2026-05-11-corpus-scale-eval/corpus-scale-eval-design.md`

## 1. 接口契约核对

对照方案第 2.1 节，`corpus case`、`case generator`、`case runner` 均有实际落点。

- [x] `corpus case`：`src/enterprise_agent_kb/corpus_eval.py` 生成 JSON case，包含 `case_id`、`query`、`source=corpus_eval`、`coverage_unit_id`、`expected_doc_id`、`expected_query_type`、`expected_evidence_shape`、`retrieval_must_hit`。
- [x] `case generator`：`generate_corpus_eval_cases()` 从 `source_units` 读取 definition / parameter / process_activity 单元，并过滤噪声、缺少锚点和缺少可追踪 coverage 的单元。
- [x] `case runner`：`run_corpus_retrieval_eval()` 执行 case，复用 `build_query_context()` 和 `evaluate_retrieval_quality()`，并写入 `golden_cases`、`eval_runs`、`eval_results`。
- [x] 流程图落点：`source_units -> quality filters -> case generator -> corpus case JSON -> sync_golden_cases / case runner -> build_query_context -> eval_runs/eval_results -> report` 均在代码中存在。

验收时发现指标命名偏差：corpus runner 曾把 case 级 `evidence_shape_match` 写入 `shape_contract_matched`，导致 dashboard 可能误读 judge contract。已修复为 `evidence_shape_match` 和 `shape_contract_matched` 分离，并补充回归测试。

## 2. 行为与决策核对

- [x] 自动生成 case 不依赖 LLM，不从错误召回结果反推 expected contract。
- [x] runner 写入 `eval_runs/eval_results`，并保留 `code_version`、summary、per-case metrics。
- [x] 自动样例同步到 `golden_cases(source=corpus_eval)`，但语义上仍作为 corpus eval 信号，不等同人工高置信 golden。
- [x] `definition`、`parameter`、`process_activity` 三类 case 均有生成和运行路径。
- [x] 明确不做项成立：未修改 answer 生成策略，未引入分布式依赖，未让 LLM 生成 expected contract。

挂载点核对：

- [x] CLI：`generate-corpus-eval-cases` 和 `run-corpus-retrieval-eval` 已挂到 `enterprise_agent_kb.cli`。
- [x] 模块：新增 `enterprise_agent_kb.corpus_eval`，没有把评测编排塞入 query 或 answer 主链路。
- [x] 持久化：复用 `closed_loop_store.sync_golden_cases()` 和 `record_eval_run()`。
- [x] 反向核查：`rg "corpus|generate-corpus|run-corpus|corpus_eval"` 的引用集中在 CLI、corpus_eval、测试和闭环文档中，挂载点清晰。

## 3. 验收场景核对

单测验证：

`C:\Python314\python.exe -m pytest tests/test_closed_loop_schema.py::test_eval_run_summary_reads_evidence_shape_match_from_contract_metrics tests/test_corpus_eval.py tests/test_query_repair_regression.py::test_query_context_honors_explicit_table_and_parameter_row_anchor tests/test_retrieval_quality.py -q -m "not benchmark"`

结果：

`12 passed`

真实库小批量 corpus eval：

`C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base run-corpus-retrieval-eval --generation-limit-per-type 3 --case-limit 9 --limit 10 --output-dir output\acceptance-corpus-eval`

结果：

- Eval run：`EVAL-53F27F7968FE2A5E`
- Total：9
- Passed：8
- Failed：1
- `retrieval_quality.recall_at_5`：0.644444
- `retrieval_quality.recall_at_10`：0.903704
- `retrieval_quality.mrr`：0.733333
- `shape_contract_quality.contract_match_rate`：1.0
- `evidence_shape_quality.shape_match_rate`：0.888889

失败样例：

- `CORPUS-DOC-000003-DEFINITION-10-082-904340101E`
- 查询：`传导充电是什么意思`
- 失败类型：`evidence_shape_mismatch`
- 根因信号：目标 source unit 链到 `FACT-113145(term_definition)`，但 top context 被同文档 requirement/section facts 占据，topic_resolution 还选到了不相关实体 `电动汽车充电唤醒功能`。
- 结论：corpus eval 功能有效，它发现了后续 query-chain issue；本 feature 不在验收阶段硬修该召回问题。

## 4. 术语一致性

- `corpus_eval`：代码命中集中在 `corpus_eval.py`、CLI、测试和文档中。
- `corpus case`：实现中用 `case_type`、`coverage_unit_id`、`expected_*` 字段表达。
- `evidence_shape_match`：用于 case 级严格期望形状。
- `shape_contract_matched`：用于 evidence judge 的 shape contract。
- 防混淆核对：已修复两类 shape 指标混写的问题。

## 5. 架构归并

- [x] `.codestable/architecture/closed-loop-architecture.md`：回归闭环图已加入 `source_units -> corpus case generator -> corpus retrieval eval -> eval run`，并写明 corpus eval 的数据流、指标边界和失败语义。
- [x] `.codestable/architecture/ARCHITECTURE.md`：模块索引已加入 `corpus_eval`，关键架构决定中补充 source_units 派生规模化验证。
- [x] 架构约束：已明确 `evidence_shape_quality` 和 `shape_contract_quality` 不能混用。

## 6. Requirement 回写

- [x] `.codestable/requirements/regression-governance-loop.md` 已更新为 `last_reviewed: 2026-05-11`。
- [x] 用户故事补充：维护者需要从 `source_units` 自动抽样评测，提前发现全局召回缺口。
- [x] 解决方案补充：corpus scale eval 从 source unit 生成样例并写入 eval 闭环。
- [x] 边界补充：不从错误召回结果反推 expected contract。

## 7. Roadmap 回写

本 feature 的 design frontmatter 未声明 `roadmap` / `roadmap_item`，不是从 `kb1-four-loop-hardening` roadmap 条目直接起头；因此不修改 roadmap items。当前能力已通过 architecture 和 requirement 回写归档。

## 8. attention.md 候选盘点

本 feature 暴露的稳定注意事项：

- corpus eval 真实运行可能返回 failed，这是质量信号，不等于 runner 失败；应看 `eval_runs.status`、failure attribution 和 report。

该事项是否写入 `.codestable/attention.md` 建议由用户确认后走 `cs-note`，本验收不直接手写。

## 9. 遗留

- 后续 issue 候选：`传导充电是什么意思` 的定义召回被 requirement/section facts 挤占，topic_resolution 选择不相关实体。建议走 `cs-issue`，从 topic resolution、definition fact rerank 和 term anchor 召回根因分析，不做单 query 硬修。
- 已知限制：当前验收仅跑小批量 9 case；后续可提高 `--generation-limit-per-type` 建立正式 corpus baseline。
- 实现阶段顺手发现：闭环汇总层原先只从 `answer_quality.evidence_shape_match` 读取形状匹配，已修复为支持 direct、contract、answer_quality 和 shape_contract 多来源。
