---
doc_type: requirement
slug: parse-quality-loop
pitch: 把解析风险拆成可处理的根因，避免低可读性页面被误当成入库失败。
status: current
last_reviewed: 2026-05-17
implemented_by:
  - closed-loop-architecture
tags:
  - parse-quality
  - diagnostics
  - closed-loop
---

# 解析质量闭环

## 用户故事

- 作为知识库维护者，我希望看到哪些高风险页面是真的没解析出来，而不是看到一堆低可读性 warning 后只能人工猜。
- 作为调试者，我希望系统能区分没有 evidence、已有 source unit 但没有 fact 映射、以及只需要复核的页面，而不是把所有解析质量问题混成一种失败。
- 作为新文档验收者，我希望低可读性页面在证据链完整时不阻塞入库验收，但真正缺 evidence 的页面必须被拦住。

## 为什么需要

入库闭环证明文档内容进来了，但解析质量还需要单独证明“页面级风险是否已经被证据链吸收”。如果只看 `low_readability` 或 `high risk page` 数量，系统会把已经有 evidence、source unit 和 fact 的页面误判为入库问题，也会掩盖真正没有 evidence 的解析缺口。

## 怎么解决

系统把每个高风险页面按证据链状态分为 `no_evidence`、`evidence_without_source_unit`、`source_unit_without_fact` 和 `fully_backed`。维护者先处理真正缺 evidence 的页面，再处理已有 source unit 但 fact 映射断开的页面；有 evidence 的低可读性页面进入人工复核 backlog，不再被当成入库失败。

## 边界

- 它不判断答案是否正确；答案质量归答案闭环。
- 它不替代 coverage；source unit 覆盖率仍由入库覆盖闭环负责，不能要求每个页面都有 source unit。
- 它不自动修 OCR 或 PDF 解析，只给出可执行的根因分类和下一步动作。
- 它依赖页面、evidence、source unit 和 fact 映射已经写入工作区。
