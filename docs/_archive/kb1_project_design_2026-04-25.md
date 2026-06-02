# KB1 项目设计方案

> 版本说明：本文档保留为 2026-04-25 阶段设计快照。当前主方案请以 `docs/kb1_current_architecture_2026-04-28.md` 为准，该版本已纳入 Query Expansion、Advanced Planner、Evidence Judge、Graph Candidate Expansion、短缩写歧义澄清、LLM 主备策略和最新回归测试体系。

## 1. 文档目的

本文档是 KB1 当前方案的独立总设计文档，用于统一描述项目目标、系统架构、数据链路、查询问答、覆盖报告、统一 Golden 测试体系、工作台 UI 和后续演进方向。

本文档不再把“入库覆盖”和“答案质量”拆成两套复杂流程，而采用当前已确认的新方案：

```text
一套 Golden Suite
  -> 覆盖召回 coverage_recall
  -> 检索质量 retrieval_quality
  -> 答案质量 answer_quality
```

也就是说，操作入口保持简单，但评估结果必须分维度展示，避免“全部通过”掩盖真实回答质量问题。

---

## 2. 项目目标

KB1 面向企业知识库、标准文档知识库和 Agent 可调用知识底座场景。

核心目标：

- 将 PDF / Markdown / 文本文档稳定入库
- 从原文构建可追溯的 evidence / facts / entities / wiki / graph
- 支持可解释检索和结构化问答
- 能回答“文档是否完整入库，哪里有漏”
- 能回答“用户真实提问是否能得到合格答案”
- 提供本地单机工作台，完成入库、覆盖、测试、查询闭环

当前版本优先满足单机运行：

- SQLite
- 本地文件工作区
- 本地 HTTP API
- 本地 Demo Workbench
- 不引入分布式依赖

---

## 3. 核心设计原则

### 3.1 可追溯

所有知识必须能沿链路追溯：

```text
source document
  -> page / block
  -> evidence
  -> fact
  -> entity / wiki / graph
  -> retrieval context
  -> answer
  -> golden / regression
```

### 3.2 覆盖优先

系统不能只统计产物数量，例如 fact_count、wiki_count。必须能说明：

- 哪些原文单元已覆盖
- 哪些原文单元漏掉
- 漏在 evidence、fact、object、wiki 还是 test 层

### 3.3 一套入口，分维度评价

测试体系不拆成两套用户操作入口。

统一使用：

```text
generate golden tests
run golden tests
```

但结果必须拆成：

- `coverage_recall`
- `retrieval_quality`
- `answer_quality`

### 3.4 先单机，后扩展

当前所有能力按单机运行设计：

- 文件系统作为 artifact store
- SQLite 作为主存储
- HTTP API / CLI / UI 共用同一工作区

后续如需多用户、多租户、队列化，可在保持数据模型不变的基础上扩展。

---

## 4. 总体架构

```text
             CLI / HTTP API / Workbench / MCP
                         |
                  Pipeline Orchestrator
                         |
    ------------------------------------------------
    |        |          |          |        |       |
 Register  Parse     Quality    Evidence  Facts  Entities
                         |          |        |       |
                         -------- Wiki / Graph ------
                                      |
                           Retrieval / Query Context
                                      |
                              Answer Policy / API
                                      |
                         Golden / Coverage / Reports
```

### 4.1 主要模块

| 模块 | 路径 | 责任 |
|---|---|---|
| CLI | `src/enterprise_agent_kb/cli.py` | 操作入口 |
| HTTP API | `src/enterprise_agent_kb/api_server.py` | Workbench 后端 |
| Workspace | `src/enterprise_agent_kb/bootstrap.py`, `config.py` | 工作区初始化和路径 |
| DB | `src/enterprise_agent_kb/db.py`, `schema.sql` | SQLite schema 和连接 |
| Parse | `parse.py` | 文档解析 |
| Quality | `quality.py` | 页面质量和风险评估 |
| Evidence | `evidence.py` | 原文证据构建 |
| Facts | `facts.py` | 事实抽取 |
| Entities | `entities.py` | 实体和参数对象建模 |
| Wiki | `wiki_compiler.py` | wiki 页面生成 |
| Graph | `graph.py` | 关系边构建 |
| Query | `query_rewrite.py`, `query_api.py`, `topic_resolution.py` | 查询理解和上下文 |
| Answer | `answer_policy.py`, `answer_api.py` | 答案策略和输出 |
| Coverage | `coverage.py` | source unit 覆盖矩阵 |
| Tests | `generated_tests.py` | Golden 生成与执行 |
| UI | `examples/demo.html` | 本地工作台 |

---

## 5. 工作区与数据存储

默认工作区：

```text
knowledge_base/
  raw/
  normalized/
  evidence/
  facts/
  wiki/
  coverage_reports/
  review_queue/
  quality_reports/
  logs/
  db/
    knowledge.db
```

核心数据库对象：

- `documents`
- `pages`
- `blocks`
- `evidence`
- `facts`
- `fact_evidence_map`
- `entities`
- `wiki_pages`
- `graph_edges`
- `jobs`
- `audit_log`

设计要求：

- schema 变更优先使用 additive migration
- 不通过 destructive reset 解决数据残留问题
- 重建文档时必须能清理不用的旧产物
- 每个阶段保留质量、置信度、来源页码等 metadata

---

## 6. 入库流水线

标准入库流程：

```text
register
  -> parse
  -> quality
  -> evidence
  -> facts
  -> entities
  -> wiki
  -> graph
  -> coverage
  -> golden generate
  -> golden run
```

### 6.1 register

职责：

- 注册源文档
- 记录 doc_id、文件名、类型、页数
- 保存 raw 文件

### 6.2 parse

职责：

- 将 PDF / Markdown / 文本解析成 pages / blocks
- 保留页码和文本块位置
- 对表格、标题、正文尽量保留结构

### 6.3 quality

职责：

- 评估页面是否可读
- 标记 OCR 风险、空页、结构异常页
- 输出质量状态

### 6.4 evidence

职责：

- 从 page/block 生成可检索证据
- 保留 doc_id、page_no、normalized_text、confidence

### 6.5 facts

职责：

- 从 evidence 中抽取结构化事实
- 支持标准号、日期、术语定义、章节、参数值、要求、时序等事实类型

### 6.6 entities / wiki / graph

职责：

- 将事实归并为术语、标准、参数对象、参数组、流程、约束等实体
- 生成 wiki 页面
- 建立文档、事实、实体之间的关系边

---

## 7. 查询与问答设计

查询链路：

```text
query
  -> semantic parse
  -> rewrite
  -> topic resolution
  -> retrieval routing
  -> rerank
  -> answer policy
  -> direct answer + evidence
```

### 7.1 query rewrite

职责：

- 识别 query_type
- 提取 normalized_query
- 提取 target_topic
- 保护关键锚点，例如 `CC`、`CC阻值`、`CP占空比`、`检测点1电压`

当前重点：

- 定义型问题：`什么是X`、`X是什么意思`、`X代表什么意思`
- 参数解释型问题：`CC阻值代表什么意思`
- 参数值型问题：`CC阻值是多少`
- 标准和日期型问题：标准号、发布日期、实施日期

### 7.2 topic resolution

职责：

- 将 query target 映射到实体或 wiki 对象
- 对参数类对象优先匹配 `parameter_topic`
- 对缩写定义问题支持 `term` 中的独立缩写锚点，例如 `connection confirm function; CC`

### 7.3 answer policy

职责：

- 根据 query_type 和目标对象选择答案策略
- 输出 direct_answer、summary、supporting_facts、supporting_evidence

当前已有策略：

- `definition`
- `parameter_meaning`
- `standard_lookup`
- `lifecycle_lookup`
- `constraint`
- `comparison`
- `general_search`

后续应补强：

- `parameter_value`
- 多对象比较
- 多跳解释
- 更严格的 forbidden answer 检查

---

## 8. Source Unit 覆盖模型

覆盖模型回答：

> 原文是否完整入库，哪里有漏，漏在哪一层？

完整链路：

```text
source unit
  -> evidence coverage
  -> fact coverage
  -> object coverage
  -> wiki / graph coverage
  -> golden / regression coverage
```

### 8.1 Source Unit 类型

v0 优先覆盖：

- `definition_unit`
- `parameter_row_unit`
- `requirement_unit`

后续扩展：

- `process_step_unit`
- `table_unit`
- `figure_unit`
- `section_summary_unit`
- `metadata_unit`

### 8.2 Coverage 输出

覆盖报告产物：

```text
knowledge_base/coverage_reports/{doc_id}.source_units.json
knowledge_base/coverage_reports/{doc_id}.coverage_matrix.json
knowledge_base/coverage_reports/{doc_id}.uncovered_units.json
knowledge_base/coverage_reports/{doc_id}.coverage_report.md
```

### 8.3 Coverage 状态

典型状态：

- `fully_covered`
- `evidence_only`
- `fact_missing`
- `object_missing`
- `wiki_missing`
- `test_missing`
- `misaligned`

### 8.4 标准文档 Chunk 策略

标准、规范、技术手册这类结构化文档不应简单按固定 token 切分。

推荐优先级：

```text
章
  -> 条
  -> 款
  -> 图表
  -> 附录
```

关键要求：

- 条款号必须进入正文索引和 metadata
- 图表不能脱离前后正文和图注/表注
- 附录应作为独立高价值区域处理
- 同一工程问题可能需要召回多个条款或图表

每个 chunk 至少保留：

```json
{
  "doc_title": "文档标题",
  "chapter": "章标题",
  "section": "条款标题",
  "clause_no": "条款号",
  "page_start": 15,
  "page_end": 16,
  "content_type": "definition | requirement | figure | table | appendix",
  "figure_no": "图号",
  "table_no": "",
  "keywords": ["关键词1", "关键词2"]
}
```

如果 chunk 策略不保留这些结构，`retrieval_quality` 会出现系统性失败：

- 图表问题召回不到图页
- 附录问题召回不到附录
- 条款定位问题只召回相邻正文
- 对比问题只召回单一片段

---

## 9. 统一 Golden 测试体系

### 9.1 总原则

不拆成两套测试。

统一文件：

```text
tests/generated/{doc_id}.golden.json
```

统一入口：

```text
generate_golden_tests_for_document()
run_golden_tests_for_document()
```

统一 UI：

```text
Golden / Regression
  -> Run full golden
```

但结果按三个维度展示：

```text
coverage_recall
retrieval_quality
answer_quality
```

### 9.2 coverage_recall

对应：

```text
assert_mode = context_contains
```

目的：

- 验证原文片段能被检索上下文召回
- 验证 source unit 没有从入库链路中丢失
- 支撑覆盖矩阵统计

不保证：

- 最终回答自然
- answer policy 正确
- 用户真实问法覆盖充分
- 用户真实问题能否召回正确条款

示例：

```json
{
  "kind": "page_coverage",
  "query": "第20页 3.2.20 剩余电流保护器 residual current device...",
  "must_include": "剩余电流保护器 residual current device",
  "assert_mode": "context_contains"
}
```

### 9.3 retrieval_quality

对应：

```text
assert_mode = retrieval_quality
```

目的：

- 验证用户自然问题能否召回标准文档中真正相关的条款、定义、图表、表格和附录
- 验证 reranker 是否把核心片段排在前 K 个结果里
- 验证容易混淆的问题是否不会误召回表面相似但语义错误的内容

这类测试是所有已入库文档的主召回黄金集。不同文档类型使用不同生成配方：

- 标准 / 规范：术语、条款、图表、附录、对比、场景化问题
- 技术方案 / 手册：模块、流程、接口、配置、限制、故障处理
- 学术 / 报告：观点、结论、数据、章节摘要、引用来源
- Markdown / 轻量文档：标题结构、关键段落、配置项、示例代码

它不直接评价大模型回答是否优雅，而是评价：

```text
user_query -> retrieved chunks / pages / clauses
```

推荐字段：

```json
{
  "query_id": "DOC-xxxxx_RQ001",
  "user_query": "充电枪插上后车和桩怎么确认状态？",
  "query_type": "scenario",
  "difficulty": "medium",
  "expected_doc": "DOC-xxxxx",
  "expected_sections": ["控制导引", "连接确认功能"],
  "expected_pages": [20, 53, 60],
  "must_hit": ["连接确认功能", "控制导引"],
  "nice_to_hit": ["状态转换", "检测点电压"],
  "negative_expected": ["V2G", "汽车电源逆变器"],
  "answer_hint": "连接确认功能用于反映车辆插头连接到车辆和/或供电插头连接到供电设备上的状态。"
}
```

评估指标：

- `Recall@5`
- `Recall@10`
- `MRR`
- 后续可加入 `nDCG@5` / `nDCG@10`

推荐阈值：

```text
Recall@5 >= 85%
Recall@10 >= 90%
MRR 越高越好，重点关注核心片段是否进入前 3-5 个结果
```

#### 全库 retrieval_quality 构成

retrieval_quality 不是只为单一文档设计，而是针对所有已入库文档按类型生成。

单文档建议规模：

| 文档规模 | 建议 retrieval_quality 数量 |
|---|---:|
| 1-10 页 | 5-15 |
| 11-50 页 | 20-50 |
| 51-150 页 | 50-100 |
| 150 页以上 | 80-150 |

全库建议先做分阶段覆盖：

```text
v0:
  每个已入库文档至少 5-10 条 retrieval_quality
  高价值文档 50-100 条

v1:
  所有文档按文档类型达到最低样本数
  高价值文档加入人工确认 must_hit

v2:
  全库 Recall@5 / Recall@10 / MRR 常态化
```

标准 / 规范类文档推荐比例：

推荐比例：

| 类型 | 数量 | 目的 |
|---|---:|---|
| 术语定义类 | 15 | 验证术语定义召回 |
| 条款定位类 | 15-20 | 验证具体要求和条款定位 |
| 对比类 | 10-15 | 验证多片段召回 |
| 场景化工程问题 | 15-20 | 验证真实研发提问 |
| 图表/表格问题 | 10 | 验证图、表、图注、表注召回 |
| 附录类问题 | 10 | 验证附录工程内容 |
| 口语化/模糊问法 | 5 | 验证语义召回 |
| 易混淆/负样本 | 5 | 验证误召回控制 |

技术方案 / 手册类文档推荐比例：

| 类型 | 数量占比 | 目的 |
|---|---:|---|
| 模块/组件定位 | 20% | 验证模块说明召回 |
| 流程/步骤类 | 20% | 验证操作流程、状态流转 |
| 接口/参数类 | 20% | 验证配置项、字段、参数 |
| 约束/限制类 | 15% | 验证边界条件 |
| 场景化问题 | 15% | 验证真实使用问题 |
| 负样本/易混淆 | 10% | 验证误召回控制 |

报告 / 论文类文档推荐比例：

| 类型 | 数量占比 | 目的 |
|---|---:|---|
| 结论/观点类 | 25% | 验证核心结论召回 |
| 数据/实验类 | 20% | 验证表格、数据段召回 |
| 背景/定义类 | 15% | 验证概念召回 |
| 方法/过程类 | 20% | 验证方法章节召回 |
| 引用/来源类 | 10% | 验证出处召回 |
| 负样本/易混淆 | 10% | 验证误召回控制 |

样例：

```json
{
  "query_id": "DOC-xxxxx_RQ023",
  "user_query": "模式 2、模式 3、模式 4 的差异是什么？",
  "query_type": "comparison",
  "difficulty": "medium",
  "expected_doc": "DOC-xxxxx",
  "expected_sections": ["充电模式"],
  "must_hit": ["模式 2", "模式 3", "模式 4"],
  "nice_to_hit": ["交流充电", "直流充电"],
  "negative_expected": ["连接方式 A", "连接方式 B"],
  "assert_mode": "retrieval_quality"
}
```

```json
{
  "query_id": "DOC-xxxxx_RQ041",
  "user_query": "快充桩和车之间有哪些东西在交互？",
  "query_type": "scenario",
  "difficulty": "hard",
  "expected_doc": "DOC-xxxxx",
  "expected_sections": ["直流充电系统", "控制导引", "通信"],
  "must_hit": ["直流充电系统", "车辆接口", "供电设备"],
  "nice_to_hit": ["控制导引", "图 7"],
  "negative_expected": ["V2G"],
  "assert_mode": "retrieval_quality"
}
```

### 9.4 answer_quality

对应：

```text
assert_mode = rich_answer
```

目的：

- 验证最终答案包含关键答案
- 验证 query rewrite / topic resolution / answer policy 是否协同正确
- 验证用户式提问是否能被稳定回答

示例：

```json
{
  "kind": "definition",
  "query": "CC是什么意思",
  "must_include": "连接确认功能",
  "assert_mode": "rich_answer"
}
```

后续可增强为：

```json
{
  "query": "CC是什么意思",
  "expected_answer_contains": ["连接确认功能", "反映车辆插头连接状态"],
  "forbidden_contains": ["没有找到足够", "GB：代替"],
  "expected_answer_mode": "definition",
  "min_confidence": 0.7
}
```

### 9.5 Golden Summary

`run_golden_tests_for_document()` 应返回：

```json
{
  "passed": 167,
  "failed": 0,
  "summary": {
    "coverage_recall": {
      "total": 154,
      "passed": 154,
      "failed": 0
    },
    "retrieval_quality": {
      "total": 80,
      "passed": 72,
      "failed": 8,
      "recall_at_5": 0.86,
      "recall_at_10": 0.93,
      "mrr": 0.74
    },
    "answer_quality": {
      "total": 13,
      "passed": 13,
      "failed": 0
    },
    "case_mix": {
      "context_contains": 154,
      "retrieval_quality": 80,
      "rich_answer": 13
    }
  }
}
```

解释：

- `167 passed` 不是充分结论
- 必须看其中多少是覆盖召回、检索质量、答案质量
- 如果标准文档问答召回不好，应优先提升 `retrieval_quality`，而不是直接修 answer prompt
- 如果用户反馈答案不好，应优先增加 `answer_quality` 用例，而不是继续堆 `context_contains`

---

## 10. 鲁棒性测试设计

鲁棒性测试目标：

- 用户换问法，系统能否理解
- 知识库不同知识类型是否覆盖
- 最终答案是否达标

三个主 KPI：

```text
Knowledge Coverage -> coverage_recall
Retrieval Quality -> retrieval_quality
Query / Answer Quality -> answer_quality
```

问法维度：

- 标准问法
- 口语问法
- 变体问法
- 追问式问法
- 噪声型问法

知识类型维度：

- definition
- parameter
- process
- constraint
- comparison
- standard
- document metadata

当前优先补强：

- 口语化参数解释
- 标准号和日期问题
- 缩写定义问题
- 参数值问题
- 约束和流程类问题

### 10.1 全库召回黄金集优先问题类型

针对所有已入库文档，`retrieval_quality` 应按文档类型覆盖不同问题。标准类文档可参考以下类型：

- 精确术语类：电动汽车传导充电系统、充电模式、控制导引、充电设备
- 条款定位类：模式 2 要求、连接方式 C、车辆接口/供电接口、交流/直流系统组成
- 对比类：交流 vs 直流，连接方式 A/B/C，模式 2/3/4，供电设备 vs 充电设备
- 场景化问题：OBC 接口设计、直流充电桩控制信号、连接确认、保护接地
- 图表/表格召回：连接方式图、直流系统框图、交流系统框图、设备分类示意图
- 附录类：附录 A、控制导引电路、车辆接口电路、状态转换逻辑
- 口语化问法：`充电枪插上后车和桩怎么确认状态？`
- 易混淆/负样本：模式和连接方式是否一回事、直流充电是否一定模式 4、供电设备和充电设备是否等同

这些用例的主指标是 Recall@K / MRR，不是 direct_answer 是否好看。

对非标准类文档，也必须生成 retrieval_quality，而不是只生成 page coverage：

- 技术手册：流程、接口、参数、限制、故障处理
- 方案文档：目标、架构、模块、依赖、风险、实施步骤
- 报告论文：结论、数据、方法、引用、限制
- 轻量 Markdown：标题、配置项、示例、关键段落

全库报告需要按 doc_id 聚合：

```text
retrieval_quality_by_doc:
  DOC-000001: total / passed / recall@5 / recall@10 / mrr
  DOC-000002: total / passed / recall@5 / recall@10 / mrr
  ...
```

---

## 11. Workbench UI 设计

当前 UI 是本地工作台，不是普通搜索页。

主要区域：

- 左侧文档列表和过滤器
- 中间主工作区
- 右侧文档详情、Trace、Query Debug、API Result
- 顶部全局查询框
- Query Lab
- Golden / Regression
- Coverage / Test Gaps / Drafts

### 11.1 查询范围设计

顶部查询默认是：

```text
全库
```

只有用户显式选择：

```text
当前文档
```

才传递 `preferred_doc_id`。

原因：

- 顶部查询应是全局问答
- 不能因为当前选中了某个 PDF，就隐式限制查询范围
- 否则会出现 `CC是什么意思` 被限制到不相关 V2G 文档的问题

### 11.2 Query Lab 输入设计

顶部 `globalQuery` 和 Query Lab `queryText` 使用统一状态：

```text
state.queryText
```

避免 `renderMain()` 重建 DOM 时覆盖用户正在输入的问题。

### 11.3 Answer 展示设计

主 Answer 面板展示人可读答案：

- Direct Answer
- answer_mode
- confidence
- scope
- 命中对象
- 答案摘要
- 依据事实

完整 JSON 只放在右侧：

- Query Debug
- API Result

避免用户看到“满屏代码”。

### 11.4 Golden 展示设计

Golden 面板仍然只有一个主要入口：

```text
Run full golden
```

但结果必须展示：

- 总通过/失败
- 覆盖召回
- 答案质量
- case mix

---

## 12. API 设计

核心 API：

| API | 作用 |
|---|---|
| `GET /health` | 健康检查 |
| `POST /documents` | 文档列表 |
| `POST /document-detail` | 文档详情 |
| `POST /build-document` | 构建当前文档 |
| `POST /answer-query` | 问答 |
| `POST /coverage-test-gaps` | 测试缺口候选 |
| `POST /generate-coverage-test-drafts` | 生成覆盖测试草稿 |
| `POST /validate-coverage-test-drafts` | 校验覆盖测试草稿 |
| `POST /promote-coverage-test-drafts` | 提升草稿到 Golden |
| `POST /run-coverage-promoted-tests` | 快速跑 promoted coverage tests |
| `POST /generate-golden-tests` | 生成统一 Golden |
| `POST /run-golden-tests` | 执行统一 Golden |

`/answer-query` 关键字段：

- `query`
- `limit`
- `preferred_doc_id`
- `direct_answer`
- `answer_mode`
- `confidence_score`
- `fallback_reason`
- `debug_query`
- `supporting_facts`
- `supporting_evidence`
- `topic_entities`

---

## 13. 当前已知边界

### 13.1 Golden 通过率仍可能误导

虽然已拆分 summary，但如果 `answer_quality` 数量过少，仍不能说明真实问答足够好。

必须持续关注：

```text
answer_quality / total
```

### 13.2 参数值型答案还需加强

已有：

- `parameter_meaning`

待补：

- `parameter_value`

例如：

- `CC阻值是多少`
- `检测点1电压是多少`

### 13.3 标准定义型答案仍需持续回归

例如：

- `什么是控制导引电路？`
- `CC是什么意思`
- `V2G是什么`

这些问题需要进入 `answer_quality` 主集，而不是只靠人工验证。

### 13.4 覆盖报告 v0 还不是完整语义覆盖

v0 重点是：

- definition
- parameter row
- requirement

后续再扩展流程、图、表、复杂章节。

---

## 14. 后续实施路线

### Phase 1：统一 Golden 结果稳定化

目标：

- 所有 `run_golden_tests_for_document()` 返回 summary
- UI 显示 coverage_recall / retrieval_quality / answer_quality
- 文档和测试保持一致

### Phase 2：全库 retrieval_quality 黄金集落地

目标：

- 为所有已入库文档生成 retrieval_quality 召回黄金样本
- 每个文档至少有最低样本数
- 高价值文档按页数、知识密度和业务重要性增加样本数
- 每条样本至少标注 1 个 must_hit
- 复杂问题标注 2-5 个 must_hit
- 记录 nice_to_hit 和 negative_expected
- 输出 Recall@5、Recall@10、MRR

实施流程：

1. 枚举所有已入库 doc_id
2. 识别文档类型、页数、知识密度和业务优先级
3. 按文档类型选择 Golden 配方
4. 生成候选 query、expected_pages、expected_sections、must_hit
5. 对高价值文档执行人工抽查和修正 must_hit
6. 固化为 `retrieval_quality` cases
7. 输出全库和单文档 Recall@5、Recall@10、MRR
8. 将高频失败样本沉淀为长期回归集

样本数建议：

```text
每个文档最低样本数:
  small: 5-15
  medium: 20-50
  large: 50-100
  critical: 80-150

全库第一阶段:
  每个已入库文档至少覆盖 5-10 条
  高价值标准/规范文档优先覆盖 50-100 条
```

### Phase 3：answer_quality 用例扩充

目标：

- 从用户真实问法生成 rich_answer cases
- 加入 forbidden_contains
- 加入 answer_mode / confidence 校验

优先问题：

- `CC是什么意思`
- `CC阻值是多少`
- `CP占空比是什么意思`
- `检测点1电压表示什么`
- `什么是控制导引电路`
- `V2G和V2X有什么区别`

### Phase 4：Coverage v0 完整落地

目标：

- source unit inventory
- coverage matrix
- uncovered report
- coverage summary
- U0/U1/U2/U3/U4 类缺口分类

### Phase 5：入库重建和残留治理

目标：

- 对旧程序生成的数据残留做可控清理
- 支持完整重建某个 doc_id
- 保持新旧 artifact 不混淆

### Phase 6：真实用户问答质量评估

目标：

- 用户风格问题集常态化
- 查询失败归因
- 自动生成下一批 answer_quality cases
- UI 展示“为什么答成这样”

---

## 15. 入库完成定义

当前建议定义：

```text
入库完成 =
  pipeline 完成
  + coverage report 完成
  + unified golden generated
  + unified golden executed
  + coverage_recall 达标
  + retrieval_quality 达标
  + answer_quality 达到最低样本要求
```

最低样本要求建议：

```text
coverage_recall:
  覆盖所有高优先级 source unit

answer_quality:
  每个高价值知识类型至少有若干真实问法

retrieval_quality:
  所有已入库文档都有最低数量的用户式召回样本，高价值文档有更高密度样本
```

因此，不能再只说：

```text
golden all passed
```

而应说：

```text
golden all passed
coverage_recall: 154/154
retrieval_quality: 720/800, Recall@5=86%, Recall@10=93%, MRR=0.74
answer_quality: 13/13
answer_quality coverage is still low/high
```

---

## 16. 最终结论

KB1 当前设计的核心不是“多做几个测试”，而是建立一条可解释、可追溯、可评估的知识入库和问答链路。

最终判断一个文档是否真正入库完成，需要同时回答：

1. 原文是否被覆盖
2. 结构化知识是否完整
3. 对象和 wiki 是否生成
4. 测试是否打到这些知识
5. 用户式问题是否能召回正确条款、图表和附录
6. 用户式问题是否能答好

最新方案将这些要求统一到一套 Golden Suite 中：

```text
一套入口
三类指标
一个工作台展示
```

这样既保持使用简单，又不会让单一通过率掩盖系统质量问题。
