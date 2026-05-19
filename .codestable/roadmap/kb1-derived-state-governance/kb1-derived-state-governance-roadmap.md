---
doc_type: roadmap
slug: kb1-derived-state-governance
status: active
created: 2026-05-11
last_reviewed: 2026-05-19
tags:
  - kb1
  - derived-state
  - data-hygiene
  - sixth-loop
---

# KB1 派生状态治理闭环 Roadmap

## 1. 背景

KB1 已经形成入库、解析质量、召回、答案和回归五个闭环。最近 corpus eval 暴露出第六类系统性问题：主数据已经更新，但派生状态仍残留旧内容。例如 `facts` 中存在当前 `FACT-113145(term_definition)`，但 `facts_fts` 缺少它并保留已不存在的旧 fact，导致查询和评测基于陈旧索引运行。

派生状态治理闭环（第六闭环）的目标是治理所有”不是事实源、但会影响查询/评测/可观测”的派生状态，让系统能检查、刷新、剪枝和解释残留风险。

## 2. 范围与明确不做

覆盖范围：

- FTS 派生索引：`evidence_fts`、`facts_fts`、`wiki_fts`。
- 结构派生物：wiki pages、graph edges、source unit 映射、coverage reports。
- 运行派生物：retrieval_runs、eval_runs、eval_results、repair_tasks、generated reports。
- 本地维护入口：workspace doctor、rebuild derived state、prune stale runs。
- Workbench 可观测：派生状态 freshness、orphan references、stale run counts。

明确不做：

- 不做破坏性 database reset。
- 不把旧 eval/retrieval runs 全部删除；默认隔离和标注，剪枝需要显式命令。
- 不引入分布式任务队列。
- 不用某个失败 query 反推系统规则。
- 不让派生状态覆盖主数据事实。

## 3. 模块拆分

| 模块 | 职责 |
|---|---|
| Derived State Registry | 定义主数据与派生状态清单，记录每类派生物依赖哪些表、文件和版本边界。 |
| Freshness Guard | 在查询、评测和维护命令入口检查派生状态是否新鲜，必要时刷新或返回风险。 |
| Rebuild Orchestrator | 统一执行 FTS、coverage mapping、wiki/graph consistency 等派生状态重建。 |
| Stale Run Governance | 按 `code_version`、`source_data_version` 和 suite 归档、过滤或剪枝旧运行记录。 |
| Hygiene Dashboard | 在 Workbench 展示数据新鲜度、残留风险、orphan 引用和建议动作。 |
| Residual-State Tests | 构造 stale FTS、orphan graph/wiki、旧 eval run 等残留态，验证系统不会误判。 |

## 4. 接口契约

### 4.1 状态清单

```python
DerivedStateSpec = {
    "state_id": "facts_fts",
    "kind": "fts_index",
    "source_tables": ["facts"],
    "source_files": [],
    "artifact_tables": ["facts_fts"],
    "artifact_files": ["knowledge_base/logs/fts_index.stamp"],
    "freshness_policy": "mtime_and_count",
    "rebuild_command": "rebuild-derived-state --scope fts",
}
```

要求：

- `state_id` 稳定，供 dashboard、CLI 和测试引用。
- `source_tables` / `artifact_tables` 明确主从关系。
- `freshness_policy` 必须可解释，不能只返回 true/false。

### 4.2 检查结果

```python
DerivedStateCheck = {
    "state_id": "facts_fts",
    "status": "fresh | stale | missing | orphaned | unknown",
    "severity": "ok | warn | fail",
    "source_version": "hash-or-mtime",
    "artifact_version": "hash-or-mtime",
    "source_count": 3884,
    "artifact_count": 3884,
    "orphan_count": 0,
    "missing_count": 0,
    "message": "facts_fts is fresh",
    "recommended_actions": ["rebuild-derived-state --scope fts"],
}
```

要求：

- `status=stale` 必须说明 stale 原因，如 mtime、count mismatch、orphan reference。
- 检查结果不能修改数据。
- 查询入口可根据检查结果选择自动刷新或带风险继续。

### 4.3 重建结果

```python
DerivedStateRebuildResult = {
    "state_id": "facts_fts",
    "action": "refresh",
    "started_at": "2026-05-11T00:00:00+00:00",
    "finished_at": "2026-05-11T00:00:02+00:00",
    "before": {"status": "stale"},
    "after": {"status": "fresh"},
    "changed_counts": {"facts_fts": 3884},
}
```

要求：

- 重建必须幂等。
- 重建前后都记录 check 摘要。
- 失败时保留错误原因，不吞异常。

### 4.4 CLI/API 契约

```text
workspace-doctor
  --scope all|fts|graph|wiki|coverage|runs
  --json

rebuild-derived-state
  --scope all|fts|graph|wiki|coverage
  --dry-run

prune-stale-runs
  --suite-id optional
  --older-than-days N
  --keep-current-code-version
  --dry-run
  --execute
```

API / Workbench 读取同一套检查结果，不另起一套 dashboard-only 逻辑。

## 5. 子 Feature 清单

| 状态 | 子 feature | 说明 |
|---|---|---|
| done | derived-state-registry | 建立主数据/派生状态 registry 和检查结果数据结构。 |
| done | fts-freshness-guard | 修复共享 connection 路径绕过 FTS freshness guard 的根因。 |
| done | workspace-doctor-cli | 提供统一数据残留检查命令，覆盖 FTS、orphan 引用和旧 runs。 |
| done | rebuild-derived-state-cli | 提供幂等重建命令，安全覆盖 FTS；graph/wiki/coverage 的 orphan artifact reconcile 由 structural-derived-rebuild-contract 补齐。 |
| done | stale-run-governance | 对 retrieval/eval runs 做 code_version 隔离，默认 dry-run 输出剪枝计划，显式 `--execute` 才删除候选 runs 和对应 eval_results。 |
| done | hygiene-dashboard | Workbench 通过 `hygiene_loop` 展示派生状态治理闭环健康度、doctor issues、dry-run prune plan 和建议动作。 |
| done | residual-state-regression-suite | 增加 stale FTS、orphan graph/wiki、旧 eval run 的回归测试，覆盖 stale FTS guard、结构孤儿引用诊断、stale/unknown runs dry-run/execute 边界和 hygiene dashboard 只读一致性。 |
| done | structural-derived-rebuild-contract | 为 graph/wiki/coverage 派生结构补齐 orphan reconcile 重建契约，关闭 doctor 建议动作与 unsupported rebuild 的断裂。 |
| done | full-derived-rebuild-contract | 为 graph/wiki/coverage 补齐从主数据重新生成派生结构的 full rebuild 契约，并与 reconcile 模式显式区分。 |

## 6. 排期

1. `derived-state-registry`：先定义统一语言，否则后续每个模块各说各的 stale。
2. `fts-freshness-guard`：最小闭环，直接关闭当前 corpus eval 暴露的根因。
3. `workspace-doctor-cli`：让维护者能一次看到残留状态。
4. `rebuild-derived-state-cli`：把人工刷新变成正式维护动作。
5. `stale-run-governance`：防止旧运行记录污染当前 dashboard。
6. `hygiene-dashboard`：把派生状态治理闭环纳入 Workbench。
7. `residual-state-regression-suite`：把残留态固化成测试体系。

## 7. 观察项

- 当前 `corpus-definition-term-retrieval-shape` issue 应由 `fts-freshness-guard` 子 feature 消化。
- `knowledge_base` 根目录存在多个空 DB 文件，后续 workspace doctor 应把“有效 DB 路径”和“可疑空 DB”分开显示。
- 派生状态治理闭环完成后，architecture 已记录全部六个闭环；目标态和当前态统一在 closed-loop-architecture.md。

## 变更日志

- 2026-05-11：创建派生状态治理闭环 roadmap，定义模块、接口契约和子 feature 清单。
- 2026-05-12：完成 stale-run-governance，补齐旧/未知 retrieval/eval runs 的 dry-run 计划、显式剪枝和 doctor 建议动作。
- 2026-05-12：完成 hygiene-dashboard，`/closed-loop-dashboard` 和 Workbench 已展示派生状态治理闭环健康度与建议动作。
- 2026-05-12：完成 residual-state-regression-suite，把 stale FTS、orphan graph/wiki/coverage refs、旧/未知 runs 和 hygiene 只读一致性固化为派生状态治理闭环回归套件。
- 2026-05-12：完成 structural-derived-rebuild-contract，`rebuild-derived-state --scope graph|wiki|coverage|all` 已支持 orphan artifact reconcile，仍不执行 graph/wiki/coverage 全量再生成。
- 2026-05-12：完成 full-derived-rebuild-contract，`rebuild-derived-state --mode full` 已支持 doc-scoped 和 all-doc graph/wiki/coverage 派生结构再生成，并保留默认 reconcile 模式。
- 2026-05-19：从"第五闭环"命名升级为"派生状态治理闭环"（六闭环体系中的第六闭环），更新全文档闭环编号。
