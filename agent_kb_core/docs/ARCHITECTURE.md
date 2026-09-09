# Agent KB Core 重建架构

## 1. 项目目标

Agent KB Core 是一个通用知识库编译框架，用于把任意领域文档编译成可追溯、可检索、可供智能体使用的结构化知识上下文。

准确定位：

```text
Generic Evidence-grounded Agent Knowledge Compiler
```

中文定位：

```text
通用证据约束型智能体知识库编译框架
```

## 2. 为什么重建

旧项目已经具备大量有价值能力，包括文档证据链、facts、entities、graph、wiki chunks、query rewrite、LLM semantic parser、query expansion、advanced query planner、answer API、agent tools 等。

但旧项目已经混入了三类东西：

1. 通用知识库核心能力。
2. 汽车标准/充电控制导引/ASPICE 等领域特化逻辑。
3. Requirement Resolver、ECO、baseline、release gate、RBAC 等业务插件能力。

继续在原结构里扩展，会导致 Core 和领域/插件边界不清晰。因此重建采用“抽核式重建”，不是推倒重写。

## 3. 新架构分层

```text
Raw Documents
  ↓
KB Compiler Core
  ↓
Evidence / Semantic Units / Facts / Entities / Relations
  ↓
Domain Ontology Pack
  ↓
Object Projections / Retrieval Cards / Hidden Context
  ↓
Context Pack
  ↓
Agent
```

### 3.1 KB Compiler Core

Core 只负责通用机制：

- document intake
- parsing
- evidence building
- semantic unit building
- generic fact/entity/relation extraction
- indexing
- retrieval
- reranking
- evidence judging
- query understanding framework
- context pack generation
- evaluation / feedback loop

Core 不允许写死具体领域概念。

### 3.2 Domain Ontology Pack

Domain Pack 负责领域差异：

- terminology
- object types
- relation types
- extraction profiles
- answer contracts
- hidden context rules
- validation rules
- golden cases

例如：

```text
domains/obc_dcdc/
domains/legal/
domains/company_policy/
domains/medical_device/
```

### 3.3 Object Projection

Object Projection 是从通用 facts/entities/evidence 投影出的领域对象层。

```text
Evidence / Fact / Entity
  → DomainCandidate
  → ObjectProjection
```

它不是完整 ontology runtime，但提供 ontology-like 的结构化入库能力。

### 3.4 Retrieval Card

Retrieval Card 是面向召回优化的对象索引卡。

普通 chunk 只保存文本；Retrieval Card 保存对象的别名、定义、约束、关系、证据、回答形状等信息。

### 3.5 Context Pack

Context Pack 是给 Agent 的主输出，不是最终答案。

它包含：

- query frame
- detected intent
- target objects
- relevant facts
- supporting evidence
- object cards
- hidden context
- warnings
- knowledge gaps
- answer contract
- recommended answer strategy

## 4. 关键数据链

```text
Document
  ↓
EvidenceBlock
  ↓
SemanticUnit
  ↓
AtomicFact / Entity / Relation
  ↓
ObjectProjection
  ↓
RetrievalCard
  ↓
ContextPack
```

## 5. 迁移原则

从旧项目迁移时按三类处理：

### 5.1 迁移到 Core

- documents / pages / blocks / evidence schema
- source_units
- facts / entities / graph_edges
- wiki_chunks / embeddings
- retrieval / reranker
- evidence_judge
- query_semantic_parser
- query_rewrite
- query_expansion
- advanced_query_planner
- eval / golden / feedback

### 5.2 下沉到 Domain Pack

- CP / CC / PWM / control pilot 语义偏置
- OBC / DCDC 术语
- 汽车标准文档结构规则
- ASPICE 过程文档规则

### 5.3 保留为 Plugin

- requirements
- baseline
- release_gate
- ECO
- approval
- RBAC
- project isolation

## 6. MVP-1 交付目标

MVP-1 不做完整旧系统功能迁移，只做新架构骨架：

1. Domain Pack schema。
2. Domain Pack loader。
3. QueryFrame schema。
4. ObjectProjection schema。
5. RetrievalCard schema。
6. ContextPack schema。
7. generic domain pack。
8. obc_dcdc 示例 domain pack。
9. 后续迁移计划。

## 7. 成功判定

第一阶段成功标准：

```text
Core 可以不依赖 OBC/DCDC 运行；
OBC/DCDC 只作为一个 domain pack 接入；
同一个 Context Pack schema 可以服务不同领域；
新领域接入优先改 domain pack，而不是改 Core。
```
