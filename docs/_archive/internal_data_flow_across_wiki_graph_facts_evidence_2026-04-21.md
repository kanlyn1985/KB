# 内部数据流：wiki / graph / facts / evidence 如何协同工作

## 1. 文档目的

本文档回答一个核心问题：

**当外部一个问题进入知识库后，内部的 wiki、graph、facts、evidence 这些不同数据层，如何串起来工作？**

目标不是讨论某个具体问句，而是定义通用的数据流逻辑。

---

## 2. 总体原则

这几层不是并列竞争关系，而是层层递进、各司其职：

- `evidence`：原始证据层
- `facts`：结构化语义层
- `graph`：关系结构层
- `wiki`：主题归并与可读视图层

在构建时，它们大致是：

```text
evidence -> facts -> graph -> wiki
```

在查询时，它们的工作顺序是：

```text
query
-> wiki 主题定位
-> graph 子图扩展
-> facts 结构化取证
-> evidence 原文落地
-> answer 组装
```

也就是说：

- 构建时：自底向上
- 查询时：自上而下，再回到底层取证

---

## 3. 各层分别是什么

### 3.1 evidence

evidence 是原文证据锚点。

它回答：

- 原文哪里这么说了？
- 是哪一页、哪一段、哪一张表、哪一张图？

evidence 的来源形式可以是：

- 段落
- 表格
- 图注
- 时序表
- 图片说明

因此：

- 表格和段落首先属于 evidence 的来源形式
- evidence 本身不是知识结论，而是知识依据

### 3.2 facts

facts 是从 evidence 中抽出来的结构化断言。

它回答：

- 这段原文到底表达了什么结构化含义？

例如：

- `R4c' = 1000Ω`
- `状态2 -> 状态2'`
- `V2G 是一种双向能量交互技术`

facts 是 evidence 的语义化。

### 3.3 graph

graph 是知识对象之间的关系结构。

它回答：

- 这些知识对象之间怎么连接？
- 哪些对象属于同一个知识子空间？

例如：

- `控制导引 -> has_entity -> CC1`
- `CC1 -> has_parameter -> R4c'`
- `R4c' -> belongs_to_loop -> CC`
- `控制导引 -> has_process -> 握手阶段`

graph 的本质是知识关系骨架。

### 3.4 wiki

wiki 不是证据，也不是单条事实。  
wiki 是知识归并后的阅读视图。

它回答：

- 围绕某个主题，系统目前知道什么？

一个 wiki 页通常建立在：

- 多条 facts
- 多个 evidence
- 多张表 / 多个段落
- 甚至多个文档

之上。

wiki 的本质是：

**主题视图 / 人类可读视图**

---

## 4. 外部问题进入后的完整内部工作链

---

## 4.1 Query Understanding

外部问题先进入问题理解层。

例如：

- `CC阻值有哪些`
- `CP 时序`
- `什么是 V2G`

系统先判断：

- 这是什么类型的问题
  - 概念
  - 参数
  - 规则
  - 过程
- 在问什么对象
  - CC
  - CP
  - V2G
  - 检测点2
- 需要什么样的答案
  - 定义
  - 参数集合
  - 时序过程
  - 约束条件

此时数据从原始字符串变成：

```text
RawQuery -> QueryIntent
```

---

## 4.2 Wiki Resolution

然后系统先用 wiki 找“这个问题最可能在问哪个主题”。

wiki 最适合做：

- 概念归并
- 别名统一
- 主题入口

例如：

### 问 `CC阻值`

wiki 会尝试定位到：

- 控制导引
- CC1/CC2
- 控制导引电路参数
- 兼容控制导引参数

### 问 `CP 时序`

wiki 会尝试定位到：

- 控制导引
- 控制时序
- 充电控制过程

所以 wiki 在查询里扮演的是：

**第一跳主题定位器**

它回答的不是最终答案，而是：

**“你大概率在问这个主题。”**

此时数据变成：

```text
QueryIntent -> KnowledgeAnchorSet
```

---

## 4.3 Graph Expansion

找到 wiki 主题之后，系统进入 graph。

graph 的作用是：

**把主题扩展成一个局部知识子图。**

例如：

### 对 `CC阻值`

graph 会展开到：

- CC1
- CC2
- 检测点
- 相关参数节点
- 相关参数表
- 相关附录
- 相关接口对象

### 对 `CP 时序`

graph 会展开到：

- 控制导引过程
- 状态节点
- 状态迁移
- 时序表
- 相关步骤
- 相关约束

所以 graph 在查询里扮演的是：

**知识子图生成器**

它负责决定：

- 哪些对象相关
- 哪些关系相关
- 哪些内容允许进入下一轮
- 哪些内容应该被排除

此时数据变成：

```text
KnowledgeAnchorSet -> KnowledgeSubgraph
```

---

## 4.4 Facts Retrieval

有了局部知识子图后，系统再去取 facts。

facts 的作用是：

**在目标知识子图内给出结构化知识结论。**

例如：

- 参数值
- 定义
- 约束
- 过程步骤
- 状态迁移

所以：

- wiki 负责主题入口
- graph 负责范围
- facts 负责结构化知识内容

此时数据变成：

```text
KnowledgeSubgraph -> StructuredFactSet
```

---

## 4.5 Evidence Grounding

facts 还不够，因为 facts 是抽取后的知识。  
系统还需要回到底层 evidence，把结论落到原文。

evidence 的作用是：

**证明这些 facts 从哪里来。**

例如：

- 哪一页
- 哪一张表
- 哪一段原文
- 哪张图的说明

此时数据变成：

```text
StructuredFactSet -> EvidenceBundle
```

---

## 4.6 Validation

现在系统已经有：

- wiki 主题
- graph 子图
- facts
- evidence

还不能马上回答，必须先校验。

校验包括：

- 问题类型与证据类型是否一致
- 命中的内容是否属于同一知识子图
- 证据之间是否冲突
- 是否缺失关键支撑
- 是否需要二次检索

例如：

- 问参数，却只命中了前言 -> 不应回答
- 问时序，却只命中了参数表 -> 不应直接回答
- 问 `CC`，却混入别的 loop 参数 -> 需要裁剪

此时数据变成：

```text
EvidenceBundle -> ValidatedAnswerSet
```

---

## 4.7 Answer Assembly

最后根据问题类型组装对外答案。

### 概念问题

- wiki 提供主题骨架
- facts 提供定义
- evidence 提供原文支撑

### 参数问题

- graph 提供参数子图范围
- facts 提供参数值
- evidence 提供表格原文
- wiki 提供参数组归属

### 过程问题

- wiki 提供过程主题
- graph 提供状态/迁移结构
- facts 提供步骤与约束
- evidence 提供时序表或过程说明

### 规则问题

- facts 提供约束
- evidence 提供出处
- wiki 提供主题背景

最终数据变成：

```text
ValidatedAnswerSet -> AnswerBundle
```

---

## 5. 每层的角色一句话总结

### evidence

原文依据层  
回答：原文哪里这么说了？

### facts

结构化断言层  
回答：原文表达了什么结构化含义？

### graph

关系骨架层  
回答：这些知识对象如何连接？

### wiki

主题视图层  
回答：围绕这个主题，系统整体知道什么？

---

## 6. 为什么不是直接搜 facts/evidence

如果直接搜 facts/evidence，会天然出现：

- 目录压正文
- 前言压参数
- 高频词污染结果
- 无法做跨表、跨附录、跨过程推理

而 wiki + graph 在前面，可以先把问题约束到正确主题和正确子图里。

---

## 7. 一个完整例子：`CP 时序`

### 1. Query Understanding

识别为：

- 类型：过程 / 时序问题
- 主题：CP / 控制导引

### 2. Wiki Resolution

命中：

- 控制导引主题页
- 控制时序主题页

### 3. Graph Expansion

扩展：

- 控制过程
- 状态节点
- 状态迁移
- 时序表
- 相关步骤说明

### 4. Facts Retrieval

取出：

- 状态迁移 facts
- 步骤 facts
- 时间约束 facts

### 5. Evidence Grounding

找到：

- 时序表
- 控制过程原文
- 附录相关段落

### 6. Validation

检查：

- 是否真的命中了时序知识
- 是否被参数表污染

### 7. Answer Assembly

输出：

- 过程说明
- 状态变化
- 触发条件
- 时间约束

---

## 8. 一句总括

**wiki、graph、facts、evidence 不是四份不同答案来源，而是一条逐层收缩和逐层落地的知识链。**

它们的协同顺序是：

- wiki 决定你在问哪个主题
- graph 决定这个主题的知识边界
- facts 决定这个边界里有哪些结构化结论
- evidence 决定这些结论的原文依据

最终答案不是从某一层单独产生的，而是从这四层协同产生的。

---

## 9. 最终结论

如果把外部问题进入后的内部数据流压缩成一句话，就是：

**外部问题先进 wiki 找主题，再进 graph 找关系，再进 facts 取结构化知识，最后回 evidence 取原文依据。**

这就是 KB1 未来应遵循的内部知识流转主链。
