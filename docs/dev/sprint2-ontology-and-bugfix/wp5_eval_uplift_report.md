# WP5 — Eval 基线提分调查与诚实锁定 报告

> Sprint 2 WP5。依据：`docs/dev/sprint2-ontology-and-bugfix/kb1_sprint2_development_guide.html` § WP5。
> 用户决策（2026-06-25）：走「修问题采样+提质（推荐）」路线，诚实锁定新基线，不改评测指标。

## 调查发现

### 0.60 是单文档偶然值，不代表语料库

CI 的 `--max-questions 10` 样本 **10 题全部来自 DOC-000015**（`_is_substantive` 过滤过严，DOC-000004/000006/000007 等多文档的 expected_points 被判为非实质、生成 0 题，导致 DOC-000015 独占样本）。0.60 是 DOC-000015 单文档的偶然值。

### 真实跨文档基线 = 0.389（18 题 7 过）/ CI 跨文档样本 = 0.30（10 题 3 过）

- 18 题跨文档探针（每文档 2 题）：pass_rate=0.389，avg_cov=0.247。
- 修复采样后 CI 10 题跨文档样本：pass_rate=0.30（9 个文档各 1 题 + DOC-000015 2 题）。
- 失败题覆盖率多在 0.02–0.22，根因是自动生成的问题与答案措辞不匹配（如「请解释: The Systems Engineer」「PwrMod = OFF/awake」类英文/代码片段生成的伪问题）。

### 与 Sprint 2 目标的差距

Sprint 2 WP5 目标「token_overlap 0.60 → 0.65-0.85 不改指标」建立在 **0.60 是真实基线** 的假设上。实际真实基线 ~0.30-0.39。在不改指标、不改答案主路径（Sprint 2 硬约束）的前提下，**0.65-0.85 在本 Sprint 不可达** —— 需要真正的答案质量提升（召回措辞对齐、答案组装优化），属 Sprint 3 范围。

## 已做的修复（采样 + 问题提质，不改指标）

1. **`evaluation/evaluator.py` `_is_substantive`**：增加「CJK 字符 < 4 判非实质」规则，过滤英文 spec 片段 / 代码标识符 / SC 编号（如 `PwrMod = OFF/awake`、`SC4100048`、`The Systems Engineer`）—— 这些原本会生成近零覆盖的噪声问题。
2. **`_generate_questions_for_point` 兜底**：仅当点含 ≥6 个 CJK 字符时才生成 `generic_hint`/`generic` 兜底问题；否则跳过该点（不生成伪问题）。
3. **`_round_robin_sample`（新增）+ `run_suite`**：`max_questions` 采样改为跨文档轮询，保证小样本（CI 10 题）跨文档均匀，不再被单文档独占。完全确定性，不改 token_overlap 评分。

## 验证

| 检查 | 结果 |
|---|---|
| 10 题样本文档分布 | 9 个文档（DOC-000015×2，其余各×1），无单文档独占 |
| 10 题 pass_rate（token_overlap） | 0.30（3/10）—— 真实跨文档值 |
| CI eval-suite `--min-token-pass 0.20` | 0.30 > 0.20，CI 仍通过 |
| `tests/test_evaluator.py` | 39 passed |
| fast suite | 696 passed, 1 skipped, 0 failed |

## 诚实锁定：新基线

- **CI 基线锁**：token_overlap pass_rate **0.30**（跨文档 10 题），code_version = 本 WP5 提交。低于此即回归。
- **CI smoke floor**：保持 `--min-token-pass 0.20`（0.30 有 0.10 余量）。
- **0.60 旧值作废**：标注为「单文档偶然值，不代表语料库」。
- **promotion gate（0.65-0.85）**：Sprint 2 不可达，移至 Sprint 3（答案质量提升路线）。

## 范围外（留 Sprint 3）

- 答案措辞与 expected_points token 对齐（召回/答案组装优化，触主路径，Sprint 2 受限）。
- LLM judge 作为辅助（当前 off，非阻塞）。
- 跨文档完整 104 题基线（540s 超时，需分批或提速后才能跑全）。
