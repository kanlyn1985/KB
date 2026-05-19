# Robustness Test Coverage Framework

## 目标

当前 KB1 的测试不能再只回答“几个代表问题能不能跑通”，而要回答两个更关键的问题：

1. 用户换一种说法，系统还能不能稳住
2. 整个知识库里的不同知识类型，到底覆盖了多少

因此，鲁棒性测试必须至少有两个主维度：

- 维度 A：用户问法鲁棒性
- 维度 B：知识库覆盖度

这两个维度缺一不可。

如果只做维度 A，会出现：

- 问法很多样
- 但其实都围绕同一小撮知识对象在测

如果只做维度 B，会出现：

- 覆盖了很多知识对象
- 但问法都太“书面化”，不接近真实用户

---

## 一、测试总模型

建议把整个鲁棒性测试看成一个二维矩阵：

```text
                 维度 A：用户问法鲁棒性
        ------------------------------------------------
        标准问法 | 口语问法 | 变体问法 | 追问式 | 噪声型

维度 B：  term
知识库    parameter
覆盖      process
          constraint
          comparison
          standard
          document
```

理想状态不是“每格都一样多”，而是：

- 每个高价值知识类型，都至少有多种问法覆盖
- 每种高频问法，都至少落在多类知识对象上

---

## 二、维度 A：用户问法鲁棒性

这个维度回答的是：

> 同一个知识对象，用户换着问，系统还能不能理解正确。

建议把问法分成 5 大类。

### A1. 标准问法

特征：

- 结构清晰
- 接近系统已有规则

例子：

- `什么是V2V`
- `CC阻值是多少`
- `急停有哪些要求`

用途：

- 作为基础能力基线

---

### A2. 口语问法

特征：

- 更像真实用户随手问
- 不严格遵循书面定义式模板

例子：

- `CC阻值是啥意思`
- `CP占空比是干嘛的`
- `V2V到底是什么`
- `这个标准什么时候开始用`

用途：

- 测语义解析和 rewrite 的稳定性

---

### A3. 多样化表达问法

特征：

- 同一意图换不同表达
- 检验 query type 分类是否稳

例子：

- `X是什么意思`
- `X代表什么意思`
- `X表示什么`
- `X指什么`
- `X含义是什么`

用途：

- 测意图边界是否清晰

---

### A4. 追问式问法

特征：

- 更像真实对话里的第二问、第三问
- 通常更短、更省略、更不完整

例子：

- `那它一般多大`
- `这个值有什么要求`
- `它跟CP有啥关系`
- `那什么时候切过去`

用途：

- 测系统对短 query / 省略 query 的稳定性

注意：

如果当前系统还没有多轮会话建模，追问式问题也可以先作为“单轮弱上下文 query”测试，观察最差情况下的表现。

---

### A5. 噪声型问法

特征：

- 夹杂冗余词、错别字、口头语、缩写混用

例子：

- `CC那个阻值到底啥意思`
- `QC/T1036这个标准哪天起执行啊`
- `V2V是不是车跟车那个`

用途：

- 测 semantic parse / rewrite 的抗噪能力

---

## 三、维度 A 的覆盖指标

建议不要只看“问题数量”，而要看“问题分布”。

### 最低覆盖要求

对每个高频知识对象，至少覆盖：

- 1 条标准问法
- 1 条口语问法
- 1 条表达变体问法

对每个高频知识类型，至少覆盖：

- 1 条追问式问法
- 1 条噪声型问法

### 推荐覆盖指标

对每个高频对象：

- 问法变体数 >= 3

对每个高频知识类型：

- 问法类型覆盖率 >= 80%

### 不推荐的做法

- 只写 20 条不同 query，但其实都是“什么是X”
- 把相同模板机械换词，假装多样性

---

## 四、维度 B：知识库覆盖度

这个维度回答的是：

> 测试是否真的打到了知识库的不同知识层，而不是反复在同一小块区域转圈。

建议从 6 个子维度来衡量。

### B1. 文档覆盖

问题：

- 测试 query 是否只命中 1-2 个主文档

指标：

- 被命中的 `doc_id` 数量
- 每个测试批次覆盖的文档占比

建议：

- 高频主文档必须覆盖
- 低频但关键文档也要抽样覆盖

---

### B2. 知识类型覆盖

问题：

- 测试是否只覆盖 parameter，而没有覆盖 process / constraint / comparison / standard

建议的知识类型：

- term / definition
- parameter
- process / timing
- constraint / requirement
- comparison
- standard / lifecycle
- document metadata

指标：

- 每类知识至少有固定数量的 query
- 每类知识至少有多种问法类型

---

### B3. 实体粒度覆盖

问题：

- 测试是否只命中了父主题，没有覆盖细粒度对象

建议粒度层次：

- document
- section / process
- parameter_group
- parameter_topic
- term
- comparison_topic
- constraint_topic

重点：

- 细粒度对象必须有专门 query，不然会被父对象遮蔽

---

### B4. 事实类型覆盖

问题：

- 测试是否只验证 direct_answer，而没有验证 system 真正用了哪些事实类型

建议覆盖的 fact_type：

- term_definition
- concept_definition
- parameter_value
- requirement
- threshold
- process_fact
- transition_fact
- comparison_relation
- document_standard
- document_lifecycle

指标：

- 每个核心 fact_type 至少有一组 query 命中

---

### B5. Wiki / Evidence / Graph 通道覆盖

问题：

- 测试是否只看最终答案，没有验证 retrieval 通道是否健康

建议关注：

- wiki_pages 是否被使用
- evidence 是否被使用
- graph_edges 是否被使用
- topic_objects / topic_entities 是否对齐

指标：

- 每个核心通道至少有若干 query 可命中

---

### B6. 质量状态覆盖

问题：

- 测试是否只命中 `passed` 文档，没有覆盖 `review_required` 文档

指标：

- 覆盖不同 `quality_status`
- 覆盖不同 `trust_status`

意义：

- 真实生产环境不会只有“干净文档”

---

## 五、维度 B 的覆盖指标

### 最低覆盖要求

每轮完整回归至少满足：

- 文档覆盖：主文档覆盖率 >= 70%
- 知识类型覆盖：核心类型覆盖率 = 100%
- 实体粒度覆盖：必须覆盖到 parameter_topic / term / process
- 事实类型覆盖：核心 fact_type 覆盖率 >= 80%

### 推荐覆盖指标

更稳妥的目标：

- 高频知识对象覆盖率 >= 90%
- 高频知识类型每类 query 数 >= 5
- 每类知识至少有 3 种不同问法风格

---

## 六、如何组合这两个维度

这两个维度不是分开跑，而是要交叉构造问题集。

### 推荐方式：分层问题集

#### Level 1：核心对象 x 多样问法

目标：

- 测语义和 rewrite 鲁棒性

例子：

- `CC阻值`
  - `CC阻值代表什么意思`
  - `CC阻值是啥意思`
  - `CC这个阻值是干嘛的`

#### Level 2：核心知识类型 x 多样问法

目标：

- 测 query_type 分类稳定性

例子：

- parameter
- process
- standard
- definition

#### Level 3：跨文档覆盖抽样

目标：

- 防止测试只命中一两个主文档

#### Level 4：长尾噪声抽样

目标：

- 测抗噪能力

---

## 七、推荐的问题集结构

建议问题集不要只是一堆 query 字符串，而要带元信息。

建议字段：

```json
{
  "name": "cc_resistance_meaning_colloquial",
  "query": "CC阻值是啥意思",
  "style_type": "colloquial",
  "knowledge_type": "parameter_meaning",
  "target_topic": "CC阻值",
  "target_entity_granularity": "parameter_topic",
  "expected_query_type": "definition",
  "expected_answer_mode": "parameter_meaning",
  "expected_doc_ids_any": ["DOC-000002", "DOC-000003"],
  "expected_top_entity_name": "CC阻值",
  "expected_top_entity_type": "parameter_topic",
  "expected_fallback_reason": "",
  "direct_answer_contains_all": ["CC阻值", "连接状态"]
}
```

这样以后才能统计：

- 哪类问法最脆
- 哪类知识最脆
- 哪类文档最脆

---

## 八、推荐的回归分层

### 回归层 1：快速单元层

关注：

- rewrite
- answer policy 选路

特点：

- 快
- 不依赖全量知识库

### 回归层 2：核心集成层

关注：

- topic_resolution
- answer_query
- fallback_reason

特点：

- 覆盖高频对象
- 可作为日常回归主集

### 回归层 3：全量鲁棒性基准层

关注：

- 知识库覆盖率
- 问法多样性覆盖率
- 长尾噪声表现

特点：

- 更慢
- 更接近真实系统质量评估

---

## 九、建议的统计报表

光有测试通过/失败不够，还应该输出覆盖统计。

当前设计更新为：

> 不新增第二套黄金测试流程，而是在同一个 Golden Suite 中保留两类 case，并在报告层分开统计。

这样用户侧操作仍然简单：

```text
Generate Golden
Run Golden
```

但报告中必须展示：

```text
Golden Summary
  - coverage_recall
  - answer_quality
```

### 统一 Golden Suite 的两个维度

#### 1. coverage_recall

对应：

```text
assert_mode = context_contains
```

用途：

- 验证 source unit 是否能被召回
- 验证入库链路是否覆盖原文
- 验证 coverage matrix 中的测试覆盖状态

边界：

- 不代表最终答案自然
- 不代表 answer policy 正确
- 不代表用户真实问法已经覆盖

#### 2. answer_quality

对应：

```text
assert_mode = rich_answer
```

用途：

- 验证最终答案是否包含关键答案
- 验证 query rewrite / topic resolution / answer policy 是否协同正确
- 验证用户式问题是否能被稳定回答

后续增强方向：

```json
{
  "query": "CC是什么意思",
  "expected_answer_contains": ["连接确认功能", "反映车辆插头连接状态"],
  "forbidden_contains": ["没有找到足够", "GB：代替"],
  "expected_answer_mode": "definition",
  "min_confidence": 0.7
}
```

这些质量字段可以逐步加，不要求 v0 一次性做完。

建议每轮输出：

1. 问法类型覆盖率
   - standard / colloquial / paraphrase / follow_up / noisy

2. 知识类型覆盖率
   - definition / parameter / process / constraint / comparison / standard

3. 文档覆盖率
   - 命中的 doc_id 分布

4. 实体粒度覆盖率
   - parameter_topic / term / process / parameter_group / constraint_topic / comparison_topic

5. fallback 使用率
   - 哪类 query 还在依赖 fallback

6. Golden case mix
   - `context_contains` 数量
   - `rich_answer` 数量
   - `answer_quality / total` 占比

如果 `context_contains` 很多但 `rich_answer` 很少，说明系统更像“可检索”，还不能说明“可回答”。

---

## 十、当前最现实的下一步

结合现在系统状态，建议下一批问题集优先扩以下三类：

### Priority 1：口语化参数解释

例如：

- `CC阻值是啥意思`
- `CP占空比是干嘛的`
- `检测点1电压有什么用`

### Priority 2：口语化标准问题

例如：

- `QC/T 1036 什么时候开始用`
- `18487.1 这个标准是哪版`

### Priority 3：术语近似问法

例如：

- `V2V是不是车跟车那个`
- `V2V到底指啥`

---

## 十一、最终判断

你提的两个维度，本质上应该变成测试体系的两个主 KPI：

1. `Query Style Coverage`
2. `Knowledge Coverage`

在当前简化实现里，这两个 KPI 不单独拆流程，而是落在统一 Golden Suite 的两个统计维度上：

```text
Knowledge Coverage -> coverage_recall
Query / Answer Quality -> answer_quality
```

也就是说：

- 不要让用户面对两套测试入口
- 不要把所有测试混成一个总通过率
- 要在一个报告里同时看到“能不能找到”和“能不能答好”

只有这两个指标一起上去，才是真的鲁棒性上去了。

否则系统很容易出现一种假象：

- “好多问题都测过了”

但其实只是：

- 问法不够多样
- 知识覆盖不够广

所以后续不应该再只问“又补了几个 query”，而应该开始问：

> 这轮回归，问法覆盖率和知识覆盖率分别提升了多少。
