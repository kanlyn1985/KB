# Agentic Knowledge Base — Canonical Data Model Specification V1.0

- 文档编号：AKB-DM-001
- 版本：V1.0
- 状态：Draft Design Baseline
- 对应需求：AKB-SRS-001 V1.1
- 适用分支：`rebuild/agent-kb-core`
- 日期：2026-09-01

## 1. Purpose

本文定义 Agentic Knowledge Base 的 Canonical Data Model（CDM）。它是后续 ICD、详细设计、数据库设计、API Schema、代码实现及验证活动的共同数据基线。

本文件不以 Semantica 或 KB1 的现有对象模型为最终真相源；二者均视为实现来源。所有实现必须服从本 Canonical Model 的语义与不变量。

## 2. Design Principles

1. **Canonical First**：Canonical Knowledge 不依赖 Graph、Vector、Search Index 或 Cache。
2. **Evidence First**：被系统认可为 `validated/asserted` 的知识必须有可验证 Evidence。
3. **Assertion First**：`KnowledgeAssertion` 是统一知识断言，不使用 Graph Edge 作为事实真相单元。
4. **Graph as Projection**：Graph 是 Assertion 的语义投影，可重建。
5. **Immutable History**：历史知识通过新版本和关系表达，不允许无审计原地覆盖。
6. **Asserted ≠ Derived**：推理得到的知识必须带 derivation，不得伪装为原始事实。
7. **Time First-Class**：valid time、observed time、transaction time 分离。
8. **Provider Neutral**：Graph、Vector、Parser、Reasoner、Connector 均通过接口解耦。
9. **Agent Safety**：Agent 可以提出 candidate/proposal，但不得绕过治理直接修改 authoritative knowledge。
10. **Rebuildable Projection**：Graph/Vector/Search 等派生索引丢失后可以从 Canonical Store 重建。

## 3. Domain Model Overview

```text
Reality
  |
  v
Source
  |
  v
Document / Artifact
  |
  v
Evidence
  |
  v
SemanticUnit
  |
  v
KnowledgeAssertion
  |
  +-------------------------------+
  |               |               |
  v               v               v
Entity          Relation         Event
  |                               |
  +---------------+---------------+
                  |
                  v
                State

KnowledgeAssertion
        |
        +--> Ontology / Rule
        |
        +--> Reasoning
                 |
                 v
          DerivedAssertion
                 |
                 v
              Context
                 |
          +------+------+
          v             v
       Decision       Memory
          |
          v
        Action
          |
          v
     Observation
          |
          v
        State
```

## 4. Canonical Objects

| ID | Object | Domain | Persistence | Authority |
|---|---|---|---|---|
| DM-001 | Source | Evidence | Persistent | Canonical |
| DM-002 | Document | Evidence | Persistent | Canonical |
| DM-003 | Evidence | Evidence | Persistent | Canonical |
| DM-004 | SemanticUnit | Compilation | Persistent/Replayable | Intermediate |
| DM-005 | KnowledgeAssertion | Knowledge | Persistent | Canonical |
| DM-006 | Entity | Semantic | Persistent | Canonical projection/entity registry |
| DM-007 | Relation | Semantic | Persistent/Projection | Semantic projection |
| DM-008 | Event | Knowledge | Persistent | Canonical |
| DM-009 | State | Runtime/World | Persistent | Canonical observation/state history |
| DM-010 | Ontology | Semantic | Persistent | Canonical |
| DM-011 | Rule | Semantic | Persistent | Canonical |
| DM-012 | ReasoningTrace | Cognitive | Persistent | Audit/trace |
| DM-013 | Memory | Cognitive | Persistent | Runtime memory |
| DM-014 | Context | Cognitive | Ephemeral/versioned | Derived |
| DM-015 | Goal | Agent | Persistent | Canonical |
| DM-016 | Decision | Agent | Persistent | Canonical |
| DM-017 | Action | Agent | Persistent | Canonical proposal/execution record |
| DM-018 | Observation | Agent/World | Persistent | Canonical |

## 5. Source Model

### 5.1 Semantics

`Source` identifies the origin of information. A Source is not itself a fact.

### 5.2 Required fields

| Field | Type | Required | Constraints |
|---|---|---:|---|
| `source_id` | string | Y | globally unique, immutable |
| `source_type` | enum | Y | document/database/api/sensor/human/agent/system |
| `name` | string | Y | non-empty |
| `authority_score` | number | N | 0..1 |
| `owner` | string | N | principal/team |
| `access_policy_ref` | string | N | policy identifier |
| `metadata` | object | N | provider-specific |

## 6. Document / Artifact Model

A Document is an immutable representation of a source artifact or a normalized version of one.

```json
{
  "document_id": "doc_001",
  "source_id": "src_001",
  "version": "1.0",
  "content_hash": "sha256:...",
  "mime_type": "application/pdf",
  "title": "...",
  "effective_at": null,
  "ingested_at": "2026-09-01T00:00:00Z",
  "metadata": {}
}
```

### Rules

- `content_hash` is mandatory for immutable artifacts.
- A content change creates a new version or document identity.
- `effective_at` and `ingested_at` must not be conflated.
- Original content should be retained in object storage where applicable.

## 7. Evidence Model

Evidence is the smallest auditable information unit used to support an assertion.

```json
{
  "evidence_id": "evd_001",
  "document_id": "doc_001",
  "location": {
    "page": 73,
    "section": "4.2",
    "start": 1200,
    "end": 1350
  },
  "content": "...",
  "evidence_type": "text",
  "observed_at": null,
  "extraction_method": "document_parser_v1",
  "confidence": 0.99,
  "metadata": {}
}
```

### Evidence requirements

- 必须可以定位回 Document/Artifact。
- 文字证据应尽可能保留原文，而非只保存摘要。
- Evidence identity 应具有稳定性；内容哈希、文档版本和位置可用于实现确定性 identity。
- Evidence 可以被多个 Assertion 引用。

## 8. SemanticUnit Model

`SemanticUnit` 是从 Evidence 到 Assertion 之间的中间表示（IR）。

用途：

- 文本归一化；
- 实体和关系候选识别；
- 时间解析；
- ontology mapping；
- extraction replay；
- validation replay。

`SemanticUnit` 不得自动被视为 authoritative knowledge。

## 9. KnowledgeAssertion Model

### 9.1 Definition

`KnowledgeAssertion` 是系统内部统一表达“某个命题”的 Canonical Knowledge Unit。

### 9.2 Schema

```json
{
  "assertion_id": "ast_001",
  "subject_ref": "entity:dcdc",
  "predicate_ref": "relation:has_rated_voltage",
  "object": {
    "kind": "literal",
    "value": 400,
    "datatype": "xsd:integer",
    "unit": "V"
  },
  "assertion_type": "asserted",
  "status": "validated",
  "confidence": 0.98,
  "evidence_refs": ["evd_001"],
  "source_unit_refs": ["su_001"],
  "ontology_ref": "ontology:automotive:1.0",
  "temporal_scope": {
    "valid_from": null,
    "valid_until": null,
    "observed_at": null
  },
  "qualifiers": {},
  "provenance_ref": "prov_001",
  "derivation": null
}
```

### 9.3 Assertion types

| Type | Meaning |
|---|---|
| `extracted` | 从内容自动抽取得到的候选声明 |
| `observed` | 来自系统/传感器/人工的观测 |
| `asserted` | 经过治理接受的权威断言 |
| `inferred` | 由规则/推理得到 |
| `hypothesized` | 尚待验证的假设 |

### 9.4 Status

`candidate → validated → asserted → disputed/deprecated`

`candidate → rejected`

任何状态迁移必须保留：actor、timestamp、reason、policy_version、previous_status。

## 10. Entity Model

Entity 是世界模型中的可识别对象。

```json
{
  "entity_id": "ent_dcdc_001",
  "entity_type": "PowerConverter",
  "canonical_name": "DCDC-001",
  "aliases": ["DCDC"],
  "ontology_ref": "ontology:automotive:1.0",
  "attributes": {},
  "status": "active"
}
```

Entity Resolution 是独立能力，不等于 Evidence Validation。

必须保留：`Evidence → mentions → Entity` 的可追踪关系。

## 11. Relation Model

Relation 是 Entity/Entity、Entity/Event 等之间的语义关系定义或图投影。

Canonical relation 必须能够回指至少一个 Assertion 或显式的 ontology/schema definition。

```json
{
  "relation_id": "rel_001",
  "subject_ref": "entity:dcdc",
  "predicate_ref": "relation:installed_in",
  "object_ref": "entity:vehicle_001",
  "assertion_ref": "ast_001"
}
```

Graph Edge 不得脱离 Assertion 成为不可解释的独立事实。

## 12. Event Model

Event 表示发生于某一时间窗口、可能导致状态变化的事件。

```json
{
  "event_id": "evt_001",
  "event_type": "ProtectionTriggered",
  "actors": ["entity:dcdc"],
  "targets": [],
  "event_time": "2026-09-01T08:00:00Z",
  "state_before_refs": ["state_001"],
  "state_after_refs": ["state_002"],
  "evidence_refs": ["evd_099"]
}
```

## 13. State Model

State 描述实体在特定时间的状态，不等同于稳定知识。

```json
{
  "state_id": "st_001",
  "subject_ref": "entity:dcdc_001",
  "attributes": {
    "temperature": 103,
    "unit": "C"
  },
  "valid_from": "2026-09-01T08:00:00Z",
  "valid_until": null,
  "observed_at": "2026-09-01T08:00:01Z",
  "evidence_refs": ["evd_099"]
}
```

State transitions should normally be explained by Event、Observation 或受控 Inference。

## 14. Ontology Model

Ontology 至少包含：

- Class
- Property
- Relation Type
- Constraint
- Namespace
- Version
- Compatibility/Migration metadata

Ontology version 必须 immutable。历史 Assertion 应绑定产生/验证时使用的 ontology version。

## 15. Rule Model

Rule 用于 Validation、Inference、Policy 或 Decision Support。

```json
{
  "rule_id": "rule_001",
  "rule_type": "inference",
  "version": "1.0",
  "conditions": [],
  "conclusions": [],
  "priority": 10,
  "enabled": true
}
```

Rule 本身必须 versioned；Derived Assertion 必须引用 `rule_id + rule_version`。

## 16. ReasoningTrace Model

ReasoningTrace 描述“为什么得到某个 Derived Assertion”，不等同于保存模型私有思维链。

```json
{
  "trace_id": "trace_001",
  "input_assertion_refs": ["ast_001", "ast_002"],
  "rule_refs": ["rule_007@1.2"],
  "steps": [],
  "conclusion_refs": ["ast_101"],
  "reasoner_id": "reasoner_x",
  "reasoner_version": "2.0",
  "created_at": "..."
}
```

## 17. Memory Model

Memory 与 authoritative Knowledge 分离。

类型：

- `working`
- `episodic`
- `semantic`
- `procedural`

Memory 可以成为未来 Knowledge Promotion 的候选来源，但必须经过 Evidence/Validation 流程后才能产生 Asserted Assertion。

## 18. Context Model

Context 是运行时派生对象，不是永久知识源。

```json
{
  "context_id": "ctx_001",
  "goal_ref": "goal_001",
  "assertion_refs": [],
  "evidence_refs": [],
  "entity_refs": [],
  "state_refs": [],
  "memory_refs": [],
  "decision_refs": [],
  "constraints": [],
  "uncertainty": [],
  "created_at": "...",
  "source_request_id": "req_001"
}
```

Context 应可重新构建或通过引用恢复。

## 19. Goal Model

Goal 表达 Agent 希望达到的目标状态。

核心字段：`goal_id`, `description`, `target_state`, `priority`, `deadline`, `constraints`, `created_by`。

## 20. Decision Model

Decision 必须包含：

- goal/context reference
- candidate options
- selected option
- reasoning trace
- evidence/assertion references
- constraints
- confidence
- outcome status

Decision 不得只有一段自然语言 reasoning。

## 21. Action Model

Action 是可执行操作的结构化提案或执行记录。

```json
{
  "action_id": "act_001",
  "agent_id": "agent_001",
  "type": "query_external_system",
  "parameters": {},
  "preconditions": [],
  "expected_effects": [],
  "risk_level": "medium",
  "permission_ref": "policy_007",
  "approval_required": true,
  "decision_ref": "dec_001"
}
```

Action 与 Knowledge 修改分离；高风险 Action 必须经过 Policy/Permission gate。

## 22. Observation Model

Observation 是 Agent/系统对 Action 或外部世界的反馈记录。

```json
{
  "observation_id": "obs_001",
  "action_ref": "act_001",
  "observed_at": "...",
  "payload": {},
  "state_delta": {},
  "evidence_refs": []
}
```

## 23. Provenance Model

每个 Canonical object 必须能够关联 Provenance。

最小 provenance：

```text
Source
  ↓
Document
  ↓
Evidence
  ↓
Assertion
  ↓
ReasoningTrace (optional)
  ↓
Decision / Answer
```

推理产生的知识增加：

```text
DerivedAssertion
  ↓
parent_assertions
rule
reasoner
trace
```

## 24. Time Model

必须至少区分：

| 时间 | 语义 |
|---|---|
| `effective/valid time` | 世界中的有效区间 |
| `event time` | 事件发生时间 |
| `observed_at` | 系统观察时间 |
| `ingested_at` | 进入系统时间 |
| `transaction time` | 系统记录/提交时间 |

不能用单一 `timestamp` 代替全部时间语义。

## 25. Projection Model

Canonical objects产生多个Projection：

```text
Canonical Store
  |
  +--> Graph Projection
  +--> Vector Projection
  +--> Lexical/Search Projection
  +--> Analytics Projection
  +--> Context Projection
```

Projection必须满足：

- 可从Canonical Store重建；
- 有版本；
- 不允许反向改变Canonical truth；
- 更新失败必须产生可恢复/可重建状态。

## 26. Storage Mapping

V1不强制单一数据库。

建议逻辑分工：

| 数据 | 首选逻辑存储 | 说明 |
|---|---|---|
| Source/Document metadata | SQL | 强一致、版本管理 |
| Evidence | SQL/Object Store | 文本与原始载荷可组合保存 |
| Assertion | SQL/Canonical Store | 真相源 |
| Entity/Relation/Graph | Graph Store | Projection/语义查询 |
| Embedding | Vector Store | 可重建 |
| Provenance | SQL/Event Store | 审计与lineage |
| Memory | SQL/Vector/Graph | 由访问模式决定 |
| Context | Cache/SQL | 派生对象 |
| Artifact | Object Store | 原始二进制 |

## 27. ID 与 Identity 规则

1. Canonical ID 在生命周期内不得复用。
2. 删除/失效对象应保留 tombstone 或等价历史记录。
3. External ID 与 Internal ID 分离。
4. Entity alias 不是新的 Entity。
5. Document content hash 用于内容完整性，不代替业务 identity。

## 28. Concurrency / Transaction Rules

- Canonical Assertion 提交必须原子化：Assertion、状态变更、Provenance 至少逻辑上同一事务。
- Projection 异步更新允许短暂最终一致，但必须可观察。
- 两个并发更新同一 Assertion 必须产生 conflict/version resolution，而不是静默覆盖。
- Idempotency key 必须用于 ingestion、observation 和关键 command。

## 29. Serialization Rules

所有 Canonical objects：

- 必须可序列化为 JSON；
- 必须声明 `schema_version`；
- 日期使用 ISO-8601；
- Enum 不得以自由文本替代；
- Reference 使用稳定 ID；
- 未知扩展字段必须进入 `metadata/extensions` 而不破坏核心 schema。

## 30. Data Quality Gates

### Gate DQ-1
Schema valid。

### Gate DQ-2
Reference integrity valid。

### Gate DQ-3
Evidence lineage valid。

### Gate DQ-4
Ontology compatibility valid。

### Gate DQ-5
Temporal consistency valid。

### Gate DQ-6
Provenance integrity valid。

### Gate DQ-7
Projection consistency valid。

## 31. Semantica Mapping

| Canonical | Semantica 主要实现来源 | 处理 |
|---|---|---|
| Entity | KG Entity | 主要复用 |
| Relation | KG relationships | 作为Projection |
| Graph | KnowledgeGraph/GraphBuilder | 主要复用 |
| Ontology | ontology package | 主要复用 |
| Rule | reasoning package | 主要复用 |
| ReasoningTrace | reasoning/provenance | 复用并规范输出 |
| Provenance | provenance package | 深度复用 |
| Temporal | temporal KG / schema | 复用 |
| Context | AgentContext/ContextGraph | 重新归一化 |
| Memory | AgentMemory | 复用基础能力 |
| Decision | Decision models | 复用并扩展 Evidence refs |

## 32. KB1 Mapping

| Canonical | KB1 当前实现来源 | 处理 |
|---|---|---|
| Source | document/source registration | 保留 |
| Document | DocumentRecord | 保留 |
| Evidence | EvidenceBlock | **核心保留** |
| SemanticUnit | SourceUnit | 升级为统一IR |
| Assertion | Fact/Compiler | **升级为Canonical Assertion** |
| Entity | ObjectProjection/domain subject | 与Semantica统一 |
| Relation | graph/extraction | 向Semantica Graph迁移 |
| Retrieval | retrieval cards/hybrid | 保留策略与评估体系 |
| Context | AgentContextPack | 作为Unified Context组成部分 |
| Answer Contract | answer contract | 保留 |
| Golden | golden cases | 保留 |
| Evidence Judge | evidence_judge | 保留为治理门 |

## 33. Forbidden Data Flows

以下流程禁止：

```text
LLM → Asserted Assertion
Graph Edge → Canonical Truth
Vector Result → Truth
Memory → Asserted Knowledge
Derived Assertion → Asserted without promotion policy
Agent → Direct Canonical Mutation
```

## 34. Required Data Flows

```text
Document
 → Evidence
 → SemanticUnit
 → Candidate Assertion
 → Validation
 → Validated/Asserted Assertion
 → Semantic Projection
 → Graph/Vector/Search
```

推理：

```text
Asserted Assertions
 → Reasoning
 → ReasoningTrace
 → Derived Assertion
 → Optional governed promotion
```

Agent：

```text
Goal
 → Context
 → Decision
 → Action Proposal
 → Policy
 → External Execution
 → Observation
 → State Update
 → Memory
```

## 35. V-Model Verification Mapping

| Model | Verification |
|---|---|
| Source/Document | schema + ingestion tests |
| Evidence | lineage + content integrity tests |
| Assertion | lifecycle/invariant tests |
| Entity | identity resolution golden tests |
| Graph | projection consistency tests |
| Ontology | schema/constraint/migration tests |
| ReasoningTrace | proof/parent reference tests |
| Context | reproducibility/contract tests |
| Decision | decision trace tests |
| Action | policy/safety tests |
| Observation/State | state transition tests |
| End-to-end | Golden Knowledge + Agent E2E |

## 36. Definition of Done for Data Model V1.0

- Canonical objects have stable schema.
- P0 invariants have automated tests designed.
- State transitions are explicitly defined.
- All authoritative knowledge has provenance.
- Graph and vector are rebuildable projections.
- Semantica/KB1 mapping is documented.
- Schema versioning strategy exists.
- Migration strategy is documented before schema-breaking implementation.

## 37. Open Decisions Before Approval

1. Canonical Store 的具体实现（SQL/Document/Hybrid）需要 Architecture Review。
2. 是否采用 RDF/OWL 作为公开语义交换格式需要独立 ADR。
3. `KnowledgeAssertion.object` 的 Literal/Entity/Collection/StructuredValue 类型体系需要进入 ICD 前冻结。
4. Confidence 的来源与组合算法需要建立单独规范，避免把不同模型概率直接混合。
5. Temporal 与 State 的完整查询语义需要在 Temporal Specification 中冻结。
6. Action 的真正执行权限应由外部 Agent/Tool Runtime 控制。

## 38. Baseline Status

**状态：Draft Design Baseline。**

本文件在完成以下工件并评审后方可升级为 Approved Baseline：

- SRS V1.1
- ICD V1.0
- Verification & Validation Plan V1.0
- ADR set
- Architecture Review Record
- Schema validation implementation
