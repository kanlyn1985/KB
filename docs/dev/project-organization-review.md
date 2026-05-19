---
doc_type: dev-guide
slug: project-organization-review
component: project-governance
status: current
summary: KB1 当前工作区整理盘点、变更归类和后续收敛计划
tags:
  - project-organization
  - governance
  - cleanup
last_reviewed: 2026-05-19
---

# KB1 Project Organization Review

## 结论

当前项目不是数据库残留导致的混乱。`workspace-doctor --scope all` 已确认知识库派生状态为 `ok`，`facts_fts`、`evidence_fts`、`wiki_fts` 均为 fresh，且没有 orphan 或 stale run issue。

真正的混乱来自工作区变更未分层收束：源码、测试、CodeStable 文档、用户/开发指南、Workbench 页面、生成 golden 文件和盲测产物同时处于未提交状态。后续整理应先按能力闭环分批验收，再决定提交、归档或删除，不能直接 `reset` 或批量清理。

## 当前状态快照

| 维度 | 状态 |
|---|---|
| 数据治理 | `workspace-doctor --scope all --json` 返回 `status=ok`。 |
| 文件规模 | `.codestable`、`docs`、`src`、`tests` 下约 379 个文件。 |
| 已修改文件 | 54 个 tracked 文件有改动，约 5838 行新增、440 行删除。 |
| 新增文件 | 包括治理模块、解析质量模块、golden 生成模块、CodeStable feature 文档、开发指南和生成测试。 |
| 最近核心回归 | user-query retrieval eval 为 `8/8 passed`；相关 query/test/API/doctor 测试已通过。 |
| 主要风险 | 多条主线混在一个工作区，难以判断每组变更的验收边界和提交边界。 |

## 变更归类

### A. 应保留的核心能力主线

这些是当前架构演进的有效主线，应作为后续提交或验收的主体。

| 主线 | 代表文件 | 说明 |
|---|---|---|
| 查询与答案链路 | `query_rewrite.py`、`query_api.py`、`retrieval_router.py`、`reranker.py`、`retrieval_quality.py`、`answer_api.py`、`evidence_judge.py` | 支撑歧义澄清、Graph 候选、证据形状、参数意图、生命周期 BP 活动召回。 |
| 入库与覆盖闭环 | `coverage.py`、`knowledge_units.py`、`facts.py`、`generated_tests.py`、`ingestion_acceptance.py` | 支撑 source units、coverage report、自动测试草稿和入库验收。 |
| 解析质量闭环 | `parse.py`、`parse_views.py`、`doc_diagnostics.py`、`parse_risk_actions.py`、`parse_risk_history.py` | 支撑多解析视图、页级解析质量、风险归因和修复动作。 |
| 回归与 golden 自动生成 | `corpus_eval.py`、`golden_generation.py`、`knowledge_contracts.py`、`closed_loop_store.py` | 支撑 corpus eval、golden candidate、eval runs/results、failure attribution。 |
| 派生状态治理闭环 | `derived_state.py`、`derived_state_rebuild.py`、`workspace_doctor.py`、`workspace_governance.py`、`run_governance.py`、`db_hygiene.py` | 支撑 stale FTS、orphan graph/wiki/coverage、旧 runs 和治理 dashboard。 |
| Workbench/API/CLI | `api_server.py`、`cli.py`、`examples/demo.html` | 把闭环能力暴露给 CLI、API 和本地 Workbench。 |

### B. 应保留但需要分批验收的文档主线

| 文档区域 | 状态 | 后续动作 |
|---|---|---|
| `.codestable/architecture` | 已覆盖六个闭环、本体论目标、数据治理与 query chain。 | 每次源码主线验收后回写对应架构章节。 |
| `.codestable/requirements` | 已包含入库、解析质量、召回、答案、回归、派生治理、本体论。 | 补齐每个 requirement 的验收指标和未完成项。 |
| `.codestable/features` | 新增大量 feature design/checklist/acceptance。 | 按功能主线核验：每个已实现 feature 必须有 acceptance；未完成 feature 保持 checklist open。 |
| `.codestable/roadmap` | 六闭环总路线和派生状态治理 roadmap 并存。 | 已完成命名升级，旧四闭环 roadmap 已更新为六闭环。 |
| `docs/dev` | 已形成开发者指南体系。 | 增加本整理文档为入口之一；保持命令、测试和闭环说明同步。 |
| `docs/user` | Workbench 用户指南已扩展。 | 后续 UI 行为变化时同步更新。 |

### C. 需要谨慎处理的生成物

这些文件可能有价值，但不应和核心源码混在同一批提交中。

| 类型 | 文件示例 | 建议 |
|---|---|---|
| 生成 golden | `tests/generated/DOC-000014.golden.json`、`DOC-000015.golden.json` | 只有对应 raw 文档和期望 case 已确认时才纳入版本控制。 |
| 生成 pytest | `tests/generated/test_doc_000014_golden.py`、`test_doc_000015_golden.py` | 与 golden JSON 同批处理；否则归档或加入忽略策略。 |
| 覆盖草稿 | `DOC-000015.coverage_test_drafts.*`、`readiness.*` | 属于人工复核材料，默认不应作为长期核心测试。 |
| 盲测报告 | `.codestable/features/2026-05-18-multi-document-blind-validation/*` | 可保留为验收证据，但不应混入功能实现提交。 |
| run prune archive | `knowledge_base/quarantine/run-prune/*.json` | 数据治理审计证据，不建议删除；不一定需要纳入 git。 |

## 当前风险清单

| 风险 | 等级 | 根因 | 建议 |
|---|---|---|---|
| 多条主线混在同一工作区 | P1 | 长时间连续开发，没有按闭环/feature 分批提交或归档。 | 先按主线拆分验收清单，再分批 stage/commit。 |
| 生成物和源码混杂 | P1 | golden、coverage draft、盲测文件与核心实现同时未跟踪。 | 建立 generated artifact policy，确认哪些要版本化。 |
| Roadmap 命名已升级 | done | 项目已从四闭环演进为六闭环，roadmap 命名已同步更新。 | 旧四闭环 roadmap 已更新标题和范围，无需额外新建总路线文档。 |
| 测试集合变大但缺少分层命令 | P2 | 新增闭环测试较多，开发者不知道该跑哪组。 | 在 `docs/dev` 增加 smoke、loop、full 三层测试矩阵。 |
| CodeStable feature 文档未统一状态 | P2 | 新增多个 feature 目录，部分 acceptance 未被索引化。 | 增加 feature inventory，标明 done / active / draft。 |
| 行尾格式警告很多 | P2 | Git 在 Windows 下提示 LF 将替换为 CRLF。 | 暂不批量改格式；后续单独引入 `.gitattributes` 策略。 |

## 建议整理顺序

### 1. 固化当前健康基线

先保留当前已知通过的基线，作为后续清理不破坏功能的判断标准。

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base workspace-doctor --scope all --json
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base run-user-query-retrieval-eval --suite regression:user_query_retrieval:current-code
C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py tests/test_retrieval_quality.py -q
```

### 2. 按闭环拆分提交边界

建议按以下顺序整理，而不是按时间顺序或文件名顺序：

1. 派生状态治理闭环：`derived_state*`、`workspace_doctor`、`workspace_governance`、`run_governance`、对应 tests/docs。
2. 解析质量闭环：`parse_views`、`doc_diagnostics`、`parse_risk*`、parse tests/docs。
3. 入库与 coverage 闭环：`knowledge_units`、`coverage`、`generated_tests`、`ingestion_acceptance`、coverage tests/docs。
4. 回归与 golden 闭环：`corpus_eval`、`golden_generation`、`knowledge_contracts`、eval tests/docs。
5. 查询与答案闭环：`query_*`、`retrieval_*`、`reranker`、`answer_api`、`evidence_*`、query tests/docs。
6. Workbench/API/CLI：`api_server`、`cli`、`examples/demo.html`、user guide。

### 3. 处理生成物

生成物单独决策，不跟源码主线自动绑定。

| 决策 | 适用条件 |
|---|---|
| 保留并提交 | 该 golden/test 是长期回归套件的一部分，并且有稳定 source document。 |
| 保留但不提交 | 该文件是盲测证据或人工复核草稿。 |
| 归档到 quarantine/report | 该文件用于一次性验证，不应污染常规测试集合。 |
| 删除 | 文件可由命令稳定再生成，且没有人工标注价值。 |

### 4. 建立测试分层

| 层级 | 用途 | 示例 |
|---|---|---|
| smoke | 每次小改后跑，耗时短。 | `test_query_repair_regression.py -q`、`workspace-doctor`。 |
| loop | 某个闭环改动后跑。 | query、coverage、parse、governance 各自测试组。 |
| full-ish | 整理/提交前跑。 | API、query、coverage、doctor、user-query eval 组合。 |

### 5. 最后做 git 清理

完成上面分组后再做 git 层清理：

1. 每组先看 `git diff --stat` 和关键 diff。
2. 只 stage 同一主线文件。
3. 每组提交前跑对应测试。
4. 未确认的 generated 文件先保持 untracked 或归档，不要混进核心提交。

## 不建议做的事

- 不建议 `git reset --hard`，当前工作区包含大量有效能力。
- 不建议一次性提交全部变更，后续很难回溯哪条能力引入问题。
- 不建议用删除旧 runs 或重建 DB 掩盖查询问题；数据库当前已经健康。
- 不建议继续以单个失败 query 为中心开发，应继续按闭环和 failure attribution 处理。

## 下一步可执行清单

- [ ] 建立 feature inventory，列出 `.codestable/features` 中每个 feature 的 done/active/draft 状态。
- [ ] 建立 generated artifact policy，明确 `tests/generated` 哪些进入版本控制。
- [x] 把旧”四闭环”路线升级为”六闭环 + 本体论目标”的总路线。
- [ ] 按闭环拆出第一批提交候选：优先派生状态治理，因为当前 doctor 已干净、边界最清晰。
- [ ] 为每个闭环补一条固定验收命令，写入 `docs/dev/README.md`。
