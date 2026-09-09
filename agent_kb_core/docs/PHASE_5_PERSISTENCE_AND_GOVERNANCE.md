# Phase 5: Persistence, Hybrid Retrieval, Evidence Judging, and Feedback

## Goal

Phase 5 moves Agent KB Core from a reusable in-memory compiler to a persistent, inspectable, and governable retrieval runtime.

```text
Document compilation
  -> CompiledKnowledgeIndex
  -> SQLiteKnowledgeStore
  -> relational retrieval surfaces + optional FTS5
  -> hybrid retrieval
  -> deterministic reranking
  -> AgentContextPack
  -> evidence sufficiency judgement
  -> retrieval run audit + explicit feedback
```

## Persistent schema

The SQLite adapter stores the following authoritative entities:

- `object_projections`
- `retrieval_cards`
- `facts`
- `evidence`
- `retrieval_runs`
- `feedback`

`search_documents` and `search_fts` are derived recall surfaces. The relational tables remain the source of truth. If SQLite was built without FTS5, the adapter falls back to deterministic `LIKE` search.

## Hybrid retrieval

`hybrid_retrieve()` combines:

1. Phase 4 in-memory multi-channel retrieval.
2. SQLite FTS/LIKE persistent candidates.
3. Cross-index corroboration.
4. A deterministic intent-aware reranker.

The reranker is a stable baseline and implements the same contract intended for future cross-encoder or LLM rerankers.

## Evidence sufficiency

`judge_context_pack()` evaluates:

- required evidence shapes for the detected intent;
- whether source evidence was selected;
- whether selected facts are bound to selected evidence;
- whether a target object is available;
- unresolved slots and domain ambiguity.

It returns one of:

- `sufficient`
- `partial`
- `insufficient`

The persistent query pipeline converts partial or insufficient judgements into warnings, knowledge gaps, and a more conservative answer strategy.

## CLI

Index a text file:

```bash
agent-kb index-text \
  --text-file ./sample.txt \
  --db ./agent-kb.sqlite3 \
  --domain-dir ./domains/obc_dcdc
```

Query the persistent store:

```bash
agent-kb query-store \
  --db ./agent-kb.sqlite3 \
  --query "输出纹波要求是多少？" \
  --domain-dir ./domains/obc_dcdc
```

Attach feedback to the returned `run_id`:

```bash
agent-kb feedback \
  --db ./agent-kb.sqlite3 \
  --run-id run_xxx \
  --rating 1 \
  --comment "retrieval is relevant"
```

## Current boundary

Phase 5 intentionally does not introduce external infrastructure. Later adapters can add:

- production database migrations and connection pooling;
- embedding providers and vector indexes;
- cross-encoder or LLM rerankers;
- graph persistence and traversal;
- multi-document versioning and deletion semantics;
- automated feedback-driven tuning.
