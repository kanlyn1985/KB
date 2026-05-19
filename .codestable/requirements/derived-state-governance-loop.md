---
doc_type: requirement
slug: derived-state-governance-loop
pitch: 让系统能发现、刷新和隔离过期派生数据，避免残留状态误导查询和评测。
status: current
last_reviewed: 2026-05-12
implemented_by:
  - closed-loop-architecture
tags:
  - derived-state
  - data-hygiene
  - governance
---

# 派生状态治理闭环

## 用户故事

- 作为知识库维护者，我希望系统能主动发现 FTS、graph、wiki、coverage 和 eval 结果是否过期，而不是等查询错了才排查残留。
- 作为调试者，我希望每次查询和评测都能知道自己基于哪一版主数据、代码和派生状态运行。
- 作为开发者，我希望重建 facts、wiki 或 source_units 后，相关派生索引能自动刷新或明确标记为 stale。
- 作为项目负责人，我希望 Workbench 能显示数据新鲜度和残留风险，避免把旧版本运行结果当成当前质量。

## 为什么需要

KB1 的查询和评测依赖很多派生状态：FTS 索引、wiki 页面、graph 边、coverage 报告、retrieval/eval runs 和本地输出报告。它们不是事实源，却经常被调试和 dashboard 当成判断依据。一旦主数据变了而派生状态没同步，系统会表现为“明明 facts 里有，查询却召不回”“graph 看起来接了但结果不对”“eval 失败来自旧代码版本”等问题。

## 怎么解决

系统把主数据和派生数据分开治理：主数据是事实源，派生数据必须带生成时间、依赖范围和版本边界。查询、评测和 Workbench 入口在使用派生数据前检查新鲜度；发现过期时自动刷新、阻断或标记风险。维护者可以通过统一命令查看残留、重建派生状态和清理旧运行记录。

## 当前已落地范围

- FTS 派生状态已有 `DerivedStateSpec` / `DerivedStateCheck` registry 和只读 freshness 检查；freshness 基于 FTS 源行签名，而不是整库 mtime，避免 retrieval/eval run 写入造成误报。
- 检索入口在使用 FTS 前执行 freshness guard，覆盖 own/shared connection 两条路径。
- `workspace-doctor` 可只读检查 FTS、graph/wiki/coverage orphan、空 DB 和旧/未知 runs 风险。
- `workspace-governance` 可把 doctor issues 统一分类为 `safe_to_auto_fix`、`historical_residue`、`manual_review_required` 和 `active_data_corruption`；默认只输出计划，显式 `--execute-safe` 只执行低风险派生重建并重新 doctor post-check。
- `rebuild-derived-state --scope fts` 可幂等重建 FTS；`--scope graph|wiki|coverage` 可清理 orphan artifact row；`--scope all` 先清理结构派生残留，再刷新 FTS。
- `rebuild-derived-state --mode full --scope graph|wiki|coverage|all` 可从主数据重新生成结构派生物，支持 `--doc-id` 限定单文档；`scope=all` 最后刷新 FTS。
- `prune-stale-runs` 默认 dry-run 输出旧/未知 retrieval/eval runs 剪枝计划，只有显式 `--execute` 才删除候选 runs 和对应 eval_results；支持 `--keep-latest-code-versions N` 保留最近 N 个非空源码版本的运行记录；执行删除前必须写 JSON archive。
- `prune-stale-runs --execute` 默认要求当前 `code_version` 已有 retrieval/eval 基线；没有当前基线时返回 blocked，不写 archive、不删除。只有显式 `--allow-without-current-baseline` 才能越过该安全门。
- `quarantine-suspicious-db-files` 默认 dry-run 输出额外可疑 DB 文件计划，只有显式 `--execute` 才移动到 quarantine，不直接删除。
- `/closed-loop-dashboard` 返回 `hygiene_loop`；Workbench Overview 和 Hygiene tab 可展示派生状态治理闭环状态、doctor issues、dry-run prune plan 和 recommended actions。
- `tests/test_residual_state_regression.py` 固化残留态回归：stale FTS 必须被检测并由检索 guard 刷新；graph/wiki/coverage orphan refs 必须被 doctor 和 hygiene dashboard 暴露；旧/未知 runs 必须 dry-run 可见且只有显式 execute 才剪枝。`tests/test_workspace_governance.py` 固化策略分类和 `--execute-safe` 边界。

该能力已达到 current：派生状态治理闭环具备 registry、guard、doctor、rebuild、run governance、Workbench 可观测和残留态回归测试的最小闭环。

## 边界

- 不把派生数据当作最终事实来源。
- 不做破坏性数据库 reset；修复优先采用增量刷新、重建和剪枝。
- 不要求所有历史 eval/retrieval runs 删除；旧结果可以保留，但必须和当前代码版本隔离。
- 不引入分布式任务系统，先保持单机本地维护命令和 API 可观测。
- 不把某个 query 的失败硬编码到清理逻辑中；失败必须回到数据生命周期和派生状态契约分析。
- 默认 rebuild mode 是 reconcile；full rebuild 必须显式传 `--mode full`。
- 可疑额外 DB 文件默认 quarantine，不直接删除；主库路径固定为 `knowledge_base/db/knowledge.db`。
- 历史 run 剪枝默认先归档再删除；不允许绕过 run governance 手工删除运行记录。
- 历史 run 剪枝不能在当前版本没有任何基线时静默清空历史证据；必须先生成当前版本样本或显式 override。
- 策略化治理入口不能替代根因分析：只有派生残留可以自动处理，解析失败、抽取缺失、schema 缺口和主数据破坏必须进入对应闭环。

## 变更日志

- 2026-05-12：派生状态治理闭环从 draft 升级为 current；补齐 residual-state regression suite 作为残留态治理的回归防线。
- 2026-05-12：FTS freshness 从整库 mtime 修正为源行签名；运行记录写入不再误报 FTS stale。
- 2026-05-13：`code_version` 从源码 mtime/size 指纹改为源码内容指纹；run 剪枝增加最近版本保留策略。
- 2026-05-13：补齐额外可疑 DB 文件 quarantine 命令；根目录 0 字节 `knowledge.db` 已从真实库隔离。
- 2026-05-13：run 剪枝增加执行前 JSON archive，删除历史运行记录前保留可回退审计文件。
- 2026-05-12：补齐 structural-derived-rebuild-contract，graph/wiki/coverage doctor 建议动作已可由 `rebuild-derived-state` 安全执行。
- 2026-05-12：补齐 full-derived-rebuild-contract，graph/wiki/coverage 已支持显式 full rebuild，且不重跑 parse/evidence/facts/entities。
- 2026-05-18：新增 `workspace-governance` 策略编排入口，把 doctor 诊断升级为 dry-run 计划、低风险执行和 post-check，不自动删除历史 runs。
- 2026-05-18：`prune-stale-runs --execute` 增加当前版本基线安全门，避免在 current runs 为 0 时误删全部历史调试证据。
