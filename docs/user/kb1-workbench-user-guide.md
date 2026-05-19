---
doc_type: user-guide
slug: kb1-workbench-user-guide
component: kb1-workbench
status: current
summary: KB1 工作台的文档入库、查询调试、答案验证、回归查看和派生状态治理指南
tags:
  - kb1
  - workbench
  - query
  - regression
last_reviewed: 2026-05-14
---

# KB1 Workbench User Guide

## 功能简介

KB1 工作台用于把标准文档导入本地知识库，并验证用户问题是否能找到正确证据、生成可信答案、进入回归闭环，以及发现派生状态残留风险。

工作台地址：

```text
http://127.0.0.1:8000/demo
```

## 前置条件

- 本地 API 已启动。
- 知识库根目录为 `knowledge_base`。
- 服务健康检查 `http://127.0.0.1:8000/health` 返回 `status=ok`。

启动命令：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base serve-api --host 127.0.0.1 --port 8000
```

## 如何使用

### 导入新文档

1. 打开 `http://127.0.0.1:8000/demo`。
2. 在导入与构建区域选择 PDF 文件。
3. 先使用“上传并转换”检查解析效果。
4. 解析正常后使用“上传并构建”入库。
5. 需要完整验收时使用“上传并构建+测试”。
6. 构建完成后在 Overview 查看“新文档入库验收”，确认 `failed=0`。`warn` 表示链路跑通但存在质量风险，需要查看告警项。

入口含义：

| 入口 | 用途 | 是否入库 | 是否测试 |
|---|---|---:|---:|
| 上传并转换 | 只验证 PDF 解析和中间结构 | 否 | 否 |
| 上传并构建 | 解析、入库、生成 evidence/facts/wiki/graph | 是 | 否 |
| 上传并构建+测试 | 构建后生成并执行 golden 测试 | 是 | 是 |

构建响应会自动包含 `ingestion_acceptance`。也可以在 Overview 点击“运行验收 / 重新验收”，单独生成入库验收报告。

验收结果含义：

| 状态 | 含义 | 下一步 |
|---|---|---|
| `passed` | 每阶段产物和最低覆盖阈值都通过 | 可以进入查询/回归验证 |
| `warn` | 入库链路完整，但 diagnostics 有质量风险 | 查看 warning checks 和诊断报告 |
| `failed` | 至少一个关键阶段缺产物或覆盖不达标 | 回到 parse/evidence/facts/wiki/coverage 对应阶段修复 |

### 查看解析视图

选择文档后打开 Parse Views。这个页面用于判断“解析差”到底是主 parser、HTML 候选、OCR 候选，还是选择规则的问题。

重点看：

| 字段 | 含义 |
|---|---|
| Candidates | 该文档保存了多少页级候选解析视图。 |
| Selected | 有多少页面已经写入 best view 选择结果。 |
| Page selected view | 该页最终进入入库链路的 view。 |
| score / struct / chars / blocks | 候选综合分、结构分、文本量和 block 数。 |
| table / rows / clauses / cont | 表格密度、行列信号、条款编号数量和续接信号。 |
| Noise | 页眉页脚噪声比例和重复行比例。 |
| risk flags | `no_text`、`low_text_density`、`symbol_noise`、`header_footer_noise`、`duplicate_lines`、`weak_table_structure` 等候选级风险。 |
| fallback chain | 该页候选排序和回退顺序。 |

判断原则：

1. 如果所有候选都 `low_text_density` 或 `no_text`，优先修 parser/OCR provider。
2. 如果 HTML 候选明显更完整但没有被选中，优先看 `struct`、`table`、`clauses` 和 `Noise` 指标，再修 selection 评分规则。
3. 如果 selected view 正确但后续 evidence/facts 缺失，问题在入库抽取链路，不在解析 provider。

点击“只看风险页”可以把页面列表收窄到带 risk flags 的候选页，用于快速定位解析 provider 或 selection 规则问题。

Parse Views 中的 Risk Attribution 会把风险页归因到下一步动作：

| 归因 | 处理方式 |
|---|---|
| `provider_quality_issue` | 所有候选都差，优先修解析/OCR/HTML provider。 |
| `selection_rule_issue` | 有更好候选没选中，修选择规则。 |
| `extraction_chain_issue` | 解析结果可用但 evidence/facts/source_units 没接上，修抽取链路。 |
| `structural_navigation_noise` | 目录/图表目录/导航点线页，不进入修复 backlog。 |
| `review_only` | 入库链路没断，进入人工复核 backlog。 |
| `test_coverage_gap` | 内容已入库但缺测试，进入 golden/corpus 生成与激活。 |

点击“生成行动计划”会把这些归因进一步整理成两类结果：

- Repair task proposals：指出应该修 parser/provider、selection 评分还是 evidence/source_units/facts 抽取链路。
- Golden candidate requests：只对 `test_coverage_gap` 页面给出候选生成请求，不会自动激活 golden。

如果行动计划显示 provider、selection 或 extraction chain 问题，先修上游链路；不要把这类问题直接当成答案失败加入黄金测试集。

“写入修复任务”是显式动作，会把非 `review_only` 的行动计划写入 Repair Tasks。任务按系统性问题聚合，文档页码保存在任务 metadata 中；这用于追踪跨文档反复出现的解析/抽取根因。

“复核修复任务”会把已写入的 parse-risk repair task 与当前文档 diagnostics 重新比较，显示建议状态：

| 建议状态 | 含义 |
|---|---|
| `done` | 原来的风险页已经消失，可以考虑关闭任务。 |
| `improved` | 风险页减少，但仍需继续处理。 |
| `still_open` | 风险页没有改善。 |
| `expanded` | 出现新的风险页，需要优先复核。 |

Workbench 只显示建议，不会自动关闭任务。
当建议状态为 `done` 时，可以点击“确认完成”，该操作走 Repair Tasks 的显式状态更新接口并记录到任务 metadata；系统不会自动关闭。

### 查询一个问题

1. 在 Query Lab 或查询区域输入用户问题。
2. 先看答案区的 `answer_mode` 和直接答案。
3. 再查看 Raw retrieval metadata。
4. 确认 `rewrite`、`query_expansion`、`topic_resolution`、`retrieval_plan` 和 `evidence_judgement` 是否符合预期。

常用判断：

| 字段 | 重点看什么 |
|---|---|
| `rewrite.query_type` | 问题是否被识别成正确类型。 |
| `query_expansion.used_llm` | 是否调用了 LLM 扩写。短缩写定义问题通常不应先调用。 |
| `topic_resolution.candidate_entities` | 主题对象是否命中正确实体。 |
| `retrieval_plan.graph_candidate_count` | graph 是否提供候选增强。 |
| `evidence_judgement.sufficient` | 证据是否足够支撑答案。 |
| `answer_mode` | 答案策略是否正确。 |

### 处理歧义问题

短缩写问题如果缺少上下文，系统应先要求澄清。

示例：

```text
CP是什么意思
CC是什么意思
```

期望表现：

- `answer_mode=clarification`
- `clarification_required=true`
- 返回多个可选语境
- 用户选择后，用选项里的 `example_query` 重新查询

如果系统直接把短缩写解释成某个参数或无关术语，需要记录为查询链路问题。

### 验证试验方法问题

示例：

```text
OBC输入过压怎么测
```

期望表现：

- `answer_mode=test_method_lookup`
- 返回试验方法和步骤
- `evidence_judgement.sufficient=true`
- 直接答案不包含 `&nbsp;` 等渲染残留

### 查看回归状态

在闭环 dashboard 或 API 结果中关注五类状态：

- ingestion loop：文档是否真的进来了。
- retrieval loop：用户问法是否能召回正确内容。
- answer loop：答案是否受证据约束且可用。
- regression loop：修复是否进入 golden/eval 闭环。
- hygiene loop：FTS、graph、wiki、coverage、旧 runs 等派生状态是否存在残留风险。

状态为 `warn` 或 `fail` 时，不要直接调 prompt，先看 failure analysis、Raw metadata 或 Hygiene tab 归因。

### 审核 Golden 候选

进入 Golden tab 后，点击 `Generate candidates` 可以从当前文档的 `source_units` 生成待审核候选。

重点看：

| 字段 | 含义 |
|---|---|
| `dry_run` | 本次只是生成审核报告，不会写入或激活 golden。 |
| `auto_activation` | 应为 `false`，表示没有自动激活。 |
| `readiness_counts` | 候选处于 ready、review_required 或 blocked 的数量。 |
| `blocked_reasons` | 不能激活的原因，例如 `corpus_eval_requires_review`。 |
| `assertion_contract` | 候选的稳定断言，只能来自 source unit、规则或人工确认。 |
| `activation gate` | 进入 active golden 前的规则校验结果。 |

如果看到噪声候选，不要针对问题文本硬修；应回到 source unit 质量、覆盖矩阵或解析链路找根因。

### 查看派生状态健康

Overview 顶部的 Six Loop Dashboard 会显示六个闭环摘要，其中“解析质量”单独展示 raw high-risk 页面、可行动解析风险和证据链完整页。进入 Hygiene tab 可以查看：

解析质量闭环还会展示 Parse Risk Trend：它来自每次行动计划和修复复核的历史报告，用于查看最新归因、归因变化和 repair review 状态。如果看到 provider/extraction 归因下降而 structural navigation noise 上升，通常表示系统把目录/图表目录页从误报修复项中剥离出来了。

| 区域 | 用途 |
|---|---|
| Workspace Doctor Issues | 展示 `workspace-doctor --scope all --json` 的风险摘要。 |
| Derived State Checks | 展示 FTS 等派生状态的 source/artifact 计数和 missing/orphan 差异。 |
| Stale Run Prune Plan | 展示 `prune-stale-runs --keep-current-code-version --dry-run` 的候选计划。 |
| Recommended Actions / Maintenance Commands | 展示建议维护命令，只读展示，不会自动执行删除。 |

Workbench 只展示 dry-run 计划。真正删除旧运行记录必须由操作者在命令行显式执行 `prune-stale-runs --execute`。

常用维护命令：

| 命令 | 作用 |
|---|---|
| `rebuild-derived-state --scope fts --dry-run` | 预览 FTS 重建，不创建索引或 stamp。 |
| `rebuild-derived-state --scope graph|wiki|coverage --dry-run` | 预览结构派生残留清理计划，不修改数据。 |
| `rebuild-derived-state --scope graph|wiki|coverage` | 只清理 orphan artifact row，不删除 facts/evidence/entities/documents/source_units。 |
| `rebuild-derived-state --scope graph|wiki|coverage --mode full --doc-id DOC-xxx --dry-run` | 预览单文档结构派生物全量再生成计划。 |
| `rebuild-derived-state --scope graph|wiki|coverage --mode full --doc-id DOC-xxx` | 从主数据重新生成指定文档的 graph/wiki/coverage 派生结构。 |
| `rebuild-derived-state --scope all` | 默认 reconcile：先清理 graph/wiki/coverage 残留，再刷新 FTS。 |
| `rebuild-derived-state --scope all --mode full --doc-id DOC-xxx` | 对指定文档按 wiki、graph、coverage、fts 顺序重建派生结构。 |
| `prune-stale-runs --keep-current-code-version --dry-run` | 预览旧/未知版本 runs 剪枝计划。 |

默认 mode 是 `reconcile`，只清理引用已断开的派生记录。需要从主数据重新生成 graph/wiki/coverage 时，必须显式传 `--mode full`。

## 常见问题

Q: 为什么 pytest 里有很多 `deselected`？

A: `deselected` 表示被 `-k` 过滤条件排除的测试，不是失败。

Q: 为什么短缩写问题不能直接回答？

A: CP、CC、PE、OBC、V2G、V2X 等缩写可能有多个语境。系统缺少上下文时直接猜会导致错误答案，应先澄清。

Q: Raw retrieval metadata 里 graph_candidate_count 是 0 是否一定错误？

A: 不一定。部分问题可以通过 routing 或 facts 命中。但如果目标对象本应在实体/图谱中存在，graph 为 0 就需要检查 topic_resolution 和 graph 构建。

Q: direct answer 干净但 supporting evidence 还有 HTML 残留怎么办？

A: 这是 evidence 展示清洗问题，应作为独立问题记录，不要混入召回或答案策略修复。

## 相关功能

- 开发者指南：`docs/dev/kb1-development-guide.md`
- 六闭环架构：`.codestable/architecture/closed-loop-architecture.md`
- 查询链路架构：`.codestable/architecture/query-chain-architecture.md`
- 六闭环强化规划：`.codestable/roadmap/kb1-four-loop-hardening/kb1-six-loop-hardening-roadmap.md`
- 派生状态治理规划：`.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-roadmap.md`
