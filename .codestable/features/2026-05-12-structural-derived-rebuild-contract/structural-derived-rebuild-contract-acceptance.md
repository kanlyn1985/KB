---
doc_type: feature-acceptance
feature: 2026-05-12-structural-derived-rebuild-contract
status: completed
accepted_at: 2026-05-12
tags:
  - derived-state
  - rebuild
  - data-hygiene
---

# Structural Derived Rebuild Contract 验收报告

> 阶段：阶段 3（验收闭环）
> 验收日期：2026-05-12
> 关联方案 doc：`.codestable/features/2026-05-12-structural-derived-rebuild-contract/structural-derived-rebuild-contract-design.md`

## 1. 接口契约核对

- [x] `rebuild_derived_state(scope="graph")` 不再返回 unsupported，执行 `action="reconcile_orphans"`。
- [x] `scope="wiki"` 清理无效 entity/source fact/source doc/source JSON 的 `wiki_pages`。
- [x] `scope="coverage"` 清理 source unit 映射中的 orphan artifact rows。
- [x] `scope="all"` 顺序为 graph、wiki、coverage、fts。

## 2. 行为与决策核对

- [x] dry-run 只返回 planned counts，不修改表数据。
- [x] execute 只改派生 artifact 表：`graph_edges`、`edge_evidence_map`、`wiki_pages`、`source_unit_fact_map`、`source_unit_evidence_map`。
- [x] 主数据边界守住：不删除 facts、evidence、entities、documents、source_units。
- [x] 没有把业务 query 失败写成清理规则。

## 3. 验收场景核对

- [x] graph orphan rows 可 dry-run 计划并 execute 清理。
  - 证据：`tests/test_derived_state_rebuild.py` 中 graph dry-run/execute 场景通过。
- [x] wiki invalid rows 可 dry-run 计划并 execute 清理。
  - 证据：`test_rebuild_wiki_scope_removes_invalid_pages_without_touching_sources` 通过。
- [x] coverage orphan mappings 可 execute 清理且保留主数据。
  - 证据：`test_rebuild_coverage_scope_reconciles_mapping_orphans_only` 通过。
- [x] residual-state regression suite 覆盖 structural cleanup。
  - 证据：`tests/test_residual_state_regression.py` 3 passed。
- [x] 派生状态治理闭环组合回归通过。
  - 证据：33 passed。
- [x] 查询链路回归未被破坏。
  - 证据：30 passed, 27 deselected。

## 4. 术语一致性

`structural derived state`、`orphan artifact row`、`structural reconcile` 与 design 第 0 节一致。实现没有引入“全量再生成”概念，避免把 orphan cleanup 扩大成 graph/wiki/coverage rebuild。

## 5. 架构归并

- [x] `.codestable/architecture/ARCHITECTURE.md`：更新派生状态治理闭环模块说明和 `rebuild-derived-state` 架构决定。
- [x] `.codestable/architecture/closed-loop-architecture.md`：写入 graph/wiki/coverage structural reconcile 的表级边界和 `scope=all` 顺序。

## 6. Requirement 回写

- [x] `.codestable/requirements/derived-state-governance-loop.md`：当前已落地范围补充 structural rebuild contract，并在边界中说明当前不做全量再生成。

## 7. Roadmap 回写

- [x] `.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-items.yaml`：`structural-derived-rebuild-contract` 标记为 `done`。
- [x] `.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-roadmap.md`：子 feature 清单和变更日志同步。
- [x] YAML 校验通过。

## 8. attention.md 候选盘点

本 feature 未暴露新的通用命令陷阱或环境变量要求；无需补入 `attention.md`。

## 9. 遗留

- graph/wiki/coverage 全量再生成仍未落地。当前能力只负责清理 orphan artifact row。
- 若后续要从 facts/source_units 重建 graph/wiki/coverage，应单独建 feature，并定义 source/artifact/rebuild/fallback 契约。
