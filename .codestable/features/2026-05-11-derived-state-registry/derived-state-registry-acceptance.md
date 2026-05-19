---
doc_type: feature-acceptance
feature: 2026-05-11-derived-state-registry
status: accepted
accepted_at: 2026-05-11
tags:
  - derived-state
  - data-hygiene
  - fifth-loop
---

# Derived State Registry 验收报告

> 阶段：阶段 3（验收闭环）
> 验收日期：2026-05-11
> 关联方案 doc：`.codestable/features/2026-05-11-derived-state-registry/derived-state-registry-design.md`

## 1. 接口契约核对

- [x] `DerivedStateSpec` 已落地，包含 `state_id`、source/artifact、freshness policy、rebuild command 和描述。
- [x] `DerivedStateCheck` 已落地，包含 status/severity/version/count/missing/orphan/message/recommended actions。
- [x] `derived_state_specs()`、`get_derived_state_spec()`、`check_derived_state()` 提供稳定入口。

## 2. 行为与决策核对

- [x] registry 当前覆盖 `facts_fts`、`evidence_fts`、`wiki_fts`。
- [x] check 阶段只读：不调用 `ensure_fts_schema()`，artifact 缺失时只返回 `missing`。
- [x] stale 原因可解释：mtime、count mismatch、missing rows、orphan rows 都进入 message。
- [x] 明确不做已守住：没有自动刷新、没有 CLI/API/Workbench 挂载、没有 schema 变更。

## 3. 验收场景核对

- [x] 稳定 spec：`tests/test_derived_state.py::test_registry_exposes_stable_fts_specs`。
- [x] missing artifact 且不创建 FTS 表：`test_missing_artifact_is_reported_without_creating_fts_tables`。
- [x] missing/orphan stale：`test_stale_fts_reports_missing_and_orphan_rows`。
- [x] DB 比 stamp 新：`test_stale_fts_reports_db_newer_than_stamp`。
- [x] fresh 状态：`test_fresh_fts_reports_ok`。

## 4. 术语一致性

- [x] 代码使用 `derived_state`、`DerivedStateSpec`、`DerivedStateCheck`，与方案术语一致。
- [x] 未引入方案外的新概念；`workspace doctor`、`freshness guard`、`rebuild` 保持为后续 roadmap 项。

## 5. 架构归并

- [x] `.codestable/architecture/ARCHITECTURE.md` 已加入 derived state 术语、模块索引和关键约束。
- [x] `.codestable/architecture/closed-loop-architecture.md` 已从四闭环更新为六闭环，并记录当前只读 FTS registry/check 范围。

## 6. requirement 回写

`.codestable/requirements/derived-state-governance-loop.md` 仍保持 draft。原因：本 feature 只完成派生状态治理闭环基础 registry，自动刷新、doctor CLI、重建命令、stale run governance 和 dashboard 仍未完成，不能把整个能力愿景标为 current。

## 7. roadmap 回写

- [x] `.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-items.yaml` 已将 `derived-state-registry` 标为 `done`。
- [x] roadmap 主文档第 5 节子 Feature 清单已同步为 `done`。

## 8. attention.md 候选盘点

无候选。本 feature 未暴露新的运行命令、环境变量或每次启动都会踩到的路径约束。

## 9. 遗留

- `fts-freshness-guard`：修复共享 connection 检索路径绕过 FTS freshness guard 的根因。
- `workspace-doctor-cli`：把 registry/check 输出为维护者可运行的诊断命令。
- `rebuild-derived-state-cli`：把建议动作变成幂等重建入口。

## 验证

- `C:\Python314\python.exe -m pytest tests/test_derived_state.py -q`：5 passed。
- `C:\Python314\python.exe -m compileall -q src\enterprise_agent_kb\derived_state.py`：通过。
- `git diff --check -- src\enterprise_agent_kb\derived_state.py tests\test_derived_state.py ...`：通过。
