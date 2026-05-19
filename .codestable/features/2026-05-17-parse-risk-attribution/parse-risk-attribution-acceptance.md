---
doc_type: feature-acceptance
feature: 2026-05-17-parse-risk-attribution
status: accepted
accepted_at: 2026-05-17
summary: Parse risk 自动归因和行动建议已接入 diagnostics、API、Workbench 并通过 IEC 验证
tags:
  - parsing
  - diagnostics
  - parse-quality
---

# Parse Risk Attribution Acceptance

## 验收结论

通过。`doc_diagnostics.parse_quality` 已输出页面级 `attribution`、`recommended_action`，以及文档级 `attribution_counts`、`recommended_actions`。`document-detail` 和 Workbench Parse Views 复用同一结构化诊断结果。

## 归因类型

- `provider_quality_issue`
- `selection_rule_issue`
- `extraction_chain_issue`
- `review_only`
- `test_coverage_gap`

## 验证

```powershell
C:\Python314\python.exe -m pytest tests/test_doc_diagnostics.py tests/test_api_server.py::test_api_health_and_answer_query tests/test_closed_loop_schema.py::test_closed_loop_tables_are_initialized tests/test_parse_views.py tests/test_pipeline_smoke.py::test_file_pipeline_emits_stage_progress_events -q
```

结果：

```text
13 passed in 111.51s
```

YAML 校验：`1 passed, 0 failed`。

## IEC 61851 验证

文档：`DOC-000015 / IEC 61851-1-2017.pdf`

结果摘要：

```text
validate-document-ingestion.status = passed
failed_count = 0
warn_count = 0
parse_views.view_count = 584
page_parse_selection.selection_count = 292
parse_quality.high_risk_page_count = 14
provider_quality_issue = 8
selection_rule_issue = 0
extraction_chain_issue = 5
review_only = 0
test_coverage_gap = 1
```

## 结论

解析质量闭环现在能把风险页指向 provider、selection、抽取链路、人工复核或测试覆盖动作，避免后续再靠人工观察 Workbench 后拍脑袋调 prompt 或写单点规则。
