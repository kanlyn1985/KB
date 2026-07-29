# KB-Ontology 领域术语表

**状态**: 已确认（grill session 2026-07-24）
**范围**: 系统全局术语定义

---

## Core Terms

### Ontology（本体）

系统的核心知识表示形式。不是文档集合，而是从文档中萃取的**结构化知识图谱**——由 Entity、Attribute、Relation 组成。

- 文档是知识的**来源**，不是知识的**存储形式**
- 知识一旦萃取进本体，与原文档解耦——同一概念的信息可来自多篇文档并合并

### Entity（实体）

本体中的**节点**——一个有独立属性和关系的领域概念。

判定标准：**如果一个概念有自己的属性，并且能和其他概念建立关系，它是 Entity。如果它只是描述另一个概念的值或位置，它是属性或证据。**

- Entity 是"DCDC输出纹波"（参数），不是"30mVpp"（属性值）
- Entity 是"ISO 14229"（标准），不是"第5章"（文档结构）
- Entity 是"示波器测量法"（方法），不是"表3"（文档元素）

### Class（类型）

Entity 的**类型模板**。声明该类 Entity 应该有哪些属性、能参与什么关系、什么条件下视为同一实体。

- Class 是**契约**——一旦确认就锁定，新增 Class 是人工决策
- Class 不是预先内置的——通过 bootstrap 从数据中发现，人工 review 后锁定
- 每个领域定义自己的 Class 集合，Core 不知道具体有哪些 Class

### Attribute（属性）

Entity 的**结构化属性**。以 triple 形式存储：`(entity_id, attribute_name, attribute_value)`。

- value 带类型标记：number / string / boolean / entity_reference
- 属性模板在 Class 定义中声明（必填/选填、类型）
- 一个属性可有多篇文档的证据支持

### Relation（关系）

两个 Entity 之间的**有类型连接**。形式：`(source_entity, relation_type, target_entity)`。

- 关系类型分两层：Core 骨架（part_of, references）+ Domain pack 扩展
- Core 骨架关系跨所有领域通用，语义固定
- Domain pack 关系是领域特有的（如 verified_by, governed_by）

### Evidence（证据）

知识可追溯到原文的**引用**。指向具体文档的具体位置。

- 不是检索单位——不用于文本匹配
- 用途：验证知识来源、回溯原文、审计可信度
- 一个 Entity/Attribute/Relation 可以有多条 evidence（来自不同文档）

### Domain Pack（领域包）

定义一个领域的**本体契约**：Class 列表、属性模板、关系类型、唯一性规则。

- Core 不知道任何具体领域概念——所有领域知识通过 Domain Pack 注入
- 新领域接入 = 编写新的 Domain Pack，不修改 Core
- Domain Pack 是 Ontology schema 的唯一来源

### ContextPack（上下文包）

系统给 Agent 的**主输出**。不是最终答案文本，而是结构化的知识上下文 + 判断。

包含：
- 查询意图理解（QueryFrame）
- 命中的 Entity 及其属性
- 相关的 Relation
- 证据引用
- 警告（歧义、冲突）
- 知识缺口
- 证据充分性判断
- 推荐答案策略

---

## 概念边界

### Ontology vs 文档检索

| | 文档检索 | Ontology |
|---|---|---|
| 知识存储 | 文本片段 + 元数据 | Entity + Attribute + Relation |
| 检索方式 | 关键词/向量匹配文本 | 查询模板遍历本体 |
| 输出 | "找到了这段话" | "这个参数的值是X，条件是Y" |
| 知识关联 | 同文档内的片段 | 跨文档的实体关系 |

### Entity vs 属性值 vs 证据

| | Entity | 属性值 | 证据 |
|---|---|---|---|
| 例子 | DCDC输出纹波 | 30mVpp | "DOC-000001 第3页" |
| 有自己的属性吗 | 有 | 没有 | 没有 |
| 能建立关系吗 | 能 | 不能 | 不能 |
| 独立存在吗 | 是 | 否，依附于 Entity | 否，依附于 Entity/Attribute |

### Class vs Entity

| | Class | Entity |
|---|---|---|
| 是什么 | 类型模板 | 具体实例 |
| 数量 | 少量（人工治理） | 大量（LLM 萃取） |
| 稳定性 | 锁定后不变 | 随文档增加而增长 |
| 定义者 | Domain Pack | LLM 按模板填充 |

---

## 系统定位

### 是什么

**Agent 知识后端**——把文档内容萃取进 Ontology，查询时返回带判断力的 ContextPack。

### 不是什么

- 不是文档管理系统——文档只是知识来源
- 不是搜索引擎——不做关键词匹配返回文本片段
- 不是最终答案生成器——输出结构化上下文，不输出自然语言答案
- 不是通用 RAG——不做向量相似度检索

### 与 Agent 的边界

系统提供：结构化知识 + 证据 + 判断（够不够、有没有歧义、缺什么、怎么答）。
Agent 负责：用这些信息生成最终回答、与用户交互、决定追问策略。
