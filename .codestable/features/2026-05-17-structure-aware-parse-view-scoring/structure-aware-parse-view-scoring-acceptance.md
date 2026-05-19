---
doc_type: feature-acceptance
feature: 2026-05-17-structure-aware-parse-view-scoring
status: accepted
accepted_at: 2026-05-17
summary: 结构感知 parse view 评分、Workbench 风险过滤和 IEC 61851 盲测通过
tags:
  - parsing
  - parse-quality
  - structure
  - workbench
---

# Structure Aware Parse View Scoring Acceptance

## 验收结论

通过。`parse_views.quality_json` 已新增结构质量指标，selection score 已纳入 `structure_quality_score`，`selected_reason` 会解释结构分。Workbench Parse Views 已展示结构指标，并支持“只看风险页”过滤。

## 覆盖能力

- 表格密度：`table_density`
- 行列信号：`row_column_signal_count`
- 条款编号：`clause_number_count`
- 条款连续性：`clause_continuity_score`
- 页眉页脚噪声：`header_footer_noise_ratio`
- 重复行：`duplicate_line_ratio`
- 跨页/续表信号：`continuation_signal_count`
- 综合结构分：`structure_quality_score`

## 验证

```powershell
C:\Python314\python.exe -m pytest tests/test_parse_views.py tests/test_api_server.py::test_api_health_and_answer_query tests/test_closed_loop_schema.py::test_closed_loop_tables_are_initialized tests/test_doc_diagnostics.py tests/test_pipeline_smoke.py::test_file_pipeline_emits_stage_progress_events -q
```

结果：

```text
12 passed in 91.13s
```

```powershell
C:\Python314\python.exe .codestable\tools\validate-yaml.py --file .codestable\features\2026-05-17-structure-aware-parse-view-scoring\structure-aware-parse-view-scoring-checklist.yaml --yaml-only
```

结果：`1 passed, 0 failed`。

## 真实文档盲测

文档：`DOC-000015 / IEC 61851-1-2017.pdf`

执行：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base build-document --doc-id DOC-000015 --progress
```

结果摘要：

```text
ingestion_acceptance.status = passed
failed_count = 0
warn_count = 0
page_count = 292
evidence_count = 292
fact_count = 415
wiki_page_count = 18
coverage_source_unit_count = 53
parse_views.view_count = 584
page_parse_selection.selection_count = 292
selected_by_type.html = 207
selected_by_type.ocr_html = 85
invalid_structure_score_count = 0
```

## 后续观察

IEC 61851 中仍有 115 个候选页带 parse-view risk flags，主要用于 Workbench 复核。入库验收通过说明它们不是阻断性解析缺口；后续优化应从 risk page 对比中判断是 provider 质量、选择规则还是 source unit/fact 抽取边界。
