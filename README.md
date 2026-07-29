# KB-Ontology

Ontology-driven agent knowledge backend.

See [CONTEXT.md](CONTEXT.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Install

```bash
pip install -e ".[dev]"
```

## LLM setup

Default provider is **krill** with model **`grok-4.5`** (OpenAI-compatible
`/v1/chat/completions`).

```bash
cp .env.example .env
# set AGENT_KB_LLM_API_KEY to the krill key
```

| Variable | Purpose | Default for krill |
|----------|---------|-------------------|
| `AGENT_KB_LLM_ENDPOINT` | API base (include `/v1`) | `https://api.cdn-krill-ai.com/v1` |
| `AGENT_KB_LLM_MODEL` | Model id | `grok-4.5` |
| `AGENT_KB_LLM_API_KEY` | Bearer token | _(required for extract / LLM modes)_ |
| `AGENT_KB_LLM_API_FORMAT` | `openai` \| `anthropic` | `openai` (auto-detected for krill) |
| `AGENT_KB_LLM_TIMEOUT` | Seconds | `120` |

```python
from kb_ontology.llm import LLMChatClient
client = LLMChatClient.from_environment()  # reads .env / process env
```

## Query pipeline (library)

```python
from kb_ontology import answer_query
from kb_ontology.storage import OntologyStore
from kb_ontology.domains import load_domain_pack

pack = load_domain_pack("domains/obc_dcdc")
with OntologyStore("ontology.db") as store:
    ctx = answer_query(store, "DC-DC转换器包含哪些？", domain_pack=pack)
    print(ctx.recommended_answer_strategy, ctx.to_dict())
```

## HTTP API

**Trusted (local / embedded, no auth):**

```bash
kb-ontology serve --db ontology.db --domain-dir domains/obc_dcdc --port 8080
```

| Method | Path | Body | Notes |
|--------|------|------|-------|
| GET | `/v1/health` | — | store stats |
| GET | `/v1/metrics` | — | counters / timings |
| GET | `/v1/openapi.json` | — | OpenAPI 3 stub |
| POST | `/v1/query` | `{"query":"…"}` | → ContextPack |
| POST | `/v1/extract` | `{"text":"…","document_id":"…"}` | needs LLM env |

**Secure (API key + RBAC + per-tenant DB):**

```bash
export KB_ONTOLOGY_API_KEYS='{"my-long-api-key-01":{"principal_id":"ops","tenant_id":"default","roles":["admin"]}}'
kb-ontology secure-serve --tenant-db-root ./data/tenants --domain-dir domains/obc_dcdc --port 8080
# Authorization: Bearer my-long-api-key-01
```

Roles: `reader` (health/query/metrics), `contributor` (+ extract), `admin` (`*`).

## CLI

```bash
kb-ontology health --db ontology.db --domain-dir domains/obc_dcdc
kb-ontology query --db ontology.db --domain-dir domains/obc_dcdc --text 'DC-DC转换器包含哪些？'
kb-ontology extract --db ontology.db --domain-dir domains/obc_dcdc --file doc.md --document-id DOC-1
kb-ontology extract-batch --db ontology.db --domain-dir domains/obc_dcdc --path ./docs_clean --max-files 20
kb-ontology jobs --db ontology.db
kb-ontology worker-once --db ontology.db --domain-dir domains/obc_dcdc
kb-ontology worker-run --db ontology.db --domain-dir domains/obc_dcdc --max-jobs 20
kb-ontology mcp --db ontology.db --domain-dir domains/obc_dcdc   # stdio JSON-RPC
```

Job queue file defaults to `<db>.jobs` (SQLite).

### Athena sample ingest

Curated OBC/DCDC markdown under Athena `raw/` → job queue → LLM extract.

```bash
# 1) enqueue only (idempotent via extract:{document_id})
PYTHONPATH=src python3 scripts/ingest_athena_sample.py \
  --db /tmp/kb_ontology_athena.db \
  --domain-dir domains/obc_dcdc \
  --max-files 12 \
  --min-bytes 400 \
  --enqueue-only

# 2) drain queue (needs AGENT_KB_LLM_*)
PYTHONPATH=src python3 scripts/ingest_athena_sample.py \
  --db /tmp/kb_ontology_athena.db \
  --domain-dir domains/obc_dcdc \
  --worker-only --max-jobs 12

# 3) smoke query against the store
kb-ontology query --db /tmp/kb_ontology_athena.db \
  --domain-dir domains/obc_dcdc --text '慢充系统的工作原理'
```

Filters: default `--min-bytes 400`, hard `SKIP_RELATIVE_PATHS` for stub/corrupt
pages, and a low-CJK noise heuristic. Prefer re-running with higher
`--max-tokens` on docs that succeed with 0 entities.

Live sample store (2026-07-26): **251** entities / **851** attributes /
**376** relations / **1120** evidence after curated core + wave-2 G5 strategy
docs (19 extract jobs succeeded).

## MCP tools

| Tool | Maps to |
|------|---------|
| `kb_ontology_health` | store health |
| `kb_ontology_query` | ContextPack |
| `kb_ontology_extract` | LLM extract into store |
| `kb_ontology_metrics` | in-process metrics |

## Deploy

- `Dockerfile` — multi-stage image, non-root user, console script `kb-ontology`
- `deploy/docker-compose.yml` — secure-serve + volume + healthcheck
- `deploy/kubernetes/deployment.yaml` — Deployment + Service skeleton

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## Tests

```bash
pytest
```
