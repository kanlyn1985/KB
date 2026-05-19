---
doc_type: issue-analysis
issue: 2026-05-11-corpus-definition-term-retrieval-shape
status: draft
root_cause_type: state-pollution
related:
  - corpus-definition-term-retrieval-shape-report.md
tags:
  - retrieval
  - fts
  - evidence-shape
---

# Corpus Definition Term Retrieval Shape 根因分析

## 1. 问题定位

| 关键位置 | 说明 |
|---|---|
| `src/enterprise_agent_kb/query_api.py:201` | `build_query_context()` 先打开共享 SQLite connection，后续把该 connection 传给 graph、routing、rerank 等检索组件。 |
| `src/enterprise_agent_kb/query_api.py:217` | `route_retrieval(..., connection=connection)` 使用共享 connection 执行结构化召回。 |
| `src/enterprise_agent_kb/retrieval_router.py:89` | `_structured_hits()` 调用 `search_knowledge_base_expanded(..., connection=connection)`。 |
| `src/enterprise_agent_kb/retrieval.py:157` | `search_knowledge_base_expanded()` 只有在 `connection is None` 时才设置 `own_connection=True`。 |
| `src/enterprise_agent_kb/retrieval.py:160` | 只有自建 connection 的路径调用 `_ensure_fts_ready()`；共享 connection 路径只调用 `ensure_fts_schema()`，不会检查 FTS 是否过期。 |
| `src/enterprise_agent_kb/retrieval.py:184` | `_ensure_fts_ready()` 通过 stamp、DB mtime 和 source count 判断是否需要刷新 FTS，但该逻辑没有覆盖共享 connection 检索。 |
| `src/enterprise_agent_kb/retrieval_router.py:199` | `_direct_fact_hits()` 对 definition 查询只查 requirement/table/threshold/parameter/process/transition/section_heading，不包含 `term_definition`，因此不能补偿 FTS 漏掉的术语定义 fact。 |
| `src/enterprise_agent_kb/query_api.py:676` | `_inject_direct_term_definition_hits()` 只处理短缩写定义；普通中文术语定义不会走该兜底。 |

数据证据：

- `facts` 当前有 `FACT-113145(term_definition)`，内容为 `传导充电 conductive charge` 的定义。
- `source_units` 的 `DOC-000003:definition:10:08297070E9CA` 正确链接到 `FACT-113145`。
- 失败发生时，`facts_fts` 仍含旧的 `FACT-053433`，但该 fact 已不在 `facts` 表中。
- 失败发生时，`facts_fts` 缺少当前的 `FACT-113145`。
- `knowledge_base/db/knowledge.db` 的 mtime 晚于 `knowledge_base/logs/fts_index.stamp`，说明索引需要刷新。
- 手动执行 `refresh_fts_index(Path("knowledge_base"))` 后，同一查询 `传导充电是什么意思` 的 top hit 变为 `FACT-113145`，evidence shape 变为 `term_definition`。

## 2. 失败路径还原

**正常路径**：用户或 corpus eval 查询 `传导充电是什么意思` → rewrite 为 `definition` / target topic `传导充电` → FTS / graph / direct routing 能看到当前 `FACT-113145(term_definition)` → rerank 把目标定义排到 top → evidence judge 选择 `term_definition` → corpus case 通过。

**失败路径**：用户或 corpus eval 查询 `传导充电是什么意思` → `build_query_context()` 打开共享 connection → `route_retrieval()` 复用该 connection 调用 `search_knowledge_base_expanded()` → 因为不是 own connection，检索层没有调用 `_ensure_fts_ready()` → 过期 `facts_fts` 缺少当前 `FACT-113145`，还保留旧 `FACT-053433` → 普通中文术语又不走 `_inject_direct_term_definition_hits()` → top context 被同文档的 scope、preface、normative reference、table/requirement facts 占据 → evidence judge 在允许形状中选择 `parameter_definition` → corpus case 报 `evidence_shape_mismatch`。

**分叉点**：`src/enterprise_agent_kb/retrieval.py:157-164` — search 使用外部 connection 时跳过 FTS freshness check，导致检索基于陈旧索引运行。

## 3. 根因

**根因类型**：state-pollution

**根因描述**：FTS 索引是派生状态，事实重建后可能落后于 `facts` 表。检索模块原本有 `_ensure_fts_ready()` 用 stamp、DB mtime 和数量比对来刷新派生索引，但这个保护只覆盖 `search_knowledge_base_expanded()` 自己创建 connection 的路径。查询主链路为了复用 connection 和记录闭环元数据，把共享 connection 传入检索函数，结果绕过了 FTS 新鲜度检查。于是查询链路看到的是陈旧 `facts_fts`，不是当前 facts/source_units 状态。

**是否有多个根因**：是，主次如下。

1. 主根因：共享 connection 检索路径跳过 FTS freshness guard。
2. 次根因：definition 查询的 direct fact 兜底没有覆盖普通 `term_definition`，只覆盖短缩写定义，无法在 FTS 过期时补偿术语定义召回。
3. 次根因：definition 的 evidence shape contract 允许 `term_definition` 和 `parameter_definition`，这对 `CC阻值是什么` 等参数定义合理，但对 corpus case 明确期望 `term_definition` 的场景只能作为宽松 judge contract，不能替代 case 级严格验收。

## 4. 影响面

- **影响范围**：所有通过共享 connection 调用 `search_knowledge_base_expanded()` 的查询路径，包括 `build_query_context()`、corpus eval、API query context 和 answer query 的检索阶段。
- **潜在受害模块**：query context、answer query、corpus retrieval eval、user query eval、Workbench Query Debug、closed-loop retrieval metrics。
- **数据完整性风险**：不会破坏 facts/source_units 本体数据，但会让运行时 retrieval/eval 基于陈旧派生索引，产生误召回、误归因和错误 dashboard 指标。
- **严重程度复核**：维持 P1。它不是单个 query 的坏答案，而是派生索引新鲜度保护在主查询链路缺失，会影响一批查询和评测。

## 5. 修复方案

### 方案 A：让检索层在共享 connection 路径也执行 FTS freshness guard

- **做什么**：重构 `retrieval.py`，让 `_ensure_fts_ready()` 支持可选 connection，或拆出 `_refresh_fts_index_with_connection()`；`search_knowledge_base_expanded()` 无论是否传入 connection，都先确保 FTS 与当前 DB 状态一致。
- **优点**：从根因处修复，所有调用 `search_knowledge_base_expanded()` 的路径都受益，不依赖 query_api 单点调用约定。
- **缺点 / 风险**：刷新 FTS 会写数据库，需要小心避免在已有事务中递归开新连接导致锁冲突；测试要覆盖外部 connection 场景。
- **影响面**：`src/enterprise_agent_kb/retrieval.py`，新增/调整 retrieval 测试；可能触发 FTS refresh 成本，但只在 stamp 或 counts 过期时发生。

### 方案 B：只在 `build_query_context()` 打开共享 connection 前调用 FTS freshness guard

- **做什么**：在 `query_api.py` 中连接数据库前调用检索层的 FTS ready 函数，确保 query 主链路进入时索引已刷新。
- **优点**：改动小，锁风险低，能修复当前 API/query/corpus eval 主路径。
- **缺点 / 风险**：不是框架层彻底修复；其他未来代码若直接传 connection 调用 `search_knowledge_base_expanded()` 仍可能绕过 freshness guard。
- **影响面**：`src/enterprise_agent_kb/query_api.py`，少量测试。

### 方案 C：为普通 definition 查询增加 direct term_definition 兜底

- **做什么**：扩展 `_inject_direct_term_definition_hits()` 或 `retrieval_router._direct_fact_hits()`，让普通中文术语定义也能从 `facts` 表按 target topic / aliases 直接查 `term_definition`。
- **优点**：能增强定义类召回，对 FTS 偶发漏召回有防御价值。
- **缺点 / 风险**：只能补 definition 类查询，不解决 FTS 派生状态过期这一框架问题；如果单独做，仍是局部补丁。
- **影响面**：`query_api.py` 或 `retrieval_router.py`，需新增定义类召回回归测试。

### 推荐方案

**推荐方案 A，并把方案 C 作为后续增强而不是本 issue 主修。**

理由：本次失败的根因是派生索引新鲜度检查在共享 connection 路径被旁路。只修某个 query、某类术语或某个 rerank 权重都不能保证其他查询不再踩到陈旧 FTS。方案 A 从检索框架层修复状态一致性，符合“先找根因，不打补丁”的要求。
