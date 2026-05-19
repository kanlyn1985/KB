---
doc_type: feature-acceptance
feature: 2026-05-10-evidence-display-sanitization
status: accepted
summary: Supporting evidence 展示清洗已统一到答案 API 输出边界
roadmap: kb1-four-loop-hardening
roadmap_item: evidence-display-sanitization
tags:
  - answer
  - evidence
  - acceptance
---

# Evidence Display Sanitization Acceptance

## 1. 验收结果

通过。`supporting_evidence[].snippet` 现在和 direct answer 一样经过 render artifact 清洗，不再直接暴露 HTML entity、LaTeX delimiter 和重复标点残留。

## 2. 代码改动

- `src/enterprise_agent_kb/answer_api.py`
  - 引入 `html.unescape()`
  - `_clean_render_artifacts()` 统一解码 HTML entity 和 `\xa0`
  - `supporting_evidence.snippet` 先清洗再截断
- `tests/test_query_repair_regression.py`
  - 扩展 `OBC输入过压怎么测` 集成回归，断言 supporting evidence 不含渲染残留

## 3. 验证

命令：

`C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py -q -m integration -k "input_overvoltage or measurement"`

结果：

`2 passed, 50 deselected`

命令：

`C:\Python314\python.exe -m pytest tests/test_answer_quality.py -q`

结果：

`10 passed`

实际查询验证：

- query: `OBC输入过压怎么测`
- `answer_mode=test_method_lookup`
- first fact: `FACT-116907`
- direct answer 不含 `&nbsp;`
- supporting evidence 不含 `&nbsp;`、`&#160;`、`&emsp;`、`$`

## 4. Roadmap 回写

`kb1-four-loop-hardening-items.yaml` 中 `evidence-display-sanitization` 已更新为 `done`，关联 feature `2026-05-10-evidence-display-sanitization`。

## 5. 后续项

- Evidence snippet 仍可能因为同页 evidence 过长而混入相邻试验段落。该问题属于 evidence selection / paragraph extraction，不属于展示清洗。
- 下一项 roadmap 是 `query-context-clarification-contract`。
