# Phase 2: Generic Ingestion Compiler

Phase 2 turns the rebuilt core from static contracts into the first executable compiler slice.

## Scope

This phase implements the domain-neutral path:

```text
Text source
  -> DocumentRecord
  -> EvidenceBlock
  -> SourceUnit
  -> Fact
```

The goal is not to solve every file format. PDF, Word, Excel, OCR, connector records, and database snapshots should all eventually materialize into this same compiler contract.

## New modules

```text
agent_kb.core.documents
agent_kb.core.evidence
agent_kb.core.source_units
agent_kb.core.facts
agent_kb.core.compiler
```

## Contracts

### DocumentRecord

Registered source metadata:

- deterministic document id
- title
- source type
- mime type
- sha256
- size
- source URI
- metadata

### EvidenceBlock

Traceable text block with stable `evidence_id`. Evidence blocks preserve numbers, units, acronyms, and table-like rows.

### SourceUnit

Semantic unit derived from evidence. Current generic unit types:

- `definition`
- `requirement`
- `test_method`
- `test_result`
- `table_like`
- `warning_or_exception`
- `narrative`

### Fact

Evidence-bound fact candidate:

- `term_definition`
- `requirement_constraint`
- `parameter_constraint`
- `test_method`
- `test_result`
- `table_row`
- `risk_or_exception`

Facts remain candidates. Promotion into ontology-lite objects still belongs to the projection/review layer.

## Domain-neutral by design

The compiler works without a domain pack. When a domain pack is supplied, terminology is only used to improve subject linking.

Example:

```text
DCDC 输出纹波在额定负载下应不大于 30mVpp。
```

With the OBC/DCDC validation domain pack, the fact subject can link to:

```text
DCDC_OUTPUT_RIPPLE
```

Without a domain pack, the same text still compiles into a generic requirement fact.

## Validation

Run from the new package root:

```bash
cd agent_kb_core
python -m pytest
```

Phase 2 tests cover:

- evidence block creation
- source unit classification
- generic fact extraction
- domain terminology subject linking
- operation without any domain pack

## Next step

Phase 3 should connect this compiler output to:

```text
Fact / SourceUnit -> ObjectProjection -> RetrievalCard -> AgentContextPack
```

This will produce the first full compile-to-context path.
