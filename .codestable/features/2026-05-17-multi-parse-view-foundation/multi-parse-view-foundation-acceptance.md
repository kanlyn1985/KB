---
doc_type: feature-acceptance
feature: 2026-05-17-multi-parse-view-foundation
status: accepted
accepted_at: 2026-05-17
summary: 多解析视图完成 schema、HTML 候选、规则选择、selected view 驱动、Workbench 对比和真实文档验证
tags:
  - parsing
  - parse-quality
  - html
  - ocr
---

# Multi Parse View Foundation Acceptance

## 验收结论

通过。多解析视图已经完成最小可用闭环：`parse_views` 保存候选视图，`page_parse_selection` 保存每页 best view 和选择原因；PDF 解析会同时生成当前 parser 输出和 `pymupdf_html` 候选，最终 `pages/blocks/normalized` 由 selected view 驱动。Document diagnostics 已暴露 `parse_views` 摘要，Workbench 已通过 Parse Views tab 展示页面级候选对比。

## 对照设计

- [x] 新增 additive schema：`parse_views`、`page_parse_selection`。
- [x] 新增规则评分和选择节点，不调用 LLM。
- [x] parse pipeline 登记当前 parser 输出为 `native_text` 或 `ocr_html`。
- [x] document diagnostics 输出 parse view summary。
- [x] 接入 PDF-to-HTML 候选 provider，且不绕过 selection。
- [x] OCR/VLM 输出归入 `ocr_html` 候选边界。
- [x] 旧 `pages`、`blocks`、`normalized` 路径保持兼容，并由 selected view 写入。
- [x] `/parse-view-detail` 和 Workbench Parse Views tab 可只读展示每页候选、分数、风险、选择原因和 fallback chain。

## 验证

```powershell
C:\Python314\python.exe -m pytest tests/test_parse_views.py tests/test_closed_loop_schema.py::test_closed_loop_tables_are_initialized tests/test_doc_diagnostics.py tests/test_pipeline_smoke.py::test_file_pipeline_emits_stage_progress_events -q
```

结果：

```text
9 passed in 8.22s
```

```powershell
C:\Python314\python.exe .codestable\tools\validate-yaml.py --file .codestable\features\2026-05-17-multi-parse-view-foundation\multi-parse-view-foundation-checklist.yaml --yaml-only
```

结果：

```text
1 passed, 0 failed
```

```powershell
C:\Python314\python.exe -m py_compile src\enterprise_agent_kb\parse.py src\enterprise_agent_kb\parse_views.py src\enterprise_agent_kb\doc_diagnostics.py
```

结果：通过。

## 后续

- 后续优化：引入更强的 HTML 结构恢复，尤其是表格、跨页续表和目录噪声分离。
- 后续优化：把扫描件专用 OCR-to-HTML provider 从现有 VLM/OCR markdown 中拆出来，提供更稳定的 layout JSON。
- 后续优化：为 Workbench Parse Views 增加差异高亮、表格结构预览和按风险过滤。

## 真实文档效果

文档：`DOC-000013`，10 页。

执行：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base build-document --doc-id DOC-000013 --progress
```

结果摘要：

```text
parse_views.view_count = 20
page_parse_selection.selection_count = 10
selected_by_type.html = 10
quality.high_risk_page_count = 0
quality.review_required_count = 0
evidence_count = 10
fact_count = 19
wiki_page_count = 22
coverage_source_unit_count = 14
ingestion_acceptance.failed_count = 0
ingestion_acceptance.warn_count = 1
```

注意：验收仍有 `document_knowledge_contract` warning，原因是该文档的 active evidence shapes 尚缺 active golden case，不是解析质量失败。
