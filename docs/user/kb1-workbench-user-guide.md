---
doc_type: user-guide
slug: kb1-workbench-user-guide
component: kb1-workbench
status: current
summary: KB1 工作台的文档入库、查询调试、答案验证和回归查看指南
tags:
  - kb1
  - workbench
  - query
  - regression
last_reviewed: 2026-05-09
---

# KB1 Workbench User Guide

## 功能简介

KB1 工作台用于把标准文档导入本地知识库，并验证用户问题是否能找到正确证据、生成可信答案和进入回归闭环。

工作台地址：

```text
http://127.0.0.1:8000/demo
```

## 前置条件

- 本地 API 已启动。
- 知识库根目录为 `knowledge_base`。
- 服务健康检查 `http://127.0.0.1:8000/health` 返回 `status=ok`。

启动命令：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base serve-api --host 127.0.0.1 --port 8000
```

## 如何使用

### 导入新文档

1. 打开 `http://127.0.0.1:8000/demo`。
2. 在导入与构建区域选择 PDF 文件。
3. 先使用“上传并转换”检查解析效果。
4. 解析正常后使用“上传并构建”入库。
5. 需要完整验收时使用“上传并构建+测试”。

入口含义：

| 入口 | 用途 | 是否入库 | 是否测试 |
|---|---|---:|---:|
| 上传并转换 | 只验证 PDF 解析和中间结构 | 否 | 否 |
| 上传并构建 | 解析、入库、生成 evidence/facts/wiki/graph | 是 | 否 |
| 上传并构建+测试 | 构建后生成并执行 golden 测试 | 是 | 是 |

### 查询一个问题

1. 在 Query Lab 或查询区域输入用户问题。
2. 先看答案区的 `answer_mode` 和直接答案。
3. 再查看 Raw retrieval metadata。
4. 确认 `rewrite`、`query_expansion`、`topic_resolution`、`retrieval_plan` 和 `evidence_judgement` 是否符合预期。

常用判断：

| 字段 | 重点看什么 |
|---|---|
| `rewrite.query_type` | 问题是否被识别成正确类型。 |
| `query_expansion.used_llm` | 是否调用了 LLM 扩写。短缩写定义问题通常不应先调用。 |
| `topic_resolution.candidate_entities` | 主题对象是否命中正确实体。 |
| `retrieval_plan.graph_candidate_count` | graph 是否提供候选增强。 |
| `evidence_judgement.sufficient` | 证据是否足够支撑答案。 |
| `answer_mode` | 答案策略是否正确。 |

### 处理歧义问题

短缩写问题如果缺少上下文，系统应先要求澄清。

示例：

```text
CP是什么意思
CC是什么意思
```

期望表现：

- `answer_mode=clarification`
- `clarification_required=true`
- 返回多个可选语境
- 用户选择后，用选项里的 `example_query` 重新查询

如果系统直接把短缩写解释成某个参数或无关术语，需要记录为查询链路问题。

### 验证试验方法问题

示例：

```text
OBC输入过压怎么测
```

期望表现：

- `answer_mode=test_method_lookup`
- 返回试验方法和步骤
- `evidence_judgement.sufficient=true`
- 直接答案不包含 `&nbsp;` 等渲染残留

### 查看回归状态

在闭环 dashboard 或 API 结果中关注四类状态：

- ingestion loop：文档是否真的进来了。
- retrieval loop：用户问法是否能召回正确内容。
- answer loop：答案是否受证据约束且可用。
- regression loop：修复是否进入 golden/eval 闭环。

状态为 `warn` 或 `fail` 时，不要直接调 prompt，先看 failure analysis 或 Raw metadata 归因。

## 常见问题

Q: 为什么 pytest 里有很多 `deselected`？

A: `deselected` 表示被 `-k` 过滤条件排除的测试，不是失败。

Q: 为什么短缩写问题不能直接回答？

A: CP、CC、PE、OBC、V2G、V2X 等缩写可能有多个语境。系统缺少上下文时直接猜会导致错误答案，应先澄清。

Q: Raw retrieval metadata 里 graph_candidate_count 是 0 是否一定错误？

A: 不一定。部分问题可以通过 routing 或 facts 命中。但如果目标对象本应在实体/图谱中存在，graph 为 0 就需要检查 topic_resolution 和 graph 构建。

Q: direct answer 干净但 supporting evidence 还有 HTML 残留怎么办？

A: 这是 evidence 展示清洗问题，应作为独立问题记录，不要混入召回或答案策略修复。

## 相关功能

- 开发者指南：`docs/dev/kb1-development-guide.md`
- 四闭环架构：`.codestable/architecture/closed-loop-architecture.md`
- 查询链路架构：`.codestable/architecture/query-chain-architecture.md`
- 四闭环强化规划：`.codestable/roadmap/kb1-four-loop-hardening/kb1-four-loop-hardening-roadmap.md`
