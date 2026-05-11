---
doc_type: issue-fix
status: fixed
severity: high
tags:
  - retrieval
  - reranker
  - evidence-judge
  - corpus-eval
created_at: 2026-05-11
fixed_at: 2026-05-11
---

# Parameter Row Routing Shape Fix Note

## Changes

- `query_rewrite.py`
  - Added `表 A.1` style table extraction.
  - Added generic parameter-query term extraction for row-like queries.

- `retrieval_router.py`
  - Added structured `parameter_value` direct hits based on table, object, parameter, symbol, and focus tags.
  - Fixed same-channel merge so a later higher-scored structured hit can replace a weaker first-seen hit.

- `reranker.py`
  - Added parameter lookup subtype scoring using table match, table mismatch, parameter name, symbol, object, row focus, and table focus.
  - Stopped relying on long Chinese substring fragments as the main signal.

- `routing_summary.py`
  - Added explicit table match/mismatch adjustment.
  - Suppressed shortcut A.4/A.7 boosts when the user explicitly requested a different table.
  - Avoided adding `检测点1` to every CP/control-guide query unless the query asks for signal-state context.

- `evidence_shapes.py` and `evidence_judge.py`
  - Scored `parameter_value` facts by structured fields.
  - Normalized `CP` to `控制导引` for evidence-shape anchor validation.
  - Avoided single-letter table section anchors such as `A`.

- `answer_api.py`
  - Added timing answer shape gating so general CP timing answers use A.7/control-timing facts, not A.4 signal-state transitions.

## Verification

Commands run:

```powershell
C:\Python314\python.exe -m pytest tests/test_corpus_eval.py tests/test_query_repair_regression.py::test_query_context_honors_explicit_table_and_parameter_row_anchor tests/test_query_repair_regression.py::test_answer_query_explains_cp_9v_pwm_state tests/test_query_repair_regression.py::test_answer_query_explains_cp_timing_from_a7 tests/test_retrieval_quality.py -q -m "not benchmark"
```

Result:

`13 passed`

Corpus smoke:

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base run-corpus-retrieval-eval --case-file output\corpus_eval_smoke\corpus_retrieval_cases_2026-05-11.json --limit 8 --output-dir output\corpus_eval_smoke
```

Result:

`6 passed, 0 failed`

## Outcome

The fix is framework-level across the retrieval and answer chain:

`rewrite -> structured retrieval -> rerank -> evidence shape -> answer fact selection`

The original A.1 parameter-row case now ranks `FACT-113543` first, preserves `parameter_definition`, and keeps the selected row in `best_fact_ids`.
