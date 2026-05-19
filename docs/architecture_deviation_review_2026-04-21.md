# 当前方案偏差复盘

## 结论

当前 KB1 **没有整体走偏**，主线方向仍然正确：

- 从文本检索走向知识对象检索
- 从单通道召回走向分层链路
- 从 query 直接搜文本走向 `semantic parse -> topic object -> subgraph -> facts/evidence -> answer`

但执行过程中，确实多次出现**局部滑回“检索补丁模式”**的情况。  
这些偏差没有推翻主线，但会拖慢系统向“真正知识系统”收敛。

---

## 一. 当前已经证明正确的主线

下面这些方向应视为 **确定保留** 的主线，不应再回退：

### 1. LLM 前置语义解析

外部 query 先做语义解析，而不是直接做字符串匹配。

当前作用：
- 识别 `query_type`
- 提取 `target_topic`
- 提取 `answer_shape`
- 提供 `aliases / must_terms / should_terms`

判断：
- 这是正确方向
- 后续应强化稳定性与可观测性
- 不应再回到纯规则 rewrite

### 2. 分层知识链

当前已经形成的链条：

`wiki -> graph -> facts -> evidence`

这条分层链是正确的，因为它区分了：
- 主题视图
- 关系结构
- 结构化事实
- 原文证据

判断：
- 必须继续强化
- 不应再把这些层重新混成单层候选池

### 3. 显式 topic object

当前 query context 已显式返回：
- `topic_objects`
- `topic_object_ids`

判断：
- 这是从“检索系统”走向“知识系统”的关键一步
- 后续所有答案链应尽量围绕 topic object 展开

### 4. 类型化主链

现在至少已经区分：
- `definition`
- `parameter`
- `process`
- `comparison`
- `constraint`

判断：
- 这是正确方向
- 后续应继续保持类型分流，而不是重新回到 generic ranking

### 5. 统一回归集

已经有统一主链回归：
- [knowledge_chain_regression_report_2026-04-21.json](E:/AI_Project/opencode_workspace/KB1/docs/knowledge_chain_regression_report_2026-04-21.json)

判断：
- 这是正确基础设施
- 后续应扩展，不应放弃

---

## 二. 已出现的偏差

下面这些不是根本性错误，但属于会拖慢系统收敛的偏差。

### 1. 过多在答案层做补丁

表现：
- 针对某个问句单独修排序
- 针对某类词临时加 bonus
- 在 answer layer 做过多“错了就兜底”

问题：
- 这些做法能短期改善单点效果
- 但会掩盖对象层缺失

本质偏差：
- 把“知识建模问题”暂时变成了“答案后处理问题”

### 2. 把对象问题推迟到 retrieval/answer 才解决

例如 `constraint` 的问题暴露出：
- `target_topic` 已经有了
- 但 requirement/threshold 自身没有形成稳定 topic object

结果：
- 系统只能在 answer 层用加权/兜底来修

本质偏差：
- 对象层不够强，后面只能用排序和 fallback 硬顶

### 3. graph 一度只是“返回关系”，不是“约束器”

虽然 graph 已开始生成：
- `has_process`
- `has_parameter_group`
- `has_constraint`
- `has_comparison`

但很多时候它仍然只是：
- 给前端看
- 给 answer 附带返回

而没有真正成为：
- 子图裁剪器
- topic 邻域约束器

本质偏差：
- graph 还没完全从“辅助信息”升级成“主链约束器”

### 4. `constraint` 一度退回成“文本要求检索”

这是最明显的偏差。

表现：
- 问“急停有什么要求”时
- 系统能识别为 constraint
- 但内部仍然在 requirement/threshold 池里找最像的文本

结果：
- topic 不稳定
- 容易被 overview / general_requirement 抢答

本质偏差：
- 约束对象没有完全对象化

---

## 三. 这些偏差为什么会出现

### 1. 工程推进压力

为了尽快让某类问题“先能答”，会自然选择：
- 在现有答案层补一点逻辑
- 在 rerank 上加一点权重

这在短周期里是合理的，但不能长期停留。

### 2. 文档解析与对象建模不同步

很多对象层问题不是答案层能修的，而是：
- parse
- knowledge_units
- facts
- entities

这些阶段先没有把对象建出来。

### 3. topic object 直到较后阶段才显式化

在此之前，系统虽然有 wiki / graph / facts，但没有统一的“topic object”返回对象。  
所以很多逻辑只能退回：
- wiki pages
- facts pool
- answer fallback

---

## 四. 当前哪些属于“临时补丁”

以下内容当前仍应视为 **过渡性方案**，后续应该逐步收缩或替换：

### 1. answer 层 topic evidence fallback

当前用途：
- 当对象层还不够强时，把答案拉回主题正文

判断：
- 作为过渡方案合理
- 但长期不应替代对象层映射

### 2. 各 intent 的 bonus 规则

包括：
- `_subgraph_bonus`
- 某些 fact_type 优先级
- 某些 intent-specific manual ranking

判断：
- 这些仍然有用
- 但后续应逐步被更强的 object relation 替代

### 3. process/constraint/comparison 的局部 fallback

判断：
- 当前是必要的工程兜底
- 不应视为最终架构

---

## 五. 当前哪些已经可以视为稳定基线

以下可以视为 **稳定保留项**：

### 1. query semantic parser
### 2. topic_objects
### 3. knowledge_subgraph
### 4. wiki 分层
### 5. graph relation types
### 6. parameter/process/comparison 主链
### 7. 统一 knowledge chain regression

这些是后续所有演进的基线。

---

## 六. 后续应淘汰或弱化的东西

### 1. 纯 query 文本 bonus 驱动

如果某个类型长期仍主要靠：
- query 词命中
- snippet 词命中

就说明对象层还没做好。

### 2. 过多依赖 generic evidence fallback

这类 fallback 可以留，但应逐步退到次要位置。

### 3. “按单个问句修系统”

后续不应再围绕某一条 query 单独调系统。  
应该围绕：
- 某类知识对象
- 某类 query intent
- 某类 topic mapping

来改。

---

## 七. 现在最应该继续的正确方向

### 1. 强化 topic object 层

目标：
- 让所有 query 都优先落到 topic object

### 2. 强化 object -> fact relation

尤其是：
- `constraint topic -> requirement / threshold`
- `process topic -> process_fact / transition_fact`
- `parameter topic -> parameter_value / table_requirement`

### 3. 让 graph 真正成为约束器

目标：
- 不只是返回 relation
- 而是决定哪些 facts 可以进入答案

### 4. 扩充 object-level regression

不要只测答案对不对，还要测：
- 是否命中正确 topic object
- 是否命中正确 subgraph
- 是否进入正确 fact type

---

## 八. 当前最准确的阶段判断

现在 KB1 处在：

**“主架构方向已经对，正在从过渡性补丁逐步回收到对象驱动主链”的阶段。**

所以当前最重要的不是怀疑总方向，而是：

- 保留主线
- 识别补丁
- 逐步把补丁替换成对象层能力

---

## 九. 一句话总结

当前系统没有根本走偏。  
真正的问题不是方向错，而是：

**执行中仍然多次滑回“检索补丁模式”，而下一阶段的工作就是把这些补丁逐步消化回 topic object / subgraph / relation 这条主线上。**
