# WP8: 完整 104 题 golden baseline 分片

> Sprint 3 WP8. Enable the full 104-question golden baseline to run reliably
> (it times out at 540s as a single run) by sharding the question set and
> merging per-shard results. Date 2026-06-30.

## 1. Problem

The full golden suite (`run_suite` with no `max_questions`) builds ~104
questions deterministically from expected_points and runs the complete answer
pipeline per question (~20-40s each), so a single run exceeds the 540s CI
timeout. CI therefore uses `--max-questions 20` for a smoke sample, which is
too small to reflect real quality improvement (WP2/WP3 uplift landed outside
the first 10 questions before the sample was expanded to 20).

## 2. Approach (Sprint 3 guide Plan A: batch + merge)

Shard the question list into N contiguous slices, run each shard independently
(writing a per-shard JSON with per-question case details), then merge the shard
JSONs into one aggregated EvalResult. This is pure arithmetic over
already-scored cases - no re-scoring, no metric change.

## 3. Implementation

### 3.1 evaluator.py

- `run_suite(...)` gained `shard_index`/`shard_count` params. Sharding is
  applied AFTER `max_questions` round-robin sampling so the two compose. The
  split uses contiguous slices with remainder distribution so all shards cover
  the full set with no overlap/gap (verified: 10 questions / 3 shards = 4+3+3).
- `EvalResult.to_full_dict()` added: like `to_dict()` but includes the
  `per_question` case list so shards can be persisted and later merged.
  `to_dict()` is unchanged (backward-compatible CLI summary).
- `shard_result_from_dict(data)` reconstructs an EvalResult from a full-dict
  payload (loads per_question back into ScoreResult objects).
- `merge_shard_results(shards)` re-aggregates total/passed/pass_rate/
  avg_coverage/multi_prompt_stability/by_doc/safety_metrics from the
  per_question records of all shards. Accepts EvalResult or dict inputs.

### 3.2 cli/_eval.py

- `eval shard-run --shard-index I --shard-count N --output PATH`: runs one
  shard, writes full-dict JSON (with per_question) to `--output`.
- `eval merge-shards --input PATH [--input PATH ...] --output PATH`: loads
  shard JSONs, merges, writes aggregated full-dict JSON, prints summary.

## 4. Verification

- Imports OK; merge roundtrip (EvalResult -> full_dict -> from_dict -> merge)
  verified with synthetic 2-shard fixture (total 4, passed 3, pass_rate 0.75,
  by_doc and safety_metrics correctly aggregated).
- Shard split arithmetic verified: 10 questions / 3 shards = [0:4]+[4:7]+[7:10]
  = 4+3+3 = 10 total covered, no overlap/gap.
- CLI subcommands registered: `eakb eval shard-run --help` and
  `eakb eval merge-shards --help` both work.
- test_evaluator.py: 52 passed (48 + 4 new sharding/merge tests:
  to_full_dict_includes_per_question, shard_result_roundtrip,
  merge_shard_results_aggregates, merge_shard_results_from_dicts).
- No regressions in test_query_api / test_retrieval_router.

## 5. Usage

```
# Run 4 shards of the golden suite (each ~26 questions, ~8-12 min per shard):
python -m enterprise_agent_kb.cli eval shard-run --shard-index 0 --shard-count 4 --output tmp/shard_0.json
python -m enterprise_agent_kb.cli eval shard-run --shard-index 1 --shard-count 4 --output tmp/shard_1.json
python -m enterprise_agent_kb.cli eval shard-run --shard-index 2 --shard-count 4 --output tmp/shard_2.json
python -m enterprise_agent_kb.cli eval shard-run --shard-index 3 --shard-count 4 --output tmp/shard_3.json
# Merge:
python -m enterprise_agent_kb.cli eval merge-shards --input tmp/shard_0.json --input tmp/shard_1.json --input tmp/shard_2.json --input tmp/shard_3.json --output tmp/golden104_merged.json
```

## 6. Boundary compliance

- No metric change (token_overlap scoring untouched); merge is pure arithmetic.
- No query_api/answer_api main-path rewrite.
- answer_changed_by_ontology remains false (untouched).
- Sharding is deterministic (contiguous slice by question index).

## 7. Status

Implementation complete and tested. A full 4-shard 104-question run is not
executed here because each shard takes ~8-12 min (4 shards ~40-48 min total);
this is an operational artifact, deferred to WP9 acceptance when the merged
104-question baseline is needed for the uplift verification. The mechanism is
verified correct via synthetic fixtures and split-arithmetic checks.
