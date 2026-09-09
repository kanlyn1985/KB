# Agentic Knowledge Base — Interface Control Document (ICD) V1.0

- 文档编号：AKB-ICD-001
- 版本：V1.0
- 状态：Draft Design Baseline
- 对应：AKB-SRS-001 V1.1 / AKB-DM-001 V1.0
- 适用分支：`rebuild/agent-kb-core`
- 日期：2026-09-01

## 1. Purpose

本文定义 Agentic Knowledge Base 各核心模块的接口边界、输入输出、行为契约、错误语义、幂等、事务、超时、事件与验证要求。它是详细设计、实现和集成测试的直接输入。

## 2. Interface Principles

1. Canonical Model first：接口传输 Canonical Object/Reference，不绑定具体数据库。
2. Evidence required：涉及 authoritative knowledge 的接口必须保留 evidence/provenance。
3. Projection isolation：Graph/Vector/Search 为派生投影，不得反向篡改 Canonical truth。
4. Version explicit：Ontology、Schema、Rule、Reasoner 等版本必须显式传递或可解析。
5. Deterministic errors：错误必须可分类、可重试性明确。
6. Idempotency：所有可重试写操作必须支持 idempotency key。
7. Async capable：长耗时 ingest/reasoning/indexing 必须支持异步 job。
8. Degraded mode：非关键 provider 故障允许受控降级，但必须显式返回 degraded 信息。

## 3. Logical Interface Map

```text
SourceProvider
      |
      v
KnowledgeCompiler
      |
      v
AssertionValidator ----> EvidenceStore / ProvenanceStore
      |
      v
AssertionStore
      |
      v
SemanticGraph / Projection
      |
      +------> VectorIndex / SearchIndex
      |
      v
RetrievalEngine
      |
      v
ReasoningEngine
      |
      v
ContextEngine <---- MemoryStore / StateStore
      |
      v
DecisionEngine
      |
      v
AgentRuntime
      |
      v
ObservationStore ---> StateStore / MemoryStore
```

## 4. Common Contract

所有接口请求建议包含：

```json
{
  "request_id": "req_...",
  "tenant_id": "tenant_...",
  "actor_id": "actor_...",
  "schema_version": "1.0",
  "idempotency_key": "...",
  "trace_id": "..."
}
```

所有响应建议包含：

```json
{
  "request_id": "req_...",
  "status": "ok | partial | degraded | rejected | failed",
  "schema_version": "1.0",
  "warnings": [],
  "errors": [],
  "trace_id": "..."
}
```

## 5. Interface Definitions

### 5.1 SourceProvider

**职责**：从外部 Source 获取 Artifact/Document。

```python
acquire(request: AcquireRequest) -> AcquireResult
```

输入：Source reference、locator、version policy、access policy。

输出：Artifact/Document reference、content hash、source metadata、ingestion metadata。

前置条件：Source 存在且访问授权通过。

后置条件：生成的 artifact 必须具备稳定 identity/hash。

失败：权限拒绝不可重试；网络/临时 provider 错误可重试。

### 5.2 KnowledgeCompiler

**职责**：把 Document 转成 Evidence、SemanticUnit 和 Candidate Assertion。

```python
compile(request: CompileRequest) -> CompileResult
```

规则：

- 必须产生 evidence lineage。
- Candidate 不得直接进入 asserted。
- 支持 partial result 与 job resume。

### 5.3 EvidenceStore

```python
create(evidence: Evidence) -> EvidenceRef
get(evidence_id) -> Evidence
find(query) -> list[EvidenceRef]
```

要求：Evidence immutable；重复写入按 evidence identity 幂等。

### 5.4 AssertionValidator

```python
validate(request: ValidateAssertionRequest) -> ValidationResult
```

必须执行：schema、ontology、evidence、constraint、policy、conflict checks。

输出：validated/rejected/disputed + violation list。

### 5.5 AssertionStore

```python
create(assertion: KnowledgeAssertion) -> AssertionRef
get(assertion_id, version=None) -> KnowledgeAssertion
transition(assertion_id, transition: AssertionTransition) -> KnowledgeAssertion
history(assertion_id) -> list[AssertionVersion]
```

规则：历史版本不可原地覆盖；状态迁移需 actor、reason、policy_version。

### 5.6 SemanticGraph

```python
project(assertion_refs, ontology_version) -> ProjectionResult
query(request: GraphQuery) -> GraphQueryResult
rebuild(scope) -> JobRef
```

规则：Graph edge 必须保留 assertion_ref；投影失败不得改变 Canonical Store。

### 5.7 RetrievalEngine

```python
retrieve(request: RetrievalRequest) -> RetrievalResult
```

Request 至少包含：query/query_frame、scope、time_range、top_k、channels、ranking_policy。

支持 channel：lexical/vector/entity/graph/temporal/memory。

返回：ranked assertion/evidence/object refs、scores、channel metadata。

### 5.8 ReasoningEngine

```python
reason(request: ReasoningRequest) -> ReasoningResult
explain(trace_id) -> ReasoningTrace
```

Request：assertion refs、graph scope、ontology version、rule set、depth/time/confidence constraints。

Result：Derived Assertions、ReasoningTrace、uncertainty、warnings。

禁止：直接覆盖 asserted knowledge。

### 5.9 MemoryStore

```python
write(entry: MemoryEntry) -> MemoryRef
retrieve(request: MemoryQuery) -> list[MemoryRef]
archive(memory_id) -> None
```

Memory 类型：working/episodic/semantic/procedural。

Memory 不得自动升级为 authoritative assertion。

### 5.10 StateStore

```python
get_state(subject_ref, at_time=None) -> State
apply_delta(delta: StateDelta) -> State
history(subject_ref, time_range) -> list[State]
```

State 必须保留 observed_at 与 validity information。

### 5.11 ContextEngine

```python
build(request: ContextRequest) -> AgentContext
validate(context) -> ContextValidationResult
```

必须组装：goal、knowledge、evidence、state、memory、constraints、uncertainty、answer contract。

缺失信息必须通过 knowledge_gaps/warnings 显式表达。

### 5.12 DecisionEngine

```python
evaluate(request: DecisionRequest) -> Decision
```

必须关联：goal、context、candidate options、reasoning trace、evidence/assertions、constraints、confidence。

### 5.13 ObservationStore

```python
record(observation: Observation) -> ObservationRef
```

必须关联 agent/action/episode；不得伪造 observed_at 或 payload provenance。

### 5.14 AgentRuntime

```python
run(request: AgentRunRequest) -> AgentRunResult
```

最小闭环：Goal → Context → Retrieve/Reason → Decision → Action Proposal → Observation → State/Memory Update。

V1 允许 Action Proposal，不要求 KB 自己执行外部生产 Action。

## 6. Error Model

统一错误分类：

| Code | 含义 | Retry |
|---|---|---|
| AKB-400 | InvalidRequest | 否 |
| AKB-401 | Unauthorized | 否 |
| AKB-403 | Forbidden | 否 |
| AKB-404 | NotFound | 否 |
| AKB-409 | Conflict | 按策略 |
| AKB-422 | ValidationFailed | 否 |
| AKB-425 | EvidenceInsufficient | 否 |
| AKB-429 | RateLimited | 是 |
| AKB-500 | InternalError | 谨慎 |
| AKB-502 | ProviderFailure | 是 |
| AKB-504 | ProviderTimeout | 是 |
| AKB-503 | DegradedDependency | 可降级 |

## 7. Idempotency

以下操作必须支持 idempotency key：

- acquire
- compile
- create evidence
- create assertion
- state update
- observation record
- decision record

同一 tenant + idempotency key + operation type 不得产生重复 canonical record。

## 8. Transaction Boundaries

推荐：

1. Evidence + provenance 写入应原子。
2. Assertion status transition 与 audit 应原子。
3. Canonical commit 与 projection event 可以采用 outbox/transactional event pattern。
4. Projection 更新失败可以重试，不回滚已提交 canonical knowledge。

## 9. Async Job Contract

长任务统一：

```json
{
  "job_id": "job_...",
  "job_type": "ingest | compile | index | reason | rebuild",
  "status": "queued | running | succeeded | partial | failed | cancelled",
  "progress": 0,
  "result_ref": null,
  "error_ref": null
}
```

Job 必须可查询、可取消（在支持的步骤）、可恢复/重试。

## 10. Event Contract

推荐事件：

- DocumentIngested
- EvidenceCreated
- AssertionCreated
- AssertionValidated
- AssertionRejected
- AssertionDeprecated
- EntityUpdated
- OntologyActivated
- ProjectionRequested
- ProjectionCompleted
- ObservationReceived
- DecisionRecorded

事件必须带：event_id、event_type、occurred_at、actor、tenant、aggregate_ref、schema_version。

## 11. Security Contract

所有接口必须支持 actor/tenant/policy context。

Agent 不能调用会绕过治理的 privileged assertion transition。

Action 相关接口必须携带 risk level、permission ref、approval requirement。

## 12. Version Compatibility

接口版本采用 major/minor：

- minor：向后兼容字段增加。
- major：允许破坏性变更。
- server 应至少支持当前 major 的一个兼容 minor 版本窗口。

## 13. Verification Requirements

每个接口至少建立：

- Schema test
- Happy path test
- Boundary test
- Invalid input test
- Authorization test
- Idempotency test（写接口）
- Retry/timeout test
- Provenance test
- Compatibility test

关键集成链必须验证：

```text
SourceProvider
 → Compiler
 → EvidenceStore
 → AssertionValidator
 → AssertionStore
 → SemanticGraph
 → Retrieval
 → Reasoning
 → Context
 → Decision
 → Observation
```

## 14. Implementation Strategy

第一阶段实现优先级：

1. SourceProvider
2. EvidenceStore
3. KnowledgeCompiler
4. AssertionValidator
5. AssertionStore
6. SemanticGraph
7. RetrievalEngine
8. ContextEngine
9. ReasoningEngine
10. Memory/State
11. Decision/Observation
12. AgentRuntime

具体 provider 不应出现在 Canonical API 中；应通过 adapter/registry 注入。

## 15. Design Freeze Criteria

ICD V1.0 在进入编码前必须通过：

- 所有 P0/P1 interface 均有输入/输出 schema；
- 所有写接口有 idempotency 定义；
- 所有长任务有 async job 定义；
- 所有 canonical write 有 provenance；
- 所有 projection interface 都明确为 rebuildable；
- 所有接口具有至少一个自动化验证用例；
- SRS 与 Data Model 引用一致。
