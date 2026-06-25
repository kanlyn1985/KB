# Sprint 3 WP0 — 现场快照与 baseline 冻结报告

> Sprint 3 WP0。依据：`docs/dev/sprint3-answer-quality/kb1_sprint3_development_guide.html` § WP0。
> 目的：进入开发前只读确认当前代码、测试、eval 与 Sprint 2 报告一致。**不改一行代码。**

## 0.1 Git 状态（只读）

| 项 | 值 |
|---|---|
| 分支 | `kb1-six-loop-rename` |
| HEAD | `d1ed846` (docs(sprint2): WP6 closure — ADR 0003 + decision + acceptance + review HTML) |
| 远端同步 | 与 `origin/kb1-six-loop-rename` 同步（ahead 0 / behind 0；fetch 时网络瞬断 schannel，本地状态显示同步） |
| 工作树 | 干净（仅本 Sprint 3 新增的归档指导书 + 本报告，待提交） |
| Safety tag | `safety/pre-sprint1-stabilization-20260624` 仍在 |

## 0.2 测试与健康

| 检查 | 结果 |
|---|---|
| fast suite (`not integration and not benchmark`) | **696 passed, 1 skipped, 0 failed, 0 xfail**（251.71s） |
| `scripts/check_health.py` | **Overall: PASS**（latest_eval_report: v9_golden_30_strong_match.json, pass_rate=50%） |

与 Sprint 2 末态完全一致：696/0/0、health 10/10。

## 0.3 复现 Sprint 2 诚实基线

```
命令: eakb eval run-now --suite golden --version v1 --max-questions 10 --root knowledge_base
scorer: token_overlap (deterministic, COVERAGE_THRESHOLD=0.30, 无 LLM)
采样: 跨文档轮询 (_round_robin_sample)
```

| 项 | 值 |
|---|---|
| total | 10 |
| passed | 3 |
| **pass_rate** | **0.30** |
| avg_coverage | 0.235 |
| multi_prompt_stability | 1.0 |

逐题：

```
[1/10] DOC-000015: cov=0.03 pass=False
[2/10] DOC-000005: cov=0.02 pass=False
[3/10] DOC-000002: cov=0.46 pass=True
[4/10] DOC-000003: cov=0.22 pass=False
[5/10] DOC-000012: cov=0.12 pass=False
[6/10] DOC-000013: cov=0.03 pass=False
[7/10] DOC-000016: cov=0.04 pass=False
[8/10] DOC-000019: cov=1.00 pass=True
[9/10] DOC-000001: cov=0.38 pass=True
[10/10] DOC-000015: cov=0.06 pass=False
```

**复现成功**：pass_rate=0.30 与 Sprint 2 WP5 锁定的诚实跨文档基线完全一致。Gate 0（Baseline 可复现）达成。

## 0.4 运行耗时

- 10 题 eval：约 4-5 分钟（每题跑完整 answer pipeline，平均 ~25s/题，部分 40s）。
- 20 题分桶样本（WP1）：约 8 分钟。
- 104 题完整 golden：预估 >8 分钟，超 CI 时限（WP8 处理分片）。

## 0.5 验收

| WP0 验收项 | 结果 |
|---|---|
| baseline 可复现 | ✅ 0.30 一致 |
| 偏离 0.30 需暂停分析 | 无偏离 |
| git/pytest/health 与 Sprint 2 报告一致 | ✅ |
| 失败样本已导出（供 WP1） | ✅ `tmp/sprint3/wp1_taxonomy_cases.json`（20 题 case-level trace） |

**Gate 0 达成**。进入 WP1 失败样本分桶（已完成，见 `wp1_failure_taxonomy_report.md`）。

## 0.6 提交建议

```
docs(sprint3): record baseline snapshot + failure taxonomy
```
（WP0 + WP1 合并提交，均为文档，无代码改动，符合「WP1 不写代码」约束。）
