# archive_garbage_docs.ps1
# Move historical/garbage doc files from docs/ root to docs/_archive/
# Generated: 2026-05-19
# Based on: CODE_DOC_ALIGNMENT_REPORT_2026-05-19.md

$ErrorActionPreference = "Stop"
$projectRoot = "E:\AI_Project\opencode_workspace\KB1"
$archiveDir = Join-Path $projectRoot "docs\_archive"

# Ensure archive directory exists
if (-not (Test-Path $archiveDir)) {
    New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null
    Write-Host "Created: $archiveDir"
}

# Files to move — 4月早期架构/设计文档 (已被 .codestable/architecture/ 取代)
$files = @(
    "docs\system_architecture_and_feature_summary_2026-04-19.md",
    "docs\knowledge_first_principles_architecture_2026-04-21.md",
    "docs\domain_knowledge_model_v1_2026-04-21.md",
    "docs\domain_model_v1_reuse_assessment_2026-04-21.md",
    "docs\external_access_and_execution_chain_design_2026-04-21.md",
    "docs\internal_data_flow_across_wiki_graph_facts_evidence_2026-04-21.md",
    "docs\v1_schema_design_2026-04-21.md",
    "docs\v1_implementation_roadmap_2026-04-21.md",
    "docs\development_roadmap.md",
    "docs\kb1_project_design_2026-04-25.md",
    "docs\kb1_current_architecture_2026-04-28.md",

    # 4月解析/PDF 评估文档 (一次性评估)
    "docs\pdf_conversion_ab_doc000007_2026-04-19.md",
    "docs\pdf_conversion_ab_doc000007_2026-04-19.json",
    "docs\paddlevl_vs_minimax_10page_benchmark_2026-04-20.md",
    "docs\paddlevl_vs_minimax_10page_benchmark_2026-04-20.json",
    "docs\minimax_multimodal_support_check_2026-04-19.json",
    "docs\minimax_multimodal_support_analysis_2026-04-19.md",
    "docs\paddle_json_llm_pipeline_comparison_analysis_2026-04-19.md",

    # 4月知识单元进展文档 (已被代码实现取代)
    "docs\doc_ir_and_knowledge_units_progress_2026-04-19.md",
    "docs\knowledge_units_progress_2026-04-19.md",
    "docs\structured_requirement_progress_2026-04-19.md",

    # 4月早期交付文档 (已被更新的 docs/user/ 取代)
    "docs\workbench_user_guide_2026-04-20.md",
    "docs\delivery_quickstart_2026-04-20.md",
    "docs\final_delivery_notes.md",
    "docs\architecture_deviation_review_2026-04-21.md",
    "docs\phase5_subgraph_answer_progress_2026-04-21.md",

    # 4月回归快照 (一次性数据)
    "docs\parameter_regression_report_2026-04-20.json",
    "docs\timing_regression_report_2026-04-21.json",
    "docs\wiki_regression_report_2026-04-21.json",
    "docs\graph_regression_report_2026-04-21.json",
    "docs\subgraph_regression_report_2026-04-21.json",
    "docs\knowledge_chain_regression_report_2026-04-21.json",
    "docs\topic_object_regression_report_2026-04-21.json",

    # 4月查询修复系列 (已完成，不再是工作参考)
    "docs\current_session_state_2026-04-22.md",
    "docs\current_session_state_2026-04-23.md",
    "docs\query_error_diagnosis_model_2026-04-22.md",
    "docs\query_repair_blueprint_2026-04-23.md",
    "docs\query_repair_task_breakdown_2026-04-23.md",
    "docs\query_repair_phase0_execution_spec_2026-04-23.md",
    "docs\query_repair_master_plan_2026-04-23.md",
    "docs\query_repair_milestone_board_2026-04-23.md",
    "docs\query_repair_acceptance_template_2026-04-23.md",
    "docs\query_repair_m0_acceptance_2026-04-23.md",
    "docs\query_repair_m0_postpatch_acceptance_2026-04-23.md",
    "docs\query_repair_m1_postpatch_acceptance_2026-04-23.md",
    "docs\query_repair_m2_postpatch_acceptance_2026-04-23.md",
    "docs\query_repair_m3_postpatch_acceptance_2026-04-23.md",
    "docs\query_repair_m4_postpatch_acceptance_2026-04-23.md",
    "docs\query_repair_m5_postpatch_acceptance_2026-04-23.md",
    "docs\query_repair_m0_baseline_snapshot_2026-04-23.json",
    "docs\query_repair_m0_postpatch_snapshot_2026-04-23.json",
    "docs\ingestion_coverage_report_model_2026-04-23.md",
    "docs\robustness_test_coverage_framework_2026-04-23.md",
    "docs\query_semantic_parser_system_prompt_v1.md",

    # 其他历史文档
    "docs\optimization_gap_analysis_from_task_list_2026-04-19.md"
)

$moved = 0
$skipped = 0
$notFound = 0

foreach ($relPath in $files) {
    $src = Join-Path $projectRoot $relPath
    $fileName = Split-Path $relPath -Leaf
    $dst = Join-Path $archiveDir $fileName

    if (-not (Test-Path $src)) {
        Write-Host "NOT FOUND: $relPath" -ForegroundColor Yellow
        $notFound++
        continue
    }

    if (Test-Path $dst) {
        Write-Host "SKIP (exists in archive): $fileName" -ForegroundColor Cyan
        $skipped++
        continue
    }

    Move-Item -Path $src -Destination $dst -Force
    Write-Host "MOVED: $relPath -> _archive/$fileName" -ForegroundColor Green
    $moved++
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor White
Write-Host "Moved:    $moved"
Write-Host "Skipped:  $skipped (already in archive)"
Write-Host "Missing:  $notFound"
Write-Host "Total:    $($files.Count)"
Write-Host ""
Write-Host "After moving, run: git add -A && git commit -m 'chore: archive historical docs to docs/_archive/'"
