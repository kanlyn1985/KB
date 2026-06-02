---
doc_type: architecture-index
slug: architecture
status: current
last_reviewed: 2026-05-19
summary: KB1 architecture entrypoint
tags:
  - kb1
  - architecture
  - codestable
---

# KB1 架构总入口

> 状态：已填充（基于 2026-05-19 全量代码审计）
> 创建日期：2026-05-09
> 最近审计：2026-05-19（68 modules, 40969 lines）

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

> 完整模块清单基于 2026-05-19 代码审计。详细闭环架构见 [closed-loop-architecture.md](closed-loop-architecture.md)。

### 入库闭环 (9 modules, 8917 lines)

| Module | Lines | Key Classes/Functions |
|---|---|---|
| `ingest` | 278 | RegisterResult, register_document |
| `evidence` | 158 | EvidenceBuildResult, build_evidence_for_document |
| `facts` | 1587 | FactsBuildResult, build_facts_for_document, _definition_has_publishable_signal |
| `entities` | 976 | EntitiesBuildResult, build_entities_for_document |
| `closed_loop_store` | 2780 | sync_source_units_from_matrix, record_eval_run, sync_golden_cases |
| `coverage` | 1792 | SourceUnit, build_coverage_for_document, build_test_gap_candidates |
| `coverage_diagnostics` | 382 | UncoveredPriorityReportResult, build_all_docs_uncovered_priority_report |
| `ingestion_acceptance` | 250 | IngestionAcceptanceResult, validate_document_ingestion |
| `knowledge_units` | 694 | KnowledgeUnit, extract_knowledge_units |

### 解析质量闭环 (7 modules, 3663 lines)

| Module | Lines | Key Classes/Functions |
|---|---|---|
| `parse` | 1123 | 4 classes (PDF provider routing, fast-text-first), parse_document |
| `quality` | 356 | QualityResult, assess_document_quality |
| `parse_views` | 725 | ParseViewCandidate, PageParseSelection, list_parse_view_pages |
| `doc_diagnostics` | 570 | build_document_diagnostics |
| `parse_risk_actions` | 672 | ParseRiskRepairTask, ParseRiskGoldenCandidateRequest |
| `parse_risk_history` | 127 | summarize_parse_risk_history |
| `pdf_chunking` | 90 | PdfChunk, PageImage |

### 召回闭环 (14 modules, 6248 lines)

| Module | Lines | Key Classes/Functions |
|---|---|---|
| `query_rewrite` | 692 | RewrittenQuery, rewrite_query |
| `query_semantic_parser` | 426 | 1 class, 23 functions |
| `query_expansion` | 370 | 2 classes, 19 functions |
| `advanced_query_planner` | 342 | 1 class, 14 functions (behind EAKB_ENABLE_ADVANCED_QUERY_PLANNER=1) |
| `topic_resolution` | 433 | TopicResolutionResult |
| `retrieval` | 408 | search_knowledge_base, ensure_fts_schema |
| `retrieval_router` | 668 | 29 functions |
| `reranker` | 680 | 35 functions |
| `graph_retrieval` | 474 | 1 class, 20 functions |
| `corpus_eval` | 1180 | CorpusEvalGenerationResult, 61 functions |
| `retrieval_quality` | 186 | evaluate_retrieval_quality |
| `evidence_shapes` | 714 | EvidenceShape, EvidenceShapeContract |
| `knowledge_contracts` | 302 | KnowledgeTypeContract |
| `routing_summary` | 457 | direct_routing_hits |

### 答案闭环 (7 modules, 5535 lines)

| Module | Lines | Key Classes/Functions |
|---|---|---|
| `answer_policy` | 1065 | select_answer_policy, build_summary_lines |
| `answer_api` | 3016 | answer_query (96 functions) |
| `answer_quality` | 254 | evaluate_answer_quality |
| `confidence` | 37 | compute_confidence_score |
| `evidence_judge` | 581 | 1 class, 33 functions |
| `query_ambiguity` | 404 | ClarificationOption, QueryAmbiguity |
| `ambiguity_index` | 178 | Sense, build_ambiguity_index |

### 回归闭环 (5 modules, 4520 lines)

| Module | Lines | Key Classes/Functions |
|---|---|---|
| `generated_tests` | 3242 | 108 functions (largest single module) |
| `golden_generation` | 626 | AssertionContract, GoldenCandidate, 5 classes |
| `user_query_retrieval_eval` | 417 | UserQueryRetrievalEvalResult |
| `graph_report` | 194 | GraphQueryTypeReport, GraphHealthReport |
| `governance` | 41 | assess_pending_quality (thin wrapper) |

### 派生状态治理闭环 (6 modules, 2875 lines)

| Module | Lines | Key Classes/Functions |
|---|---|---|
| `derived_state` | 388 | DerivedStateSpec, DerivedStateCheck |
| `derived_state_rebuild` | 773 | DerivedStateRebuildItem, rebuild_derived_state |
| `workspace_doctor` | 717 | WorkspaceDoctorIssue, run_workspace_doctor |
| `workspace_governance` | 297 | WorkspaceGovernanceStep |
| `run_governance` | 506 | RunPruneItem, RunPruneReport, prune_stale_runs |
| `db_hygiene` | 194 | DatabaseHygieneItem, quarantine_suspicious_db_files |

### 基础设施 (7 modules, ~2417 lines)

| Module | Lines | Key Classes/Functions |
|---|---|---|
| `db` | 30 | connect, apply_schema, list_tables |
| `schema.sql` | — | full DB schema |
| `config` | 54 | AppPaths |
| `bootstrap` | 43 | initialize_workspace, workspace_status |
| `ids` | 31 | next_prefixed_id |
| `pipeline` | 569 | PipelineEvent, run_document_pipeline |
| `cli` | 1623 | CLI entry point |

### 共享服务 (6 modules, 3921 lines)

| Module | Lines | Key Classes/Functions |
|---|---|---|
| `api_server` | 2346 | 2 classes, 99 functions |
| `wiki_compiler` | 743 | WikiBuildResult, build_wiki_for_document |
| `graph` | 331 | GraphBuildResult, build_graph_for_document |
| `mcp_server` | 193 | run_mcp_stdio |
| `agent_tools` | 206 | AgentRunResult, run_agent_query |
| `workspace_admin` | 102 | reset_workspace_data |

### 文档处理辅助 (5 modules, 501 lines)

| Module | Lines | Key Classes/Functions |
|---|---|---|
| `doc_ir` | 148 | DocIRBlock, DocIRPage |
| `structure_recovery` | 101 | RecoveredSection, RecoveredStructure |
| `reading_order` | 20 | restore_reading_order |
| `layout_cleaner` | 174 | CleanedDocumentIR |
| `synonyms` | 58 | SYNONYM_MAP, expand_with_synonyms |

### 作业/辅助 (2 modules, 120 lines)

| Module | Lines | Key Classes/Functions |
|---|---|---|
| `jobs` | 114 | JobRunResult, run_parse_jobs |
| `__init__` | 6 | version string |

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

## 6. 代码与文档差异（2026-05-19 审计）

### 代码有但文档未覆盖的模块

- `synonyms.py`：SYNONYM_MAP 和 expand_with_synonyms 同义词扩展机制在文档中没有描述。
- `confidence.py`：compute_confidence_score 加权公式（37 行）在文档中只提到 confidence_score，没有描述计算逻辑。
- `graph_report.py`：GraphQueryTypeReport 和 GraphHealthReport 在文档中未描述。
- `coverage_diagnostics.py`：UncoveredPriorityReport 和根因分类在文档中未描述。
- `routing_summary.py`：direct_routing_hits 路由统计在文档中未描述。
- `layout_cleaner.py` / `structure_recovery.py` / `reading_order.py`：文档处理管线的清洗和结构恢复阶段在文档中未描述。
- `workspace_admin.py`：reset_workspace_data 破坏性清理在文档中未描述。

### 文档引用了但代码中尚未正式实现的功能

- ontology-knowledge-layer.md 描述了 4 阶段本体层，但代码中只有隐式实现（evidence_shapes、knowledge_contracts），没有正式 ontology registry。

### 审计遗留

- F-04（user-style regression golden 合同与 query_type 不一致）：partial — 当前 golden case 已一致，但"行为合同"升级未实施。
- F-05（delivery asset 测试断言旧 tab 集合）：mitigated — 测试与 UI 当前一致，但测试仍断言字符串而非结构。

详见 `.codestable/audits/2026-05-18-core-regression-integrity/index.md`。

## 7. 下一步路线

两个前置 roadmap 已全部完成（kb1-six-loop-hardening 7/7 done、kb1-derived-state-governance 9/9 done）。下一阶段 roadmap 见 `.codestable/roadmap/kb1-next-phase/kb1-next-phase-roadmap.md`，核心优先级：

1. 基线验证与审计遗留关闭
2. 本体层阶段一（ontology registry）落地
3. 答案质量扩展和 confidence 校准
4. 代码与文档持续同步机制
