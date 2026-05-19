---
doc_type: requirement
slug: multi-parse-view-selection
pitch: 让系统按页比较 PDF 原生文本、HTML 和 OCR 结果，选择最可靠的解析视图。
status: current
last_reviewed: 2026-05-17
implemented_by:
  - closed-loop-architecture
tags:
  - parsing
  - html
  - ocr
  - parse-quality
---

# 多解析视图选择

## 用户故事

- 作为知识库维护者，我希望同一份 PDF 可以保留多种解析结果，而不是一次解析失败后只能重跑整个文档。
- 作为新文档验收者，我希望系统能说明每页为什么选择 PDF 原生文本、HTML 或 OCR，而不是只看到最终 blocks。
- 作为调试者，我希望比较不同解析视图对 evidence、facts 和 source units 的影响，而不是靠肉眼判断 HTML 是否更好。

## 为什么需要

PDF 原生文本、PDF-to-HTML 和 OCR-to-HTML 各有优势。复杂表格、扫描件和标准文档页眉页脚会让单一路径不稳定；如果系统只保存最终结果，就无法解释某页为什么解析差，也无法安全接入新的 HTML/OCR 工具。

## 怎么解决

系统为每页保存多个 parse view，并用统一质量评分比较文本可读性、结构完整度、表格/列表信号、条款编号、跨页续接、页眉页脚噪声和重复行风险。后续入库只消费被选中的 best parse view，但所有候选视图保留为诊断和回退依据。

## 边界

- 当前阶段已经具备结构感知评分、选择合同、PDF HTML 候选和 Workbench 页面级候选对比；更强的外部 OCR-to-HTML provider 属于后续增强。
- 不让 LLM 直接决定最佳视图；LLM 最多作为后续候选生成器，最终选择必须经过规则评分和可解释约束。
- 不替代解析质量闭环；它向解析质量闭环提供更细的候选和选择证据。
- 不要求每页都有 HTML 或 OCR 视图；缺失视图应被记录为 unavailable，而不是失败。
