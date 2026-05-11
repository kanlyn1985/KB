---
doc_type: feature-design
feature: 2026-05-10-failure-analysis-workbench
status: approved
summary: 让 Failure Analysis Workbench 成为全局可用的失败归因入口
roadmap: kb1-four-loop-hardening
roadmap_item: failure-analysis-workbench
tags:
  - workbench
  - failure-analysis
  - regression
---

# Failure Analysis Workbench Design

## 1. 目标

Workbench 的 Failure Analysis 应作为全局回归分析页面使用，不应该依赖用户先选择某个文档。失败分析关注 eval run、failure case、repair task 和 golden draft，属于回归闭环，不是单文档详情页。

## 2. 明确不做

- 不重写现有 `/failure-analysis`、`/repair-tasks`、`/draft-golden-from-failure` 后端。
- 不改变 failure type 推断规则。
- 不新建数据库表。
- 不移动旧文档。

## 3. 根因

现有 `examples/demo.html::renderMain()` 在渲染任何 tab 前先检查 `state.detail?.document`。这让 `Failures`、`Retrieval`、`Query Lab` 这类全局视图被单文档状态门禁挡住，属于页面编排层的职责边界错误。

## 4. 方案

把 tab 分成两类：

- 文档域 tab：`overview`、`coverage`、`gaps`、`drafts`、`golden`
- 全局 tab：`retrieval`、`failures`、`query`

只有文档域 tab 在没有选中文档时显示“选择左侧文档开始”。全局 tab 不再被文档详情状态阻断。

## 5. 验收场景

- 点击 `Failures` 能看到 eval runs、failure analysis、repair tasks 和 failure cards。
- Failure card 展示 query/case、期望命中、实际召回、失败原因、建议动作、链路诊断、召回质量、答案质量。
- 页面仍保留生成 Golden 草案、激活草案、repair task 状态更新入口。
- 交付资产测试覆盖全局 tab 门禁规则，避免回归。
