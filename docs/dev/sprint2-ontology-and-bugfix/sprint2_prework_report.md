# Sprint 2 — WP0 Prework：成果保护

> 执行依据：`kb1_sprint2_development_guide.html` § WP0 / Gate 0。
> 执行时间：2026-06-25。

## 1. 只读确认（WP0.1）

| 项 | 值 |
|---|---|
| 分支 | `kb1-six-loop-rename` |
| 最新提交 | `83694db` (docs(review): update stage-review HTML for Sprint 1) |
| 工作树 | **干净**（git status 空） |
| 远端 | `origin → https://github.com/kanlyn1985/evt.git`（**已配置、可达**） |
| 远端引用 | `refs/heads/main` @ `6ee044e`（无 kb1-six-loop-rename 分支） |
| upstream | 未配置（需 `git push -u`） |
| 领先 origin/main | **67 commits** |
| safety tag | `safety/pre-sprint1-stabilization-20260624` @ `df775a9` |

**关键变化**：Sprint 1 时远端不可达、push 不可能；现在远端可达且有 `main` 分支，**push 可行**。用户选定备份策略 = **push 到远端**。

## 2. 备份执行

### 2.1 离线 bundle（双保险，所选选项"推之前可先 bundle"）

```
git bundle create docs/dev/sprint2-ontology-and-bugfix/kb1_sprint2_prework_backup_20260625.bundle --all
```

- 文件：`docs/dev/sprint2-ontology-and-bugfix/kb1_sprint2_prework_backup_20260625.bundle`（76.5MB）
- `git bundle verify` → **ok**，记录完整历史（HEAD 83694db、safety tag、origin/main）
- 已加入 `.gitignore`（`*.bundle`），不会进版本控制

### 2.2 push 到远端（主备份）

```
git push -u origin kb1-six-loop-rename
```

（执行后补充实际输出与 upstream 设置结果）

## 3. WP1 入口确认

备份完成后进入 WP1（建立 Sprint 2 baseline）：pytest + check_health + eakb eval run-now（deterministic token_overlap）。

## 4. 验收（对照 Gate 0）

| 验收项 | 状态 |
|---|---|
| 67 commits 已 push 或 bundle verify 通过 | （执行后填） |
| bundle 路径写入本报告 | ✅ 见 §2.1 |
| 未备份前不动代码 | ✅ 备份先行 |
