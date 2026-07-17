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

## MVP 范围

当前第一版只搭建框架骨架：

- domain pack loader
- query frame schema
- object projection schema
- retrieval card schema
- context pack schema
- generic + obc_dcdc 示例 domain pack
- 架构说明与迁移计划

后续再从旧项目迁移文档解析、证据构建、检索、重排、LLM query parser、evaluation 等模块。

## 当前目录

```text
agent_kb_core/
  docs/
  src/agent_kb/
  domains/
  tests/
```
