# Development Roadmap

## Goal

Build a single-node, evidence-first enterprise knowledge base that compiles raw documents into traceable evidence, facts, wiki pages, and retrieval assets.

## Phase 0: foundation

Deliverables:

- Python package and CLI
- canonical directory layout
- SQLite schema
- local bootstrap flow

Exit criteria:

- a developer can create a fresh workspace with one command
- the database contains all baseline tables

## Phase 1: ingest

Deliverables:

- document registration service
- SHA-256 hashing and duplicate detection
- source type and MIME classification
- initial job enqueue

Primary tables:

- `documents`
- `jobs`

Exit criteria:

- a local file can be registered into the system with a stable `doc_id`
- duplicate files are detected deterministically

## Phase 2: parse

Deliverables:

- PDF parser pipeline
- OCR integration for scanned pages
- normalized page and block output
- screenshot generation hooks

Primary tables:

- `pages`
- `blocks`

Exit criteria:

- one PDF can be parsed into pages and ordered blocks
- each block has page anchor and bounding box metadata

## Phase 3: quality gate

Deliverables:

- page risk heuristics
- OCR and layout quality scoring
- review queue generation
- quality report materialization

Primary tables:

- `quality_reports`
- review queue files

Exit criteria:

- high-risk and low-confidence pages are flagged before downstream compilation

## Phase 4: evidence and facts

Deliverables:

- evidence objects from normalized blocks
- entity extraction
- fact extraction
- fact to evidence linkage
- conflict detection baseline

Primary tables:

- `evidence`
- `entities`
- `facts`
- `fact_evidence_map`

Exit criteria:

- every produced fact links to at least one evidence record

## Phase 5: wiki compiler and retrieval

Deliverables:

- entity page generation
- topical and index page generation
- graph edge derivation
- full-text indexing
- query routing baseline

Primary tables:

- `wiki_pages`
- `graph_edges`
- `edge_evidence_map`

Exit criteria:

- a query can retrieve evidence-backed facts and wiki summaries

## Phase 6: governance

Deliverables:

- dependency tracking
- dirty propagation
- selective rebuild jobs
- audit and feedback hooks

Primary tables:

- `dependencies`
- `jobs`

Exit criteria:

- a changed document can trigger partial rebuilds without a full reset

## Immediate next build target

Implement Phase 1 first:

- add a document ID generator
- add file hashing utility
- add `ingest register` CLI command
- persist document metadata into SQLite
- enqueue parse jobs
