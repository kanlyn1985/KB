# Eval Baseline 策略 (Sprint 1 WP3)

> 执行依据：`kb1_next_development_guide.html` § WP3 / §6。
> 目标：先让评测**可复现**，再谈优化。固定一个 CI 主口径，避免 token-overlap / strong-match / LLM judge 来回切换。

## 1. 主口径（CI 硬门禁）

| 项 | 值 |
|---|---|
| **评分器** | `token_overlap`（**确定性，无 LLM**） |
| **触发** | `eakb eval run-now --suite golden --version v1`（不设 `EVAL_USE_LLM`） |
| **pass 判定** | 单题 `coverage >= COVERAGE_THRESHOLD(0.30)`；`pass_rate = passed / total` |
| **CI 取样** | `--max-questions 10`（与 `.github/workflows/tests.yml` eval-suite 一致，CI 速度） |
| **门禁语义** | **baseline lock**：pass_rate 不得相对当前固定版本明显退化（硬门槛） |

> 为什么 token_overlap：无外部 LLM 依赖，讯飞/Minimax 等 API 500 时仍可跑；多 prompt 稳定性 = 1.0（确定性）。这正是指导书要求的"deterministic eval 可跑、LLM judge optional"。

## 2. 辅助口径（非阻塞，人工分析）

| 口径 | 触发 | 用途 |
|---|---|---|
| LLM judge | `EVAL_USE_LLM=1`（hybrid: LLM 主、token_overlap 兜底） | 语义覆盖人工分析，**不阻断 CI** |
| strong-match | 历史报告 `eval_runs/v9_golden_30_strong_match.json`（手工口径） | 仅作历史参照，不作 CI 主口径 |
| 召回 | Recall@5/Recall@10、citation correctness | 单独记录，未接入 CI |

## 3. Gate 分层

| Gate | 含义 | 当前 |
|---|---|---|
| baseline lock | 分数不得明显退化 | **本 WP 固定** |
| promotion gate | pass_rate 稳定进入 0.65–0.85 | 未达（0.60） |
| release gate | 跨文档 eval + citation + unsupported_claim 达标 | 未启用 |

## 4. 当前 baseline 快照（2026-06-24，deterministic）

```
run_id       : sprint1-wp3-golden-10-deterministic-20260624
code_version : 28fb5b7
db_version   : schema user_version=1 (knowledge.db)
qa_bank      : 确定性构建，104 questions（17 docs × expected_points v1），suite=golden cap=10
scoring_mode : token_overlap (COVERAGE_THRESHOLD=0.30)
result       : total=10, passed=6, pass_rate=0.60, avg_coverage=0.462, multi_prompt_stability=1.0
verdict      : FAIL promotion gate (0.60 < 0.65) — 已知，Phase 1 未达 65–85%
LLM          : 未使用（deterministic）
```

**结论**：INFRASTRUCTURE-READY（可复现、可跑、不依赖 LLM）；EVAL-NOT-YET-PASSING（0.60 < 0.65）。这与 Phase 1 signoff 的"基础设施就绪、评测待提升"一致。本 WP 不负责提升分数，只负责**锁定可复现基线**。

## 5. 复现命令

```bash
# CI 主口径（确定性，~30s）
eakb eval run-now --suite golden --version v1 --max-questions 10

# 完整 golden（104 题，~5min+，可能超 CI 时限）
eakb eval run-now --suite golden --version v1

# LLM 辅助口径（非阻塞）
EVAL_USE_LLM=1 eakb eval run-now --suite golden --version v1 --max-questions 10
```

## 6. 后续（不在 WP3 内）

- 提升分数需修 retrieval/answer 主链路（见 issue `definition-query-exact-term-gate-drops-evidence` 一类问题），属 Phase 1 后续。
- 把 `unsupported_claim_rate` 趋近 0 纳入 release gate。
- 跨 LLM gating（第二 LLM 交叉判定）作为 release gate 候选。
- AUTO 模式（CI 跑 golden 阻断 merge、nightly 跑 full）待 promotion gate 达标后启用。
