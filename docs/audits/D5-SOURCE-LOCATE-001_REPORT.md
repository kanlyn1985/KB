# D5-SOURCE-LOCATE-001 — Source Location Report

- Date: 2026-09-04 · Locator: independent read-only（AI 执行）
- Classification: **SOURCE FOUND**

## 1. SOURCE STATUS: FOUND

| 项 | 值 |
|---|---|
| repository path（remote） | https://github.com/kanlyn1985/Yilife.git |
| branch | design/developmental-core-v1 |
| commit | **82b744e8d8fb3861e3ab54961b166307e3805356**（与任务书前缀精确匹配） |
| commit reachable | ✅（fetch-only → refs/remotes/yilife/d5；`git cat-file -t` = commit） |
| commit message | experiment(d5): formal adaptive developmental agency run |
| author | unknown \<000043ce@hzevt.com\> · 2026-09-05 19:09:56 +0800 |
| artifact directory reachable | ✅（git ls-tree @ 82b744e 全清单见 §3） |

## 2. 搜索轨迹（SEARCH ORDER 实录）

1. `git remote -v` → kb（github.com/kanlyn1985/KB）+ origin（github.com/kanlyn1985/evt）
2. `git ls-remote --heads origin/kb` → 两 remote 均**无** design/developmental-core-v1
3. 本地全部 refs / worktree list（唯一 worktree=KB1）/ reflog → 无 developmental/82b744e
4. FETCH-only 可达性测试：kb 与 origin 均无法提供 82b744e 对象
5. 父级/邻级 git 仓库枚举（14 个）逐一 `cat-file -t 82b744e` → 全部 no
6. GitHub kanlyn1985 名下仓库枚举（Yilife/new_stock/KB/evt/wudx）→
   **Yilife 的 design/developmental-core-v1 = 82b744e8…** ✓
7. FETCH-only（含 SSL blip 重试一次）→ refs/remotes/yilife/d5 → cat-file = commit ✓

## 3. Artifact Inventory（git ls-tree @ 82b744e，tracked 状态逐项）

| 文件 | 状态 |
|---|---|
| D5_RESULT.html | tracked ✓ |
| protocol.md | tracked ✓ |
| manifest.json | tracked ✓ |
| seed-list.json | tracked ✓ |
| statistics.json | tracked ✓ |
| verdict.json | tracked ✓ |
| audit.md | tracked ✓ |
| sha256.txt | tracked ✓ |
| raw.log | **MISSING from git**（runtime-only artifact——D1 系列同类实验的 raw.log 均
  tracked，D5 目录无此文件；未自行生成/复制） |
| D5_manifest.json | tracked ✓ |
| trajectories.jsonl | tracked ✓ |

10/11 tracked；1 个 runtime-only（raw.log）。**未修改/生成/复制任何文件**（任务书 §11）。

## 4. 边界执行声明

- 仅 FETCH（refs/remotes/yilife/d5）；**零 merge/rebase/cherry-pick/checkout**；
- 本仓库 HEAD 未变（9475e7a）；git status clean；
- production DB 未触碰；
- 未执行统计审计（任务书 §12 STOP——定位即止）。

## 5. 对 D5-STAT-AUDIT-001 重启的交接指引

审计应在 82b744e（refs/remotes/yilife/d5）上以 `git show 82b744e:<path>` 只读读取工件
（无需 checkout）；raw.log 将缺失——permutation/原始日志类检查按 runtime-only 缺席处理
（verdict/statistics 可交叉验证的部分不受影响）。