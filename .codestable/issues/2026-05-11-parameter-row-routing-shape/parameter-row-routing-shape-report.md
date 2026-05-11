---
doc_type: issue-report
status: fixed
severity: high
tags:
  - retrieval
  - evidence-shape
  - parameter-row
  - corpus-eval
created_at: 2026-05-11
---

# Parameter Row Routing Shape Report

## Problem

Corpus retrieval smoke exposed a parameter-row failure after the explicit table and source-unit eval work.

Representative query:

`表 A.1 控制导引电路的参数供电设备容抗参数是什么`

Expected:

- `FACT-113543` should rank first.
- Evidence shape should be `parameter_definition`.
- `best_fact_ids` should preserve the selected row fact.

Observed before fix:

- A.4/A.7 routing shortcuts could outrank explicit A.1 parameter rows.
- Same-table rows such as `FACT-113535` could beat the row-specific `FACT-113543`.
- Evidence Judge sometimes selected nearby parameter rows instead of the top row.
- CP timing answer could later be pulled back to A.4 by answer fact expansion.

## Impact

This was not a single-query typo. The failure showed a framework-level gap in how parameter questions move through:

`query rewrite -> retrieval candidate merge -> rerank -> evidence shape -> answer fact selection`

Any table-row style question with an explicit table number, object column, parameter name, or acronym alias could be affected.
