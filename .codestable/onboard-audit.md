# CodeStable Onboard Audit

生成日期：2026-05-09

## 扫描结论

- `.codestable/`：原先不存在，已创建标准骨架。
- 旧版目录 `easysdd/`：未发现。
- 旧版目录 `codestable/`：未发现。
- 项目已有大量 `docs/`、`knowledge_base/wiki/`、`coverage_reports/`、`tmp/` 下的 Markdown 文件，因此本次按迁移路径处理。
- 本次没有移动、删除或重命名任何既有文档。

## 高置信度映射建议

| 现有文件 | 推测内容类型 | 建议归入 CodeStable | 置信度 | 当前处理 |
|---|---|---|---|---|
| `docs/kb1_current_architecture_2026-04-28.md` | 当前主架构方案 | `.codestable/architecture/ARCHITECTURE.md` 的主参考来源 | 高 | 保留原位，待用户确认是否迁移/整合 |
| `docs/kb1_project_design_2026-04-25.md` | 项目设计方案历史快照 | `.codestable/architecture/` 或历史设计参考 | 高 | 保留原位 |
| `docs/development_roadmap.md` | 路线图 | `.codestable/roadmap/` | 高 | 保留原位 |
| `docs/architecture_deviation_review_2026-04-21.md` | 架构偏差复盘 | `.codestable/compound/decision/` 或 `.codestable/architecture/` | 中 | 保留原位，需确认 |
| `docs/ingestion_coverage_report_model_2026-04-23.md` | 入库覆盖模型设计 | `.codestable/architecture/` | 高 | 保留原位 |
| `docs/robustness_test_coverage_framework_2026-04-23.md` | 测试覆盖框架 | `.codestable/architecture/` 或 `.codestable/roadmap/` | 高 | 保留原位 |
| `docs/query_repair_master_plan_2026-04-23.md` | 查询修复总计划 | `.codestable/roadmap/` | 高 | 保留原位 |
| `docs/query_repair_task_breakdown_2026-04-23.md` | 查询修复任务拆解 | `.codestable/issues/` 或 `.codestable/roadmap/` | 中 | 保留原位，需确认 |
| `output/pdf/KB1_project_design_book_diagram_2026-05-09.pdf` | 项目设计书图示版交付物 | `.codestable/architecture/` 可引用，不建议移动 PDF | 中 | 保留原位 |

## 不建议纳入 CodeStable 的 Markdown

以下类型数量很大，建议保留原位，不直接迁入 `.codestable/`：

- `knowledge_base/wiki/**`：系统生成的知识库 wiki 页面。
- `knowledge_base/coverage_reports/**`：系统生成的 coverage 报告。
- `tmp/**`：临时 OCR / PDF / 测试中间产物。
- `.pytest_cache/**`：测试缓存。
- `.opencode/plans/**`：外部工具计划记录，可按需人工筛选。

## 已创建骨架

```text
.codestable/
├── attention.md
├── requirements/.gitkeep
├── architecture/ARCHITECTURE.md
├── roadmap/.gitkeep
├── features/.gitkeep
├── issues/.gitkeep
├── compound/.gitkeep
├── tools/
└── reference/
```

## 待用户确认

1. 是否把 `docs/kb1_current_architecture_2026-04-28.md` 整合进 `.codestable/architecture/ARCHITECTURE.md`。
2. 是否把 `docs/development_roadmap.md` 迁入 `.codestable/roadmap/`。
3. 是否将查询修复系列文档归档为 roadmap、issues，还是继续保留在 `docs/`。
