---
doc_type: feature-acceptance
feature: 2026-05-12-residual-state-regression-suite
status: completed
accepted_at: 2026-05-12
tags:
  - derived-state
  - regression
  - data-hygiene
---

# Residual State Regression Suite 验收报告

> 阶段：阶段 3（验收闭环）
> 验收日期：2026-05-12
> 关联方案 doc：`.codestable/features/2026-05-12-residual-state-regression-suite/residual-state-regression-suite-design.md`

## 1. 接口契约核对

- [x] 新增 `tests/test_residual_state_regression.py`，按 residual state 类型组织场景：stale FTS、structural orphan refs、stale/unknown runs。
- [x] suite 复用正式入口：`check_derived_state`、`search_knowledge_base_expanded`、`run_workspace_doctor`、`_hygiene_loop_snapshot`、`prune_stale_runs`。
- [x] 测试 fixture 使用 `initialize_workspace(tmp_path / "kb", schema.sql)`，没有访问真实 `knowledge_base`。

## 2. 行为与决策核对

- [x] 明确不做生产代码改动：本 feature 只新增测试文件和 CodeStable 文档回写。
- [x] stale FTS 场景同时验证检测与 containment：`check_derived_state` 先报 stale，检索 guard 刷新后只保留当前 fact。
- [x] orphan graph/wiki/coverage 场景走只读诊断：doctor 与 hygiene snapshot 暴露风险，但不删除构造出的残留记录。
- [x] stale/unknown runs 场景先 dry-run，确认原表数量不变；显式 execute 只删除目标 retrieval/eval runs 和对应 eval_results。
- [x] 挂载点反向核对：本 feature 的代码挂载点仅限 `tests/test_residual_state_regression.py`；架构、需求、roadmap 仅做文档归并。

## 3. 验收场景核对

- [x] stale FTS 被检测并由 retrieval guard 刷新。
  - 证据：`C:\Python314\python.exe -m pytest tests/test_residual_state_regression.py -q`，3 passed。
- [x] orphan graph/wiki/coverage refs 被 doctor 与 hygiene_loop 暴露。
  - 证据：同 residual suite 第 2 个场景通过。
- [x] stale/unknown runs dry-run 不删除，execute 只删除候选运行派生物。
  - 证据：同 residual suite 第 3 个场景通过。
- [x] hygiene dashboard snapshot 与 doctor/prune plan 一致且只读。
  - 证据：residual suite + `tests/test_api_server.py::test_hygiene_loop_snapshot_reuses_doctor_and_dry_run_prune` 通过。
- [x] 派生状态治理闭环组合回归通过。
  - 证据：29 passed。
- [x] 查询链路回归未被破坏。
  - 证据：`tests/test_query_repair_regression.py` 30 passed, 27 deselected。

## 4. 术语一致性

- `residual state`、`detection path`、`containment path`、`hygiene_loop`、`stale/unknown runs` 的用法与 design 第 0 节一致。
- 未引入方案外生产概念；测试 helper 仅用于构造临时 workspace 残留态。

## 5. 架构归并

- [x] `.codestable/architecture/closed-loop-architecture.md`：补充 residual-state regression suite 作为派生状态治理闭环系统级回归防线。
- [x] `.codestable/architecture/ARCHITECTURE.md`：总入口的派生状态治理闭环增加 residual suite，并记录“残留态必须有系统级回归保护”的架构决定。

## 6. Requirement 回写

- [x] `.codestable/requirements/derived-state-governance-loop.md` 从 `draft` 升级为 `current`。
- [x] `.codestable/requirements/VISION.md` 将 `derived-state-governance-loop` 从 Draft 移入 Current。

## 7. Roadmap 回写

- [x] `.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-items.yaml`：`residual-state-regression-suite` 标记为 `done`。
- [x] `.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-roadmap.md`：子 feature 清单与变更日志同步。
- [x] YAML 校验通过。

## 8. attention.md 候选盘点

本 feature 未暴露新的运行命令陷阱、路径约定或环境变量要求；无需补入 `attention.md`。

## 9. 遗留

- graph/wiki/coverage 的 rebuild contract 仍是明确边界，当前只支持 doctor 可见和 unsupported rebuild，不在本 feature 中扩展。
- 后续如果要支持结构派生物自动重建，应单独走 feature 或 roadmap 子项，不能把删除孤儿引用混入检测入口。
