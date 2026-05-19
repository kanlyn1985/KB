---
doc_type: feature-acceptance
feature: 2026-05-11-fts-freshness-guard
status: accepted
accepted_at: 2026-05-11
tags:
  - retrieval
  - fts
  - derived-state
---

# FTS Freshness Guard 验收报告

> 阶段：阶段 3（验收闭环）
> 验收日期：2026-05-11
> 关联方案 doc：`.codestable/features/2026-05-11-fts-freshness-guard/fts-freshness-guard-design.md`

## 1. 接口契约核对

- [x] `_ensure_fts_ready(workspace_root, connection=None)` 支持 own/shared connection。
- [x] `refresh_fts_index()` 与 guard 复用 `_refresh_fts_index(connection, paths)`。
- [x] guard 消费 `check_derived_state()`，没有复制一套 freshness 判断。

## 2. 行为与决策核对

- [x] `search_knowledge_base_expanded()` 无论是否传入 connection 都先执行 FTS guard。
- [x] shared connection 刷新时不打开第二个写连接，降低 SQLite 锁风险。
- [x] 明确不做已守住：没有 direct fact 特例、没有 query-specific patch、没有改 answer/rerank。

## 3. 验收场景核对

- [x] shared connection stale FTS 刷新：`tests/test_retrieval_fts_guard.py::test_shared_connection_search_refreshes_stale_fts`。
- [x] own connection missing FTS 仍可刷新：`test_own_connection_search_still_refreshes_missing_fts`。
- [x] `refresh_fts_index()` count contract：`test_refresh_fts_index_keeps_count_contract`。
- [x] derived-state registry/check 回归：`tests/test_derived_state.py`。
- [x] query repair 主回归：`tests/test_query_repair_regression.py`。

## 4. 术语一致性

- [x] 代码使用 FTS freshness guard / derived state registry 语义，与方案一致。
- [x] 没有引入方案外概念；普通 definition direct hit 仍留作后续增强，不作为本次根因修复。

## 5. 架构归并

- [x] `.codestable/architecture/ARCHITECTURE.md` 已记录检索入口使用 FTS freshness guard。
- [x] `.codestable/architecture/closed-loop-architecture.md` 已记录 own/shared connection 两条路径均受 guard 保护。

## 6. requirement 回写

`.codestable/requirements/derived-state-governance-loop.md` 仍保持 draft。原因：本 feature 完成派生状态治理闭环最小查询保护，但 workspace doctor、rebuild CLI、stale run governance 和 dashboard 尚未完成。

## 7. roadmap 回写

- [x] `.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-items.yaml` 已将 `fts-freshness-guard` 标为 `done`。
- [x] roadmap 主文档第 5 节子 Feature 清单已同步为 `done`。

## 8. attention.md 候选盘点

无候选。本 feature 未新增操作者命令或环境约束。

## 9. 遗留

- `workspace-doctor-cli`：把 registry/check 暴露给维护者。
- `rebuild-derived-state-cli`：把 FTS refresh 变成显式幂等维护命令。
- 普通 definition direct hit 兜底可作为后续召回增强，但不是本次 stale FTS 根因修复的一部分。

## 验证

- `C:\Python314\python.exe -m pytest tests/test_retrieval_fts_guard.py tests/test_derived_state.py tests/test_retrieval_router.py -q`：10 passed。
- `C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py -q`：30 passed, 27 deselected。
- `C:\Python314\python.exe -m compileall -q src\enterprise_agent_kb\retrieval.py src\enterprise_agent_kb\derived_state.py`：通过。
