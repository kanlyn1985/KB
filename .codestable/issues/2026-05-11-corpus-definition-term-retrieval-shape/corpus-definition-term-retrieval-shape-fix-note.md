---
doc_type: issue-fix-note
issue: 2026-05-11-corpus-definition-term-retrieval-shape
status: fixed
root_cause_type: state-pollution
fixed_by:
  - 2026-05-11-derived-state-registry
  - 2026-05-11-fts-freshness-guard
tags:
  - retrieval
  - fts
  - derived-state
---

# Corpus Definition Term Retrieval Shape 修复记录

## 根因

FTS 是派生状态。主查询链路通过 shared SQLite connection 调用 `search_knowledge_base_expanded()`，旧实现只在 own connection path 执行 `_ensure_fts_ready()`，导致 stale `facts_fts` 可以绕过刷新并污染召回。

## 修复

- 新增 `enterprise_agent_kb.derived_state`，登记 `facts_fts`、`evidence_fts`、`wiki_fts` 的 source/artifact/freshness policy。
- `retrieval._ensure_fts_ready()` 改为消费 `check_derived_state()`。
- `search_knowledge_base_expanded()` 在 own/shared connection 两条路径都执行 FTS freshness guard。
- FTS 刷新节点抽为 `_refresh_fts_index(connection, paths)`，公开 `refresh_fts_index()` 和 guard 共用。

## 验证

- `tests/test_retrieval_fts_guard.py::test_shared_connection_search_refreshes_stale_fts` 构造 stale `facts_fts`，确认 shared connection 搜索会刷新并删除孤儿 row。
- `tests/test_derived_state.py` 覆盖 missing/stale/fresh 派生状态诊断。
- `tests/test_query_repair_regression.py` 保持通过。

## 非本次范围

普通 definition direct fact 兜底仍是后续召回增强，不作为本次修复。此次修复点是派生状态生命周期和检索入口 guard。
