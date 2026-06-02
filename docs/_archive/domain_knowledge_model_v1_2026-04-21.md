# 领域知识模型 V1

## 1. 目标

本模型用于把 `KB1` 从“文档处理系统”升级为“知识系统”。

V1 的目标不是一次性覆盖所有领域，而是建立一个最小但通用的知识抽象，使系统可以：

- 表达领域对象
- 表达对象间关系
- 表达约束与过程
- 支持结构化检索与推理
- 支持 wiki 和 graph 成为召回主链

---

## 2. 设计原则

### 2.1 以知识对象为中心，而不是以文档结构为中心

文档结构：

- 页
- 块
- 表
- 图
- 标题

只作为观察层存在。  
知识层应围绕：

- 概念
- 对象
- 关系
- 约束
- 过程

### 2.2 支持跨表达方式同一性

同一个知识对象，可能同时出现在：

- 术语定义
- 参数表
- 电路图
- 流程说明
- 附录

模型必须允许这些不同来源汇聚到同一知识节点。

### 2.3 可检索、可解释、可推理

模型必须同时满足三件事：

- 检索时可索引
- 回答时可解释
- 推理时可扩展邻域

---

## 3. V1 核心对象

V1 采用六类一等知识对象：

### 3.1 Concept

定义领域中的抽象概念。

示例：

- 控制导引
- 车辆适配器
- V2G
- 锁止装置
- 充电模式

核心字段：

- `concept_id`
- `name`
- `canonical_name`
- `aliases`
- `description`
- `domain`
- `source_docs`

### 3.2 Entity

定义可独立存在的对象、部件、接口或组件。

示例：

- 充电机
- 车辆插头
- 车辆插座
- CC1
- CC2
- 检测点 2
- R4c'
- S2'

核心字段：

- `entity_id`
- `entity_type`
- `name`
- `aliases`
- `belongs_to_concept`
- `scope`
- `source_docs`

### 3.3 Attribute / Parameter

定义某对象的属性或参数实例。

示例：

- R4c' 标称值 = 1000 Ω
- U2 = 12 V
- 输出频率 = 1000 Hz

核心字段：

- `parameter_id`
- `name`
- `symbol`
- `value_nominal`
- `value_min`
- `value_max`
- `unit`
- `applies_to_entity`
- `loop_scope`
- `interface_scope`
- `state_scope`
- `detection_point`
- `source_table`
- `source_page`

### 3.4 Constraint

定义规则、阈值、要求和条件性约束。

示例：

- 在某模式下必须具备锁止装置
- 某检测点电压不应超过某值
- 某状态下应切断电路

核心字段：

- `constraint_id`
- `constraint_type`
- `subject`
- `predicate`
- `value`
- `condition_scope`
- `applies_to_entity`
- `severity`
- `source_section`

### 3.5 Process

定义过程、流程、时序、状态机。

示例：

- 握手
- 预充
- 能量传输
- 正常结束
- 紧急停机

核心字段：

- `process_id`
- `name`
- `process_type`
- `description`
- `trigger`
- `precondition`
- `result_state`
- `source_section`

### 3.6 State / Transition

定义状态及状态变化。

示例：

- 状态 1
- 状态 2
- 状态 2'
- 状态迁移 1 -> 2

核心字段：

- `state_id`
- `name`
- `system_scope`
- `description`

以及：

- `transition_id`
- `from_state`
- `to_state`
- `trigger`
- `action`
- `time_constraint`

---

## 4. V1 关系类型

V1 建议最少支持以下边类型。

### 4.1 概念与对象

- `concept -> has_entity -> entity`
- `entity -> instance_of -> concept`

### 4.2 对象与参数

- `entity -> has_parameter -> parameter`
- `parameter -> belongs_to_loop -> concept/entity`
- `parameter -> belongs_to_interface -> entity`
- `parameter -> measured_at_detection_point -> entity`

### 4.3 对象与约束

- `entity -> constrained_by -> constraint`
- `constraint -> valid_under -> state/process`

### 4.4 过程与状态

- `process -> has_state -> state`
- `process -> has_transition -> transition`
- `transition -> triggers -> process`
- `transition -> acts_on -> entity`

### 4.5 表/图与知识对象

- `table -> describes_entity -> entity`
- `table -> provides_parameter -> parameter`
- `figure -> illustrates_process -> process`
- `section -> defines_concept -> concept`

### 4.6 文档级关系

- `document -> defines -> concept`
- `document -> references -> standard`
- `document -> replaces -> standard`

---

## 5. wiki 与 graph 在 V1 中的角色

### 5.1 wiki：可读的知识视图

wiki 不是简单展示页面，而是知识对象的阅读视图。

V1 建议支持四类 wiki：

- `concept_wiki`
- `entity_wiki`
- `process_wiki`
- `parameter_group_wiki`

例如：

- 控制导引主题页
- CC 回路页
- 充电控制过程页
- 兼容参数表主题页

### 5.2 graph：可计算的知识结构

graph 是召回的主骨架。

查询应先通过 graph 定位知识子图，再进入 evidence/facts 取证。

即：

`query -> concept/entity resolution -> graph neighborhood -> evidence/facts`

---

## 6. 查询语义模型

系统最终不应按“定义/参数/表格/时序”这些表面形式工作，而应按知识意图工作。

V1 建议分成四类：

### 6.1 概念型查询

问：

- 这是什么
- 什么叫
- 如何定义

目标空间：

- `concept`
- `concept_wiki`
- `definition constraints`

### 6.2 对象/组成型查询

问：

- 包含哪些
- 有哪些组成
- 相关对象是什么

目标空间：

- `entity`
- `entity relations`

### 6.3 属性/约束型查询

问：

- 阻值是多少
- 参数有哪些
- 有什么要求
- 阈值是多少

目标空间：

- `parameter`
- `constraint`
- `parameter_group_wiki`

### 6.4 过程/状态型查询

问：

- 时序是什么
- 如何启动
- 结束流程是什么
- 故障如何停机

目标空间：

- `process`
- `state`
- `transition`
- `process_wiki`

---

## 7. 文档到知识模型的映射

V1 要求每种文档表达都映射到知识对象。

### 7.1 标题

映射为：

- `concept`
- `section`
- `process`

### 7.2 术语定义

映射为：

- `concept`
- `concept_wiki`

### 7.3 参数表

映射为：

- `parameter`
- `parameter group`
- `table -> parameter` 边

### 7.4 时序表 / 步骤说明

映射为：

- `process`
- `state`
- `transition`
- `constraint`

### 7.5 电路图 / 图注

映射为：

- `entity`
- `relation`
- `process context`

---

## 8. V1 最小落地范围

为了避免架构过大，V1 只要求覆盖以下高价值能力：

### 8.1 概念

- 控制导引
- V2G
- 车辆适配器
- 锁止装置

### 8.2 对象

- CC1 / CC2 / CP
- 检测点
- 充电机 / 车辆插头 / 车辆插座 / 电动汽车

### 8.3 参数

- 电阻
- 电压
- 电流
- 频率
- 占空比

### 8.4 过程

- 握手
- 预充
- 能量传输
- 正常结束
- 故障停机
- 紧急停机

---

## 9. V1 成功标准

如果 V1 有效，系统应具备：

1. 相同概念的不同表达能聚合到同一知识入口
2. 参数问答不依赖单纯关键词命中
3. 时序问答不依赖表面是否出现“时序”两个字
4. wiki 成为概念归并层
5. graph 成为查询扩展和裁剪主链

---

## 10. 对当前 KB1 的实现含义

V1 对现有实现的要求不是“推翻重来”，而是：

- 现有 parse / evidence 继续作为观察层
- facts 从“松散事实”升级为“知识对象实例”
- wiki 从展示页升级为概念页
- graph 从少量边升级为领域图
- retrieval 从文本检索升级为子图检索

---

## 11. 后续实现顺序

建议顺序：

1. 定义 V1 schema
2. 扩 graph edge types
3. 扩 wiki page types
4. 改 facts 生成逻辑，让 facts 对齐本模型
5. 改 query route，让 wiki/graph 进入主链
6. 改 answer assembly，让答案基于概念子图生成

---

## 12. 结论

领域知识模型 V1 的本质，是把 KB1 从“文档理解系统”推进到“知识表示系统”。

V1 的关键不是更多解析规则，而是：

- 明确知识对象
- 明确关系类型
- 明确查询语义
- 明确 wiki/graph 在检索链中的中心角色

这是后续所有实现和重构的基线。
