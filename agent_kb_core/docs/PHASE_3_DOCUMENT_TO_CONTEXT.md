# Phase 3: Document-to-Context Pipeline

Phase 3 connects the Phase 2 compiler output to the Phase 1 Agent Context Pack contracts.

The new vertical slice is:

```text
plain text
  -> DocumentRecord
  -> EvidenceBlock
  -> SourceUnit
  -> Fact
  -> ContextFact / ContextEvidence
  -> ObjectProjection
  -> RetrievalCard
  -> QueryFrame
  -> AgentContextPack
```

## New entry points

### `compile_text_to_context_pack()`

Compiles one text payload and immediately returns a context pack for one user query.

```python
from pathlib import Path
from agent_kb.domains.loader import load_domain_pack
from agent_kb.pipeline import compile_text_to_context_pack

pack = load_domain_pack(Path("domains/obc_dcdc"))
result = compile_text_to_context_pack(
    "DCDC 输出纹波在额定负载下应不大于 30mVpp。",
    query="输出纹波要求是多少？",
    title="sample",
    domain_pack=pack,
)

print(result.context_pack.to_dict())
```

### `build_context_pack_from_compilation()`

Reuses an existing `KnowledgeCompilation` and builds a context pack for a query. This lets callers compile once and answer many queries.

```python
from agent_kb.core.compiler import compile_text_document
from agent_kb.pipeline import build_context_pack_from_compilation

compilation = compile_text_document(text, title="sample", domain_pack=pack)
result = build_context_pack_from_compilation("LV ripple limit?", compilation, domain_pack=pack)
```

### `build_compiled_knowledge_index()`

Builds an in-memory context-ready index from a `KnowledgeCompilation`:

- `ContextFact`
- `ContextEvidence`
- `ObjectProjection`
- `RetrievalCard`

This is not a production database or vector index. It is a deterministic Phase 3 bridge.

## CLI

```bash
cd agent_kb_core
agent-kb compile-context \
  --text-file ./sample.txt \
  --query "输出纹波要求是多少？" \
  --domain-dir ./domains/obc_dcdc
```

For counts only:

```bash
agent-kb compile-context \
  --text-file ./sample.txt \
  --query "输出纹波要求是多少？" \
  --domain-dir ./domains/obc_dcdc \
  --summary-only
```

## Boundary

Phase 3 intentionally stays in-memory and deterministic:

- no vector store
- no database persistence
- no LLM query parser
- no final answer generation
- no requirement resolver
- no RBAC/release gate/ECO logic

Those remain later phases or plugins.

## Why this matters

The system now has a complete skeleton from source text to Agent Context Pack. This validates the target architecture before migrating heavier legacy components.
