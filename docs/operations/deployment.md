# KB1 Deployment Guide

**Audience**: Operators deploying KB1 to production environments.
**Scope**: End-to-end deployment from a fresh checkout to a running system.

## 1. Prerequisites

- **Python**: 3.12+ (tested with 3.12.3)
- **SQLite**: 3.39+ (FTS5 support required; ships with Python)
- **OS**: Linux/macOS/Windows (CI tested on Windows-latest)
- **Disk**: 2 GB minimum (KB data is ~500 MB after build)
- **Optional**: LLM API endpoint (e.g., Xunfei, MiniMax) for `EVAL_USE_LLM=1` mode
- **Optional**: Source PDFs in `knowledge_base/documents/` for first-time build

## 2. Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_BASE_URL` | LLM only | (empty) | LLM endpoint for evaluator + answer generation |
| `ANTHROPIC_AUTH_TOKEN` | LLM only | (empty) | LLM auth token |
| `LLM_MODEL` | No | `xopkimik26` | Model name for LLM calls |
| `EVAL_USE_LLM` | No | `0` | Set to `1` to use LLM scoring |
| `EVAL_MIN_TOKEN_PASS` | CI only | `0.30` | Min token-overlap pass rate for CI gate |
| `EVAL_MIN_LLM_PASS` | CI only | `0.10` | Min LLM pass rate for CI gate |
| `API_TIMEOUT_MS` | No | `600000` | HTTP API timeout |

### Production-required:
- `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` must be set for LLM-based features
- For the system to use LLM answer generation, both must be present and reachable

## 3. Installation

```bash
# 1. Clone the repo
git clone <repo-url> kb1 && cd kb1

# 2. Create virtualenv
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies (editable for development)
pip install -e ".[dev]"

# 4. Verify install
python -c "import enterprise_agent_kb; print('OK')"
```

## 4. First-time Knowledge Base Build

If starting without `knowledge_base/`:

```bash
# 1. Place source PDFs
mkdir -p knowledge_base/documents
cp /path/to/*.pdf knowledge_base/documents/

# 2. Compile (parses PDFs → facts → indices)
python -m enterprise_agent_kb.compile --workspace knowledge_base

# 3. Build expected_points (for evaluator)
python tools/build_expected_points.py --version v1

# 4. Build sample_qa (golden suite)
python tools/build_sample_qa.py --version v1

# 5. Verify
python -m enterprise_agent_kb.evaluation.evaluator run_suite --suite golden
```

## 5. Running the System

### API Server
```bash
# Start the API server (default port 8000)
python -m enterprise_agent_kb.api_server

# Or with custom port
python -m enterprise_agent_kb.api_server --port 8080
```

### CLI
```bash
# Compile a single document
python -m enterprise_agent_kb.cli compile path/to/file.pdf

# Run constraint regression
python scripts/run_constraint_regression.py

# Run evaluation suite
python scripts/run_eval_suite.py
```

### Programmatic
```python
from enterprise_agent_kb.answer_api import answer_query
from pathlib import Path

ans = answer_query(
    workspace_root=Path("knowledge_base"),
    query="什么是汽车电源逆变器?",
    limit=8,
)
print(ans["direct_answer"])
```

## 6. Health Checks

### Built-in health check script
```bash
python scripts/check_health.py
```
Returns exit 0 if healthy, 1 if any check fails. CI-friendly.

### Manual checks
```bash
# 1. DB accessible
sqlite3 knowledge_base/db/knowledge.db "SELECT COUNT(*) FROM facts;"

# 2. Expected points populated
sqlite3 knowledge_base/db/knowledge.db "SELECT doc_id, point_count FROM expected_points WHERE version='v1';"

# 3. Eval suite smoke
python scripts/run_eval_suite.py --max-questions 10

# 4. Unit tests
pytest tests/test_evaluator.py -v
```

## 7. Monitoring (Production)

See `docs/operations/monitoring.md` for details.

Key metrics to track:
- Eval pass rate (alert if < 0.30 token / < 0.10 LLM)
- API response latency (alert if p95 > 30s)
- DB size growth
- Evidence/facts counts per document

## 8. Updating the Knowledge Base

To add new documents after initial build:

```bash
# 1. Add PDF
cp new_doc.pdf knowledge_base/documents/

# 2. Run full pipeline
python -m enterprise_agent_kb.cli compile new_doc.pdf

# 3. Refresh expected_points for new doc
python tools/build_expected_points.py --version v1 --doc-id DOC-000XXX

# 4. Re-run eval to check for regressions
python scripts/run_eval_suite.py
```

## 9. Backup and Recovery

```bash
# Backup
cp -r knowledge_base/db/ backups/db-$(date +%Y%m%d)/
cp -r knowledge_base/facts.db backups/ 2>/dev/null || true

# Restore (from backup)
cp -r backups/db-20260101/* knowledge_base/db/
```

The pipeline supports `_backup_pipeline_database` and `_restore_pipeline_database` in `pipeline.py` for atomic backup/restore during builds.

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `knowledge.db` not found | First-time build not run | `python -m enterprise_agent_kb.compile` |
| Eval pass rate drops to 0% | Schema migration | Check `migrations/` applied, re-run `derived_state_rebuild` |
| FTS query returns no results | Stale FTS index | `python -m enterprise_agent_kb.derived_state_rebuild` |
| LLM scoring returns 0 for all | API key expired | Verify `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` |
| `answer_query` times out (> 60s) | Large doc, slow LLM | Increase `API_TIMEOUT_MS` |

## 11. Security Considerations

- **API tokens**: never commit `ANTHROPIC_AUTH_TOKEN` to source control
- **DB access**: KB contains potentially sensitive source data; restrict file permissions to 600
- **SOCKS proxy**: if behind corporate firewall, configure `httpx` trust_env appropriately (see `evidence_judge.py` for the pattern)
- **Query audit**: log all queries for review; PII may be embedded in user queries

## 12. Versioning

- `v1`, `v2`, ... in `expected_points.version` track schema evolution
- `multi_prompt_stability` in eval reports tracks evaluator reproducibility
- All eval reports are versioned under `knowledge_base/eval_runs/`
