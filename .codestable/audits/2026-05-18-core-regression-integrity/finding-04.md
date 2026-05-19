---
doc_type: audit-finding
slug: user-style-regression-contract-stale
severity: P1
type:
  - maintainability
  - arch-drift
confidence: high
suggested_action: cs-issue
---

# F-04 User Style Regression Contract Is Stale

## Finding

`tests/generated/user_style_query_regression_cases_2026-04-23.json` 仍要求参数含义类问题的 `expected_query_type` 为 `definition`，但当前架构已把显式参数意图归为 `parameter_lookup`，再由 answer policy 输出 `parameter_meaning`。全量测试因此失败，但这个失败很可能是测试合同过期，而不是功能错误。

## Evidence

- `tests/generated/user_style_query_regression_cases_2026-04-23.json:3-8`
  - `CC阻值代表什么意思`
  - `expected_query_type=definition`
  - `expected_answer_mode=parameter_meaning`
- `tests/generated/user_style_query_regression_cases_2026-04-23.json:15-20`
  - `CP占空比是什么意思`
  - `expected_query_type=definition`
  - `expected_answer_mode=parameter_meaning`
- `tests/generated/user_style_query_regression_cases_2026-04-23.json:27-32`
  - `检测点1电压表示什么`
  - `expected_query_type=definition`
  - `expected_answer_mode=parameter_meaning`
- 全量 pytest 失败：
  - actual `parameter_lookup`
  - expected `definition`

## Impact

过期 golden/test contract 会制造假失败，导致开发者为了让旧测试通过而把架构改回去。这会放大“打补丁”倾向，削弱参数查询和术语定义查询的边界。

## Root Cause

回归用例仍记录旧 query_type 语义，而没有随着 evidence shape / answer mode 架构升级。`query_type` 是内部路由合同，不应长期和用户可见 answer mode 混为同一个稳定断言。

## Suggested Fix

- 将这些 case 的 `expected_query_type` 更新为 `parameter_lookup`，或改成允许集合 `{definition, parameter_lookup}` 并以 `expected_answer_mode=parameter_meaning` 作为主断言。
- Golden schema 区分：
  - user-visible contract：answer_mode、direct_answer、must_hit、evidence_shape
  - internal route contract：query_type，仅对架构明确要求的 case 断言。
- 为 generated regression cases 增加 schema version 和 migration note。

