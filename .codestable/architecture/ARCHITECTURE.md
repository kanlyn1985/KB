---
doc_type: architecture-index
slug: architecture
status: current
last_reviewed: 2026-05-17
summary: KB1 architecture entrypoint
tags:
  - kb1
  - architecture
  - codestable
---

# KB1 架构总入口

> 状态：骨架（待填充）
> 创建日期：2026-05-09

## 1. 项目简介

KB1 是面向企业标准文档和工程知识库的本地单机知识底座。系统将 PDF、Markdown、文本等文档编译为 evidence、facts、entities、wiki、graph 和 source_units，再支撑自然语言查询、证据约束答案和回归评测。

## 2. 核心概念 / 术语表

- `source_units`：入库覆盖的最小可追踪单元，用于证明文档内容是否进入知识库。
- `evidence`：来自文档块或结构化解析的证据片段，是事实和答案引用的基础。
- `facts`：从 evidence 归纳出的结构化知识，必须保留来源链路。
- `entities` / `wiki_pages`：面向概念、过程、参数和术语的主题对象与可读知识页。
- `graph_edges`：实体、事实、wiki 和文档单元之间的关系边，用于召回增强与解释。
- `parse_views` / `page_parse_selection`：每页多解析候选和最终选择记录，用于比较主 parser、HTML、OCR 等解析视图，并解释为什么某个 view 被用于最终入库。
- `golden_cases` / `eval_runs` / `eval_results`：回归闭环的测试样例、运行记录和结果归因。
- `derived state`：由主数据计算得到的派生状态，例如 FTS 索引；它影响查询和评测，但不是事实源。
- `DerivedStateSpec` / `DerivedStateCheck`：派生状态 registry 的稳定描述和只读诊断结果。
- `ontology layer`：KB1 的长期目标层，用统一的 entity types、relation types、knowledge types、evidence shapes 和 domain/range 约束组织知识对象。当前系统已具备轻量知识工程基础，后续要演进为可校验、可约束、可有限推理的实用本体层。

## 3. 子系统 / 模块索引

- 入库闭环：`enterprise_agent_kb.ingest`、`enterprise_agent_kb.document_pipeline`、`enterprise_agent_kb.evidence`、`enterprise_agent_kb.facts`、`enterprise_agent_kb.coverage_*`。
- 解析质量闭环：`parse_views` 记录主 parser 与 HTML/OCR 候选，`page_parse_selection` 用规则选择每页 best view；`quality` 生成页级风险，`doc_diagnostics` 把 high-risk 页面按 evidence、source unit 和 fact 链路拆成根因，`api_server` 在 `/closed-loop-dashboard` 暴露 `parse_quality_loop`。
- 召回闭环：`query_rewrite`、`query_expansion`、`advanced_query_planner`、`topic_resolution`、`graph_retrieval`、`retrieval_router`、`reranker`、`query_api`。
- 答案闭环：`query_ambiguity`、`evidence_judge`、`answer_policy`、`answer_api`。
- 回归闭环：`golden_cases`、`eval_*`、`closed_loop_*`、`corpus_eval`、`golden_generation`、`tests/test_query_repair_regression.py`。
- 派生状态治理闭环：`derived_state` 登记并只读检查 `facts_fts`、`evidence_fts`、`wiki_fts`；`retrieval` 在 own/shared connection 搜索路径执行 FTS freshness guard；`workspace_doctor` 提供只读 CLI 健康检查；`workspace_governance` 把 doctor issues 策略化分为可自动修复派生残留、历史 run 残留、人工复核和活跃数据破坏，并在 `--execute-safe` 下只执行低风险派生重建；`derived_state_rebuild` 提供显式 FTS rebuild、graph/wiki/coverage orphan artifact reconcile，以及 graph/wiki/coverage full rebuild；`run_governance` 提供旧/未知 `code_version` runs 的 dry-run 计划和显式剪枝；`api_server` 的 `/closed-loop-dashboard` 与 Workbench 展示 `hygiene_loop`；`tests/test_residual_state_regression.py` 和 `tests/test_workspace_governance.py` 固化 stale FTS、结构孤儿引用、旧 runs 和策略化治理边界。
- 操作入口：`enterprise_agent_kb.cli`，本地 API 入口通过 `serve-api` 启动。

## 4. 关键架构决定

- LLM 只做查询规划、扩写、证据裁判等中间判断，最终事实必须经过规则校验和候选集合约束。
- 短缩写、短问题和多义问题先进入歧义澄清或规则回退，不允许直接由 LLM 猜最终含义。
- 检索链路保留 `retrieval_runs` 元数据，便于定位 query rewrite、routing、graph、rerank 和 answer policy 的责任边界。
- 规模化验证从 `source_units` 派生 corpus eval case，经 `run-corpus-retrieval-eval` 写入 `eval_runs/eval_results`，用于发现少量人工 golden 覆盖不到的全局召回缺口。
- 自动 golden 生成必须先形成 `GoldenCandidate` review payload。候选保留 origin、confidence tier、assertion contract、trace 和 readiness；CLI/API/Workbench 默认 dry-run 展示，不能绕过 activation gate 自动激活。
- 解析质量必须独立成闭环：`low_readability` 和 `risk_level=high` 先进入 `parse_quality` 根因分类，只有没有 evidence 或证据链未闭合的页面才影响健康状态；证据链完整的页面作为复核 backlog，不阻塞入库覆盖。
- PDF 解析必须先进入多解析视图候选层：主 parser 输出、PyMuPDF HTML 输出和后续 OCR-to-HTML 输出都只能写入 `parse_views`，再由规则 selection 写入 `page_parse_selection` 并驱动最终 `pages/blocks/normalized`。任何 provider 都不能绕过 selection 直接写 facts。
- FTS 等派生状态必须通过 registry 描述 source、artifact、freshness policy 和建议动作；检查阶段只读，不把派生物当作最终事实来源。检索入口使用 FTS 前必须执行 freshness guard，避免共享 connection 路径旁路过期检查。
- `workspace-doctor` 是诊断入口，不是修复入口；它只能报告 FTS、graph/wiki/coverage orphan 和旧 runs 风险，并给出建议动作，不能在检查阶段刷新、删除或重建。
- `workspace-governance` 是策略化治理入口；它复用 `workspace-doctor` 的诊断结果生成统一计划，默认只 dry-run。保守策略只允许 `--execute-safe` 自动执行 FTS、graph、wiki 和 coverage 映射 orphan 的派生重建；旧/未知 runs 永远先归为历史残留并保留 dry-run prune 计划，不在该入口自动删除。
- `rebuild-derived-state` 是显式修复入口；默认 `--mode reconcile` 下，`--scope graph|wiki|coverage` 只清理引用已断开的派生行，不删除 facts、evidence、entities、documents、source_units；`--mode full` 下，graph/wiki/coverage 从主数据重新生成派生结构，支持 `--doc-id` 限定单文档。`--scope all --mode full` 的顺序固定为 wiki、graph、coverage、fts。
- `prune-stale-runs` 是运行派生物治理入口；默认只 dry-run 输出候选计划，只有显式 `--execute` 才删除旧/未知 `code_version` 的 retrieval/eval runs，且不删除 golden_cases、repair_tasks 或报告文件。
- `hygiene_loop` 是派生状态治理闭环的 dashboard 视图，只读复用 `workspace_doctor` 和 `prune_stale_runs(dry_run=True)`；Workbench 展示 recommended actions，但不执行 rebuild 或 prune。
- 残留态必须有系统级回归保护：测试应在临时 workspace 构造 stale FTS、orphan graph/wiki/coverage refs、旧/未知 runs，分别验证 detection path 与 containment path，而不是把某个业务查询失败硬编码成补丁。
- 数据模型必须保持 `evidence -> facts -> wiki/graph` 的可追踪关系，schema 变更优先使用增量迁移。
- 本体论知识层是 KB1 的长期完成目标。Graph、wiki、facts、query type 和 evidence shape 后续应收敛到统一 ontology registry；本体推理只能作为候选约束和解释增强，不能绕过 evidence judge 或直接生成最终事实。

## 5. 已知约束 / 硬边界

- 当前目标是单机本地执行，暂不引入分布式依赖。
- CLI 查询命令必须显式使用 `--query`，知识库根目录必须显式使用 `--root knowledge_base`。
- PowerShell 中文输入存在编码风险，自动化验证优先使用 Python Unicode escape 或 HTTP JSON。
- `.codestable/attention.md` 是 CodeStable 技能启动必读的运行约定入口；涉及命令、路径、环境变量的经验应优先沉淀到该文件。
