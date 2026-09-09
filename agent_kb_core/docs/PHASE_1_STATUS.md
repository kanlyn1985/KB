# Phase 1 Status

Branch: `rebuild/agent-kb-core`

PR: `#1 Rebuild Agent KB Core skeleton`

## Implemented

Phase 1 now has a concrete deterministic end-to-end context path:

```text
DomainPack
  -> QueryFrame
  -> ObjectProjection
  -> RetrievalCard
  -> AgentContextPack
```

Added modules:

- `agent_kb.query.understanding`
  - deterministic domain-aware query understanding
  - intent detection
  - target object linking from domain terminology
  - missing slot detection
  - answer contract selection
  - retrieval channel planning

- `agent_kb.projection.projector`
  - terminology-to-object projection
  - evidence candidate projection helper
  - object alias index helper

- `agent_kb.retrieval.card_builder`
  - object-centered retrieval card construction
  - alias/fact/evidence aggregation surface

- `agent_kb.context.builder`
  - AgentContextPack assembly
  - hidden context injection
  - warning and knowledge gap generation

- `tests/test_query_context_flow.py`
  - verifies alias linking
  - verifies constraint missing slots
  - verifies hidden context injection and retrieval card selection

## Still not implemented

The rebuild is not yet connected to the old KB runtime. The following remain next-phase work:

1. Register/parse/evidence ingestion migration.
2. SourceUnit and fact extraction migration.
3. Existing LLM query semantic parser migration behind QueryFrame.
4. Retrieval router/reranker/evidence judge migration.
5. SQLite schema and persistence for object projections, retrieval cards, and context packs.
6. CLI/API entrypoints for `context-pack`.
7. CI validation for `agent_kb_core`.

## Local validation command

```bash
cd agent_kb_core
python -m pytest
```

Testing has not been executed in this environment.
