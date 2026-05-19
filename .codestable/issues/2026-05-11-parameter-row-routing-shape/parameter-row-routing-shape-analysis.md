---
doc_type: issue-analysis
status: confirmed
severity: high
tags:
  - retrieval
  - reranker
  - evidence-judge
  - answer-policy
created_at: 2026-05-11
---

# Parameter Row Routing Shape Analysis

## Root Cause Chain

1. `query_rewrite.py` did not extract structured parameter-row anchors for queries like `表 A.1 ... 供电设备容抗参数是什么`.
   It missed `表 A.1` table syntax and left useful row anchors as long or broken Chinese fragments.

2. `routing_summary.py` applied shortcut boosts for A.4/A.7 style control-guide tables without fully respecting explicit table mismatch.
   A query that explicitly asked for A.1 could still inherit A.4 signal-state priority.

3. `retrieval_router.py` merged direct fact hits by first-seen ID inside the same channel.
   A weak `LIKE '%表 A.1%'` hit could block a later, higher-scored structured `parameter_value` hit for the same fact.

4. `reranker.py` scored parameter lookup as generic lexical evidence.
   It did not separately validate table number, object column, parameter name, symbol, row tags, and table tags.

5. `evidence_shapes.py` and `evidence_judge.py` treated `CP` as a literal anchor even when the corpus expresses the same concept as `控制导引`.
   This caused valid parameter rows to look shape-unknown.

6. `answer_api.py` allowed timing answer fact expansion to reintroduce non-timing transition facts from A.4.
   The final answer could bypass the A.7 evidence chosen by retrieval and judge.

## Confirmed Fix Direction

The fix must preserve structured traceability instead of adding query-specific rules:

- Extract table and parameter-row terms generically.
- Use structured `parameter_value` fields as retrieval and rerank signals.
- Make shortcut routing obey explicit table constraints.
- Let evidence shape score parameter rows by schema fields.
- Normalize CP control-guide anchors during evidence validation.
- Gate timing answer facts by timing evidence shape.
