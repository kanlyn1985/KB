---
doc_type: architecture-index
slug: architecture
status: current
last_reviewed: 2026-05-09
summary: KB1 architecture entrypoint
tags:
  - kb1
  - architecture
  - codestable
---

# KB1 架构总入口

> 状态：骨架（待填充）
> 创建日期：2026-05-09

## 1. 项目简介

KB1 是面向企业标准文档和工程知识库的本地单机知识底座。系统将 PDF、Markdown、文本等文档编译为 evidence、facts、entities、wiki、graph 和 source_units，再支撑自然语言查询、证据约束答案和回归评测。

## 2. 核心概念 / 术语表

- `source_units`：入库覆盖的最小可追踪单元，用于证明文档内容是否进入知识库。
- `evidence`：来自文档块或结构化解析的证据片段，是事实和答案引用的基础。
- `facts`：从 evidence 归纳出的结构化知识，必须保留来源链路。
- `entities` / `wiki_pages`：面向概念、过程、参数和术语的主题对象与可读知识页。
- `graph_edges`：实体、事实、wiki 和文档单元之间的关系边，用于召回增强与解释。
- `golden_cases` / `eval_runs` / `eval_results`：回归闭环的测试样例、运行记录和结果归因。

## 3. 子系统 / 模块索引

- 入库闭环：`enterprise_agent_kb.ingest`、`enterprise_agent_kb.document_pipeline`、`enterprise_agent_kb.evidence`、`enterprise_agent_kb.facts`、`enterprise_agent_kb.coverage_*`。
- 召回闭环：`query_rewrite`、`query_expansion`、`advanced_query_planner`、`topic_resolution`、`graph_retrieval`、`retrieval_router`、`reranker`、`query_api`。
- 答案闭环：`query_ambiguity`、`evidence_judge`、`answer_policy`、`answer_api`。
- 回归闭环：`golden_cases`、`eval_*`、`closed_loop_*`、`tests/test_query_repair_regression.py`。
- 操作入口：`enterprise_agent_kb.cli`，本地 API 入口通过 `serve-api` 启动。

## 4. 关键架构决定

- LLM 只做查询规划、扩写、证据裁判等中间判断，最终事实必须经过规则校验和候选集合约束。
- 短缩写、短问题和多义问题先进入歧义澄清或规则回退，不允许直接由 LLM 猜最终含义。
- 检索链路保留 `retrieval_runs` 元数据，便于定位 query rewrite、routing、graph、rerank 和 answer policy 的责任边界。
- 数据模型必须保持 `evidence -> facts -> wiki/graph` 的可追踪关系，schema 变更优先使用增量迁移。

## 5. 已知约束 / 硬边界

- 当前目标是单机本地执行，暂不引入分布式依赖。
- CLI 查询命令必须显式使用 `--query`，知识库根目录必须显式使用 `--root knowledge_base`。
- PowerShell 中文输入存在编码风险，自动化验证优先使用 Python Unicode escape 或 HTTP JSON。
- `.codestable/attention.md` 是 CodeStable 技能启动必读的运行约定入口；涉及命令、路径、环境变量的经验应优先沉淀到该文件。
