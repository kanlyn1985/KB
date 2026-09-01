# Agentic Knowledge Base — Verification & Validation Plan V1.0

- 文档编号：AKB-VV-001
- 版本：V1.0
- 状态：Draft Verification Baseline
- 适用分支：`rebuild/agent-kb-core`
- 对应基线：SRS V1.1 / Canonical Data Model V1.0 / ICD V1.0
- 方法：V-Model + Incremental Verification

## 1. Purpose

定义 Agentic Knowledge Base 的 Verification & Validation（V&V）体系，用于证明：

1. 软件实现符合系统需求、数据模型和接口契约；
2. 知识结果符合 Evidence、Assertion、Provenance 与 Governance 约束；
3. Retrieval / Reasoning / Context / Decision 的行为可重复、可解释、可回归；
4. Agent 不会绕过权限、证据和策略边界；
5. 每个 P0/P1 需求都能够追踪到验证工件和验收结果。

本文定义“如何证明正确”，不定义具体模块实现。

## 2. V&V Principles

### 2.1 Dual V-Model

```text
Software V
Requirement → Architecture → Component → Interface → Implementation
                                                     ↑
                         Unit → Contract → Integration → System → Acceptance

Knowledge V
Knowledge Requirement → Data Model → Evidence/Assertion → Compiler
                                                     ↑
                         Evidence → Assertion → Reasoning → Answer/Decision
```

### 2.2 Core Principles

- Verification 证明“按设计实现正确”；Validation 证明“实现满足实际目标”。
- P0/P1 需求必须可自动验证，或明确记录为什么只能人工验证。
- Evidence lineage、Assertion lifecycle 和 Graph projection consistency 属于不可绕过的核心门禁。
- 测试失败时禁止用修改测试期望值的方式掩盖产品回归，除非存在已批准的需求/基线变更。
- 所有性能结果必须记录测试环境、数据集、负载、版本与统计口径。

## 3. Verification Levels

| Level | 名称 | 目标 | 主要对象 |
|---|---|---|---|
| V0 | Schema/Data Validation | 保证对象合法 | JSON Schema、模型 |
| V1 | Unit Verification | 验证最小行为 | Compiler、Validator、Resolver |
| V2 | Contract Verification | 验证接口契约 | ICD interfaces |
| V3 | Integration Verification | 验证跨模块一致性 | Compiler→Store→Graph |
| V4 | System Verification | 验证端到端系统 | ingest→knowledge→context |
| V5 | Agent E2E | 验证 Agent 闭环 | Goal→Action→Observation |
| V6 | Acceptance | 验证业务目标 | Golden / business scenarios |

## 4. Validation Categories

### 4.1 Software Correctness

- Schema compliance
- API behavior
- lifecycle correctness
- concurrency/idempotency
- error handling
- recovery
- security

### 4.2 Knowledge Correctness

- Evidence linkage
- Assertion correctness
- entity/relation correctness
- temporal semantics
- ontology constraint correctness
- reasoning correctness
- provenance completeness
- retrieval quality

### 4.3 Agent Correctness

- context completeness
- policy compliance
- decision traceability
- action preconditions
- observation integrity
- state update correctness
- memory separation

## 5. Test Environment Baseline

测试环境必须记录：

```text
OS / CPU / RAM
Python / runtime version
Database versions
Graph backend
Vector backend
Embedding model/provider
Ontology version
Rule set version
Application commit SHA
Dataset version
Test configuration
```

同一 benchmark 的结果只有在环境信息完整时才允许进行版本比较。

## 6. Test Data Strategy

测试数据分为四级：

1. Synthetic：边界、异常、状态机、并发。
2. Golden：已人工确认的知识与答案。
3. Representative：接近实际生产的数据分布。
4. Adversarial：冲突、歧义、缺证据、时间矛盾、恶意输入。

任何自动抽取模型升级至少要通过 Synthetic + Golden + Representative。

## 7. Core System Invariant Tests

### INV-T01 Evidence Gate

Given：没有有效 Evidence。

When：尝试创建 `validated/asserted` Assertion。

Expected：操作拒绝；记录明确失败原因；不得进入 Canonical Store。

### INV-T02 Derived Isolation

Given：Reasoning 输出 Derived Assertion。

Expected：`assertion_type=inferred`；存在 parent references、rule、reasoner 和 trace；不得自动变成 asserted。

### INV-T03 Graph Projection Integrity

Given：Canonical Assertion。

When：Graph projection 创建/更新。

Expected：Graph edge 可以反查 assertion；Projection 失败不能修改 Canonical truth。

### INV-T04 Provenance Completeness

Expected：Answer/Decision→Assertion→Evidence→Document→Source 全链路可追踪。

### INV-T05 Index Rebuild

Given：删除 Graph/Vector/Search projection。

When：从 Canonical Store rebuild。

Expected：重建后 identity、links、status 和 provenance 与基线一致。

### INV-T06 Historical Integrity

Given：知识发生变化。

Expected：创建新版本/新的 assertion，不覆盖历史版本；supersedes/invalidates 关系可追踪。

## 8. Evidence Tests

| Test ID | 场景 | 通过条件 |
|---|---|---|
| EVD-001 | source→document | source identity完整 |
| EVD-002 | document hash | 同内容稳定、内容变更可检测 |
| EVD-003 | evidence location | page/section/range可恢复 |
| EVD-004 | evidence reuse | 多Assertion可共享同一Evidence |
| EVD-005 | evidence archive | 归档不破坏历史引用 |
| EVD-006 | malformed evidence | 非法证据不能进入validated状态 |

## 9. Assertion Tests

### Lifecycle Matrix

```text
candidate --validate--> validated --promote--> asserted
candidate --reject----> rejected
asserted --dispute---> disputed
asserted --supersede-> deprecated
```

测试必须覆盖：正常跳转、非法跳转、重复操作、并发操作、权限不足、缺 Evidence、Ontology 不匹配、类型不匹配。

### Assertion Property Tests

- `assertion_id` 唯一且不可复用。
- confidence ∈ [0,1]。
- validated/asserted 必须满足 Evidence Gate。
- predicate 必须符合 active ontology version。
- object datatype 必须满足 predicate range。

## 10. Entity / Relation / Event / State Tests

### Entity

- Identity resolution 不得导致无依据实体合并。
- merge 必须保留 aliases 和 provenance。
- deprecated entity 的历史引用必须仍可解析。

### Relation

- relation type 必须受到 ontology 约束。
- Graph edge 必须能够反查 Assertion。

### Event

- event_time、actor、targets 等 schema 必须正确。
- state transition 可由 event/observation 解释。

### State

- state 必须带时间语义。
- 后续状态不得覆盖历史状态。
- state delta 可以从 Observation 重放。

## 11. Ontology and Rule Verification

### Ontology

测试：schema、class hierarchy、relation domain/range、constraints、versioning、migration。

### Rule

测试：

- condition evaluation
- rule priority
- deterministic outcome
- rule version pinning
- enable/disable behavior
- conflict between rules

## 12. Provenance Verification

每个关键处理活动至少记录：

```text
actor
activity
timestamp
input references
output references
method/version
source/evidence references
```

Derived knowledge additionally requires：

```text
parent_assertions
rule_id + rule_version
reasoner_id + version
reasoning_trace
```

Provenance integrity failure必须阻止P0知识进入release baseline。

## 13. Retrieval Verification

### 13.1 Channels

- lexical
- vector
- entity
- graph
- temporal
- causal（启用后）
- memory

### 13.2 Metrics

- Hit@K
- MRR
- Evidence Recall
- Assertion Recall
- Entity/Object Recall
- latency P50/P95/P99

### 13.3 Ablation

新通道或新fusion策略必须与冻结baseline比较；如果核心指标下降，必须有Change Request 才能进入默认配置。

### 13.4 Negative Retrieval

测试 query 与知识高度相似但不支持答案的情况，验证系统不会因为语义相似而错误引用证据。

## 14. Evidence Sufficiency / Answer Verification

三种结果必须可区分：

```text
Sufficient
Partial
Insufficient
```

测试至少覆盖：

1. 完整证据→正常回答；
2. 部分证据→partial + knowledge_gaps；
3. 无充分证据→abstain；
4. 冲突证据→披露冲突；
5. derived answer→包含 reasoning trace；
6. answer→assertion/evidence 引用完整。

## 15. Reasoning Verification

### 15.1 Golden Rule Tests

输入一组已知 Assertions + Rules，预定义 expected derived assertions。

通过条件：

- conclusion 正确；
- parent references 正确；
- rule version 正确；
- trace 完整；
- 不产生未授权的额外 conclusion。

### 15.2 Boundary Tests

- max depth
- cycle
- conflicting rules
- incomplete graph
- timeout
- invalid ontology
- missing parent assertion

## 16. Context Verification

Context 必须满足：

```text
goal
knowledge
assertions
evidence
state
memory
constraints
uncertainty
```

测试：

- context 可序列化；
- 相同输入和版本可重建；
- knowledge gap 不被删除；
- insufficient evidence 不得被 context builder 隐藏；
- memory 不得伪装成 authoritative knowledge。

## 17. Memory Verification

测试四类 memory：

- working
- episodic
- semantic
- procedural

关键规则：Memory → Knowledge 必须经过受控 Promotion Pipeline。

测试非法直接晋升必须失败。

## 18. Decision Verification

Decision 至少必须关联：

```text
goal
context
options
selected option
reasoning trace
knowledge/evidence references
constraints
confidence
outcome status
```

验证要求：Decision 可以重放并说明“为什么选择该方案”。

## 19. Agent E2E Verification

最小 E2E：

```text
Goal
 ↓
Context
 ↓
Retrieve
 ↓
Reason
 ↓
Decision
 ↓
Action Proposal
 ↓
Policy Check
 ↓
Observation
 ↓
State Update
 ↓
Memory
```

通过条件：所有关键对象均存在合法引用，且没有越权知识修改。

## 20. Security Verification

必须覆盖：

- authentication
- authorization
- tenant isolation
- source access policy
- assertion read/write policy
- agent permission
- action approval
- audit integrity

安全测试不得只验证API返回403，还必须验证数据没有通过其他查询路径泄露。

## 21. Failure / Recovery Verification

必须测试：

- parser failure
- embedding provider unavailable
- graph store unavailable
- vector store unavailable
- reasoner timeout
- duplicate ingestion
- partial transaction
- process restart
- database restore
- projection rebuild

恢复后的 Canonical Store 是最终依据；Projection 必须允许从 Canonical 重建。

## 22. Performance Verification

首次 baseline 以真实测试数据测量并冻结阈值。

必须记录：

```text
P50 / P95 / P99
Throughput
Concurrency
CPU
Memory
Storage growth
```

至少进行：1 / 5 / 10 / 25 / 50 concurrent workload profiles。

## 23. Regression Strategy

每次代码或配置变更触发：

```text
Schema Tests
 ↓
Unit Tests
 ↓
Contract Tests
 ↓
Integration Tests
 ↓
Knowledge Golden
 ↓
Retrieval Benchmark
 ↓
Reasoning Golden
 ↓
Answer Contract
 ↓
Agent E2E
```

P0失败必须阻止发布；P1回归必须有批准的例外记录才能继续。

## 24. Golden Dataset Requirements

每个 Golden Case 至少包含：

```text
case_id
query
intent
expected_entities
expected_assertions
expected_evidence
expected_reasoning
expected_support_level
expected_answer_constraints
negative_cases
```

Golden Set必须版本化，不允许静默修改 expected result。

## 25. Release Gates

| Gate | 条件 |
|---|---|
| G-01 Build | build/package成功 |
| G-02 Unit | P0 unit 100%通过 |
| G-03 Contract | 所有P0接口契约通过 |
| G-04 Integration | P0集成通过 |
| G-05 Knowledge Integrity | 所有核心 invariants 通过 |
| G-06 Retrieval | 不低于冻结baseline |
| G-07 Reasoning | Golden reasoning 通过 |
| G-08 Answer | Evidence/Answer Contract通过 |
| G-09 Security | P0安全问题=0 |
| G-10 Recovery | Canonical restore + projection rebuild成功 |
| G-11 Agent E2E | Agent闭环通过 |
| G-12 Acceptance | 业务验收通过 |

## 26. Test Naming Convention

```text
UT-<DOMAIN>-<NNN>
CT-<INTERFACE>-<NNN>
IT-<FLOW>-<NNN>
ST-<SYSTEM>-<NNN>
GT-<KNOWLEDGE>-<NNN>
RT-<RETRIEVAL>-<NNN>
RE-<REASONING>-<NNN>
AT-<ACCEPTANCE>-<NNN>
NEG-<DOMAIN>-<NNN>
PERF-<DOMAIN>-<NNN>
REC-<DOMAIN>-<NNN>
```

## 27. Requirement-to-Test Mapping

最低要求：

```text
Requirement
 ↓
Architecture Element
 ↓
Interface / Data Model
 ↓
Test Case
 ↓
Automation
 ↓
Result
 ↓
Acceptance
```

P0/P1需求覆盖率目标：100%。

## 28. V&V Exit Criteria

V1.0 可以验收的条件：

1. 所有 P0 需求有完整 RTM。
2. 所有 P0 invariant 有自动化验证。
3. Golden Dataset 已冻结。
4. Retrieval baseline 已测量并冻结。
5. Reasoning golden 已建立。
6. Agent E2E 至少存在一个完整场景。
7. Security / Recovery / Performance reports 齐全。
8. 无未批准的 P0 缺陷。

## 29. Next Verification Deliverables

后续应产生：

- `Requirement_Traceability_Matrix_V1.0.md`
- `Golden_Knowledge_Dataset_V1.0.md` 或对应机器可读数据集
- `Architecture_Decision_Records_V1.0.md`
- automated test suites
- V&V execution reports

## 30. Baseline Status

当前状态：**Draft Verification Baseline**。

当 SRS V1.1、Data Model V1.0、ICD V1.0、V&V Plan V1.0、RTM、Golden Dataset、ADR 和 Architecture Review 均完成并批准后，才将项目标记为 Design Baseline Approved。