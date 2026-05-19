# Final Delivery Notes

## Delivered capabilities

- document ingest, dedupe, and workspace bootstrap
- PDF/text parsing with OCR fallback for problematic PDFs
- quality gate with page-level risk state and document-level quality reports
- evidence generation from ready pages
- fact extraction for metadata, section headings, term definitions, concept definitions, and abstracts
- entity generation for documents, standards, and terms
- wiki generation for document, standard, and term pages
- graph edge generation for standard references and term definitions
- retrieval, structured query context, explainable answer, and lightweight multi-hop agent query
- HTTP API server
- MCP stdio server
- browser demo page
- one-click launch scripts
- standalone PDF conversion entrypoints
- build-and-test one-click entrypoints
- workbench user guide

## Verified document types

- standards/specification PDFs
- OCR-degraded standards that require PaddleVL fallback
- article/review PDFs that rely on abstract-based concept extraction
- Markdown/plain-text technical implementation documents

## Test layers

- `unit`: isolated logic checks
- `smoke`: fast end-to-end sanity checks on synthetic local inputs
- `integration`: real local document regressions and database consistency checks
- `benchmark`: query, answer, and agent quality regression checks

## Recommended local commands

Fast tests:

```bash
pytest -q
```

Benchmark tests:

```bash
pytest -q -m benchmark
```

Integration tests:

```bash
pytest -q -m integration
```

Demo:

```powershell
.\launch.ps1
```

Workbench guide:

```text
docs/workbench_user_guide_2026-04-20.md
```

Quickstart:

```text
docs/delivery_quickstart_2026-04-20.md
```

## Known limitations

- Some standard PDFs still require document-specific cover prioritization to make all metadata facts perfect.
- Retrieval is still rule-heavy and synonym-driven rather than fully semantic.
- Article-style documents currently extract concept definitions from abstracts, but broader concept graphing remains shallow.
- The demo and API are local-first and do not include authentication, persistence isolation, or production hardening.

## Workspace hygiene

The repository ignores transient runtime/test directories such as:

- `.pytest-tmp/`
- `.pytest_cache/`
- `eakb_test_*/`
- `test_runtime_*/`

If these directories already exist locally from previous runs, they can be removed manually without affecting project state.
