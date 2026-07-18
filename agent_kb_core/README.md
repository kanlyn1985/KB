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

Phase 6 已加入：

- provider-neutral `EmbeddingProvider`
- deterministic `HashEmbeddingProvider` baseline
- `SQLiteVectorIndex`
- `SQLiteGraphStore`
- `ProductionCandidateProvider`
- monotonic `SchemaMigrator`
- logical document/version lifecycle
- production indexing/query pipeline
- versioned JSON service endpoints
- feedback-driven evaluation

`HashEmbeddingProvider` 和 SQLite cosine scan 是无外部依赖的契约验证基线，不等同于已经接入学习型 embedding 模型或大规模向量数据库。

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

Phase 5 持久化索引：

```bash
agent-kb index-text \
  --text-file ./sample.txt \
  --db ./agent-kb.sqlite3 \
  --domain-dir ./domains/obc_dcdc

agent-kb query-store \
  --db ./agent-kb.sqlite3 \
  --query "输出纹波要求是多少？" \
  --domain-dir ./domains/obc_dcdc
```

Phase 6 生产索引和查询：

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

生命周期和反馈：

```bash
agent-kb documents --db ./agent-kb.sqlite3

agent-kb document-status \
  --db ./agent-kb.sqlite3 \
  --logical-document-id ldoc_ripple \
  --status deprecated

agent-kb feedback \
  --db ./agent-kb.sqlite3 \
  --run-id run_xxx \
  --rating 1 \
  --comment "retrieval is relevant"

agent-kb eval-feedback --db ./agent-kb.sqlite3
```

服务：

```bash
agent-kb serve \
  --db ./agent-kb.sqlite3 \
  --domain-dir ./domains/obc_dcdc \
  --host 127.0.0.1 \
  --port 8080
```

HTTP 端点：

```text
GET  /v1/health
GET  /v1/documents
POST /v1/index
POST /v1/query
POST /v1/feedback
POST /v1/documents/{logical_document_id}/status
```

## 当前目录

```text
agent_kb_core/
  docs/
  src/agent_kb/
    core/
    domains/
    query/
    projection/
    retrieval/
    embeddings/
    graph/
    evaluation/
    context/
    storage/
    pipeline/
    service/
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

Phase 7 应聚焦生产硬化，而不是继续堆叠新的抽象：

```text
learned embedding providers and secret management
  + external vector backend
  + relation extraction and graph evaluation
  + authentication / RBAC / tenant isolation
  + transactional document cleanup
  + background jobs and concurrency control
  + OpenAPI / gRPC / MCP adapters
  + metrics / tracing / backup / recovery
```

所有后续适配器必须继续输出既有 `RetrievalResult` 和 `AgentContextPack`，并通过同一套 golden 与 feedback evaluation contracts 对比效果。
