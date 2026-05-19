# AGENTS

## Development rules

- Keep the data model traceable from `evidence` to `facts` to `wiki`.
- Prefer additive schema changes with migrations instead of destructive resets.
- Preserve quality metadata across every processing stage.
- Build for single-node execution first; do not introduce distributed dependencies prematurely.

## Initial module ownership

- `enterprise_agent_kb.cli`: operator-facing commands
- `enterprise_agent_kb.bootstrap`: workspace initialization
- `enterprise_agent_kb.db`: SQLite connectivity and schema setup
- future packages under `enterprise_agent_kb.*`: ingest, parse, quality, evidence, facts, wiki, retrieval, governance

