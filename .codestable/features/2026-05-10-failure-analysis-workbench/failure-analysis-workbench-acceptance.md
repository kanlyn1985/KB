---
doc_type: feature-acceptance
feature: 2026-05-10-failure-analysis-workbench
status: accepted
summary: Failure Analysis Workbench 已作为全局失败归因入口验收
roadmap: kb1-four-loop-hardening
roadmap_item: failure-analysis-workbench
tags:
  - workbench
  - failure-analysis
  - acceptance
---

# Failure Analysis Workbench Acceptance

## 1. 验收结果

通过。Failure Analysis Workbench 现在不再被文档详情状态阻断，可以作为全局回归失败归因入口使用。

## 2. 代码改动

- `examples/demo.html`
  - `renderMain()` 增加 `documentScopedTabs`
  - 仅 `overview`、`coverage`、`gaps`、`drafts`、`golden` 需要选中文档
  - `retrieval`、`failures`、`query` 作为全局 tab 可直接渲染
- `tests/test_delivery_assets.py`
  - 增加 Workbench 全局 tab 和 Failure Analysis 入口的静态回归断言

## 3. 验证

命令：

`C:\Python314\python.exe -m pytest tests/test_delivery_assets.py tests/test_api_server.py -q -k "demo or failure_analysis or retrieval_runs"`

结果：

`2 passed, 9 deselected`

浏览器验证：

- 打开 `http://127.0.0.1:8000/demo`
- 点击 `Failures`
- 页面加载 eval runs
- 页面展示 Failure Analysis、Repair Task Coverage、Repair Tasks、失败类型和 failure cards
- failure card 包含期望命中、实际召回、失败原因、建议动作、链路诊断、召回质量和答案质量

## 4. Roadmap 回写

`kb1-four-loop-hardening-items.yaml` 中 `failure-analysis-workbench` 已更新为 `done`，关联 feature `2026-05-10-failure-analysis-workbench`。

## 5. 后续项

- `unknown_pytest_failure` 仍需要转为更结构化的 eval result，避免 failure cards 缺少期望命中和实际召回。
- Supporting evidence 展示清洗仍是下一项独立任务。
- `query-context` clarification contract 仍需单独定义。
