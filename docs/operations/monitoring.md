# KB1 Monitoring & Alerting Guide

**Audience**: SREs and operators running KB1 in production.
**Scope**: Metrics to track, alert thresholds, dashboards, on-call runbook.

## 1. Key Metrics

### 1.1 Quality Metrics (most important)

| Metric | Source | Target | Alert if |
|---|---|---|---|
| **Eval pass rate (token)** | `run_suite("golden")` | ≥ 0.40 | < 0.30 for 24h |
| **Eval pass rate (LLM)** | `EVAL_USE_LLM=1 run_suite` | ≥ 0.15 | < 0.10 for 24h |
| **Coverage (token)** | same | ≥ 0.30 | < 0.20 for 24h |
| **Coverage (LLM)** | same | ≥ 0.10 | < 0.05 for 24h |
| **Multi-prompt stability** | same | = 1.00 | < 0.95 for 24h |
| **Latest eval report exists** | `scripts/check_health.py` | yes | missing > 7 days |

### 1.2 Performance Metrics

| Metric | Source | Target | Alert if |
|---|---|---|---|
| **API p50 latency** | API server metrics | < 10s | > 20s |
| **API p95 latency** | API server metrics | < 30s | > 60s |
| **API p99 latency** | API server metrics | < 60s | > 120s |
| **API error rate** | API server metrics | < 1% | > 5% |
| **LLM API latency** | LLM provider metrics | < 15s | > 30s |
| **LLM API error rate** | LLM provider metrics | < 5% | > 15% |

### 1.3 Capacity Metrics

| Metric | Source | Target | Alert if |
|---|---|---|---|
| **DB size** | `du -h knowledge_base/db/knowledge.db` | < 1 GB | > 2 GB |
| **Evidence count per doc** | DB query | ≥ 5 | < 1 |
| **Fact count per doc** | DB query | ≥ 10 | < 5 |
| **Total active docs** | DB query | stable | Δ > 20% week-over-week |
| **FTS index rows** | DB query | > 0 | = 0 |
| **Disk free** | `df -h` | > 20% | < 10% |

### 1.4 Operational Metrics

| Metric | Source | Target | Alert if |
|---|---|---|---|
| **Health check pass** | `scripts/check_health.py` | 100% | any check fails |
| **CI eval gate** | `.github/workflows/tests.yml` | passes | fails 2 runs in a row |
| **Unit test pass** | `pytest` | 100% | any failure |
| **Build duration** | compile pipeline | < 10 min/doc | > 30 min/doc |

## 2. Alert Thresholds

### Critical (page on-call immediately)
- Eval pass rate drops to 0% (system broken)
- Health check fails
- DB corruption (e.g., `sqlite3.OperationalError`)
- LLM API error rate > 50%
- Disk free < 5%

### High (alert within 1h)
- Eval pass rate drops > 0.20
- API p95 > 60s
- FTS index empty
- Health check intermittent failures

### Medium (alert during business hours)
- Eval pass rate drops > 0.10
- API p95 > 30s
- DB size growing fast (> 100 MB/day)
- New docs without expected_points

### Low (weekly review)
- Coverage drops > 0.05
- Single eval check fails
- Build duration > 1.5x baseline

## 3. Dashboards

### Recommended dashboard panels

1. **Eval pass rate (token vs LLM)**: time series over the last 30 days
2. **API latency heatmap**: p50/p95/p99 by hour
3. **DB size & growth**: daily snapshot
4. **Health check status**: green/yellow/red indicator
5. **Latest eval report timestamp**: gauge showing days since last run
6. **Fact/evidence counts per doc**: bar chart, last 7 days

### Example PromQL (if using Prometheus)

```promql
# Eval pass rate
kb1_eval_pass_rate{scorer="token_overlap"}

# API p95 latency
histogram_quantile(0.95, kb1_api_latency_seconds_bucket)

# DB size
kb1_db_size_bytes / 1024 / 1024   # in MB

# Health check
kb1_health_check_passed
```

## 4. On-Call Runbook

### Scenario 1: Eval pass rate drops to 0%

**Likely cause**: Schema migration or FTS index corruption

**Steps**:
1. Check `scripts/check_health.py` output
2. If FTS empty: run `python -m enterprise_agent_kb.derived_state_rebuild`
3. If facts empty: check `expected_points` table, re-run `build_expected_points.py`
4. Re-run `python scripts/run_eval_suite.py`
5. If still 0%: revert last commit, check git log

### Scenario 2: API latency p95 > 60s

**Likely cause**: LLM API slow or KB too large for query

**Steps**:
1. Check LLM API status
2. Run `query_api.build_query_context` manually with the failing query
3. If specific query is slow, consider adding to a "slow queries" list and precomputing
4. If general slowdown, check DB indices: `ANALYZE` on facts_fts
5. Increase `API_TIMEOUT_MS` if only edge case

### Scenario 3: New doc added but not in eval

**Likely cause**: `expected_points` not regenerated for new doc

**Steps**:
1. `python tools/build_expected_points.py --version v1 --doc-id DOC-XXX`
2. `python scripts/run_eval_suite.py` to verify regression
3. If regression, check the new doc's facts and evidence

### Scenario 4: LLM API changes model name

**Likely cause**: Provider deprecated the model

**Steps**:
1. Check `ANTHROPIC_BASE_URL` and `LLM_MODEL` env vars
2. Test with `curl $ANTHROPIC_BASE_URL/v1/messages ...` directly
3. Update `LLM_MODEL` env var
4. Re-run `EVAL_USE_LLM=1 python scripts/run_eval_suite.py`

### Scenario 5: Health check fails on "expected_points_populated"

**Likely cause**: Migration applied but `build_expected_points.py` not run

**Steps**:
1. `python tools/build_expected_points.py --version v1`
2. Verify: `sqlite3 knowledge_base/db/knowledge.db "SELECT COUNT(*) FROM expected_points;"`
3. Re-run `scripts/check_health.py`

## 5. Scheduled Tasks

### Daily (cron)
```cron
# Run eval suite and health check
0 2 * * * cd /opt/kb1 && python scripts/run_eval_suite.py --max-questions 30 > /var/log/kb1/eval.log 2>&1
0 3 * * * cd /opt/kb1 && python scripts/check_health.py > /var/log/kb1/health.log 2>&1
```

### Weekly
```cron
# Run full eval (slower)
0 4 * * 0 cd /opt/kb1 && python scripts/run_eval_suite.py > /var/log/kb1/eval-full.log 2>&1
# Backup DB
0 5 * * 0 cd /opt/kb1 && cp -r knowledge_base/db/ backups/db-$(date +\%Y\%m\%d)/
```

## 6. Integration with Existing Tools

### Prometheus
- `kb1_eval_pass_rate{scorer="..."}` from cron output
- `kb1_db_size_bytes` from `du -b knowledge_base/db/knowledge.db`

### Grafana
- Import the dashboard template (see `docs/operations/dashboards/`)
- Add data source: Prometheus or scripted JSON
- Alert rules in `docs/operations/alerts/`

### Slack/PagerDuty
- Webhook from CI on `eval-suite` failure
- `scripts/check_health.py` exit 1 → alert

## 7. Capacity Planning

| Trigger | Action |
|---|---|
| DB size > 1 GB | Consider archiving old docs, splitting DB |
| Fact count > 100K | Add FTS index on term weight, partition tables |
| API QPS > 100 | Add caching layer (Redis) for hot queries |
| Doc count > 100 | Consider per-doc embedding precompute |

## 8. Compliance and Audit

- All queries are logged (enable query_audit.log in production)
- All eval reports versioned under `knowledge_base/eval_runs/`
- All health check runs logged
- DB backups retained for 30 days
- Access logs to KB DB retained for 90 days (compliance)

## 9. Related Documents

- [deployment.md](deployment.md) — How to install and run KB1
- [docs/dev/api-cli-development-guide.md](../dev/api-cli-development-guide.md) — API/CLI internals
- [docs/dev/derived-state-governance-development-guide.md](../dev/derived-state-governance-development-guide.md) — FTS/state maintenance
- `knowledge_base/eval_runs/` — All historical eval reports
