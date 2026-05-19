---
doc_type: audit-finding
slug: demo-delivery-asset-test-stale
severity: P2
type:
  - maintainability
confidence: medium
suggested_action: cs-issue
---

# F-05 Demo Delivery Asset Test Is Stale

## Finding

`tests/test_delivery_assets.py` 仍断言旧的 document-scoped tab 字符串 `["overview", "coverage", "gaps", "drafts", "golden"]`，但 `examples/demo.html` 已新增 `parse` 和 `hygiene` 页签，代码实际使用 `new Set(["overview", "parse", "coverage", "gaps", "drafts", "golden"])`。测试没有跟随 Workbench 新闭环更新。

## Evidence

- `examples/demo.html:1017` 新增 `Parse Views` tab。
- `examples/demo.html:1024` 新增 `Hygiene` tab。
- `examples/demo.html:1373` document scoped tabs 包含 `parse`。
- `tests/test_delivery_assets.py:41` 仍断言旧数组字符串。

## Impact

这是低风险但会污染全量测试信号的失败。它会让真正的 P0/P1 问题淹没在 UI 字符串断言里。

## Root Cause

UI delivery test 是 brittle string snapshot，没有抽象成“必须包含哪些 tabs / 哪些 tabs 是 document-scoped / 哪些 tabs 是 global-scoped”的结构化断言。

## Suggested Fix

- 更新测试合同，显式允许 `parse` 和 `hygiene`。
- 优先用 DOM/正则结构断言替代整段字符串断言。
- 将 Workbench tabs 作为可测试配置导出，避免 HTML 字符串和测试重复维护。

