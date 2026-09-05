# Phase 4 — Multi-channel Retrieval and Golden Evaluation

Phase 4 replaces direct list filtering with a reproducible retrieval subsystem.

## Runtime flow

```text
User Query
  -> QueryFrame
  -> requested retrieval channels
  -> channel candidate generation
  -> weighted reciprocal-rank fusion
  -> intent/evidence-shape boosts
  -> RetrievalResult
  -> retrieved object/card/fact/evidence subset
  -> AgentContextPack
```

## Implemented channels

- `object_card`: canonical object ids, names, aliases, answer shapes, related indexed text
- `fact`: subject, predicate, fact type, value, qualifiers
- `table`: `table_row` facts and table-like evidence
- `evidence`: source evidence snippets
- `keyword`: combined card and evidence lexical search
- `semantic`: dependency-free domain-alias semantic fallback

`graph`, `wiki_chunk`, `source_unit`, and `document` are explicitly reported as skipped until those surfaces are materialized in the new index. They are not silently treated as successful channels.

## Fusion

Each channel produces ranked candidates. The engine applies weighted reciprocal-rank fusion and bounded channel relevance. It then applies small deterministic boosts for:

- exact target-object matches
- preferred fact/evidence shapes from the selected answer contract
- answer-shape compatibility

The output preserves matched terms, reasons, source type, source id, channel provenance, and diagnostic counts.

## Retrieval result

```json
{
  "selected_object_ids": ["DCDC_OUTPUT_RIPPLE"],
  "selected_card_ids": ["card:obc_dcdc:DCDC_OUTPUT_RIPPLE"],
  "selected_fact_ids": ["fact_..."],
  "selected_evidence_ids": ["evd_..."],
  "diagnostics": {
    "requested_channels": ["object_card", "fact", "table", "graph", "evidence"],
    "executed_channels": ["object_card", "fact", "table", "evidence"],
    "skipped_channels": {
      "graph": "channel_not_materialized_in_phase4_index"
    }
  }
}
```

## Golden evaluation

`agent_kb.evaluation.evaluate_retrieval()` evaluates QueryFrame understanding and retrieval together.

Supported metrics:

- Hit@K
- Mean Reciprocal Rank
- object recall
- retrieval-card recall
- fact recall
- evidence recall

Example golden case:

```json
[
  {
    "case_id": "ripple-constraint",
    "query": "LV ripple limit?",
    "expected_object_ids": ["DCDC_OUTPUT_RIPPLE"],
    "expected_fact_ids": ["fact_..."],
    "expected_evidence_ids": ["evd_..."],
    "top_k": 6
  }
]
```

CLI:

```bash
agent-kb eval-retrieval \
  --text-file ./sample.txt \
  --cases-file ./golden_cases.json \
  --domain-dir ./domains/obc_dcdc
```

## Deliberate boundary

Phase 4 does not claim embedding-based semantic retrieval. The current semantic channel is a deterministic domain-object/alias fallback. Vector providers and cross-encoder or LLM rerankers can be added behind the same retrieval contracts in a later phase without changing Context Pack consumers.
