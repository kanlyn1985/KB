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

## 当前 MVP 能力

Phase 1 已完成架构骨架：

- domain pack loader
- query frame schema
- object projection schema
- retrieval card schema
- context pack schema
- generic + obc_dcdc 示例 domain pack
- 架构说明与迁移计划

Phase 2 已加入第一条可执行编译链：

```text
plain text
  -> DocumentRecord
  -> EvidenceBlock
  -> SourceUnit
  -> Fact
  -> KnowledgeCompilation
```

该链路可以在没有领域包的情况下抽取 generic fact；在加载领域包时，可用 terminology 把文本中的别名链接到 canonical subject。

Phase 3 已把编译结果接入 Agent Context Pack：

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

CLI：

```bash
agent-kb compile-context \
  --text-file ./sample.txt \
  --query "输出纹波要求是多少？" \
  --domain-dir ./domains/obc_dcdc
```

## 当前目录

```text
agent_kb_core/
  docs/
  src/agent_kb/
  domains/
  tests/
```

## 本地验证

```bash
cd agent_kb_core
python -m pytest
```

## 下一步

Phase 4 建议开始迁移旧项目中的真实查询能力：

```text
retrieval router / FTS adapter / reranker / evidence judge / eval golden suite
```

Phase 4 的目标不是引入更多业务插件，而是让 Phase 3 的 in-memory RetrievalCard/ContextPack 可以接入可评测的多路召回链路。
