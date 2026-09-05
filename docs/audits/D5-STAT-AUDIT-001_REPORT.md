# D5-STAT-AUDIT-001 — Audit Report（BLOCKED — AUDIT TARGET NOT FOUND）

- Date: 2026-09-04 · Auditor: independent read-only audit（AI 执行）
- Claimed baseline: 82b744e · Claimed experiment: reports/d1-history-dependence/d5-adaptive-agency-formal-v1/
- Classification: **无法归类为 A/B/C/D —— 审计目标不存在，审计未开始**

## 1. 审计纪律声明

本任务为 AUDIT ONLY。审计者未修改任何 experiment code/protocol/seed/raw trajectories/
verdict；未重新运行任何实验。本报告为唯一产出工件（任务书允许：追加 audit 文档）。

## 2. 阻断发现（STOP-级）

审计无法开始——审计目标在审计执行环境中**不存在**：

| 检查 | 命令/方法 | 结果 |
|---|---|---|
| commit 82b744e | `git cat-file -t 82b744e` | fatal: Not a valid object name |
| 本仓库全部对象 | `git cat-file --batch-all-objects --batch-check` | 无 82b744e 前缀对象 |
| 全部 18 分支 | `git branch -a` | 无 d5/stat/audit/formal 相关分支 |
| 全部 508 commits 全历史 | `git log --all --grep`（d5/adaptive-agency/history-dependence，-i） | 零命中 |
| reports/ 目录 | 文件系统 | 不存在 |
| 全仓递归 `*d5*` 目录 / `D5_RESULT.html` 文件 | 3 层深 | 零命中 |
| 姊妹仓库 KB / KB1_backup_20260503 / KB1_bak20260624 | reports/d1-history-dependence | 均不存在 |
| 全工作区 2 层深目录名匹配 d1-history/adaptive-agency/d5- | 文件系统 | 零命中 |
| .agents/.dsh-recovery 等非常规目录 | 递归 | 零命中 |

## 3. 阻断原因分析（候选）

1. D5 formal experiment 属于**另一条任务线/另一环境**（82b744e 可能是另一仓库或
   未推送的私有 checkout 的 HEAD）；
2. 实验工件可能仅存在于运行时环境（未纳入 git 的 reports/ 输出目录）；
3. 任务书 baseline 引用可能有误（commit SHA 或路径错置）。

## 4. 对任务书各检查项的状态

| 检查项 | 状态 |
|---|---|
| 1. DEFAULT P median=1.07 / CI95=[1.10,1.33] 内部一致性 | **BLOCKED**（statistics.json 不存在） |
| 2. g3_mut3 同上 | BLOCKED |
| 3. 独立复算 δ/δCI/R/P/stable counts/generalization | BLOCKED（raw trajectories.jsonl 不存在） |
| 4. Permutation p=0 诊断（N/exceedance/1/N 解释） | BLOCKED |
| 5. Verdict MULTI_BLOCK_CARRIER_SUPPORTED 预注册判据复核 | BLOCKED（verdict.json 不存在） |
| 6. Block decomposition 复算 | BLOCKED |
| 7. Artifact consistency（六工件对比） | BLOCKED |
| 8. sha256.txt hash 一致性 | BLOCKED |
| 9. 分类 A/B/C/D | **N/A**——四分类前提是审计已执行；目标缺失不属于任何一类 |

## 5. P0/P1/P2

- **P1（阻断级）**：审计目标缺失——82b744e 与
  reports/d1-history-dependence/d5-adaptive-agency-formal-v1/ 在本环境不可达。
  修复路径（任一）：①提供包含该 commit 的仓库/远端（git fetch + merge 后重发审计任务）；
  ②提供实验工件目录的实际文件系统路径；③确认正确的 baseline SHA。
- P0 = 0（本审计未发现任何已有工件的错误——因为无工件可审）
- P2 = 0

## 6. 审计者承诺

按任务书 §10：未重跑实验、未改 frozen inputs、未改 verdict、未创建实验 commit。
本报告为新增 audit 文档（任务书允许的唯一写操作）。审计待目标可达后重启。