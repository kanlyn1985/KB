---
doc_type: requirement-index
status: current
last_reviewed: 2026-05-17
summary: KB1 capability vision index
tags:
  - kb1
  - requirements
  - codestable
---

# KB1 能力愿景索引

## Current

- [ingestion-coverage-loop](ingestion-coverage-loop.md) — 证明文档真的进来了，并能定位未覆盖内容。
- [parse-quality-loop](parse-quality-loop.md) — 把解析风险拆成可处理的根因，避免低可读性页面被误当成入库失败。
- [multi-parse-view-selection](multi-parse-view-selection.md) — 让系统按页比较 PDF 原生文本、HTML 和 OCR 结果，选择最可靠的解析视图。
- [retrieval-quality-loop](retrieval-quality-loop.md) — 证明用户问法能找到正确内容，并能解释召回失败。
- [evidence-constrained-answer-loop](evidence-constrained-answer-loop.md) — 让答案只基于候选证据输出，歧义先澄清，不让 LLM 直接决定事实。
- [regression-governance-loop](regression-governance-loop.md) — 用 golden suite 和失败归因证明系统越改越稳。
- [derived-state-governance-loop](derived-state-governance-loop.md) — 让系统能发现、刷新和隔离过期派生数据，避免残留状态误导查询和评测。
- [ontology-knowledge-layer](ontology-knowledge-layer.md) — 将 KB1 的长期目标定义为具备本体约束、语义校验和有限推理能力的可信知识库。

## Draft

- 暂无。

## Outdated

- 暂无。
