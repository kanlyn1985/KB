---
doc_type: requirement
slug: retrieval-quality-loop
pitch: 让每次查询都能解释为什么找到或没找到正确内容。
status: current
last_reviewed: 2026-05-09
implemented_by:
  - query-chain-architecture
tags:
  - retrieval
  - graph
  - query-rewrite
---

# 召回质量闭环

## 用户故事

- 作为调试者，我希望看到 query rewrite、routing、graph、rerank 的完整链路，而不是只看到最终答案。
- 作为知识库维护者，我希望每次查询都有 retrieval_runs 记录，方便复盘错误召回。
- 作为评测者，我希望能用 Recall@5、MRR、negative_hit_rate 判断召回质量，而不是凭感觉判断。

## 为什么需要

用户问法千变万化，召回失败可能来自改写、图谱、路由、排序或入库缺口。没有召回闭环，系统优化会退化成针对失败样例打补丁。

## 怎么解决

系统把用户问题转成结构化查询计划，经过 rewrite、expansion、topic resolution、graph candidates、routing、rerank 形成 context，并记录 retrieval_runs。失败时可以根据 must_hit、negative hit 和排名指标归因。

## 边界

- 不让 LLM 直接决定最终事实。
- 不把召回分数等同于答案正确。
- 对短缩写和歧义问题必须先保留锚点或要求澄清。
