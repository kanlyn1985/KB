---
doc_type: feature-acceptance
feature: 2026-05-11-rebuild-derived-state-cli
status: accepted
accepted_at: 2026-05-11
tags:
  - derived-state
  - cli
  - rebuild
---

# Rebuild Derived State CLI 验收报告

> 阶段：阶段 3（验收闭环）
> 验收日期：2026-05-11
> 关联方案 doc：`.codestable/features/2026-05-11-rebuild-derived-state-cli/rebuild-derived-state-cli-design.md`

## 1. 接口契约核对

- [x] `DerivedStateRebuildItem` 已落地，包含 scope/state/action/status/dry_run/before/after/changed_counts/recommended_actions。
- [x] `DerivedStateRebuildReport` 已落地，包含 scope、dry_run、status、summary 和 items。
- [x] `rebuild_derived_state()` 提供代码入口。
- [x] CLI 新增 `rebuild-derived-state --scope all|fts|graph|wiki|coverage --dry-run`。

## 2. 行为与决策核对

- [x] `DerivedStateSpec.rebuild_command` 已指向公开命令 `rebuild-derived-state --scope fts`。
- [x] retrieval guard 按 FTS state 判断刷新，不依赖 command string。
- [x] `scope=fts` 复用现有 `refresh_fts_index()` 并记录前后 `check_derived_state()`。
- [x] `graph/wiki/coverage` scope 返回 unsupported，不删除数据。
- [x] 明确不做已守住：不剪枝 runs，不把 doctor 和 rebuild 合并，不修改 query/answer/eval 策略。

## 3. 验收场景核对

- [x] dry-run 只读：`tests/test_derived_state_rebuild.py::test_rebuild_fts_dry_run_does_not_create_fts_tables_or_stamp`。
- [x] FTS 实际 rebuild：`test_rebuild_fts_refreshes_stale_index_and_after_checks_are_ok`。
- [x] 非 FTS scope 安全 unsupported：`test_rebuild_non_fts_scope_is_unsupported_and_readonly`。
- [x] CLI parser/JSON 输出：`test_rebuild_cli_parser_and_json_output`。
- [x] retrieval guard 未被命令名变更破坏：`test_retrieval_guard_still_refreshes_with_public_rebuild_command`。
- [x] 真实库 dry-run：`rebuild-derived-state --scope fts --dry-run` 返回 planned 且 FTS before 为 ok。
- [x] 真实库非 FTS dry-run：`rebuild-derived-state --scope graph --dry-run` 返回 unsupported 且不写数据。

## 4. 术语一致性

- [x] 代码使用 rebuild-derived-state / rebuild result / dry-run / implemented scope 语义，与方案一致。
- [x] 未把 unsupported 的 graph/wiki/coverage 伪装成已实现。

## 5. 架构归并

- [x] `.codestable/architecture/ARCHITECTURE.md` 已记录显式 FTS rebuild CLI 和非 FTS unsupported 边界。
- [x] `.codestable/architecture/closed-loop-architecture.md` 已记录 rebuild 前后检查、dry-run 只读和当前 scope 边界。

## 6. requirement 回写

`.codestable/requirements/derived-state-governance-loop.md` 仍保持 draft。原因：派生状态治理闭环已具备 FTS 检查、防护和显式修复入口，但 stale run governance、hygiene dashboard 和 residual-state regression suite 尚未完成。

## 7. roadmap 回写

- [x] `.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-items.yaml` 已将 `rebuild-derived-state-cli` 标为 `done`。
- [x] roadmap 主文档第 5 节子 Feature 清单已同步为 `done` 并标明非 FTS scope 边界。

## 8. attention.md 候选盘点

候选：可考虑把 `rebuild-derived-state --scope fts --dry-run` 和 `rebuild-derived-state --scope fts` 加入数据残留排查命令清单。本次未直接写入，等待用户确认。

## 9. 遗留

- `stale-run-governance`：提供旧/未知 code_version runs 的显式剪枝和隔离策略。
- `hygiene-dashboard`：在 Workbench 展示 doctor/rebuild 状态。
- graph/wiki/coverage rebuild：需要后续独立定义 source/artifact/rebuild contract 后再实现。

## 验证

- `C:\Python314\python.exe -m pytest tests/test_derived_state_rebuild.py tests/test_derived_state.py tests/test_retrieval_fts_guard.py tests/test_workspace_doctor.py -q`：18 passed。
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base rebuild-derived-state --scope fts --dry-run`：status ok，planned 1。
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base rebuild-derived-state --scope graph --dry-run`：status warn，unsupported 1。
