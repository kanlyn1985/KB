# Agent KB Core

通用证据约束型智能体知识库编译框架。

本目录是从现有 `enterprise-agent-kb` 项目中重新抽核后的新架构起点。目标不是继续扩展旧的汽车/需求治理实现，而是重建一个可复用的通用核心：

```text
Documents -> Evidence -> Semantic Units -> Facts/Entities/Relations -> Object Projections -> Retrieval Cards -> Context Packs -> Agent
```

## 定位

```text
Generic Evidence-grounded Agent Knowledge Compiler
```

中文：

```text
通用证据约束型智能体知识库编译框架
```

## 核心原则

1. **Core 不绑定领域**：核心代码不能写死 OBC、DCDC、CP、CC、PWM、RequirementVariant、ECO 等领域对象。
2. **Domain Pack 承载领域差异**：术语、对象、关系、回答模板、隐藏知识、抽取规则放在 `domains/<domain>/`。
3. **Evidence-first**：任何结构化对象都必须能回溯到原文证据。
4. **Object-centered retrieval**：召回不只找 chunk，还要找对象、别名、关系和 retrieval card。
5. **Context Pack for Agent**：知识库主要输出给智能体消费的结构化上下文，而不是只输出最终自然语言答案。
6. **Retrieval must be measurable**：任何召回升级都必须通过 golden cases 和指标验证。
7. **Persistent and auditable**：持久化检索结果、证据充分性判断和用户反馈必须可审计。
8. **Adapters are replaceable**：embedding、vector、graph、service 和 storage 适配器不得改变核心检索与上下文契约。
9. **Tenant boundaries are explicit**：当前嵌入式部署采用每租户独立 SQLite 数据库，避免依赖易漏写的查询过滤条件。

## 当前能力

### Phase 1：架构骨架

- domain pack loader
- query frame schema
- object projection schema
- retrieval card schema
- context pack schema
- generic + obc_dcdc 示例 domain pack

### Phase 2：通用文档编译

```text
plain text
  -> DocumentRecord
  -> EvidenceBlock
  -> SourceUnit
  -> Fact
  -> KnowledgeCompilation
```

### Phase 3：文档到 Agent Context Pack

```text
KnowledgeCompilation
  -> ContextFact / ContextEvidence
  -> ObjectProjection
  -> RetrievalCard
  -> QueryFrame
  -> AgentContextPack
```

主要入口：

```python
from agent_kb.pipeline import compile_text_to_context_pack
```

### Phase 4：多路召回与评测

```text
QueryFrame
  -> object/card/fact/table/evidence channels
  -> weighted reciprocal-rank fusion
  -> intent and evidence-shape boosts
  -> RetrievalResult
  -> retrieved Context Pack subset
```

包括 object-card、fact、table、evidence、keyword、领域别名语义回退、召回诊断、Hit@K、MRR、object/card/fact/evidence recall 和 golden-case evaluation。

### Phase 5：持久化、混合召回与证据治理

```text
CompiledKnowledgeIndex
  -> SQLite relational store
  -> optional FTS5 / LIKE fallback
  -> hybrid retrieval
  -> deterministic reranker
  -> AgentContextPack
  -> evidence sufficiency judgement
  -> retrieval run audit / feedback
```

包括 SQLite 持久化、FTS5/LIKE 回退、可插拔 reranker、证据充分性判断、retrieval run 审计和用户反馈。

### Phase 6：生产适配层

```text
Document version
  -> schema migration + lifecycle
  -> lexical index
  -> embedding provider + vector index
  -> graph persistence/traversal
  -> production candidate provider
  -> hybrid retrieval
  -> Context Pack + evidence judgement
  -> service API + feedback evaluation
```

Phase 6 已加入 provider-neutral `EmbeddingProvider`、`SQLiteVectorIndex`、`SQLiteGraphStore`、`ProductionCandidateProvider`、单调迁移、文档版本生命周期、生产查询链路和版本化 JSON 服务。

`HashEmbeddingProvider` 和 SQLite cosine scan 是无外部依赖的契约验证基线，不等同于已经接入学习型 embedding 模型或大规模向量数据库。

### Phase 7：生产硬化

```text
Client
  -> API-key authentication
  -> Principal / tenant binding
  -> RBAC
  -> rate limiting
  -> tenant database router
  -> lexical / local-vector / external-vector / graph retrieval
  -> Context Pack
  -> audit / metrics / feedback
```

Phase 7 已加入：

- `RemoteJSONEmbeddingProvider` 与环境变量密钥配置
- `ExternalVectorBackend`、`HTTPVectorBackend` 和测试用 `InMemoryVectorBackend`
- 显式关系抽取接口与 graph precision/recall/F1 评测
- API-key authentication、RBAC、物理租户隔离
- token-bucket rate limiting
- 持久化安全审计
- 后台任务队列、租约、重试和 worker
- 在线 SQLite 备份、SHA-256 和完整性验证
- 事务化文档及派生索引清理
- 指标计数和耗时摘要
- OpenAPI 3.1 与 MCP-compatible 工具适配层
- hardened HTTP service

当前 schema version：

```text
1 document lifecycle
2 vector index
3 graph index
4 jobs / audit / backup history
5 graph extraction governance
```

## CLI

文档到 Context Pack：

```bash
agent-kb compile-context \
  --text-file ./sample.txt \
  --query "输出纹波要求是多少？" \
  --domain-dir ./domains/obc_dcdc \
  --retrieval-top-k 12
```

召回评测：

```bash
agent-kb eval-retrieval \
  --text-file ./sample.txt \
  --cases-file ./golden_cases.json \
  --domain-dir ./domains/obc_dcdc
```

生产索引和查询：

```bash
agent-kb migrate-db --db ./agent-kb.sqlite3

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

后台任务、备份和清理：

```bash
agent-kb queue-index \
  --db ./agent-kb.sqlite3 \
  --text-file ./sample.txt \
  --logical-document-id ldoc_ripple

agent-kb worker-once \
  --db ./agent-kb.sqlite3 \
  --domain-dir ./domains/obc_dcdc

agent-kb backup \
  --db ./agent-kb.sqlite3 \
  --backup-dir ./backups

agent-kb purge-document \
  --db ./agent-kb.sqlite3 \
  --logical-document-id ldoc_ripple
```

OpenAPI：

```bash
agent-kb openapi --output ./openapi.json
```

## Hardened service

配置 API keys：

```bash
export AGENT_KB_API_KEYS='{
  "replace-with-a-long-random-token": {
    "principal_id": "operator-1",
    "tenant_id": "tenant-a",
    "roles": ["admin"]
  }
}'
```

启动：

```bash
agent-kb secure-serve \
  --tenant-db-root ./tenants \
  --backup-root ./backups \
  --domain-dir ./domains/obc_dcdc \
  --host 127.0.0.1 \
  --port 8443
```

请求头：

```text
Authorization: Bearer <api-key>
X-Tenant-ID: tenant-a
```

Hardened endpoints：

```text
GET  /v1/health
GET  /v1/documents
GET  /v1/jobs/{job_id}
GET  /v1/metrics
GET  /v1/audit
GET  /v1/openapi.json
POST /v1/index
POST /v1/query
POST /v1/feedback
POST /v1/jobs/index
POST /v1/admin/worker-once
POST /v1/admin/backup
POST /v1/admin/purge
```

`secure-serve` 表示已经加入认证、RBAC、限流、审计和租户隔离；它仍然使用标准库 HTTP server，不提供内建 TLS。对外部署必须放在 TLS 终止代理之后。

## 当前目录

```text
agent_kb_core/
  docs/
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
  domains/
  tests/
```

## 本地验证

```bash
cd agent_kb_core
python -m pytest
```

GitHub Actions 会在 Python 3.11、3.12 和 3.13 上执行安装、`compileall` 和完整测试。

## 下一步

Phase 8 聚焦部署级可靠性，而不是继续堆叠核心抽象：

```text
distributed rate limiting and job coordination
  + managed vector database connectors
  + secret-manager adapters and key rotation
  + TLS/mTLS deployment profiles
  + full MCP transport and generated SDKs
  + OpenTelemetry metrics/traces
  + backup retention and recovery drills
  + load / chaos / security testing
  + policy-driven retention and legal hold
```

所有后续适配器必须继续输出既有 `RetrievalResult` 和 `AgentContextPack`，并通过同一套 golden、graph 和 feedback evaluation contracts 对比效果。
