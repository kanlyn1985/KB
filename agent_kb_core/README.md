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

1. **Core 不绑定领域**：术语、对象、关系、回答契约和规则位于 `domains/<domain>/`。
2. **Evidence-first**：结构化事实、对象和关系必须可回溯到原文证据。
3. **Object-centered retrieval**：召回对象、别名、关系和 Retrieval Card，而不只召回文本 chunk。
4. **Context Pack for Agent**：主要输出是结构化智能体上下文，而非不可审计的最终文本。
5. **Measurable retrieval**：召回升级必须通过 golden cases、反馈和图谱指标验证。
6. **Replaceable adapters**：embedding、vector、graph、service、storage 和 transport 可替换，但不得破坏核心契约。
7. **Explicit tenant boundaries**：嵌入式部署采用每租户独立 SQLite 数据库。
8. **Operational truthfulness**：基线适配器和托管服务必须明确区分。

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
- logical document/version lifecycle
- production index/query pipeline
- versioned JSON service

`HashEmbeddingProvider` 和 SQLite cosine scan 是无外部依赖的契约验证基线。

### Phase 7：生产硬化

- `RemoteJSONEmbeddingProvider`
- `ExternalVectorBackend`
- 显式关系抽取及 graph precision/recall/F1
- API-key authentication、RBAC、物理租户隔离
- token-bucket rate limiting
- 持久化安全审计
- 后台任务、租约和重试
- 在线备份和事务化清理
- OpenAPI 3.1 和 MCP-compatible adapter

### Phase 8：部署级可靠性与发布门禁

- rotating Secret Provider
- SQLite 跨进程限流和 worker registry
- tenant-aware、idempotent background jobs
- TLS / mTLS
- Qdrant REST adapter
- MCP JSON-RPC stdio transport
- OTLP-compatible telemetry adapter
- backup replication、pruning 和 isolated recovery drill
- retention、legal hold 和外部向量同步清理
- load、chaos 和 security harness
- `agent-kb-ops readiness`
- GitHub Actions operational evidence gate

### Phase 9 R1：平台部署基线

```text
non-root container
  -> API process
  -> continuous worker process
  -> shared tenant data volume
  -> authenticated probes
  -> backup / recovery / readiness gates
```

已加入：

- package version `0.5.0`
- multi-stage non-root Docker image
- Docker Compose API/worker topology
- Kubernetes one-replica StatefulSet topology
- continuous multi-tenant worker
- SIGTERM/SIGINT graceful shutdown
- worker heartbeat 和 readiness-file lifecycle
- optional SQLite scheduler leader lease
- container、Compose 和 deployment CI gate

详细设计：

```text
docs/PHASE_9_R1_PLATFORM_DEPLOYMENT.md
docs/PHASE_9_R1_STATUS.md
```

## Package 与 Schema

```text
package version: 0.5.0
Core schema version: 8
platform schema version: 9 when leader leases are enabled
```

Core 普通运行保持 schema v8。只有实例化 `SQLiteLeaderLeaseStore` 时才应用可选平台迁移 v9。

## CLI

### 文档编译与查询

```bash
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

### 队列与持续 Worker

```bash
agent-kb queue-index \
  --db ./tenants/default.sqlite3 \
  --text-file ./sample.txt \
  --tenant-id default \
  --idempotency-key import-ripple-v1

agent-kb-worker \
  --tenant-db-root ./tenants \
  --domain-dir ./domains/obc_dcdc \
  --worker-id worker-a \
  --ready-file /tmp/agent-kb-worker.ready
```

### 备份、恢复与 Readiness

```bash
agent-kb backup \
  --db ./agent-kb.sqlite3 \
  --backup-dir ./backups \
  --keep-last 10 \
  --keep-days 90

agent-kb-ops recovery-drill \
  --backup-path ./backups/default-backup_x.sqlite3

agent-kb-ops readiness \
  --db ./agent-kb.sqlite3 \
  --min-schema-version 8 \
  --require-documents \
  --require-backup
```

### OpenAPI、客户端和 MCP

```bash
agent-kb openapi --output ./openapi.json
agent-kb generate-client --output ./agent_kb_client.py
agent-kb mcp-stdio --db ./agent-kb.sqlite3
```

## 容器部署

### Docker

```bash
docker build -t agent-kb-core:0.5.0 agent_kb_core
```

镜像使用 UID/GID `10001`，不以 root 运行，持久化边界为 `/data`。

### Docker Compose

```bash
cd agent_kb_core
docker compose -f deploy/docker-compose.yml up --build
```

Compose 文件中的 API key 仅用于本地验证，部署前必须替换。

### Kubernetes

替换镜像地址和 `secret.example.yaml` 后：

```bash
kubectl apply -k agent_kb_core/deploy/kubernetes/base
```

当前 Kubernetes 基线固定为：

```text
one StatefulSet replica
one Pod
API + worker sidecars
one ReadWriteOnce PVC
```

使用 SQLite 时禁止直接增加副本数。

## Secure service

```bash
export AGENT_KB_API_KEYS='{
  "replace-with-a-long-random-token": {
    "principal_id": "operator-1",
    "tenant_id": "tenant-a",
    "roles": ["admin"]
  }
}'

agent-kb secure-serve \
  --tenant-db-root ./tenants \
  --backup-root ./backups \
  --domain-dir ./domains/obc_dcdc \
  --distributed-rate-limit \
  --host 0.0.0.0 \
  --port 8080
```

请求头：

```text
Authorization: Bearer <api-key>
X-Tenant-ID: tenant-a
```

## 验证

```bash
cd agent_kb_core
python -m pytest
```

GitHub Actions 执行：

```text
Python 3.11 / 3.12 / 3.13 tests
Docker image build
non-root UID assertion
container entrypoint validation
Docker Compose render
continuous-worker job execution
backup and isolated restore
readiness gate
operational and platform evidence artifacts
```

## 目录

```text
agent_kb_core/
  Dockerfile
  deploy/
    docker-compose.yml
    kubernetes/base/
  docs/
  domains/
  src/agent_kb/
  tests/
```

## 平台边界

Phase 9 R1 是单节点平台基线，不是无限水平扩展方案：

- SQLite coordination 不是 Redis、etcd 或分布式事务协调器；
- Kubernetes StatefulSet 目前只能保持一个副本；
- Qdrant collection provisioning 仍属于部署职责；
- OTLP exporter 不是完整 OpenTelemetry SDK；
- 证书签发、续期和企业级 legal-hold 授权仍需接入组织基础设施。

## 下一步

Phase 9 R2 聚焦多节点运行依赖：

```text
Redis coordination and queue adapters
  + platform-native leader election
  + continuous scheduler daemon
  + Vault / cloud secret managers
  + image signing / provenance / SBOM gates
  + managed Qdrant provisioning
  + OpenTelemetry SDK and context propagation
  + SLO dashboards and alerts
  + staging recovery drills
```
