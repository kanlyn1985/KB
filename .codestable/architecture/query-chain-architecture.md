---
doc_type: architecture
slug: query-chain-architecture
status: current
last_reviewed: 2026-05-11
implements:
  - retrieval-quality-loop
  - evidence-constrained-answer-loop
tags:
  - query
  - retrieval
  - answer
  - llm-boundary
---

# 查询与答案链路架构

## 主链路

```mermaid
flowchart TD
  U["user query"] --> A{"ambiguous short acronym?"}
  A -- yes --> CL["clarification_required"]
  A -- no --> RW["query_rewrite"]
  RW --> QE["query_expansion"]
  QE --> AP["advanced_query_planner (optional)"]
  AP --> TR["topic_resolution"]
  TR --> GR["graph_retrieval"]
  GR --> TSF["topic source facts by evidence shape"]
  TR --> RR["retrieval_router"]
  TSF --> RK["reranker"]
  RR --> RK
  RK --> CTX["query context"]
  RK --> RUN["retrieval_runs with rerank_explanations"]
  CTX --> EJ["evidence_judge"]
  EJ --> POL["answer_policy"]
  POL --> ANS["answer_api response"]
```

## LLM 边界

- Query Expansion 可以扩写检索计划，但必须保留硬锚点。
- Advanced Query Planner 默认关闭，只作为实验性多视角规划链路。
- Evidence Judge 只能在候选 fact/evidence ID 集合内裁判。
- Answer API 不允许把 LLM 输出当最终事实来源。
- 短缩写定义类查询先进入歧义澄清或规则回退，不应先交给 LLM 扩写。

## 关键入口

| 入口 | 作用 |
|---|---|
| `query_api.build_query_context` | 构建结构化召回上下文；短缩写歧义先返回 clarification context，其余查询写入 retrieval_runs。 |
| `answer_api.answer_query` | 构建可解释答案，短缩写歧义先澄清。 |
| `query_expansion.expand_query` | 结构化查询扩写，带规则准入门和 fallback。 |
| `evidence_judge.judge_evidence` | 根据 evidence shape 和候选约束判定证据是否足够。 |

## 已知边界

- `query-context` 对短缩写歧义查询返回 `clarification_required=true`，不进入 retrieval/rerank，也不写 retrieval run。
- Graph 是候选增强通道，不是最终事实裁决层。`graph_retrieval` 命中 topic entity 后必须按 query_type 的证据形状扩展到 topic wiki 的 `source_fact_ids`，例如 `lifecycle_lookup` 的 `has_process` 应优先返回带 BP 锚点的 `process_fact`，不能只返回过程概览表或章节标题。
- Graph 是否发挥作用以 `retrieval_runs.metadata_json.rerank_explanations[*].graph_source` 进入 top context 为准；closed-loop dashboard 聚合 `graph_retention_rate` 和 `graph_lost_after_rerank_runs`。
- 标准号查询包含 `GB/T`、`GBT`、`GB`、`ISO`、`IEC` 编号锚点时，topic resolution 必须优先解析 `standard` / `document` 实体；graph 不应沿 `has_process` 或 weak `relates_to_term` 扩散。
- Supporting evidence 展示清洗和 direct answer 清洗不是同一层。
