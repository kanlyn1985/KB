# Agent KB Core

通用证据约束型智能体知识库编译框架。

```text
Documents
  -> Evidence
  -> Semantic Units
  -> Facts / Entities / Relations
  -> Object Projections
  -> Retrieval Cards
  -> QueryFrame-aware retrieval
  -> Agent Context Packs
```

## 定位

```text
Generic Evidence-grounded Agent Knowledge Compiler
```

目标不是继续扩展旧的汽车或需求治理单体，而是建立一个可复用的通用核心。OBC/DCDC 仅作为验证 Domain Pack，不属于 Core 的硬编码业务模型。

## 核心原则

1. **Core 不绑定领域**：领域术语、对象、关系、回答契约和规则位于 `domains/<domain>/`。
2. **Evidence-first**：结构化事实、对象和关系必须可回溯到原文证据。
3. **Object-centered retrieval**：召回对象、别名、关系和 Retrieval Card，而不只召回文本 chunk。
4. **Context Pack for Agent**：主要输出是结构化智能体上下文，而非不可审计的最终文本。
5. **Measurable retrieval**：召回升级必须通过 golden cases、反馈和图谱指标验证。
6. **Replaceable adapters**：embedding、vector、graph、service、storage 和 transport 可替换，但不得破坏核心契约。
7. **Explicit tenant boundaries**：当前嵌入式部署采用每租户独立 SQLite 数据库。
8. **Operational truthfulness**：基线适配器和生产托管服务必须明确区分，不把 hash embedding 或 SQLite scan 描述为学习型模型或大规模向量数据库。

## 能力演进

### Phase 1–3：知识编译骨架

```text
plain text
  -> DocumentRecord
  -> EvidenceBlock
  -> SourceUnit
  -> Fact
  -> ObjectProjection
  -> RetrievalCard
  -> QueryFrame
  -> AgentContextPack
```

包括 Domain Pack loader、QueryFrame、ObjectProjection、RetrievalCard、Answer Contract 和 Context Pack 契约。

### Phase 4：多路召回与评测

```text
QueryFrame
  -> object / card / fact / table / evidence channels
  -> weighted reciprocal-rank fusion
  -> intent and evidence-shape boosts
  -> RetrievalResult
```

包括 Hit@K、MRR、object/card/fact/evidence recall、召回诊断和 golden-case evaluation。

### Phase 5：持久化与证据治理

```text
CompiledKnowledgeIndex
  -> SQLite
  -> FTS5 / LIKE fallback
  -> hybrid retrieval
  -> reranker
  -> evidence sufficiency judgement
  -> retrieval audit / feedback
```

### Phase 6：生产适配层

- provider-neutral `EmbeddingProvider`
- deterministic `HashEmbeddingProvider`
- `SQLiteVectorIndex`
- `SQLiteGraphStore`
- `ProductionCandidateProvider`
- 单调 schema migration
- logical document/version lifecycle
- production index/query pipeline
- versioned JSON service

`HashEmbeddingProvider` 和 SQLite cosine scan 是无外部依赖的契约验证基线。

### Phase 7：生产硬化

- `RemoteJSONEmbeddingProvider`
- `ExternalVectorBackend`、HTTP adapter 和内存验证后端
- 显式关系抽取及 graph precision/recall/F1
- API-key authentication、RBAC、物理租户隔离
- token-bucket rate limiting
- 持久化安全审计
- 后台任务、租约和重试
- SQLite 在线备份、SHA-256 和完整性检查
- 事务化文档及派生索引清理
- OpenAPI 3.1 和 MCP-compatible tool adapter

### Phase 8：部署级可靠性

```text
Client / MCP host
  -> TLS or mTLS
  -> rotating secrets
  -> authentication / RBAC / tenant binding
  -> local or SQLite-coordinated rate limiting
  -> idempotent jobs / worker registry
  -> lexical + learned embedding + Qdrant + graph retrieval
  -> Context Pack
  -> audit + metrics + OTLP traces
```

Phase 8 已加入：

- 环境变量、JSON 文件、HTTP 和组合式 Secret Provider
- 无需重启的 API-key 轮换
- SQLite 跨进程固定窗口限流基线
- worker heartbeat、capability 和 lease registry
- tenant-aware、job-type-aware、idempotent background jobs
- 原生 TLS 和可选 mTLS
- `QdrantVectorBackend`
- 直接清理和 retention 清理时的外部向量同步删除
- MCP JSON-RPC stdio transport
- dependency-free Python client generator
- trace span 和最小 OTLP/HTTP JSON exporter
- telemetry failure isolation
- backup replication、pruning 和 isolated recovery drill
- retention planning、legal hold 和 retention-run audit
- load、chaos 和 security validation harness

详细设计：

```text
docs/PHASE_8_DEPLOYMENT_RELIABILITY.md
docs/PHASE_8_STATUS.md
```

## Package 与 Schema

```text
package version: 0.4.0
schema version: 8
```

```text
1 document lifecycle
2 vector index
3 graph index
4 jobs / audit / backup history
5 graph extraction governance
6 distributed rate limits / worker heartbeats
7 legal holds / retention runs
8 job idempotency / backup replication records
```

## CLI

### 文档编译与召回

```bash
agent-kb compile-context \
  --text-file ./sample.txt \
  --query "输出纹波要求是多少？" \
  --domain-dir ./domains/obc_dcdc \
  --retrieval-top-k 12

agent-kb index-production \
  --text-file ./sample.txt \
  --db ./agent-kb.sqlite3 \
  --domain-dir ./domains/obc_dcdc \
  --logical-document-id ldoc_ripple \
  --version-label v1

agent-kb query-production \
  --db ./agent-kb.sqlite3 \
  --query "输出纹波要求是多少？" \
  --domain-dir ./domains/obc_dcdc
```

### Idempotent job 和 worker

```bash
agent-kb queue-index \
  --db ./agent-kb.sqlite3 \
  --text-file ./sample.txt \
  --tenant-id tenant-a \
  --idempotency-key import-2026-07-18-ripple

agent-kb worker-once \
  --db ./agent-kb.sqlite3 \
  --domain-dir ./domains/obc_dcdc \
  --tenant-id tenant-a \
  --worker-id worker-a
```

### Legal hold 和 retention

```bash
agent-kb legal-hold \
  --db ./agent-kb.sqlite3 \
  --tenant-id tenant-a \
  --logical-document-id ldoc_ripple \
  --reason "litigation"

agent-kb retention \
  --db ./agent-kb.sqlite3 \
  --tenant-id tenant-a \
  --retain-days 365

agent-kb retention \
  --db ./agent-kb.sqlite3 \
  --tenant-id tenant-a \
  --retain-days 365 \
  --execute
```

### Backup、复制、保留和恢复演练

```bash
agent-kb backup \
  --db ./agent-kb.sqlite3 \
  --backup-dir ./backups \
  --replica-dir ./backup-replica \
  --keep-last 10 \
  --keep-days 90

agent-kb-recovery \
  --backup ./backups/tenant-a-backup_x.sqlite3
```

恢复演练在隔离目录中还原数据库，检查 SQLite integrity、required tables、table counts 和 schema version，不修改在线数据库。

### OpenAPI、客户端和 MCP

```bash
agent-kb openapi --output ./openapi.json
agent-kb generate-client --output ./agent_kb_client.py
agent-kb mcp-stdio --db ./agent-kb.sqlite3
```

## Secure deployment

### 环境变量 API-key 映射

```bash
export AGENT_KB_API_KEYS='{
  "replace-with-a-long-random-token": {
    "principal_id": "operator-1",
    "tenant_id": "tenant-a",
    "roles": ["admin"]
  }
}'
```

### TLS + Qdrant + OTLP

```bash
export AGENT_KB_EMBEDDING_URL='https://embedding.example/v1/embeddings'
export AGENT_KB_EMBEDDING_MODEL='enterprise-embedding-model'
export AGENT_KB_EMBEDDING_DIMENSIONS='1024'
export AGENT_KB_EMBEDDING_API_KEY='...'
export QDRANT_API_KEY='...'
export OTEL_EXPORTER_OTLP_ENDPOINT='https://otel-collector.example:4318'

agent-kb secure-serve \
  --tenant-db-root ./tenants \
  --backup-root ./backups \
  --backup-replica-dir ./backup-replica \
  --domain-dir ./domains/obc_dcdc \
  --remote-embedding \
  --qdrant-url https://qdrant.example \
  --qdrant-collection agent-kb \
  --distributed-rate-limit \
  --otlp \
  --tls-cert ./certs/server.crt \
  --tls-key ./certs/server.key \
  --tls-ca ./certs/clients-ca.crt \
  --require-client-cert \
  --host 0.0.0.0 \
  --port 8443
```

目标 Qdrant collection 必须预先创建，并与 embedding dimensions 匹配。

### Hardened endpoints

```text
GET  /v1/health
GET  /v1/documents
GET  /v1/jobs/{job_id}
GET  /v1/metrics
GET  /v1/audit
GET  /v1/openapi.json
GET  /v1/admin/workers
POST /v1/index
POST /v1/query
POST /v1/feedback
POST /v1/jobs/index
POST /v1/admin/worker-once
POST /v1/admin/backup
POST /v1/admin/purge
POST /v1/admin/legal-holds
POST /v1/admin/legal-holds/release
POST /v1/admin/retention
```

请求头：

```text
Authorization: Bearer <api-key>
X-Tenant-ID: tenant-a
```

## 目录

```text
agent_kb_core/
  docs/
  domains/
  src/agent_kb/
    adapters/
    context/
    core/
    domains/
    embeddings/
    evaluation/
    graph/
    observability/
    pipeline/
    projection/
    query/
    retrieval/
    runtime/
    security/
    service/
    storage/
    testing/
  tests/
```

## 验证

```bash
cd agent_kb_core
python -m pytest
```

GitHub Actions 在 Python 3.11、3.12 和 3.13 上执行 editable install、`compileall` 和完整测试。

## 边界

Phase 8 是部署可靠性基线，不等同于无限水平扩展：

- SQLite coordination 不是 Redis 或分布式事务协调器；
- Qdrant collection provisioning 属于部署职责；
- OTLP exporter 是最小依赖实现，不是完整 OpenTelemetry SDK；
- MCP transport 当前为 stdio JSON-RPC；
- HTTP backup replication 会把备份载入内存；
- 证书签发、续期、信任治理和企业级 legal-hold 授权仍需接入组织基础设施。

## 下一步

Phase 9 聚焦平台化部署和持续运营：

```text
container / Kubernetes deployment
  + Redis and production queue adapters
  + Vault / cloud secret-manager implementations
  + managed Qdrant provisioning
  + OpenTelemetry SDK and context propagation
  + continuous worker and scheduler services
  + SLO dashboards and alerting
  + SBOM / dependency / security gates
  + staging recovery drills
  + enterprise policy integration
```

所有后续适配器必须继续输出既有 `RetrievalResult` 和 `AgentContextPack`，并通过统一的 golden、graph、feedback 和 reliability evaluation contracts 验证。
