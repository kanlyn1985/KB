# 旧 KB 项目到 Agent KB Core 的迁移计划

## 阶段 0：当前提交

当前提交只完成新项目骨架，不迁移旧代码主体。

已完成：

- 新目录 `agent_kb_core/`
- 新包名 `agent-kb-core`
- Domain Pack schema
- Domain Pack loader
- QueryFrame model
- ObjectProjection model
- RetrievalCard model
- AgentContextPack model
- generic domain pack
- obc_dcdc domain pack 示例
- loader 单元测试

## 阶段 1：抽取通用 Core

从旧项目迁移以下模块，但要去掉领域硬编码：

```text
config / db / migration runner
document registration
parse / block / evidence builder
source_units
facts / entities / graph_edges
wiki_chunks / embeddings
retrieval / graph retrieval / reranker
evidence_judge
eval / golden / feedback
```

迁移要求：

1. 不引入 OBC/DCDC、CP/CC/PWM、汽车标准等硬编码。
2. 领域规则通过 Domain Pack 注入。
3. 所有对象、事实、关系必须能绑定 evidence。

## 阶段 2：升级查询理解

从旧项目迁移：

```text
query_semantic_parser
query_rewrite
query_expansion
advanced_query_planner
```

但输出从 `SemanticQuery / RewrittenQuery` 升级为：

```text
QueryFrame
```

新增能力：

- domain detection
- object linking
- slot extraction
- missing slot detection
- ambiguity detection
- preferred fact types
- required evidence shapes
- answer contract selection

## 阶段 3：Object Projection 与 Retrieval Card

新增编译步骤：

```text
Evidence / Fact / Entity
  → ObjectProjection
  → RetrievalCard
```

目标：让召回从“找文本”升级为“找对象”。

## 阶段 4：Context Pack API

新增主接口：

```text
build_context_pack(query, domain=None)
```

输出：

```text
QueryFrame
TargetObjects
RetrievalCards
Facts
Evidence
HiddenContext
AnswerContract
Warnings
KnowledgeGaps
RecommendedAnswerStrategy
```

## 阶段 5：OBC/DCDC 验证包

把 OBC/DCDC 作为第一个验证领域，而不是 Core 本体。

需补充：

- 50 个核心术语/参数
- 20 个 answer contracts
- 30 个 hidden context rules
- 100 条 query understanding golden cases
- 100 条 retrieval golden cases

## 阶段 6：第二领域验证

必须选择一个非汽车领域验证通用性，例如：

- company_policy
- legal_contract
- medical_device
- equipment_maintenance

判定标准：

```text
不改 Core，仅通过新 domain pack 接入第二领域。
```

## 暂不迁移

以下旧模块暂时不迁移到 Core：

```text
requirements/*
ECO
baseline
release_gate
approval
RBAC
project isolation
```

它们以后作为 plugin 接入。
