# Query Repair Blueprint

## 文档目标

这份蓝图是对 [query_error_diagnosis_model_2026-04-22.md](E:/AI_Project/opencode_workspace/KB1/docs/query_error_diagnosis_model_2026-04-22.md) 的工程化展开。

它回答的不是“哪里错了”，而是：

1. 具体要改哪些模块
2. 每个模块改什么，不改什么
3. 改完如何验收
4. 先后顺序怎么排
5. 哪些风险要提前控住

这份蓝图明确遵守一个原则：

> 不为单个 query 打补丁，而是修正“缩写 + 限定词 + 解释型问法”这一整类链路。

---

## 一、修复总目标

### 目标问题

当前系统对以下类型问题稳定性不足：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `检测点1电压表示什么`
- `什么是V2V`
- `V2V的定义是什么`

### 修复后期望能力

系统应具备以下能力：

1. 能稳定识别“定义型解释问法”和“参数解释型问法”
2. 能保留限定词，不把 `CC阻值` 压成 `CC`
3. 能把 topic resolution 锚定到细粒度对象，而不是总表
4. 对参数类问题能产出“参数意义 + 依据”的解释，不再退回 general search
5. 对缺知识节点的问题能做显式 fallback，而不是静默漂移或空答

---

## 二、修复范围划分

### 范围内

- query semantic parse
- rewrite consistency
- topic resolution ranking
- retrieval routing
- answer policy
- fallback strategy
- observability
- regression design

### 暂不进入本轮

- UI 改造
- 数据库存储结构重构
- 大规模知识重建
- 全量术语体系重做

原因：

当前的主问题是“查询理解链路失真”，不是 UI，也不是数据库 schema 本身。

---

## 三、分模块实施方案

## 模块 A：Semantic Parse 规范化

### 目标

让语义解析器稳定识别“解释型问法”，并输出可用于后续锚定的细粒度主题。

### 当前问题

- `代表什么意思`
- `表示什么`
- `指什么`
- `含义是什么`

这类问法未被稳定覆盖。

### 需要做的事

1. 重新定义 intent pattern

把定义类意图拆成两个子范式：

- `term_definition`
  例：`什么是V2V`
- `meaning_explanation`
  例：`CC阻值代表什么意思`

这两个子范式在业务上可继续映射到同一上层 intent，但在语义解析阶段必须区别对待。

2. 约束输出质量

对 semantic parser 的输出增加以下要求：

- `normalized_query` 不能仅保留缩写，若原问题存在参数限定词，必须保留
- `target_topic` 优先为“细粒度对象”
- `must_terms` 必须包含缩写和限定词
- `aliases` 只能做等价表达，不允许做上位概念替代

3. 加入危险输出校验

如果 semantic parser 输出以下情况，应判为低质量：

- `target_topic = undefined`
- `normalized_query` 只剩缩写，但原问题明显包含限定词
- `confidence` 很高，但 `must_terms` 为空

### 验收标准

对以下 query：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `V2V的定义是什么`

验收要求：

- `target_topic` 不得是 `CC` / `CP` 这类裸缩写
- `must_terms` 必须含缩写和限定词
- `query_type` 不能掉到 `general_search`

---

## 模块 B：Rewrite 一致性修复

### 目标

解决当前最核心的问题：

> query_type 被纠正了，但 topic anchor 没有同步纠正。

### 当前问题

在 `rewrite_query()` 中：

- `normalized_query` 来自 semantic parse
- `query_type` 允许规则兜底纠正
- 但 `target_topic / normalized_query / must_terms` 不会在规则纠正后同步重算

这是当前最关键的结构性 bug。

### 需要做的事

1. 拆成两阶段 rewrite

第一阶段：
- 只做意图判定

第二阶段：
- 基于最终意图，重建 `normalized_query / target_topic / must_terms / should_terms`

2. 建“限定词保护机制”

输入 query 中出现以下结构时，视为不可丢失锚点：

- `缩写 + 参数词`
- `缩写 + 状态词`
- `检测点 + 编号 + 参数`
- `符号 + 数字 / 下标`

例如：

- `CC阻值`
- `CP占空比`
- `检测点1电压`
- `R4c'`

这些词组必须整体保留到最终 topic anchor。

3. 建“粗化检测”

若原 query 中存在细粒度对象，而最终 `target_topic` 比原 query 更粗，应触发 rewrite 修正。

### 验收标准

以下 query 输入到 rewrite 后：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `检测点1电压表示什么`

验收要求：

- `normalized_query` 不得退化为 `CC`、`CP`
- `target_topic` 必须体现参数限定词
- `must_terms` 必须含保护锚点

---

## 模块 C：Topic Resolution 优先级修复

### 目标

让 topic resolution 优先细粒度对象，而不是总表/总章。

### 当前问题

当前 `parameter_lookup` 容易优先命中：

- `parameter_group`
- 参数总表
- 控制导引大章节

这会让查询漂到“表 A.1 控制导引电路参数”这种大对象。

### 需要做的事

1. 重排 parameter 类候选优先级

建议优先级：

- `parameter_topic`
- `term`
- `parameter_group`

而不是让 `parameter_group` 成为默认强候选。

2. 引入锚点一致性分

对 candidate entity 增加：

- 是否完整包含 `must_terms`
- 是否同时命中“缩写 + 限定词”
- 是否只是上位概念

如果一个候选只命中裸缩写，应显著低于命中完整限定词的候选。

3. 引入父子对象惩罚

当 query 是细粒度参数解释类时：

- 命中 parameter group 视为弱匹配
- 命中总章节视为更弱匹配

### 验收标准

对 `CC阻值代表什么意思`：

- topic resolution top1 不应是控制导引参数总表，除非不存在更细对象

对 `V2V的定义是什么`：

- 若没有 V2V term，也要明确标记为“近似候选”，不能装作精确命中

---

## 模块 D：Retrieval Routing 修复

### 目标

让正确 query type 走正确 channel，而不是“理解稍微对一点，召回却仍按通用搜索跑”。

### 当前问题

参数解释类问题虽然可能被识别成 `parameter_lookup`，
但 routing / answer 上仍然更像通用搜索。

### 需要做的事

1. 将“参数解释型”与“参数值查找型”区分开

参数问题要再拆至少两类：

- `parameter_meaning`
- `parameter_value_lookup`

例如：

- `CC阻值代表什么意思` 属于 `parameter_meaning`
- `CC阻值是多少` 属于 `parameter_value_lookup`

2. 为 `parameter_meaning` 指定 channel priority

建议优先顺序：

- facts
- wiki
- evidence
- document

而不是把 document / evidence 放得过前。

3. direct wiki injection 需要偏向 term / parameter topic

这类问题更应优先直接注入：

- parameter topic wiki
- term wiki

### 验收标准

对参数解释类 query：

- retrieval plan 首通道不能是 document
- facts/wiki 必须先于大表 evidence 被纳入主要候选

---

## 模块 E：Answer Policy 重构

### 目标

不再让 `parameter_lookup` 用 `general_search` 的方式回答。

### 当前问题

当前策略下：

- `parameter_lookup -> general_search`

这是错误类别“最后一步失真”的直接来源。

### 需要做的事

1. 新增参数解释策略

至少新增两类 policy：

- `parameter_meaning`
- `parameter_value`

2. 定义输出模板

对于 `parameter_meaning`：

输出结构应优先是：

```text
<参数名> 表示 <语义解释>。
如有结构化值，再补充：
相关值/范围为 <...>。
依据来自 <...>。
```

而不是直接甩整段表格。

3. 建立 fallback 层级

参数解释类 fallback 顺序建议：

- parameter definition fact
- term definition fact
- wiki definition section
- evidence paragraph
- parameter group summary

注意：parameter group summary 应是最后 fallback，不是默认 answer。

### 验收标准

对 `CC阻值代表什么意思`：

- 若已有参数定义/术语定义，不能返回通用搜索结果
- 若没有直接定义，也不能直接丢整张参数表当回答

---

## 模块 F：可解释 Fallback

### 目标

当知识库没有精确对象时，系统应“明确地退化”，而不是“悄悄漂移”。

### 当前问题

像 `V2V` 这种问题，现在会：

- 要么空答
- 要么漂到 `V2X`

但系统不说明“这是近似替代”。

### 需要做的事

1. fallback 输出必须显式

例如：

```text
知识库中未找到 V2V 的直接定义。
当前最接近的相关概念是 V2X，其含义为……
以下内容为近似参考，不是 V2V 的精确定义。
```

2. 建 fallback reason

每次 fallback 都要带出原因：

- missing_exact_term
- fallback_to_parent_concept
- fallback_to_parameter_group

### 验收标准

对 `什么是V2V`：

- 若无直接定义，答案必须明确说明是近似解释

---

## 模块 G：Observability / Debug 输出

### 目标

以后遇到类似问题，不再靠人工猜链路错哪层。

### 需要做的事

每个 query 至少输出以下调试字段：

- final_query_type
- final_normalized_query
- final_target_topic
- protected_anchor_terms
- semantic_confidence
- rewrite_override_applied
- topic_resolution_top_candidates
- retrieval_channels
- answer_policy
- fallback_reason

### 验收标准

任一错答问题，工程师在单次日志/响应里就能看出：

- 类型是否错
- anchor 是否丢
- top candidate 是否漂
- answer policy 是否错配

---

## 模块 H：知识建模补齐

### 目标

在链路修完后，补足系统反复命中的知识缺口。

### 需要做的事

1. 补细粒度 term / parameter topic

优先候选：

- V2V
- CC阻值
- CP占空比
- 检测点电压

2. 补 definition fact

对高频术语补：

- `term_definition`
- `concept_definition`
- 参数语义解释 fact

3. 补 wiki 页面

至少给高频细粒度对象独立 wiki，而不是只挂在总表下面。

### 验收标准

补完后：

- 高频问题不再只能 fallback 到父主题

---

## 四、实施顺序

### Phase 0：止血

目标：

- 避免继续产生“类型对、主题错”的半修正状态

内容：

- Rewrite 一致性修复
- 解释型问法覆盖
- 基础 observability

验收：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`

这类问题至少不再被压成裸 `CC / CP`

---

### Phase 1：链路纠偏

目标：

- 让细粒度问题走对 topic resolution / retrieval / answer policy

内容：

- topic resolution 优先级调整
- retrieval routing 拆分
- parameter meaning answer policy

验收：

- 参数解释型 query 不再默认命中总表

---

### Phase 2：可解释退化

目标：

- 对知识缺口做显式 fallback

内容：

- fallback reason
- parent concept fallback
-近似解释模板

验收：

- `V2V` 这类问题不再静默漂移或空答

---

### Phase 3：知识补齐

目标：

- 从“能工作”提升到“高质量工作”

内容：

- term / parameter topic / definition fact / wiki 补齐

---

## 五、验收矩阵

### 类别 1：限定词丢失型

query：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `检测点1电压表示什么`

验收：

- query_type 正确
- target_topic 保留限定词
- top candidate 不漂到总表
- direct answer 是解释，不是表格堆叠

### 类别 2：参数值型

query：

- `CC阻值是多少`
- `CP占空比是多少`

验收：

- 优先命中参数值 fact
- 回答包含值、范围、来源

### 类别 3：别名漂移型

query：

- `什么是V2V`
- `V2V的定义是什么`

验收：

- 有精确对象时命中精确对象
- 无精确对象时显式 fallback

### 类别 4：定义型

query：

- `什么是控制导引电路`
- `V2G的定义是什么`

验收：

- definition policy 被正确选择
- direct answer 优先 term/concept definition

---

## 六、明确不推荐的修法

### 不推荐 1：只补 synonym

原因：

- 只能让词“更多”
- 不能让 topic “更准”

### 不推荐 2：只调 rerank

原因：

- 若主题一开始就错，rerank 只是把错误候选排得更漂亮

### 不推荐 3：只补 answer template

原因：

- 若 supporting facts 就不对，换模板不会让答案变准

### 不推荐 4：为单个 query 写 if/else

原因：

- 会快速把系统变成 query patchwork

---

## 七、核心决策

本轮修复的核心决策应是：

1. 先修 rewrite consistency
2. 再拆 parameter meaning answer policy
3. 再调 topic resolution ranking
4. 最后补知识对象

原因：

- rewrite consistency 是整个链路最上游的失真点
- 不先修这一层，后面所有优化都容易继续围着错主题转

---

## 八、阶段性交付物

### 交付物 A

查询理解链路修复说明：

- 覆盖哪些 query class
- 新增哪些内部 intent
- rewrite 如何保证一致性

### 交付物 B

参数解释型答案策略说明：

- 输入条件
- answer builder 逻辑
- fallback 顺序

### 交付物 C

类错误回归集：

- query 清单
- 期望 query_type
- 期望 target_topic
- 期望 top candidate
- 期望 direct answer 行为

---

## 九、最终判断

这类错误的修复，不应被当作“召回优化”，而应被当作：

> 面向细粒度知识对象的查询理解链路重构。

这决定了：

- 修复优先级要从 rewrite 开始
- 验收标准要看 target_topic 是否正确
- 回归标准要按 query class，而不是按单句
