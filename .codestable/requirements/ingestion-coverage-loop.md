---
doc_type: requirement
slug: ingestion-coverage-loop
pitch: 让每份文档从页面到知识单元都有覆盖凭证。
status: current
last_reviewed: 2026-05-09
implemented_by:
  - closed-loop-architecture
tags:
  - ingestion
  - coverage
  - source-units
---

# 入库覆盖闭环

## 用户故事

- 作为知识库维护者，我希望知道文档哪些页面、块和知识单元已经入库，而不是只看到“解析完成”。
- 作为调试者，我希望能定位未覆盖 source unit 和高风险页面，而不是靠人工翻 PDF 猜漏了哪里。
- 作为系统验收者，我希望入库结果有可量化指标，而不是只看生成文件数量。

## 为什么需要

如果入库阶段没有覆盖凭证，后面的召回失败无法判断是“没召回到”还是“内容根本没进来”。KB1 必须先证明文档真的被解析成可追踪的 pages、blocks、evidence、facts 和 source_units。

## 怎么解决

系统把文档拆成页面、块、证据、事实和 source unit，并生成覆盖报告。维护者可以看到解析成功率、证据数量、未覆盖单元和风险页面，从源头判断知识链是否完整。

## 边界

- 不保证每个 source unit 都能直接回答用户问题。
- 不替代召回质量评测；它只证明内容是否进入知识库。
- 需要先完成文档注册和解析流程。
