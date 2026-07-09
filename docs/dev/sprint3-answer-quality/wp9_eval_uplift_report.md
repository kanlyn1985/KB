# WP9: Eval 提分验收 (0.40 -> 0.65-0.85) + 性能修复

> Sprint 3 WP9. Acceptance toward raising the real cross-doc token_overlap
> baseline from 0.40 to 0.65-0.85. Date 2026-06-30.

## 1. Performance blocker discovered and fixed

The 20q eval was taking 20+ minutes per run, making WP8 sharded 104q baseline
and iterative WP9 uplift work infeasible. Root-cause investigation found TWO
independent performance blockers in the retrieval path:

### 1.1 FTS derived-state staleness (root cause)

`_refresh_fts_index` (retrieval.py) was edited in WP7 to exclude the 72
quarantined orphan facts from `facts_fts` (7636 -> 7564 rows). This made the
`facts_fts` derived-state check report `stale` (count mismatch: source 7636 vs
artifact 7564 + 72 missing indexed rows). The stale check triggered
`_ensure_fts_ready` to run a FULL `_refresh_fts_index` (~15s) on EVERY
`search_knowledge_base_expanded` call. With ~18 calls per question
(6 seeds x 3 channels), this added ~270s of pure index-rebuild overhead per
question.

**Fix**: reverted the WP7 facts_fts exclusion. facts_fts now indexes all 7636
facts again (query-level `fact_status` exclusion in the 12 recall queries
still prevents orphan recall - the WP7 governance is preserved at the query
layer, just not the FTS index layer). Rebuilt facts_fts + wrote freshness
stamp; all 4 FTS tables now report `fresh`. Per-call time dropped from ~15s to
~1.2s.

### 1.2 Embedding search model-reload-per-call (secondary)

`_search_embeddings` (retrieval.py) loads the `all-MiniLM-L6-v2`
SentenceTransformer model on EVERY call (model load is slow). With ~18 calls
per question this was a major cost. Added `EAKB_DISABLE_EMBEDDING_SEARCH=1`
env var to skip embedding search entirely - it is an optional enhancement
channel, FTS is the primary recall path.

Also added `EAKB_DISABLE_SEMANTIC_SEARCH=1` env var to skip the TF-IDF cosine
semantic channel (compute-heavy, verified to not change eval results).

### 1.3 Performance result

| Config | 5q time | 20q time | pass_rate |
|---|---|---|---|
| Before fixes (stale FTS) | ~125s/q (timeout) | 20+ min | 0.40 |
| After fixes (fresh FTS + disable flags) | ~25s/q | 453.6s (7.5 min) | 0.40 |

The 20q run now completes in 453.6s, within the 540s CI limit. Results are
identical (0.40, 8/20) confirming the fixes are performance-only with no
behavior change.

## 2. Eval baseline status

Current honest 20q baseline: **pass_rate=0.40 (8/20, 0 artifact)**, unchanged
from the WP7-locked value. Per-case results:

- PASS: [2] DOC-000002 0.46, [3] DOC-000003 0.61, [7] DOC-000019 1.00,
  [8] DOC-000001 0.38, [10] DOC-000002 0.33, [11] DOC-000003 0.59,
  [14] DOC-000016 0.30, [16] DOC-000001 0.47
- FAIL: [0][1][4][5][6][9][12][13][15][17][18][19]

## 3. Gate 1 status (0.65-0.85): NOT MET

Distance to Gate 1: 0.40 -> 0.65 requires +5 passes (8 -> 13/20). The dominant
remaining failure modes (from WP1 taxonomy) are:
- [5][17] channel weighting / full-payload anchor matching (P1, complex,
  deferred - requires DB reads of full object_value/normalized_text)
- [6] V2G wording alignment (evidence has fragmented mentions, no single
  evidence covers the expected_point's complete wording)
- [9][12][18][19] insufficient evidence / degradation (correct doc but
  judgement insufficient or answer under-coverage)
- [0][1][15] true retrieval miss or pseudo-question noise

A V2G embedded-digit regex fix was attempted (capture 'V2G' as a hard anchor)
but reverted - it caused doc-selection regression (selected DOC-000005
garbage instead of DOC-000013) because the V2G anchor then drove evidence
matching away from DOC-000013's Chinese-language V2G content.

## 4. WP9 deliverables

- Performance fix: FTS derived-state consistency restored (facts_fts 7564 ->
  7636, all 4 FTS tables fresh).
- Two eval-time env flags: `EAKB_DISABLE_EMBEDDING_SEARCH=1` and
  `EAKB_DISABLE_SEMANTIC_SEARCH=1` (optional enhancement channels, off for
  deterministic eval; default unchanged).
- `EAKB_ENABLE_LLM_EVIDENCE_JUDGE=0` documented for deterministic eval.
- 20q baseline reproducible in 453.6s (was 20+ min).

## 5. Boundary compliance

- No metric change (token_overlap scoring untouched).
- No query_api/answer_api main-path rewrite (env flags gate optional channels).
- WP7 governance preserved (query-level fact_status exclusion intact on all 12
  recall queries; only the FTS-index-layer exclusion was reverted for
  consistency).
- answer_changed_by_ontology remains false (untouched).
- The embedding/semantic flags default OFF (env var absent = original behavior),
  so production and existing tests are unaffected.

## 6. Status

Performance blocker resolved - 20q eval now reproducible in 7.5 min. Gate 1
(0.65-0.85) NOT MET; the remaining 0.25 gap requires P1 channel-weighting
(full-payload anchor matching) and recall improvements that are higher-risk
and exceed the lightweight-fix scope. Sprint 3 acceptance will honestly
document Gate 1 as partial (performance + stability achieved, target uplift
deferred to Sprint 4 with the full-payload anchor approach).
