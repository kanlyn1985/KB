# Phase 2 Status

## Completed in this phase

Phase 2 adds the first executable ingestion compiler slice.

Implemented:

```text
DocumentRecord
EvidenceBlock
SourceUnit
Fact
KnowledgeCompilation
compile_text_document()
```

The current compiler path is:

```text
plain text
  -> register_text_document()
  -> build_evidence_blocks()
  -> build_source_units()
  -> extract_facts()
  -> KnowledgeCompilation
```

## What this proves

The rebuilt project is no longer only schemas and architecture documents. It can now take source text and compile it into evidence-bound knowledge candidates.

It also proves the domain-neutral design:

- with no domain pack, generic facts are still extracted
- with a domain pack, terminology improves subject linking
- no OBC/DCDC logic is hardcoded in the compiler core

## What is deliberately not included

Not included yet:

- PDF/DOCX/XLSX parsers
- OCR
- table cell extraction
- database persistence
- vector embeddings
- LLM extraction
- human review workflow
- object promotion
- end-to-end retrieval from compiled documents

These should be added incrementally after this compiler contract is stable.

## Next phase

Phase 3 should connect:

```text
KnowledgeCompilation
  -> ObjectProjection
  -> RetrievalCard
  -> AgentContextPack
```

That will create the first complete path from source document to agent-ready context.
