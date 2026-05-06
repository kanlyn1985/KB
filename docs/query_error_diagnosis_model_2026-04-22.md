# Query Error Diagnosis Model

## 目标

这份模型不是为单个问句做补丁，而是为 KB1 当前查询主链建立一套可复用的诊断框架：

```text
user query
-> semantic parse
-> rewrite
-> topic resolution
-> retrieval routing
-> retrieval / rerank
-> answer policy
-> answer synthesis
```

目标是回答 4 个问题：

1. 这是哪一类错误
2. 错误发生在链路哪一层
3. 为什么该层没有把上游错误纠正回来
4. 应该在哪一层修，而不是在哪里打补丁

---

## 一、错误分类总表

### A. 限定词丢失型

定义：
用户问的是“细粒度对象 + 修饰限定 + 解释/参数/约束”，系统把它压成更大的父主题。

典型问法：

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `检测点1电压表示什么`
- `R4c' 是什么`

典型症状：

- `normalized_query` 只剩缩写或大主题
- `target_topic` 变成父主题，而不是细对象
- 命中整张表、整章、整类参数，而不是目标项
- 最终答案像“泛介绍”或“大表摘录”

根因关键词：

- semantic compression
- topic anchor drift
- parameter-group overmatch

---

### B. 术语别名漂移型

定义：
系统做了别名扩展，但扩展后的词把查询带向了语义相近但不等价的对象。

典型问法：

- `什么是V2V`
- `车车通信是什么`
- `V2V和V2X是什么关系`

典型症状：

- 能召回相关内容，但不是用户原问题
- `aliases` 和 `should_terms` 很强，但 `must_terms` 很弱
- topic resolution 候选实体偏向上位概念或相邻概念
- answer 阶段看似“有答案”，但并不精确

根因关键词：

- alias expansion drift
- hypernym substitution
- near-concept substitution

---

### C. 类型判定错位型

定义：
系统没有把问题归到正确的 `query_type`，导致整条后续链路使用了错误的检索和答案策略。

典型问法：

- `CC阻值代表什么意思`
- `V2V的定义是什么`
- `CP时序有哪些状态`

典型症状：

- 应该是 `definition`，却落到 `general_search`
- 应该是 `parameter_lookup`，却落到 `general_search`
- 应该是 `timing_lookup`，却落到 `section_lookup` 或 `general_search`

根因关键词：

- intent classification miss
- definition pattern gap
- rule coverage hole

---

### D. 主题锚点粗化型

定义：
`query_type` 看起来是对的，但 `normalized_query / target_topic / must_terms` 仍然太粗，导致 topic resolution 和 retrieval 依旧偏。

典型问法：

- `CC阻值是多少`
- `CP占空比是什么意思`
- `绝缘电阻要求是什么`

典型症状：

- `query_type = parameter_lookup`
- 但 `target_topic = CC / CP / 绝缘`
- 最终命中的是 parameter group、章节、总表

根因关键词：

- type corrected but topic not corrected
- half-correct rewrite
- coarse anchor propagation

---

### E. 召回通道错配型

定义：
系统并非没有相关知识，而是用了错误的 channel priority，导致先看 document/evidence，没优先看 term/fact/wiki。

典型问法：

- 定义类问题先看 evidence，而不是 definition fact
- 参数解释类问题先看 document 表片段，而不是 parameter topic / wiki

典型症状：

- query-context 有命中
- answer-query 仍然给出“没有足够结构化结果”
- supporting_evidence 有，但 supporting_facts 很弱

根因关键词：

- retrieval routing mismatch
- channel priority mismatch
- fact channel under-privileged

---

### F. 答案策略错配型

定义：
前面的 query type、topic、retrieval 都还可以，但最后 answer policy 没有给这类问题正确的答案生成路径。

典型问法：

- 参数解释类问题被当 `general_search`
- 定义类问题没有触发 definition answer builder

典型症状：

- 能命中 facts / wiki / evidence
- 但 direct answer 仍然是“没有足够的结构化结果”
- 或者 direct answer 只是片段拼接，不是定义句

根因关键词：

- answer policy mismatch
- synthesis gap
- fallback policy missing

---

### G. 知识建模缺口型

定义：
链路本身没完全错，但知识库中缺乏目标粒度的实体、fact、wiki 页面或 graph 节点。

典型问法：

- `V2V是什么`
- `CC阻值的定义是什么`

典型症状：

- topic resolution 只能命中相邻概念
- 没有对应 term_definition / concept_definition
- wiki 页面只有父主题，没有子术语页面

根因关键词：

- missing term node
- missing definition fact
- missing fine-grained parameter topic

---

## 二、分层诊断模型

### Layer 1: Semantic Parse

检查对象：

- `query_type`
- `normalized_query`
- `target_topic`
- `aliases`
- `must_terms`
- `should_terms`
- `confidence`

核心诊断问题：

1. 语义解析是否保留了“限定词”
2. 语义解析是否把问法识别成正确意图
3. 语义解析是否引入了错误的别名扩展

危险信号：

- `normalized_query` 比原问题缩短太多
- `target_topic` 是父主题而不是目标项
- `must_terms` 里没有关键限定词
- `confidence` 很高，但输出明显错误
- `target_topic = undefined` / 空 / 泛词

这层错误的本质：

> 用户问题被压缩成“方便检索的大词”，而不是“能正确定位知识对象的锚点”。

---

### Layer 2: Rewrite

检查对象：

- LLM semantic 输出
- rule-based `query_type`
- 最终 `rewrite_query()` 的返回对象

核心诊断问题：

1. 规则是否纠正了 query type
2. 纠正 query type 之后，topic anchor 是否同步纠正
3. rewrite 是否处于“半修正状态”

最重要的系统性风险：

> query type 被规则纠正了，但 normalized_query / target_topic 没被纠正。

这会导致：

- 表面上看类型正确
- 实际上所有后续层仍围绕错误主题运行

这是当前系统最典型的失真模式。

---

### Layer 3: Topic Resolution

检查对象：

- `candidate_entity_ids`
- `candidate_entities`
- `candidate_wiki_pages`
- confidence

核心诊断问题：

1. 候选实体是细粒度目标对象，还是父级大对象
2. 排名前几位候选中是否存在“主题漂移”
3. 没命中目标对象时，是因为不存在，还是因为匹配函数偏向大对象

危险信号：

- `parameter_lookup` 却总是优先命中 `parameter_group`
- `definition` 问题没有命中 `term`
- 缩写问题优先命中总章节/总表

---

### Layer 4: Retrieval Routing

检查对象：

- `channels`
- 每个 channel 的 hits
- channel priority

核心诊断问题：

1. 这类 query type 该优先走哪个 channel
2. 当前 routing 是否把最可能正确的 channel 放前面
3. 当前 routing 是否把“大文档命中”权重抬得太高

判断原则：

- definition 类：优先 facts/wiki，而不是 evidence/document
- parameter 解释类：优先 parameter topic / wiki / facts，而不是泛 evidence
- timing 类：优先 process/wiki/facts

---

### Layer 5: Retrieval / Rerank

检查对象：

- hits 排序
- rerank explanation
- lexical / exact / term / query_type alignment bonus

核心诊断问题：

1. 命中了正确对象，但排序掉下去了吗
2. 排前的是“大而泛”的匹配，还是“小而准”的匹配
3. rerank 是否过度奖励高频主题

危险信号：

- 父主题 lexical 高频，压过细粒度目标项
- exact term 没有被高权重保留
- parameter topic 比 parameter group 分数低

---

### Layer 6: Answer Policy / Synthesis

检查对象：

- `answer_mode`
- `policy`
- `supporting_facts`
- `supporting_evidence`
- `topic_objects`
- `topic_entities`
- `direct_answer`

核心诊断问题：

1. 这个 query type 是否映射到了正确的 answer policy
2. facts / wiki / evidence 已经足够时，为什么 direct answer 仍然失败
3. 有没有正确 fallback

危险信号：

- `parameter_lookup -> general_search`
- 已有相关 facts，却仍返回“没有足够的结构化结果”
- definition 问题没有优先使用 `term_definition`

---

## 三、错误树

### 诊断总流程

```text
如果 answer-query 没答出来：
  先看 query-context 是否有 hits

  如果 query-context 也没有 hits：
    优先排查 semantic parse / rewrite / synonym / topic anchor

  如果 query-context 有 hits，但 answer-query 没答出来：
    优先排查 answer policy / fact selection / direct answer synthesis

  如果 query-context 命中的是相关但不精确对象：
    优先排查 topic resolution / rerank / alias drift
```

---

## 四、这类错误的根因模板

对“缩写 + 限定词 + 解释型问法”这一大类，可统一套用下面模板：

```text
用户真正问题:
  想问一个细粒度对象的定义/含义/参数语义

系统实际理解:
  把细粒度对象压成父主题或缩写主题

链路失真位置:
  semantic parse / rewrite

放大失真的位置:
  topic resolution / retrieval routing / rerank

最终失败位置:
  answer policy / direct answer synthesis
```

---

## 五、为什么不能只修词典

只补 synonym 或 alias 会有帮助，但不够。

原因：

1. 词典只能解决“这个词认识不认识”
2. 它不能解决“这个词在当前问法里到底是父主题还是子主题”
3. 它不能解决“参数解释类问题最后为什么还走 general_search”

所以这类问题不能只在 synonyms 层修。

必须分层修：

- semantic parse / rewrite：保留限定词
- topic resolution：优先细粒度 topic
- answer policy：参数解释类不能走 general_search

---

## 六、修复优先级模型

### P0: Rewrite 一致性

要求：

- 只要规则纠正了 `query_type`
- 就必须重新校准 `normalized_query / target_topic / must_terms`

否则会持续出现“类型对了，主题错了”的半修正状态。

---

### P1: 解释型问法覆盖

需要补进统一的解释型模式：

- `代表什么意思`
- `表示什么`
- `指什么`
- `含义是什么`
- `是什么意思`

这些不能有的被识别成 definition，有的掉到 general_search。

---

### P2: 参数解释型答案策略

当前 `parameter_lookup -> general_search` 是结构性短板。

需要新增：

- parameter explanation
- parameter definition
- parameter meaning fallback

---

### P3: 细粒度知识对象补齐

如果没有：

- `CC阻值`
- `CP占空比`
- `V2V`

这类 term / parameter topic / wiki 页面，
那上面再好的链路也只能围着父主题兜圈子。

---

## 七、回归测试设计

要验证的是“类修复”，不是单个 query 修复。

### 回归集 1：限定词丢失型

- `CC阻值代表什么意思`
- `CP占空比是什么意思`
- `检测点1电压表示什么`
- `R4c' 是什么`

预期：

- query_type 稳定
- target_topic 保留限定词
- 命中细粒度对象
- 不再漂到整表

### 回归集 2：别名漂移型

- `什么是V2V`
- `V2V的定义是什么`
- `车车通信是什么`

预期：

- 如果库里没有 V2V term，也要能明确 fallback 到 V2X 相关解释，而不是空答
- fallback 需要可解释，不允许静默漂移

### 回归集 3：参数解释型

- `CC阻值是什么意思`
- `CP占空比是什么意思`
- `绝缘电阻是什么意思`

预期：

- 参数类问题不能只返回大表
- 至少要产出“该参数表示什么”的解释

---

## 八、最终诊断结论模板

以后遇到类似错误，建议统一按下面格式诊断：

```text
错误类型:
  限定词丢失型 / 别名漂移型 / 类型判定错位型 / 答案策略错配型 / 知识建模缺口型

首发层:
  semantic parse / rewrite / topic resolution / retrieval / answer policy

放大层:
  topic resolution / rerank / routing / synthesis

根因:
  用一句话描述链路失真机制

为什么不是单点补丁:
  说明这类错误会影响哪些同类问法

应该修的层:
  P0 / P1 / P2 / P3
```

---

## 九、当前 KB1 的初步结论

基于当前代码和实际样例，KB1 目前最主要的不是“召回能力不足”，而是：

1. query rewrite 的主题锚点保真不够
2. parameter / definition / general_search 三类边界不稳定
3. topic resolution 对粗主题过于友好
4. parameter 类问题缺专用 answer policy

所以最核心的工程判断是：

> 当前问题首先是“理解失真”，其次才是“召回不足”。

如果只补召回，不修理解链路，同类问题会继续重复出现。
