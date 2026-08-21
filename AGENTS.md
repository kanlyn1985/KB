# AGENTS

## Repository layout

- `agent_kb_core/` — the active project: the `agent_kb` package, Web UI, and the landing/eval tooling. See `agent_kb_core/README.md`.
- `docs/ontology/` — the RFLP ontology layer: tree skeleton, document-landing data, node cards, golden cases, and query-understanding design.
- `corpus/` — source document corpus (standards PDFs, requirements xlsx/docx, the Athena team corpus).
- `archive/` — superseded work, kept for reference only: the legacy `enterprise_agent_kb` pipeline outputs and the old `kb1_ontology` design.

## Development rules

- Keep the data model traceable from `evidence` to `facts` to ontology nodes.
- Prefer additive schema changes with migrations instead of destructive resets.
- Preserve quality metadata across every processing stage.
- Build for single-node execution first; do not introduce distributed dependencies prematurely.

## Module ownership (package `agent_kb`)

- `agent_kb.cli` / `agent_kb.platform_cli` / `agent_kb.recovery_cli` / `agent_kb.worker_cli`: operator-facing commands
- `agent_kb.core`: document intake, evidence, semantic units, facts
- `agent_kb.domains`: domain pack loading and schema
- `agent_kb.query`: query understanding (rule + LLM hybrid)
- `agent_kb.retrieval`: multi-channel retrieval, fusion, cards, reranking
- `agent_kb.pipeline`: document → context-pack compilation
- `agent_kb.storage`: SQLite connectivity, migrations, backup/recovery
- `agent_kb.service` / `agent_kb.security`: HTTP API, auth/RBAC/audit
- `agent_kb.adapters`: OpenAPI, MCP, client codegen
- `agent_kb.observability` / `agent_kb.runtime`: metrics/telemetry, jobs/leadership/rate limiting
