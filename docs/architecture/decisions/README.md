# Architecture Decision Records - Index

> 本目录是 Agentic Knowledge Base 的架构决策记录（ADR）唯一存放处。
> 基线：SRS V1.1 / Data Model V1.0 / ICD V1.0 / V&V Plan V1.0 / RTM V1.0 / Golden Dataset V1.0。
> 状态约定：Proposed -> Accepted -> Superseded。
> **2026-09-01：Architecture Baseline Acceptance（AR-V1.0 APPROVED）通过，ADR-001..010 全部 Accepted。**
> 批准记录：[ARCHITECTURE_ACCEPTANCE_V1.0.md](../reviews/ARCHITECTURE_ACCEPTANCE_V1.0.md)。

## ADR Index

| ADR | 标题 | Status | 一句话决策 |
|---|---|---|---|
| ADR-001 | KnowledgeAssertion is the Canonical Knowledge Unit | Accepted | KnowledgeAssertion（DM-005）是唯一 Canonical 知识单元；Fact/Graph Edge/Embedding/Chunk 都不是 |
| ADR-002 | Graph is a Projection of Canonical Assertions | Accepted | Graph 是断言的投影，可重建可删除；边必须带 assertion_ref（INV-003） |
| ADR-003 | Evidence First | Accepted | 无证据则无 asserted 知识；但 candidate/observed/hypothesized/inferred 合法存在（epistemic boundary） |
| ADR-004 | Asserted vs Derived Separation | Accepted | 断言类型+状态双轴强制分离；derived 必带 derivation 块，禁止自动晋升 |
| ADR-005 | Canonical Store vs Projections | Accepted | Canonical 8 类对象 vs 5 类投影；恢复顺序 Canonical -> Projection -> Cache |
| ADR-006 | Semantica as Semantic Runtime Foundation | Accepted | Semantica 是实现候选（机制层复用），其 KnowledgeGraph 不得直接当 Canonical Model |
| ADR-007 | KB1 as Epistemic Governance Reference | Accepted | 采纳 KB1 的治理语义（不复制代码/目录）；Graph/Storage 收敛到 AKB 接口 |
| ADR-008 | Agent Runtime Decoupling | Accepted | Agent 只依赖 ICD 接口；禁止直连 Neo4j/Qdrant/Semantica/LLM SDK |
| ADR-009 | Provider Neutrality | Accepted | 七类 provider 全接口隔离；Canonical 禁止 provider 字段作核心语义 |
| ADR-010 | V-Model + Local-AI Workflow | Accepted | 冻结 Design -> GitHub -> Local AI -> Implementation -> Tests -> Review 开发方式 |

（表格内文件链接：ADR-001.md 同目录命名 ADR-001-canonical-assertion.md，依此类推，见下"文件清单"）

## 文件清单

- [ADR-001-canonical-assertion.md](ADR-001-canonical-assertion.md)
- [ADR-002-graph-as-projection.md](ADR-002-graph-as-projection.md)
- [ADR-003-evidence-first.md](ADR-003-evidence-first.md)
- [ADR-004-asserted-derived-separation.md](ADR-004-asserted-derived-separation.md)
- [ADR-005-canonical-vs-projections.md](ADR-005-canonical-vs-projections.md)
- [ADR-006-semantica-semantic-runtime.md](ADR-006-semantica-semantic-runtime.md)
- [ADR-007-kb1-epistemic-governance.md](ADR-007-kb1-epistemic-governance.md)
- [ADR-008-agent-runtime-decoupling.md](ADR-008-agent-runtime-decoupling.md)
- [ADR-009-provider-neutrality.md](ADR-009-provider-neutrality.md)
- [ADR-010-vmodel-local-ai-workflow.md](ADR-010-vmodel-local-ai-workflow.md)

## 状态流转

Proposed --(Architecture Review 批准)--> Accepted
   |
   +--(被新决策取代)------------------> Superseded

## 与不变量的对应

| 不变量 | 相关 ADR |
|---|---|
| INV-001 Evidence Gate | ADR-003 |
| INV-002 Derived Isolation | ADR-004 |
| INV-003 Graph Traceability | ADR-002 |
| INV-004 Evidence Traceability | ADR-001, ADR-003 |
| INV-005 History Integrity | ADR-003, ADR-005 |
| INV-006 Index Independence | ADR-005, ADR-009 |
| INV-007 LLM Governance Gate | ADR-003, ADR-006 |
| INV-008 Agent Write Boundary | ADR-008 |
| INV-009 Memory Promotion Gate | ADR-004, ADR-008 |
| INV-010 Action Policy Gate | ADR-008, ADR-010 |

> 完整定义见 [INVARIANT_REGISTRY_V1.0](../INVARIANT_REGISTRY_V1.0.md)（唯一权威来源）。

## 已识别的架构缺口（Architecture Gaps）

ADR 落地时发现当前代码与目标态的差距（V0.1 待办，本任务不改生产代码）：

| Gap | 当前态 | 目标态 | 涉及 ADR |
|---|---|---|---|
| graph_edges 无 assertion_ref 列 | edges 只有 origin 元数据 | 每条边可反查断言 | ADR-002 |
| 无 Assertion/ReasoningTrace 对象 | facts/cards 是弱对应物 | DM-005/012 对象级实现 | ADR-001, ADR-004 |
| 状态迁移无审计记录 | 无 transition 日志 | actor/timestamp/reason/policy_version | ADR-003, ADR-004 |
| agent 平面无 import 边界 lint | 无静态检查 | 禁止直连 graph/vector/LLM SDK | ADR-008 |

## 参考流程

SRS V1.1 -> Data Model V1.0 -> ICD V1.0 -> V&V Plan V1.0 -> RTM V1.0
-> Golden Dataset V1.0 -> ADR V1.0（本目录）-> Architecture Review
-> V0.1 Evidence Core Detailed Design