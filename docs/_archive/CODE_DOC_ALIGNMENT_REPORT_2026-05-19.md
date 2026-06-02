# KB1 Code-Doc Alignment Report
# Generated: 2026-05-19

## 1. 源码现状 (68 modules, 40969 lines)

### 按闭环归属

**入库闭环 (9 modules)**
| Module | Lines | Key Classes/Functions | Status |
|---|---|---|---|
| ingest.py | 278 | RegisterResult, register_document | active |
| evidence.py | 158 | EvidenceBuildResult, build_evidence_for_document | active |
| facts.py | 1587 | FactsBuildResult, build_facts_for_document, _definition_has_publishable_signal | active |
| entities.py | 976 | EntitiesBuildResult, build_entities_for_document | active |
| closed_loop_store.py | 2780 | sync_source_units_from_matrix, record_eval_run, sync_golden_cases | active, core |
| coverage.py | 1792 | SourceUnit, build_coverage_for_document, build_test_gap_candidates | active |
| coverage_diagnostics.py | 382 | UncoveredPriorityReportResult, build_all_docs_uncovered_priority_report | active |
| ingestion_acceptance.py | 250 | IngestionAcceptanceResult, validate_document_ingestion | active |
| knowledge_units.py | 694 | KnowledgeUnit, extract_knowledge_units | active |

**解析质量闭环 (7 modules)**
| Module | Lines | Key Classes/Functions | Status |
|---|---|---|---|
| parse.py | 1123 | 4 classes (PDF provider routing, fast-text-first), parse_document | active |
| quality.py | 356 | QualityResult, assess_document_quality | active |
| parse_views.py | 725 | ParseViewCandidate, PageParseSelection, list_parse_view_pages | active |
| doc_diagnostics.py | 570 | build_document_diagnostics | active |
| parse_risk_actions.py | 672 | ParseRiskRepairTask, ParseRiskGoldenCandidateRequest | active |
| parse_risk_history.py | 127 | summarize_parse_risk_history | active |
| pdf_chunking.py | 90 | PdfChunk, PageImage | active |

**召回闭环 (14 modules)**
| Module | Lines | Key Classes/Functions | Status |
|---|---|---|---|
| query_rewrite.py | 692 | RewrittenQuery, rewrite_query | active |
| query_semantic_parser.py | 426 | 1 class, 23 functions | active |
| query_expansion.py | 370 | 2 classes, 19 functions | active |
| advanced_query_planner.py | 342 | 1 class, 14 functions (behind EAKB_ENABLE_ADVANCED_QUERY_PLANNER=1) | active but gated |
| topic_resolution.py | 433 | TopicResolutionResult | active |
| retrieval.py | 408 | search_knowledge_base, ensure_fts_schema | active, includes FTS guard |
| retrieval_router.py | 668 | 29 functions | active |
| reranker.py | 680 | 35 functions | active |
| graph_retrieval.py | 474 | 1 class, 20 functions | active |
| corpus_eval.py | 1180 | CorpusEvalGenerationResult, 61 functions | active |
| retrieval_quality.py | 186 | evaluate_retrieval_quality | active |
| evidence_shapes.py | 714 | EvidenceShape, EvidenceShapeContract | active, core |
| knowledge_contracts.py | 302 | KnowledgeTypeContract | active |
| routing_summary.py | 457 | direct_routing_hits | active |

**答案闭环 (7 modules)**
| Module | Lines | Key Classes/Functions | Status |
|---|---|---|---|
| answer_policy.py | 1065 | select_answer_policy, build_summary_lines | active |
| answer_api.py | 3016 | answer_query (96 functions) | active, largest |
| answer_quality.py | 254 | evaluate_answer_quality | active |
| confidence.py | 37 | compute_confidence_score | active, tiny |
| evidence_judge.py | 581 | 1 class, 33 functions | active |
| query_ambiguity.py | 404 | ClarificationOption, QueryAmbiguity | active |
| ambiguity_index.py | 178 | Sense, build_ambiguity_index | active |

**回归闭环 (5 modules)**
| Module | Lines | Key Classes/Functions | Status |
|---|---|---|---|
| generated_tests.py | 3242 | 108 functions (largest single module) | active |
| golden_generation.py | 626 | AssertionContract, GoldenCandidate, 5 classes | active |
| user_query_retrieval_eval.py | 417 | UserQueryRetrievalEvalResult | active |
| graph_report.py | 194 | GraphQueryTypeReport, GraphHealthReport | active |
| governance.py | 41 | assess_pending_quality (simple wrapper) | active but thin |

**派生状态治理闭环 (6 modules)**
| Module | Lines | Key Classes/Functions | Status |
|---|---|---|---|
| derived_state.py | 388 | DerivedStateSpec, DerivedStateCheck | active |
| derived_state_rebuild.py | 773 | DerivedStateRebuildItem, rebuild_derived_state | active |
| workspace_doctor.py | 717 | WorkspaceDoctorIssue, run_workspace_doctor | active |
| workspace_governance.py | 297 | WorkspaceGovernanceStep | active |
| run_governance.py | 506 | RunPruneItem, RunPruneReport, prune_stale_runs | active |
| db_hygiene.py | 194 | DatabaseHygieneItem, quarantine_suspicious_db_files | active |

**基础设施 (7 modules)**
| Module | Lines | Key Classes/Functions | Status |
|---|---|---|---|
| db.py | 30 | connect, apply_schema, list_tables | active |
| schema.sql | - | full DB schema | active |
| config.py | 54 | AppPaths | active |
| bootstrap.py | 43 | initialize_workspace, workspace_status | active |
| ids.py | 31 | next_prefixed_id | active |
| pipeline.py | 569 | PipelineEvent, run_document_pipeline | active |
| cli.py | 1623 | CLI entry point | active |

**共享服务 (6 modules)**
| Module | Lines | Key Classes/Functions | Status |
|---|---|---|---|
| api_server.py | 2346 | 2 classes, 99 functions | active |
| wiki_compiler.py | 743 | WikiBuildResult, build_wiki_for_document | active |
| graph.py | 331 | GraphBuildResult, build_graph_for_document | active |
| mcp_server.py | 193 | run_mcp_stdio | active |
| agent_tools.py | 206 | AgentRunResult, run_agent_query | active |
| workspace_admin.py | 102 | reset_workspace_data | active |

**文档处理辅助 (5 modules)**
| Module | Lines | Key Classes/Functions | Status |
|---|---|---|---|
| doc_ir.py | 148 | DocIRBlock, DocIRPage | active |
| structure_recovery.py | 101 | RecoveredSection, RecoveredStructure | active |
| reading_order.py | 20 | restore_reading_order | active |
| layout_cleaner.py | 174 | CleanedDocumentIR | active |
| synonyms.py | 58 | SYNONYM_MAP, expand_with_synonyms | active |

**作业/辅助 (3 modules)**
| Module | Lines | Key Classes/Functions | Status |
|---|---|---|---|
| jobs.py | 114 | JobRunResult, run_parse_jobs | active |
| __init__.py | 6 | version string | active |
| **TOTAL** | **40969** | | |

## 2. 文档归档建议

### 应移到 docs/_archive/ 的文件 (历史快照，不再维护)

**4月早期架构/设计文档** — 已被 .codestable/architecture/ 取代：
- docs/system_architecture_and_feature_summary_2026-04-19.md
- docs/knowledge_first_principles_architecture_2026-04-21.md
- docs/domain_knowledge_model_v1_2026-04-21.md
- docs/domain_model_v1_reuse_assessment_2026-04-21.md
- docs/external_access_and_execution_chain_design_2026-04-21.md
- docs/internal_data_flow_across_wiki_graph_facts_evidence_2026-04-21.md
- docs/v1_schema_design_2026-04-21.md
- docs/v1_implementation_roadmap_2026-04-21.md
- docs/development_roadmap.md
- docs/kb1_project_design_2026-04-25.md (已标注被 04-28 取代)
- docs/kb1_current_architecture_2026-04-28.md (已被 .codestable/architecture/ 取代)

**4月解析/PDF 评估文档** — 一次性评估，不再是当前工作参考：
- docs/pdf_conversion_ab_doc000007_2026-04-19.md + .json
- docs/paddlevl_vs_minimax_10page_benchmark_2026-04-20.md + .json
- docs/minimax_multimodal_support_check_2026-04-19.json
- docs/minimax_multimodal_support_analysis_2026-04-19.md
- docs/paddle_json_llm_pipeline_comparison_analysis_2026-04-19.md

**4月知识单元进展文档** — 已被代码实现取代：
- docs/doc_ir_and_knowledge_units_progress_2026-04-19.md
- docs/knowledge_units_progress_2026-04-19.md
- docs/structured_requirement_progress_2026-04-19.md

**4月早期交付文档** — 已被更新的 docs/user/ 取代：
- docs/workbench_user_guide_2026-04-20.md
- docs/delivery_quickstart_2026-04-20.md
- docs/final_delivery_notes.md
- docs/architecture_deviation_review_2026-04-21.md
- docs/phase5_subgraph_answer_progress_2026-04-21.md

**4月回归快照** — 一次性数据：
- docs/parameter_regression_report_2026-04-20.json
- docs/timing_regression_report_2026-04-21.json
- docs/wiki_regression_report_2026-04-21.json
- docs/graph_regression_report_2026-04-21.json
- docs/subgraph_regression_report_2026-04-21.json
- docs/knowledge_chain_regression_report_2026-04-21.json
- docs/topic_object_regression_report_2026-04-21.json

**4月查询修复系列** — 已完成，不再是工作参考：
- docs/current_session_state_2026-04-22.md
- docs/current_session_state_2026-04-23.md
- docs/query_error_diagnosis_model_2026-04-22.md
- docs/query_repair_blueprint_2026-04-23.md
- docs/query_repair_task_breakdown_2026-04-23.md
- docs/query_repair_phase0_execution_spec_2026-04-23.md
- docs/query_repair_master_plan_2026-04-23.md
- docs/query_repair_milestone_board_2026-04-23.md
- docs/query_repair_acceptance_template_2026-04-23.md
- docs/query_repair_m0_acceptance_2026-04-23.md
- docs/query_repair_m0_postpatch_acceptance_2026-04-23.md
- docs/query_repair_m1_postpatch_acceptance_2026-04-23.md
- docs/query_repair_m2_postpatch_acceptance_2026-04-23.md
- docs/query_repair_m3_postpatch_acceptance_2026-04-23.md
- docs/query_repair_m4_postpatch_acceptance_2026-04-23.md
- docs/query_repair_m5_postpatch_acceptance_2026-04-23.md
- docs/query_repair_m0_baseline_snapshot_2026-04-23.json
- docs/query_repair_m0_postpatch_snapshot_2026-04-23.json
- docs/ingestion_coverage_report_model_2026-04-23.md
- docs/robustness_test_coverage_framework_2026-04-23.md
- docs/query_semantic_parser_system_prompt_v1.md

### 应保留在 docs/ 中的文件

**当前活跃开发文档：**
- docs/dev/README.md
- docs/dev/kb1-development-guide.md
- docs/dev/api-cli-development-guide.md
- docs/dev/query-chain-development-guide.md
- docs/dev/ingestion-coverage-development-guide.md
- docs/dev/regression-eval-development-guide.md
- docs/dev/derived-state-governance-development-guide.md
- docs/dev/project-organization-review.md
- docs/user/kb1-workbench-user-guide.md

## 3. 代码与文档差异

### 文档引用了不存在的模块/功能
- .codestable/requirements/ontology-knowledge-layer.md 描述了 4 阶段本体层，但代码中只有隐式实现（evidence_shapes, knowledge_contracts），没有正式 ontology registry

### 代码有但文档未覆盖
- synonyms.py (SYNONYM_MAP) — 文档中没有描述同义词扩展机制
- confidence.py — 文档中只提到 confidence_score，没有描述计算逻辑
- graph_report.py — GraphHealthReport 在文档中未描述
- coverage_diagnostics.py — UncoveredPriorityReport 在文档中未描述
- routing_summary.py — direct_routing_hits 在文档中未描述
- layout_cleaner.py / structure_recovery.py / reading_order.py — 文档处理管线未描述

### roadmap 全部 done 但缺少下一步
- kb1-six-loop-hardening: 7/7 done
- kb1-derived-state-governance: 9/9 done
- 需要新的总路线文档

### 审计遗留
- F-04 (golden 合同与 query_type 不一致): 状态未确认
- F-05 (delivery asset 测试断言旧 UI): 状态未确认
