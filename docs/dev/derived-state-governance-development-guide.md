---
doc_type: dev-guide
slug: derived-state-governance-development-guide
component: derived-state-governance
status: current
summary: FTS、graph/wiki/coverage 派生物、workspace doctor、governance plan 和 rebuild 命令的开发指南
tags:
  - derived-state
  - workspace-doctor
  - rebuild
  - hygiene
last_reviewed: 2026-05-12
---

# Derived State Governance Development Guide

## 概述

派生状态治理闭环解决数据残留问题。它把主数据和派生物分开：主数据包括 documents、evidence、facts、entities；派生物包括 FTS、wiki、graph、coverage 映射、retrieval/eval runs。修复时必须先判断是 freshness、orphan、doc-scoped rebuild 还是 run hygiene，不能用 destructive reset。

## 前置依赖

- 工作目录：`E:\AI_Project\opencode_workspace\KB1`
- 知识库根目录：`knowledge_base`
- 相关架构文档：`.codestable/architecture/closed-loop-architecture.md`

## 快速上手

查看全局健康：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base workspace-doctor --scope all --json
```

生成治理计划：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base workspace-governance --scope all --json
```

执行低风险派生残留治理：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base workspace-governance --scope all --execute-safe --json
```

刷新 FTS：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base rebuild-derived-state --scope fts
```

结构残留 dry-run：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base rebuild-derived-state --scope graph --dry-run
```

隔离额外可疑 DB 文件：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base quarantine-suspicious-db-files --dry-run
```

文档级 full rebuild：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base rebuild-derived-state --scope all --mode full --doc-id DOC-000013
```

## 核心概念

| 概念 | 说明 |
|---|---|
| DerivedStateSpec | 派生状态注册项。 |
| DerivedStateCheck | freshness/missing/orphan 检查结果。FTS freshness 使用源行签名，不使用整库 mtime。 |
| workspace doctor | 只读健康检查入口。 |
| workspace governance | doctor 之上的策略编排层，分类并只执行安全派生修复。 |
| reconcile mode | 清理 orphan artifact rows，不重新生成主数据。 |
| full rebuild mode | 从主数据重新生成 graph/wiki/coverage 派生物。 |
| doc-scoped validation | `--doc-id` 模式只用该文档派生物完整性判定成功。 |
| run governance | 旧/未知 code_version 的 retrieval/eval runs 治理。 |

## 模块入口

| 文件 | 责任 |
|---|---|
| `src/enterprise_agent_kb/derived_state.py` | FTS 派生状态注册和检查。 |
| `src/enterprise_agent_kb/derived_state_rebuild.py` | rebuild 编排、reconcile、full rebuild。 |
| `src/enterprise_agent_kb/workspace_doctor.py` | 全局只读健康检查。 |
| `src/enterprise_agent_kb/workspace_governance.py` | doctor issue 策略分类、dry-run 计划和 `--execute-safe` 后检查。 |
| `src/enterprise_agent_kb/run_governance.py` | run dry-run 和显式 prune。 |
| `src/enterprise_agent_kb/db_hygiene.py` | 额外可疑 DB 文件的 dry-run 和 quarantine。 |
| `src/enterprise_agent_kb/retrieval.py` | FTS freshness guard。 |
| `src/enterprise_agent_kb/graph.py` | 文档级 graph 幂等重建。 |
| `src/enterprise_agent_kb/wiki_compiler.py` | 文档级 wiki stale 清理。 |

## 常见场景

### 处理 FTS stale

FTS stale 表示 `facts`、`evidence` 或可检索 `wiki_pages/entities` 的源行签名与 `logs/fts_index.stamp` 中记录的签名不一致，或存在 count/missing/orphan 差异。`retrieval_runs`、`eval_runs` 等运行记录写入不应触发 FTS stale。首选 `rebuild-derived-state --scope fts` 或让 retrieval guard 自动刷新。不要手工删 FTS 表。

### 处理 graph/wiki orphan

先运行 `workspace-doctor --scope graph|wiki --json` 看 issue 类型，再用 reconcile dry-run 查看计划删除量。确认后执行 reconcile。若主数据变化后需要重新生成指定 doc 的派生物，用 `--mode full --doc-id DOC`。

### 处理多类残留

首选运行 `workspace-governance --scope all --json`。它不会新增诊断逻辑，而是复用 doctor 结果统一分类：`safe_to_auto_fix` 可以在 `--execute-safe` 下调用 `rebuild-derived-state`；`historical_residue` 只保留 `prune-stale-runs --dry-run`；`manual_review_required` 和 `active_data_corruption` 必须回到解析、抽取、schema 或主数据根因，不能自动清理。治理层执行后会再次运行 doctor，作为 post-check。若执行的是 graph/wiki/coverage reconcile，治理层必须继续刷新 FTS，因为这些结构派生物也是 `wiki_fts` 等索引的源。

### 剪枝历史 run

先运行 `prune-stale-runs --keep-current-code-version --keep-latest-code-versions 3 --dry-run` 查看候选规模。执行剪枝前必须有当前 `code_version` 的 retrieval/eval 基线；否则 `--execute` 会返回 blocked，不写 archive、不删除。正确顺序是先跑当前版本 regression 或 retrieval eval，再执行 prune。只有在明确接受“没有当前基线也删除历史运行记录”的维护场景下，才允许加 `--allow-without-current-baseline`。

### 判断 doc-scoped rebuild 是否成功

`--doc-id` 的 item 状态只看该 doc 的派生物完整性。全局其他文档残留会继续出现在 `after.issues`，但不应让本次 doc 级 rebuild 失败。若 `after.doc_scoped_issues` 非空，才说明该 doc 自身仍有问题。

### 处理额外空 DB 文件

`workspace-doctor --scope all` 如果报告 `empty_db_file` 或 `empty_schema_db_file`，先执行 `quarantine-suspicious-db-files --dry-run` 确认只命中非主库文件。确认后再执行 `--execute`，文件会移动到 `knowledge_base/quarantine/db`，不会删除，也不会影响主库 `knowledge_base/db/knowledge.db`。

## 测试

```powershell
C:\Python314\python.exe -m pytest tests/test_derived_state.py tests/test_derived_state_rebuild.py tests/test_workspace_doctor.py tests/test_workspace_governance.py tests/test_residual_state_regression.py -q
```

FTS guard：

```powershell
C:\Python314\python.exe -m pytest tests/test_retrieval_fts_guard.py -q
```

FTS freshness 签名回归：

```powershell
C:\Python314\python.exe -m pytest tests/test_derived_state.py -q -k "source_signature or unrelated_run_writes"
```

DB hygiene：

```powershell
C:\Python314\python.exe -m pytest tests/test_db_hygiene.py tests/test_workspace_doctor.py -q
```

## 已知限制与注意事项

- `workspace-doctor` 和 dashboard 不执行修复，只给 recommended actions。
- `workspace-governance` 默认只生成计划；`--execute-safe` 只执行低风险派生重建，不删除历史 runs。
- `prune-stale-runs` 默认 dry-run；`--execute` 需要当前版本基线，除非显式 `--allow-without-current-baseline`。
- `quarantine-suspicious-db-files` 默认 dry-run，只有显式 `--execute` 才移动文件到 quarantine。
- full rebuild 不重跑 parse/evidence/facts/entities。
- 不要删除 golden_cases、repair_tasks、source_units、facts、evidence、wiki、graph 来掩盖残留。

## 相关文档

- `.codestable/architecture/closed-loop-architecture.md`
- `.codestable/requirements/derived-state-governance-loop.md`
- `.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-roadmap.md`
