---
doc_type: feature-acceptance
slug: golden-generation-v1-acceptance
feature: 2026-05-12-golden-generation-v1
status: accepted
accepted_at: 2026-05-12
---

# Golden Generation v1 Acceptance

## Scope

Golden Generation v1 establishes a unified candidate layer for automatic golden generation. It covers source-unit candidates, eval-failure candidates, confidence tiering, activation readiness, CLI dry-run reports, API review payloads, and Workbench review rendering.

## Accepted Behavior

- `GoldenCandidate` includes `origin`, `confidence_tier`, `assertion_contract`, `trace`, `metadata`, and `readiness`.
- Source-unit candidates inherit stable corpus eval contracts and stay `review_required`.
- Eval-failure candidates inherit only the original expected contract; wrong retrieved top items remain trace-only and never become `must_hit`.
- `generate-golden-candidates` writes JSON/Markdown reports and keeps `dry_run=true`, `auto_activation=false`.
- `/golden-candidates` exposes the same review payload to Workbench.
- Workbench Golden tab displays candidate counts, dry-run state, readiness, blocked reasons, assertion contract, and activation gate output.

## Validation

- `C:\Python314\python.exe -m pytest tests/test_golden_generation.py tests/test_corpus_eval.py -q`
  - Result: 11 passed.
- `C:\Python314\python.exe -m pytest tests/test_api_server.py -q -k "golden_candidate or lists_eval_runs_and_details or blocks_unready_golden_draft_activation"`
  - Result: 3 passed, 20 deselected.
- `C:\Python314\python.exe -m py_compile src\enterprise_agent_kb\golden_generation.py src\enterprise_agent_kb\api_server.py src\enterprise_agent_kb\cli.py`
  - Result: passed.
- Browser check on `http://127.0.0.1:8011/demo`
  - Result: Golden tab rendered candidates with `dry_run=true`, `auto_activation=false`, `review_required`, and `corpus_eval_requires_review`.
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base workspace-doctor --scope coverage --json`
  - Result before source fix: reported `source_unit_weak_definition_shape` with 4 real source-unit quality samples after shape-gate refinement.
  - Result after source fix and rebuilding DOC-000003/DOC-000013 facts/entities/wiki/graph/coverage: status `ok`, no coverage issues.
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base generate-golden-candidates --origin source_unit --doc-id DOC-000013 --limit-per-type 10`
  - Result: one candidate, `V2G是什么意思`; no author-line or figure-legend candidates.
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base generate-corpus-eval-cases --doc-id DOC-000013 --limit-per-type 3 --output-dir output\corpus-eval-current-code`
  - Result: one deterministic corpus retrieval case generated from the valid DOC-000013 source unit.
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base run-corpus-retrieval-eval --case-file output\corpus-eval-current-code\corpus_retrieval_cases_2026-05-12.json --suite-id regression:corpus_retrieval:current-code --limit 10 --output-dir output\corpus-eval-current-code`
  - Result: `EVAL-B812AFC2A1CFE247`, 1 passed, 0 failed.
- Re-run after FTS source-signature freshness fix:
  - Result: `EVAL-CBE2099D697698DF`, 1 passed, 0 failed; subsequent doctor output kept all FTS checks `fresh`.
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base rebuild-derived-state --scope all`
  - Result: reconciled graph/wiki/coverage artifacts and refreshed FTS after rebuilding DOC-000003/DOC-000013.
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base rebuild-derived-state --scope fts`
  - Result: refreshed FTS and wrote source-signature stamp for `facts_fts`, `evidence_fts`, and `wiki_fts`.
- `C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base workspace-doctor --scope all --json`
  - Result: FTS/graph/wiki/coverage issues cleared; remaining warnings are historical runs and an extra empty `knowledge_base/knowledge.db` file.
- `C:\Python314\python.exe -m pytest tests\test_derived_state.py tests\test_derived_state_rebuild.py tests\test_workspace_doctor.py tests\test_retrieval_fts_guard.py -q`
  - Result: 30 passed. Includes regression coverage that unrelated retrieval run writes do not mark FTS stale.

## Residual Risks

- Full `tests/test_api_server.py` run exceeded 180 seconds in this environment; targeted API tests passed.
- Real DOC-000013 source units originally produced a few noisy definition candidates. A definition evidence-shape gate now classifies these as `weak_definition_shape`; DOC-000013 dry-run candidate count dropped from 3 to 1 while retaining the valid `V2G` candidate. Remaining risk belongs to broader source-unit quality governance.
- `workspace-doctor --scope coverage` exposes weak definition shape as an ingestion/coverage quality issue, and the current source fix removes the observed DOC-000003/DOC-000013 weak definition samples after rebuild.
- Historical retrieval/eval runs remain as a separate run-governance cleanup decision. Dry-run reports 2027 retrieval runs, 61 eval runs and 505 eval results as stale/unknown for the current code version; these were not deleted automatically. The current-code eval run remains available, raising total run tables to 2028 retrieval runs and 62 eval runs in doctor output.
