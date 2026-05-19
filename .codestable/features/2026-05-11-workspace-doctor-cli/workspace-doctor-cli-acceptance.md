---
doc_type: feature-acceptance
feature: 2026-05-11-workspace-doctor-cli
status: accepted
accepted_at: 2026-05-11
tags:
  - derived-state
  - cli
  - data-hygiene
---

# Workspace Doctor CLI 验收报告

> 阶段：阶段 3（验收闭环）
> 验收日期：2026-05-11
> 关联方案 doc：`.codestable/features/2026-05-11-workspace-doctor-cli/workspace-doctor-cli-design.md`

## 1. 接口契约核对

- [x] `WorkspaceDoctorIssue` 已落地，包含 issue_id、scope、severity、message、details 和 recommended_actions。
- [x] `WorkspaceDoctorReport` 已落地，包含 status、summary、derived_state_checks 和 issues。
- [x] `run_workspace_doctor()` 与 `format_workspace_doctor_report()` 提供代码入口。
- [x] CLI 新增 `workspace-doctor --scope all|fts|graph|wiki|coverage|runs --json`。

## 2. 行为与决策核对

- [x] FTS 检查复用 `check_derived_state()`，没有复制 freshness 规则。
- [x] graph/wiki/coverage 检查只做 orphan 引用计数。
- [x] runs 检查只报告旧或未知 `code_version`。
- [x] 明确不做已守住：不刷新、不删除、不重建、不修改查询/答案/评测策略。

## 3. 验收场景核对

- [x] missing FTS 且不创建表：`tests/test_workspace_doctor.py::test_workspace_doctor_reports_missing_fts_without_creating_tables`。
- [x] 指定 scope 时数据库缺失也会失败：`test_workspace_doctor_reports_missing_database_for_specific_scope`。
- [x] graph/wiki/coverage orphan 与 stale runs：`test_workspace_doctor_reports_orphans_and_stale_runs`。
- [x] 文本输出含建议动作：`test_workspace_doctor_text_report_contains_actions`。
- [x] CLI parser 与 JSON 输出：`test_workspace_doctor_cli_parser_and_json_output`。
- [x] 真实库 `workspace-doctor --scope fts --json` 返回 `status=ok`。
- [x] 真实库 `workspace-doctor --scope runs` 返回旧/未知 code_version 风险。

## 4. 术语一致性

- [x] 代码使用 workspace doctor / issue / scope / residual state 语义，与方案一致。
- [x] 没有把 rebuild、prune、dashboard 等后续概念提前实现。

## 5. 架构归并

- [x] `.codestable/architecture/ARCHITECTURE.md` 已记录 workspace doctor 的只读诊断边界。
- [x] `.codestable/architecture/closed-loop-architecture.md` 已记录 CLI scope、报告对象和不执行修复的约束。

## 6. requirement 回写

`.codestable/requirements/derived-state-governance-loop.md` 仍保持 draft。原因：workspace doctor 已落地，但 rebuild CLI、stale run governance、hygiene dashboard 和 residual-state regression suite 尚未完成。

## 7. roadmap 回写

- [x] `.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-items.yaml` 已将 `workspace-doctor-cli` 标为 `done`。
- [x] roadmap 主文档第 5 节子 Feature 清单已同步为 `done`。

## 8. attention.md 候选盘点

候选：可考虑把 `workspace-doctor --scope fts --json` 作为数据残留排查首选命令加入 `.codestable/attention.md`。本次未直接写入，等待用户确认。

## 9. 遗留

- `rebuild-derived-state-cli`：把 recommended_actions 变成幂等修复命令。
- `stale-run-governance`：提供旧/未知 code_version runs 的显式剪枝和隔离策略。
- `hygiene-dashboard`：在 Workbench 展示 doctor 报告摘要。

## 验证

- `C:\Python314\python.exe -m pytest tests/test_workspace_doctor.py -q`：5 passed。
- `C:\Python314\python.exe -m pytest tests/test_workspace_doctor.py tests/test_derived_state.py tests/test_retrieval_fts_guard.py tests/test_corpus_eval.py::test_corpus_eval_cli_commands_parse -q`：14 passed。
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base workspace-doctor --scope fts --json`：status ok。
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base workspace-doctor --scope runs`：发现旧/未知 code_version runs 风险。
