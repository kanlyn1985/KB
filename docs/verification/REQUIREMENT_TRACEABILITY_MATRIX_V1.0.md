# Agentic Knowledge Base — Requirement Traceability Matrix V1.0

- Document ID: AKB-RTM-001
- Version: V1.0
- Status: Draft Verification Baseline
- Branch: `rebuild/agent-kb-core`
- Baselines: SRS V1.1 / Data Model V1.0 / ICD V1.0 / V&V Plan V1.0

## 1. Purpose

建立需求 → 架构 → 数据模型 → 接口 → 实现 → 验证 → 验收的双向追踪链。

## 2. Traceability Rules

1. 每个 P0/P1 需求必须至少映射一个设计元素和一个验证活动。
2. 每个 Canonical Data Model 对象必须至少有一个需求来源和一个数据完整性测试。
3. 每个核心 ICD 接口必须至少有一个契约测试和一个集成测试。
4. 任何验证失败必须能够追溯到对应需求。
5. 任何进入 Release Gate 的代码变更必须能回指需求、设计或经批准的缺陷修复。

## 3. System Requirement Matrix

| Requirement | Priority | Architecture | Data Model | Interface | Verification | Acceptance |
|---|---|---|---|---|---|---|
| SYS-001 Source registration | P0 | Evidence/Source | DM-001 | SourceProvider | V-SRC-001 | AT-SRC-001 |
| SYS-002 Document version/integrity | P0 | Evidence | DM-002 | SourceProvider | V-DOC-001 | AT-DOC-001 |
| SYS-003 Evidence定位 | P0 | Evidence | DM-003 | KnowledgeCompiler/EvidenceStore | V-EVD-001 | AT-EVD-001 |
| SYS-004 Assertion canonical unit | P0 | Knowledge Core | DM-005 | AssertionStore | V-AST-001 | AT-AST-001 |
| SYS-005 Evidence required | P0 | Governance | DM-003/005 | AssertionValidator | V-AST-002 | AT-AST-002 |
| SYS-006 epistemic status | P0 | Knowledge Governance | DM-005 | AssertionValidator | V-AST-003 | AT-AST-003 |
| SYS-007 Entity/Relation/Event/State | P0 | Semantic Runtime | DM-006/007/008/009 | SemanticGraph | V-SEM-001 | AT-SEM-001 |
| SYS-008 Graph projection | P0 | Semantic Runtime | DM-005/006/007 | SemanticGraph | V-GRAPH-001 | AT-GRAPH-001 |
| SYS-009 Ontology versioning | P1 | Semantic | DM-010 | OntologyService | V-ONT-001 | AT-ONT-001 |
| SYS-010 Explainable reasoning | P1 | Reasoning | DM-011/012 | ReasoningEngine | V-REA-001 | AT-REA-001 |
| SYS-011 Provenance | P0 | Evidence/Governance | DM-003/005/012 | Provenance interfaces | V-PROV-001 | AT-PROV-001 |
| SYS-012 Retrieval channels | P1 | Knowledge Runtime | — | RetrievalEngine | V-RET-001 | AT-RET-001 |
| SYS-013 Evidence sufficiency/abstain | P0 | Knowledge Runtime | DM-003/005/014 | ContextEngine | V-ANS-001 | AT-ANS-001 |
| SYS-014 AgentContext | P0 | Cognitive Runtime | DM-014 | ContextEngine | V-CTX-001 | AT-CTX-001 |
| SYS-015 Knowledge/State/Memory separation | P1 | Cognitive/Knowledge | DM-005/009/013 | StateStore/MemoryStore | V-SEP-001 | AT-SEP-001 |
| SYS-016 Decision trace | P1 | Agent Runtime | DM-016 | DecisionEngine | V-DEC-001 | AT-DEC-001 |
| SYS-017 Observation→State Update | P1 | Agent Runtime | DM-009/018 | ObservationStore | V-OBS-001 | AT-OBS-001 |
| SYS-018 Golden regression | P1 | Evaluation Plane | — | Evaluation Engine | V-EVAL-001 | AT-EVAL-001 |
| SYS-019 Schema/migration | P0 | Operations | All Canonical | Schema Registry | V-MIG-001 | AT-MIG-001 |
| SYS-020 provider neutrality | P1 | Platform | — | All provider interfaces | V-SUB-001 | AT-SUB-001 |

## 4. Canonical Data Model Traceability

| Data Model | Requirement | Interface | Minimum Test |
|---|---|---|---|
| DM-001 Source | SYS-001 | SourceProvider | T-SOURCE-001 |
| DM-002 Document | SYS-002 | SourceProvider | T-DOC-001 |
| DM-003 Evidence | SYS-003, SYS-005, SYS-011 | EvidenceStore | T-EVD-001..003 |
| DM-004 SemanticUnit | SYS-003, compiler requirements | KnowledgeCompiler | T-UNIT-001 |
| DM-005 Assertion | SYS-004..006 | AssertionStore/Validator | T-AST-001..006 |
| DM-006 Entity | SYS-007 | SemanticGraph | T-ENT-001 |
| DM-007 Relation | SYS-007, SYS-008 | SemanticGraph | T-REL-001 |
| DM-008 Event | SYS-007, SYS-017 | SemanticGraph/ObservationStore | T-EVT-001 |
| DM-009 State | SYS-007, SYS-015, SYS-017 | StateStore | T-STATE-001..003 |
| DM-010 Ontology | SYS-009 | OntologyService | T-ONT-001..002 |
| DM-011 Rule | SYS-010 | ReasoningEngine | T-RULE-001 |
| DM-012 ReasoningTrace | SYS-010, SYS-016 | ReasoningEngine | T-TRACE-001 |
| DM-013 Memory | SYS-015 | MemoryStore | T-MEM-001 |
| DM-014 Context | SYS-013, SYS-014 | ContextEngine | T-CTX-001..003 |
| DM-015 Goal | SYS-016/017 | AgentRuntime | T-GOAL-001 |
| DM-016 Decision | SYS-016 | DecisionEngine | T-DEC-001 |
| DM-017 Action | SYS-016/017 | AgentRuntime/Policy | T-ACT-001 |
| DM-018 Observation | SYS-017 | ObservationStore | T-OBS-001 |

## 5. ICD Traceability

| Interface | Consumer | Provider | Contract Test | Integration Test |
|---|---|---|---|---|
| SourceProvider | Compiler | Connector | C-SRC-001 | I-SRC-001 |
| KnowledgeCompiler | Validator | Compiler | C-COMP-001 | I-COMP-001 |
| AssertionValidator | Store | Governance | C-AST-001 | I-AST-001 |
| AssertionStore | Graph/Runtime | Canonical Store | C-STORE-001 | I-STORE-001 |
| SemanticGraph | Retrieval/Reasoning | Semantic Runtime | C-GRAPH-001 | I-GRAPH-001 |
| RetrievalEngine | Context | Retrieval | C-RET-001 | I-RET-001 |
| ReasoningEngine | Context | Reasoning | C-REA-001 | I-REA-001 |
| ContextEngine | Agent | Runtime | C-CTX-001 | I-CTX-001 |
| MemoryStore | Context/Agent | Memory | C-MEM-001 | I-MEM-001 |
| StateStore | Agent/Observation | State | C-STATE-001 | I-STATE-001 |
| DecisionEngine | Agent | Decision | C-DEC-001 | I-DEC-001 |
| ObservationStore | State/Memory | Observation | C-OBS-001 | I-OBS-001 |

## 6. Verification Classification

- UT: Unit Test
- CT: Contract Test
- IT: Integration Test
- ST: System Test
- E2E: End-to-End
- GT: Golden Test
- PT: Performance Test
- SEC: Security Test
- REC: Recovery Test

## 7. Release Traceability Rule

A release candidate is eligible only when:

```text
All P0 requirements → verification PASS
All P1 requirements → verification PASS or approved waiver
No unresolved P0 defect
Canonical invariants = PASS
Golden regression = PASS
Security gate = PASS
Recovery gate = PASS
```

## 8. Bidirectional Review Checklist

### Requirement → Test
- 每个P0/P1需求都有验证用例。
- Acceptance criteria可以自动或人工明确判定。

### Test → Requirement
- 每个核心测试均能回指至少一个需求或Invariant。
- 孤立测试必须标明其目的，否则不得成为发布门禁。

### Code → Requirement
- 核心代码变更必须引用需求/设计/缺陷ID。

### Architecture → Requirement
- 架构组件不得成为无需求依据的永久系统负担；新增组件应记录ADR。
