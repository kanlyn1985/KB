# Sprint 1 — WP3 报告：Eval Baseline 固定

> 执行依据：`kb1_next_development_guide.html` § WP3 / §6。
> 目标：固定可复现 baseline，不负责提分。

## 1. 主口径选定

经核对 `evaluation/evaluator.py` 与 `.github/workflows/tests.yml`：
- **CI 主口径 = `token_overlap`**（确定性，`COVERAGE_THRESHOLD=0.30`，无 LLM）。这是 evaluator 默认 scorer（`EVAL_USE_LLM` 未设时）。
- `strong_match` 不是代码内 scorer，仅是历史报告文件名（`eval_runs/v9_golden_30_strong_match.json`），不作主口径。
- LLM judge（`EVAL_USE_LLM=1`，hybrid）为辅助、非阻塞。

→ 与指导书"deterministic strong-match / expected_points coverage 作为 CI 主口径，LLM judge optional"一致（token_overlap 即 expected_points coverage 的确定性实现）。

## 2. 当前 baseline（确定性快照）

```
eakb eval run-now --suite golden --version v1 --max-questions 10
→ total=10, passed=6, pass_rate=0.60, avg_coverage=0.462, multi_prompt_stability=1.0
verdict: FAIL promotion gate (0.60 < 0.65) — 已知，Phase 1 未达 65–85%
```

- code_version: `28fb5b7`，db schema user_version=1，qa_bank 确定性构建 104 题（17 docs / expected_points v1）。
- **不依赖 LLM**：讯飞 API 500 不影响此基线（指导书硬要求）。

## 3. CI 门禁对齐

`tests.yml` eval-suite 跑 `scripts/run_eval_suite.py --max-questions 10 --min-token-pass 0.20`。
当前 baseline 0.60 ≫ 0.20 → **CI baseline lock 通过**。0.20 是保守 smoke 下限；promotion gate（0.65）未达但不阻断 CI。

## 4. 产物

- `docs/dev/eval-baseline-policy.md`：主/辅口径、Gate 分层、baseline 快照、复现命令、后续。

## 5. 验收（对照指导书 §8 "Eval" 项）

| 验收项 | 状态 |
|---|---|
| baseline 口径固定 | ✅ token_overlap（确定性） |
| deterministic eval 可跑 | ✅ 无 LLM，~30s |
| LLM judge optional | ✅ `EVAL_USE_LLM=1` 才启用，非阻塞 |

→ **WP3 完成。baseline 已锁定可复现；提分属 Phase 1 后续（含已立 issue 的 answer-pipeline 修复）。**
