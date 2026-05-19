---
doc_type: feature-acceptance
feature: 2026-05-12-full-derived-rebuild-contract
status: completed
accepted_at: 2026-05-12
tags:
  - derived-state
  - rebuild
  - idempotence
---

# Full Derived Rebuild Contract 验收报告

> 阶段：阶段 3（验收闭环）
> 验收日期：2026-05-12
> 关联方案 doc：`.codestable/features/2026-05-12-full-derived-rebuild-contract/full-derived-rebuild-contract-design.md`

## 1. 接口契约核对

- [x] `rebuild_derived_state(..., mode="full", doc_id=...)` 已支持 graph/wiki/coverage/all。
- [x] CLI `rebuild-derived-state` 已新增 `--mode reconcile|full` 和 `--doc-id`。
- [x] 默认 mode 仍为 `reconcile`，旧 cleanup 语义保持兼容。

## 2. 行为与决策核对

- [x] graph 文档级 build 先删除该 doc 的旧 graph artifacts，再从 facts/entities/evidence 生成新边。
- [x] wiki 文档级 build 删除本轮仍为 stale 的旧 wiki rows。
- [x] coverage 继续由 `sync_source_units_from_matrix` 做文档级替换。
- [x] full rebuild 不重跑 parse/evidence/facts/entities，不生成主数据。

## 3. 验收场景核对

- [x] graph full rebuild 支持 doc scoped，并且不影响其他 doc 的旧边。
  - 证据：`test_rebuild_full_graph_is_doc_scoped_and_replaces_old_doc_edges` 通过。
- [x] wiki full rebuild 删除 stale rows。
  - 证据：`test_rebuild_full_wiki_removes_stale_rows_for_document` 通过。
- [x] doc scoped full rebuild 的状态判定不被其他文档的全局残留误报为失败。
  - 根因验证：真实库 DOC-000013 首次演练发现 wiki/graph 全局残留会让 doc-scoped rebuild 误报 failed。
  - 修复证据：`test_rebuild_full_doc_scope_status_ignores_unrelated_global_doctor_issues` 通过。
  - 真实库复验：`rebuild-derived-state --scope all --mode full --doc-id DOC-000013` 返回 `status=ok`，wiki/graph/coverage/fts 均为 `done`，且 wiki/graph 的 `doc_scoped_issues={}`。
- [x] coverage full rebuild 从 main data 重新生成 source units。
  - 证据：`test_rebuild_full_coverage_rebuilds_source_units_from_main_data` 通过。
- [x] scope all full rebuild 顺序为 wiki、graph、coverage、fts，最终 FTS fresh。
  - 证据：`test_rebuild_full_all_runs_pipeline_order_and_refreshes_fts` 通过。
- [x] 派生状态治理闭环组合回归通过。
  - 证据：`tests/test_residual_state_regression.py tests/test_workspace_doctor.py tests/test_derived_state_rebuild.py` 共 23 passed。
- [x] 查询链路回归未被破坏。
  - 证据：30 passed, 27 deselected。

## 4. 术语一致性

`reconcile mode` 与 `full rebuild mode` 已在代码、CLI、用户指南和架构文档中显式区分。未把 full rebuild 伪装成默认 cleanup。

## 5. 架构归并

- [x] `.codestable/architecture/ARCHITECTURE.md`：更新派生状态治理闭环模块说明和 rebuild 决策。
- [x] `.codestable/architecture/closed-loop-architecture.md`：写入 full rebuild orchestration、doc scoped 行为和不重跑主数据边界。

## 6. Requirement 回写

- [x] `.codestable/requirements/derived-state-governance-loop.md`：当前已落地范围补充 full rebuild contract。

## 7. Roadmap 回写

- [x] `.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-items.yaml`：`full-derived-rebuild-contract` 标记为 `done`。
- [x] `.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-roadmap.md`：子 feature 清单和变更日志同步。

## 8. attention.md 候选盘点

本 feature 未暴露新的环境或路径陷阱；无需补入 `attention.md`。

## 9. 遗留

- full rebuild 目前是串行本地执行；如果后续需要大规模进度恢复、错误重试或并行任务，应单独设计批处理 contract。
- Workbench 仍只展示建议动作，不自动执行 full rebuild。
