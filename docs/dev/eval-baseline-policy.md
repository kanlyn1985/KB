# Eval Baseline 策略 (Sprint 1 WP3)

> 执行依据：`kb1_next_development_guide.html` § WP3 / §6。
> 目标：先让评测**可复现**，再谈优化。固定一个 CI 主口径，避免 token-overlap / strong-match / LLM judge 来回切换。

## 1. 主口径（CI 硬门禁）

| 项 | 值 |
|---|---|
| **评分器** | `token_overlap`（**确定性，无 LLM**） |
| **触发** | `eakb eval run-now --suite golden --version v1`（不设 `EVAL_USE_LLM`） |
| **pass 判定** | 单题 `coverage >= COVERAGE_THRESHOLD(0.30)`；`pass_rate = passed / total` |
| **CI 取样** | `--max-questions 20`（与 `.github/workflows/tests.yml` eval-suite 一致，样本稳定性）。Sprint 3 P3 从 10 题扩到 20 题：10 题轮转样本太小，恒 0.30 无法反映质量提升；20 题 ~6min 给出更稳定的诚实信号 |
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
| baseline lock | 分数不得明显退化 | **Sprint 3 P3 诚实重新锁定**（见§4） |
| promotion gate | pass_rate 稳定进入 0.65–0.85 | 未达（0.40 真实值；Sprint 3 提升路线） |
| release gate | 跨文档 eval + citation + unsupported_claim 达标 | 未启用 |

## 4. 当前 baseline 快照（2026-06-26 Sprint 3 P3，deterministic，跨文档采样 20 题）

```
run_id       : sprint3-p3-golden-20-crossdoc-20260626
code_version : Sprint 3 P3+[6] 提交（WP2 doc-selection fix + P0 硬降级 + P3 噪声题收紧 + metric 防降级 + [6] 学术元数据降权）
qa_bank      : 确定性构建，87 questions（噪声 point 跳过后，原 100 题）
sampling     : 跨文档轮询（_round_robin_sample），20 题覆盖多文档
scoring_mode : token_overlap (COVERAGE_THRESHOLD=0.30) + 防降级守卫
result       : total=20, passed=7, pass_rate=0.35, avg_coverage~0.28
verdict      : FAIL promotion gate (0.35 < 0.65) — 诚实真实值（0 artifact，[6] 元数据降权去 [14] artifact 后）
LLM          : 未使用（deterministic）
```

### 诚实化说明（Sprint 3 P3）

1. **10→20 题**：10 题轮转样本恒 0.30（恰好都是难题/降级题），WP2 doc-selection fix
   修复的 [15] case 进不了前 10 题。扩到 20 题后真实值 0.40。CI 10 题样本太小，
   已作废。
2. **metric 防降级**：P0 硬降级文本（`当前候选证据不足以给出确定性答案。期望证据
   形状：term_definition、parameter_definition...`）含通用英文词，与英文 expected_point
   共享 token 曾算出 cov=0.59-0.81 假通过。`_is_degraded_answer` 现让降级答案强制
   cov=0，消除 artifact。0.40→0.35 不是回退，是去 artifact 后的诚实值。
3. **P3 噪声题清理**：题池 100→87（移除 13 噪声题：封面/页眉/SC码/英文片段），
   0 噪声残留，V2G 实质段落保留。

### 历史基线（已作废）

- **Sprint 2 WP5 的 0.30（10 题）**：已作废，样本太小。
- **Sprint 1 的 0.60（10 题）**：已作废，单文档偶然值。

## 5. 复现命令

```bash
# CI 主口径（确定性，~6min，20 题）
eakb eval run-now --suite golden --version v1 --max-questions 20

# 完整 golden（87 题，~25min+，可能超 CI 时限，用于离线全量评估）
eakb eval run-now --suite golden --version v1

# LLM 辅助口径（非阻塞）
EVAL_USE_LLM=1 eakb eval run-now --suite golden --version v1 --max-questions 20
```

## 6. 后续（不在 WP3 内）

- 提升分数需修 retrieval/answer 主链路（见 issue `definition-query-exact-term-gate-drops-evidence` 一类问题），属 Phase 1 后续。
- 把 `unsupported_claim_rate` 趋近 0 纳入 release gate。
- 跨 LLM gating（第二 LLM 交叉判定）作为 release gate 候选。
- AUTO 模式（CI 跑 golden 阻断 merge、nightly 跑 full）待 promotion gate 达标后启用。
