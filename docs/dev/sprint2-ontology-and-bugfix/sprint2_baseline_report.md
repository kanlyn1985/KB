# Sprint 2 — WP1：Baseline 报告

> 执行依据：`kb1_sprint2_development_guide.html` § WP1。
> 执行时间：2026-06-25（WP0 完成、67 commits 已 push 之后）。

## 1. Baseline 三项检查结果

| 检查 | 命令 | 结果 | 与评审报告一致性 |
|---|---|---|---|
| Fast suite | `pytest -q -m "not integration and not benchmark"` | **679 passed, 1 skipped, 1 xfailed, 0 failed**（381.84s） | ✅ 与 Sprint 1 一致 |
| Health | `python scripts/check_health.py` | **10/10 PASS** | ✅ 与 Sprint 1 一致 |
| Eval (deterministic) | `eakb eval run-now --suite golden --version v1 --max-questions 10` | **pass_rate=0.60, avg_coverage=0.462, stability=1.0** | ✅ 与 Sprint 1 锁定 baseline 一致 |

## 2. Health 详情

```
[PASS] workspace_exists / db_file_exists / db_connect
[PASS] active_documents: 16
[PASS] facts_populated: 7636
[PASS] evidence_populated: 29988
[PASS] expected_points_populated: distinct_docs=17
[PASS] fts_index_populated: facts_fts_rows=7636
[PASS] fact_type_diversity: types=15, zero_ratio=0.00%
[PASS] latest_eval_report_exists: v9_golden_30_strong_match.json (50.00%)
Overall: PASS
```

## 3. Eval 详情（10 题，确定性 token_overlap）

逐题 coverage：0.03, 0.06, 0.26, **0.79✓**, 0.21, **0.79✓**, **0.50✓**, **0.63✓**, **0.69✓**, **0.66✓**
- passed=6/10，pass_rate=0.60（< 0.65 promotion gate，未达标 → WP5 提分目标）
- 全部 10 题解析到 DOC-000015（expected_points 最多的文档之一，660 points）
- multi_prompt_stability=1.0（deterministic，无 prompt 抖动）

## 4. CLI 命令校正

指导书 WP1 写的 `--profile deterministic --metric token_overlap` 在实际 CLI 中**不存在**。正确入口：

```
python -m enterprise_agent_kb.cli eval run-now --suite {golden,full} --version V --max-questions N --root knowledge_base
```

评分口径通过环境变量 `EVAL_USE_LLM` 选择：**默认（未设）= token_overlap 确定性**（即指导书所述 deterministic），`EVAL_USE_LLM=1` = llm+fallback。本 baseline 未设 `EVAL_USE_LLM`，符合"不切换口径"要求。

## 5. xfail 记录

- `test_mcp_server_tools_call_answer_query`（xfail strict=True）
- 绑定 issue：`definition-query-exact-term-gate-drops-evidence`
- WP2 将修复该 bug 并解除 xfail

## 6. 结论

Baseline 与评审报告 / Sprint 1 锁定值**完全一致**：测试 679/0/1xfail、health 10/10、eval 0.60。处于已知良好状态，可安全进入 WP2（修定义查询 bug）。WP5 目标：把 eval 从 0.60 推进到 0.65–0.85。
