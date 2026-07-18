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

## 当前能力

### Phase 1：架构骨架

- domain pack loader
- query frame schema
- object projection schema
- retrieval card schema
- context pack schema
- generic + obc_dcdc 示例 domain pack
- 架构说明与迁移计划

### Phase 2：通用文档编译

```text
plain text
  -> DocumentRecord
  -> EvidenceBlock
  -> SourceUnit
  -> Fact
  -> KnowledgeCompilation
```

该链路可以在没有领域包的情况下抽取 generic fact；在加载领域包时，可用 terminology 把文本中的别名链接到 canonical subject。

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

当前实现包括：

- object-card retrieval
- fact retrieval
- table retrieval
- evidence retrieval
- keyword retrieval
- domain-alias semantic fallback
- 显式 skipped-channel diagnostics
- Hit@K
- Mean Reciprocal Rank
- object/card/fact/evidence recall
- golden-case evaluation CLI

当前 `semantic` channel 是无外部依赖的领域对象/别名语义回退，不代表已接入 embedding/vector provider。

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

Phase 5 已加入：

- SQLite 持久化对象、Retrieval Card、Fact 和 Evidence
- FTS5 检索与无 FTS5 环境下的 LIKE 回退
- 持久化索引重建
- 内存召回与持久化检索的混合融合
- 可插拔 `Reranker` 接口及确定性基线实现
- `sufficient / partial / insufficient` 证据充分性判断
- retrieval run 审计记录
- 用户反馈持久化

## CLI

编译文档并生成带召回诊断的 Context Pack：

```bash
agent-kb compile-context \
  --text-file ./sample.txt \
  --query "输出纹波要求是多少？" \
  --domain-dir ./domains/obc_dcdc \
  --retrieval-top-k 12
```

运行召回评测：

```bash
agent-kb eval-retrieval \
  --text-file ./sample.txt \
  --cases-file ./golden_cases.json \
  --domain-dir ./domains/obc_dcdc
```

编译并写入持久化索引：

```bash
agent-kb index-text \
  --text-file ./sample.txt \
  --db ./agent-kb.sqlite3 \
  --domain-dir ./domains/obc_dcdc
```

查询持久化索引：

```bash
agent-kb query-store \
  --db ./agent-kb.sqlite3 \
  --query "输出纹波要求是多少？" \
  --domain-dir ./domains/obc_dcdc
```

提交检索反馈：

```bash
agent-kb feedback \
  --db ./agent-kb.sqlite3 \
  --run-id run_xxx \
  --rating 1 \
  --comment "retrieval is relevant"
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
    evaluation/
    context/
    storage/
    pipeline/
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

Phase 6 应在当前持久化、可评测基线上增加生产适配层：

```text
embedding provider interface
  + vector index adapter
  + graph persistence/traversal
  + service/API layer
  + schema migrations and document lifecycle
  + feedback-driven evaluation
```

任何新检索适配器必须继续输出现有 `RetrievalResult`，并通过同一套 golden evaluation contracts 对比效果。
