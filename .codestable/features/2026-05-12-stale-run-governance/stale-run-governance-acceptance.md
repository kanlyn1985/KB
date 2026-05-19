---
doc_type: feature-acceptance
feature: 2026-05-12-stale-run-governance
status: completed
summary: 旧/未知 retrieval/eval runs 已具备 dry-run 计划、显式剪枝和 doctor 建议动作
tags:
  - derived-state
  - runs
  - governance
---

# Stale Run Governance 验收报告

> 阶段：阶段 3（验收闭环）
> 验收日期：2026-05-12
> 关联方案 doc：`.codestable/features/2026-05-12-stale-run-governance/stale-run-governance-design.md`

## 1. 接口契约核对

- [x] `RunPruneReport` / `RunPruneItem` 已落地在 `src/enterprise_agent_kb/run_governance.py`，输出 dry-run、当前 code version、过滤条件、summary、items、候选样例和截断标记。
- [x] `prune_stale_runs()` 默认 `dry_run=True`，只选择旧/未知 `code_version` 的 retrieval/eval runs；current code version runs 保留。
- [x] `code_version` 已改为源码内容指纹，不再受文件 mtime 影响。
- [x] `prune_stale_runs()` 支持 `keep_latest_code_versions`，可在 current 之外保留最近 N 个非空源码版本。
- [x] `prune-stale-runs` CLI 已接入 `src/enterprise_agent_kb/cli.py`，默认 dry-run；只有显式 `--execute` 才删除。
- [x] `workspace-doctor --scope runs` 的 recommended action 指向公开维护命令 `prune-stale-runs --keep-current-code-version --dry-run`。

验收中发现 CLI 原先未传 `--dry-run` 会执行删除，偏离“不默认删除”原则；已修为默认 dry-run + 显式 `--execute`，并补测试覆盖。

## 2. 行为与决策核对

- [x] dry-run 只读：`tests/test_run_governance.py::test_prune_stale_runs_dry_run_is_readonly` 验证数据不删除。
- [x] 显式剪枝：`test_prune_stale_runs_deletes_candidates_and_keeps_current_and_unrelated_tables` 验证 stale/unknown runs 与对应 eval_results 被删，current runs 保留。
- [x] `suite_id` 约束：`test_prune_stale_runs_suite_filter_only_applies_to_eval_runs` 验证 suite 只应用到 eval_runs，retrieval_runs 返回 skipped。
- [x] 年龄过滤：`test_prune_stale_runs_older_than_filter_keeps_recent_candidates` 验证 recent stale runs 保留。
- [x] 最近版本保留：`test_prune_stale_runs_can_keep_latest_code_versions` 验证最近 N 个非空 code version 不进入候选。
- [x] 内容指纹：`test_source_tree_content_hash_ignores_mtime` 验证源码 mtime 变化不改变 `code_version`，源码内容变化才改变。
- [x] 反向边界：测试验证不删除 `golden_cases` 和 `repair_tasks`；代码未写入 reports、facts、evidence、wiki 或 graph 删除逻辑。

挂载点反向核查使用 `rg "RunPrune|prune_stale_runs|prune-stale-runs|check_run" src tests`，命中均落在 design 第 2.3 节声明的 `run_governance`、`cli`、`workspace_doctor` 和测试文件内。

拔除沙盘推演：移除该 feature 需要删除 `run_governance.py`、CLI 子命令、doctor recommended action 和对应测试；不会影响查询、答案、ingest 或 eval 写入主链路。

## 3. 验收场景核对

- [x] S1 dry-run 可列计划且不删数据：单测通过。
- [x] S2 显式 `--execute` 删除旧/未知 runs 并同步删除 eval_results：单测通过。
- [x] S3 current code version runs 保留：单测通过。
- [x] S4 `--suite-id` 只剪指定 suite 的 eval_runs：单测通过。
- [x] S5 `--older-than-days` 过滤生效：单测通过。
- [x] S6 doctor 推荐 public prune 命令：`tests/test_workspace_doctor.py` 通过。
- [x] S7 query/answer 主链路未受影响：`tests/test_query_repair_regression.py` 通过。

## 4. 术语一致性

- `stale run` / `unknown run` / `current code version` / `prune plan` / `--execute` 在 design、代码、architecture 和 roadmap 中语义一致。
- 禁用语义核对：没有把旧 run 改写为当前 `code_version`，没有默认删除，未出现 reset 式清理。

## 5. 架构归并

- [x] `.codestable/architecture/ARCHITECTURE.md` 已加入 `run_governance` 和 `prune-stale-runs` 的系统级职责与硬边界。
- [x] `.codestable/architecture/closed-loop-architecture.md` 已把运行派生物治理并入派生状态治理闭环，记录默认 dry-run、显式 `--execute`、删除边界、suite/age 过滤和 doctor 行为。

## 6. requirement 回写

- [x] `.codestable/requirements/derived-state-governance-loop.md` 已补当前已落地范围。
- [x] requirement 仍保持 `draft`，原因是 Workbench hygiene dashboard 和 residual-state regression suite 尚未完成。
- [x] `.codestable/requirements/VISION.md` 已更新 review 日期，Draft 分组保持不变。

## 7. roadmap 回写

- [x] `.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-items.yaml` 中 `stale-run-governance` 已改为 `done`。
- [x] `.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-roadmap.md` 已同步子 feature 状态和 CLI 契约。

## 8. attention.md 候选盘点

候选：`prune-stale-runs` 默认只 dry-run，删除必须显式 `--execute`。这是长期安全约束，适合后续经 `cs-note` 加入 `.codestable/attention.md` 的命令陷阱分节。

## 9. 遗留

- `hygiene-dashboard` 未做：Workbench 仍未可视化派生状态治理闭环健康度。
- `residual-state-regression-suite` 未做：残留态还未形成完整回归套件。
- graph/wiki/coverage rebuild scope 仍为 unsupported，等待各自 source/artifact/rebuild contract 落地。

## 验证

- `C:\Python314\python.exe -m pytest tests/test_run_governance.py tests/test_workspace_doctor.py -q`：11 passed。
- `C:\Python314\python.exe -m pytest tests/test_run_governance.py tests/test_workspace_doctor.py tests/test_residual_state_regression.py -q`：17 passed。
- `C:\Python314\python.exe -m pytest tests/test_run_governance.py tests/test_workspace_doctor.py tests/test_derived_state_rebuild.py tests/test_derived_state.py tests/test_retrieval_fts_guard.py -q`：24 passed。
- `C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py -q`：30 passed, 27 deselected。
- `C:\Python314\python.exe -m compileall -q src\enterprise_agent_kb tests\test_run_governance.py tests\test_workspace_doctor.py`：通过。
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base prune-stale-runs --keep-current-code-version`：真实库 dry-run，通过；summary 为 retrieval_runs 2018、eval_runs 61、eval_results 505，删除计数均为 0，候选 ID 输出已截断。
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base prune-stale-runs --keep-current-code-version --keep-latest-code-versions 3 --dry-run`：真实库 dry-run，通过；summary 为 retrieval_runs 2028、eval_runs 62、eval_results 506，删除计数均为 0。大量 unknown runs 仍需年龄过滤或人工确认后显式剪枝。
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base run-corpus-retrieval-eval --case-file output\corpus-eval-current-code\corpus_retrieval_cases_2026-05-12.json --suite-id regression:corpus_retrieval:current-code --limit 10 --output-dir output\corpus-eval-current-code`：`EVAL-37AD8BB47F32F344`，1 passed，0 failed。
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base workspace-doctor --scope runs --json`：真实库返回 warn，并推荐 `prune-stale-runs --keep-current-code-version --dry-run`。
