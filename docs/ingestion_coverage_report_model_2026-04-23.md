# Ingestion Coverage Report Model

## 文档目标

这份文档定义：

> 一份原始文档入库完成后，系统应该如何回答“是否已覆盖原文档、哪里有漏、漏在哪一层”。

当前系统已有：

- parse
- quality
- evidence
- facts
- entities
- wiki
- graph
- golden tests

但还缺：

- 源文档单元化
- 入库覆盖映射
- 未覆盖单元报告
- 覆盖率指标体系

这份模型的目标就是补这块。

---

## 一、核心问题

目前系统只能看到“产出了多少”，看不到“覆盖了多少”。

例如现在可以知道：

- `fact_count`
- `evidence_count`
- `term_definition_count`
- `answerability_score`

但看不到：

- 哪些原文段落完全没进入 evidence
- 哪些定义进了 evidence 但没进 fact
- 哪些 fact 没形成实体
- 哪些实体没进 wiki
- 哪些知识从未进入黄金测试

换句话说：

当前缺少的是一套 **Source-to-Knowledge Coverage Map**。

---

## 二、模型总结构

完整覆盖模型建议拆成 5 层：

```text
原文 source units
  -> evidence coverage
  -> fact coverage
  -> object coverage
  -> wiki/graph coverage
  -> golden/regression coverage
```

最终要形成一份“覆盖报告”，回答：

1. 文本层是否覆盖
2. 语义层是否覆盖
3. 对象层是否覆盖
4. 测试层是否覆盖
5. 哪些单元完全漏掉

---

## 三、Source Unit 模型

### 为什么必须先做 source unit

如果不先把原文拆成稳定单元，就无法追踪“漏了哪些内容”。

你只能看到总数，永远看不到遗漏位置。

### Source Unit 定义

一个 `source unit` 是原文中可被独立覆盖、独立追踪的最小知识单元。

### 建议的 unit 类型

#### 1. definition_unit

适用于：

- 术语定义
- 概念定义

示例：

- `V2G 是……`
- `控制导引电路是……`

#### 2. parameter_row_unit

适用于：

- 参数表中的一行

示例：

- `R4c' = 1000Ω`
- `Dco 最大 +0.5% 最小 -0.5%`

#### 3. requirement_unit

适用于：

- 规范性要求句
- 阈值/限制句

示例：

- `应满足……`
- `不应超过……`

#### 4. process_step_unit

适用于：

- 流程步骤
- 时序迁移

示例：

- `状态2 -> 状态3`
- `版本协商成功后进入参数配置阶段`

#### 5. section_unit

适用于：

- 章节标题
- 结构性知识入口

示例：

- `A.2 充电控制导引电路`

---

## 四、Source Unit 最小字段

每个 source unit 至少应包含：

```json
{
  "doc_id": "DOC-000002",
  "page_no": 53,
  "unit_id": "DOC-000002:param-row:53:12",
  "unit_type": "parameter_row_unit",
  "source_text": "...",
  "source_locator": {
    "page_no": 53,
    "table_title": "表 A.1 控制导引电路的参数",
    "row_index": 12
  },
  "semantic_key": "CC阻值",
  "importance": "high"
}
```

### 说明

- `unit_id`: 稳定主键
- `unit_type`: 单元类别
- `source_text`: 原文或清洗后的文本
- `source_locator`: 定位信息
- `semantic_key`: 该单元代表的语义锚点
- `importance`: 可用于优先级统计

---

## 五、Coverage Matrix 模型

### 核心思想

每个 source unit，都应该回答：

> 它在知识链的哪些层被覆盖了。

### 建议字段

```json
{
  "unit_id": "...",
  "covered_by": {
    "evidence_ids": ["EV-..."],
    "fact_ids": ["FACT-..."],
    "entity_ids": ["ENT-..."],
    "wiki_page_ids": ["WPAGE-..."],
    "graph_edge_ids": ["EDGE-..."],
    "golden_case_ids": ["GOLD-..."],
    "regression_case_ids": ["REG-..."]
  }
}
```

这样就能对每个 source unit 做精确判断：

- 完全未覆盖
- 只到 evidence
- 到了 fact 但没对象
- 到了对象但没进入测试

---

## 六、覆盖层定义

### 1. Text Coverage

定义：

`source unit -> evidence`

回答：

- 这个单元的内容有没有被抽成 evidence

### 2. Semantic Coverage

定义：

`source unit -> fact`

回答：

- 这个单元有没有被结构化

### 3. Object Coverage

定义：

`source unit -> entity / topic object`

回答：

- 这个知识有没有被挂到对象系统里

### 4. Knowledge Page Coverage

定义：

`source unit -> wiki / graph`

回答：

- 这个知识有没有进入可浏览、可扩展的知识骨架

### 5. Test Coverage

定义：

`source unit -> golden / regression`

回答：

- 这个知识有没有被测试真正打到

---

## 七、未覆盖分类

为了让报告可行动，未覆盖不能只是一条“漏了”。

建议分成下面几类。

### U0. 全漏

定义：

- 没有 evidence
- 没有 fact
- 没有 object

含义：

- parser / cleaner / extraction 直接漏掉

### U1. 文本已覆盖，语义未覆盖

定义：

- 有 evidence
- 没有 fact

含义：

- 抽到了文本，但没结构化

### U2. 语义已覆盖，对象未覆盖

定义：

- 有 fact
- 没有 entity / topic object

含义：

- fact 抽到了，但对象系统没长出来

### U3. 对象已覆盖，测试未覆盖

定义：

- 有 fact / entity / wiki
- 没有 golden / regression case

含义：

- 知识已经入库，但从未被验证

### U4. 错覆盖

定义：

- source unit 有 coverage
- 但 semantic_key 与实际对象不一致

含义：

- 不是漏了，而是挂错了

这是最危险的一类。

---

## 八、覆盖率指标

### 总体指标

建议至少输出 4 个总分：

```text
text_coverage_rate
semantic_coverage_rate
object_coverage_rate
test_coverage_rate
```

### 分类指标

按 unit_type 输出：

- definition_unit_coverage
- parameter_row_coverage
- requirement_coverage
- process_step_coverage
- section_coverage

### 重要性指标

按 `importance` 输出：

- high_importance_coverage
- medium_importance_coverage
- low_importance_coverage

原因：

不是所有漏项都一样严重。

---

## 九、报告输出结构

建议每份文档入库后自动生成：

### 1. summary.json

例如：

```json
{
  "doc_id": "DOC-000002",
  "source_unit_count": 428,
  "text_coverage_rate": 0.91,
  "semantic_coverage_rate": 0.67,
  "object_coverage_rate": 0.41,
  "test_coverage_rate": 0.18,
  "uncovered_counts": {
    "u0_full_miss": 12,
    "u1_text_only": 46,
    "u2_fact_no_object": 39,
    "u3_not_tested": 201,
    "u4_misaligned": 7
  }
}
```

### 2. uncovered_units.json

列出所有未覆盖或错覆盖单元。

### 3. coverage_matrix.json

完整 unit -> layer 映射。

### 4. coverage_report.md

给人看的摘要版本。

---

## 十、完成入库的新定义

你前面说：

> 入库完成后，以完成黄金测试集测完为完成入库的标志

我建议把定义升级成：

```text
入库完成 =
  pipeline 完成
  + 覆盖报告生成完成
  + 黄金测试生成完成
  + 黄金测试执行完成
```

这里的“黄金测试”不再拆成两套独立流程，而是保持一个统一 Golden Suite。

统一 Golden Suite 内部按 `assert_mode` 分成两个评价维度：

```text
Golden Suite =
  覆盖召回测试 context_contains
  + 答案质量测试 rich_answer
```

也就是说，操作入口仍然只有：

- generate golden tests
- run golden tests

但执行结果必须同时输出：

- `coverage_recall`
- `answer_quality`

这样避免把系统做复杂，也避免一个总通过率掩盖真实问题。

如果没有覆盖报告，就无法判断：

- 黄金测试只覆盖了文档的 20%
- 还是已经覆盖了核心知识单元

所以“黄金测试跑完”不是充分条件。

同时，“黄金测试全部通过”也不能只看一个总数。

例如：

```text
total: 167 passed
coverage_recall: 154 passed
answer_quality: 13 passed
```

这比单纯 `167 passed` 更可解释。前者说明：

- 154 条主要验证 source unit 是否能被检索召回
- 13 条主要验证最终 answer 是否包含关键答案

如果用户认为回答质量不够，应该优先提升 `answer_quality` 用例数量和质量，而不是继续堆 `page_coverage/context_contains`。

---

## 十一、统一 Golden Suite 的测试分层

为了保持流程简单，测试数据仍然写入同一个文件：

```text
tests/generated/{doc_id}.golden.json
```

每条 case 通过 `assert_mode` 表达验证目的：

```json
{
  "kind": "page_coverage",
  "query": "第20页 3.2.20 剩余电流保护器 residual current device...",
  "must_include": "剩余电流保护器 residual current device",
  "assert_mode": "context_contains"
}
```

```json
{
  "kind": "definition",
  "query": "CC是什么意思",
  "must_include": "连接确认功能",
  "assert_mode": "rich_answer"
}
```

### A. 覆盖召回测试

`assert_mode = context_contains`

目的：

- 验证 source unit 已进入可检索上下文
- 验证 evidence/fact/object/wiki 链路没有断
- 支撑入库覆盖率统计

不保证：

- 最终答案表达自然
- 问法符合真实用户习惯
- answer policy 一定正确

### B. 答案质量测试

`assert_mode = rich_answer`

目的：

- 验证最终 `direct_answer / summary / supporting_facts` 包含关键答案
- 验证 query rewrite / topic resolution / answer policy 能协同工作
- 支撑真实用户问答质量评估

后续可逐步扩展字段：

```json
{
  "expected_answer_contains": ["连接确认功能", "反映车辆插头连接状态"],
  "forbidden_contains": ["没有找到足够", "GB：代替"],
  "expected_answer_mode": "definition",
  "min_confidence": 0.7
}
```

这些增强字段不是 v0 必需，但应作为后续质量验收方向。

---

## 十二、最小落地版本

为了避免一上来就做得太大，建议先做 `v0`。

### v0 先只覆盖 3 类单元

- definition_unit
- parameter_row_unit
- requirement_unit

这三类已经能覆盖大多数高价值知识。

### v0 先只做 4 层映射

- evidence
- facts
- entities
- golden/regression

先不强求 graph edge 的完整映射。

### v0 的 Golden 结果摘要

`run_golden_tests_for_document()` 应返回统一 summary：

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
    "answer_quality": {
      "total": 13,
      "passed": 13,
      "failed": 0
    },
    "case_mix": {
      "context_contains": 154,
      "rich_answer": 13
    }
  }
}
```

UI 上仍然显示一个 Golden 面板，但必须把这两个维度分开展示。

### v0 先只做高优先级文档

例如：

- `DOC-000002`
- `DOC-000003`

---

## 十三、推荐实施顺序

### Step 1

建立 `source unit inventory`

### Step 2

建立 `unit -> fact/evidence/object` 映射

### Step 3

建立 `unit -> test case` 映射

### Step 4

输出 `coverage summary + uncovered report`

### Step 5

在同一个 Golden Suite 中平衡两类 case：

- 对未覆盖 source unit 生成 `context_contains`
- 对高价值对象和真实用户问法生成 `rich_answer`

---

## 十四、最终结论

你现在之所以无法知道“有没有漏”，不是因为少一个 UI 页面，而是因为：

> 系统目前只有产出统计，没有覆盖映射。

真正要补的不是更多 count，而是：

- source unit inventory
- coverage matrix
- uncovered report
- coverage scorecard

只有这样，入库后你才能真正判断：

1. 是否覆盖了原文档
2. 漏了哪些内容
3. 漏在哪一层
4. 黄金测试到底覆盖了多少有效知识
5. 通过的测试里有多少是真正的答案质量测试
