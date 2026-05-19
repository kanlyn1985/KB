---
doc_type: audit-finding
slug: workspace-doctor-misses-document-source-unit-loss
severity: P1
type:
  - bug
confidence: high
suggested_action: cs-issue
---

# F-03 Workspace Doctor Misses Document Source Unit Loss

## Finding

`workspace-doctor --scope coverage --json` 返回 `ok`，但当前数据库里 `DOC-000003` 已经有 pages/evidence/facts，却没有任何 `source_units`。doctor 只检查 orphan mapping、missing fact/evidence 和 weak definition shape，没有检查“active document 的 coverage/source unit 是否整体缺失”。

## Evidence

- `workspace-doctor --scope coverage --json` 输出 `status=ok`，无 issues。
- DB 当前状态：
  - `DOC-000003` pages=157
  - `DOC-000003` evidence=317
  - `DOC-000003` facts=185
  - `DOC-000003` source_units=0
- `src/enterprise_agent_kb/workspace_doctor.py:434-504` `_coverage_issues` 主要检查 source unit mapping orphan 和 weak definition shape，没有 doc-level coverage absence 检查。

## Impact

系统已有“第五/第六闭环”的概念，但健康检查没覆盖最关键的状态丢失场景。用户看到查询失败时，doctor 却显示 coverage ok，会误导排查方向。

## Root Cause

coverage doctor 关注 mapping 一致性，而不是 document-level completeness。它没有把 `documents/pages/evidence/facts/source_units` 之间的数量关系作为合同。

## Suggested Fix

- `_coverage_issues` 增加 doc-level contract：
  - active parsed doc 有 pages/evidence/facts 但 source_units=0 => fail/warn
  - source_units=0 但 coverage report 声称 ok => fail
  - core docs / active docs 的 coverage artifact 与 DB 数量不一致 => warn/fail
- dashboard 和 doctor 都应显示 affected doc IDs。

