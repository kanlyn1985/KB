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
| promotion gate | pass_rate 稳定进入 0.65–0.85 | 未达（0.30 跨文档真实值；Sprint 3 提升路线） |
| release gate | 跨文档 eval + citation + unsupported_claim 达标 | 未启用 |

## 4. 当前 baseline 快照（2026-06-25 Sprint 2 WP5，deterministic，跨文档采样）

```
run_id       : sprint2-wp5-golden-10-crossdoc-20260625
code_version : 本 WP5 提交
qa_bank      : 确定性构建，104 questions（9 docs 通过提质过滤），suite=golden cap=10
sampling     : 跨文档轮询（_round_robin_sample），9 个文档各 1 题 + DOC-000015 2 题
scoring_mode : token_overlap (COVERAGE_THRESHOLD=0.30)
result       : total=10, passed=3, pass_rate=0.30, multi_prompt_stability=1.0
verdict      : FAIL promotion gate (0.30 < 0.65) — 真实跨文档值，Sprint 3 提升路线
LLM          : 未使用（deterministic）
```

**0.60 旧值作废**：Sprint 1 的 0.60 是「10 题全来自 DOC-000015」的单文档偶然值，不代表语料库。修复采样后真实跨文档值为 0.30。详见 `docs/dev/sprint2-ontology-and-bugfix/wp5_eval_uplift_report.md`。

**结论**：INFRASTRUCTURE-READY（可复现、可跑、不依赖 LLM、跨文档采样）；EVAL-NOT-YET-PASSING（0.30 < 0.65）。0.65–0.85 需答案质量提升（召回措辞对齐、答案组装），属 Sprint 3 范围（Sprint 2 硬约束禁改答案主路径）。本 WP 负责**诚实锁定可复现跨文档基线**。

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
