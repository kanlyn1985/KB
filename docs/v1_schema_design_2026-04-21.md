# V1 Schema 设计

## 1. 文档目的

本文档把以下三份上位设计继续收敛到可实现的数据结构层：

- 第一性原理架构设计
- 领域知识模型 V1
- 内部数据流设计

目标是定义：

1. KB1 V1 需要哪些核心对象
2. 每个对象至少需要哪些字段
3. 哪些对象应成为一等 schema，哪些可以先挂在现有结构中
4. wiki / graph / facts / evidence 在 schema 上如何对齐

本文档不是数据库迁移脚本，而是实现层 schema 基线。

---

## 2. 设计原则

### 2.1 观察层与知识层分离

观察层保留：

- `documents`
- `pages`
- `blocks`
- `evidence`

知识层新增或重构：

- `concept`
- `entity`
- `parameter`
- `constraint`
- `process`
- `state`
- `transition`
- `graph_edge`
- `wiki_page`

### 2.2 schema 必须支持两种视角

#### 机器视角

- 可检索
- 可排序
- 可扩展子图
- 可约束

#### 人类视角

- 可解释
- 可浏览
- 可定位来源

### 2.3 先做逻辑 schema，再决定物理表拆分

V1 先定义逻辑对象。  
物理实现可以分为两种路径：

- 新建物理表
- 在现有 `facts/entities/wiki_pages/graph_edges` 上扩展字段

短期建议优先采用“现有表扩展 + typed payload”路径。

---

## 3. V1 核心逻辑对象

## 3.1 Concept

表示抽象概念。

### 关键字段

- `concept_id`
- `canonical_name`
- `aliases`
- `concept_type`
- `domain`
- `description`
- `status`
- `source_doc_ids`
- `source_evidence_ids`

### concept_type 建议值

- `technical_concept`
- `standard_concept`
- `process_concept`
- `loop_concept`
- `interface_concept`

### 示例

- 控制导引
- V2G
- 锁止装置

---

## 3.2 Entity

表示具体对象、组件、接口、回路、测点。

### 关键字段

- `entity_id`
- `canonical_name`
- `aliases`
- `entity_type`
- `belongs_to_concept_id`
- `description`
- `scope`
- `status`
- `source_doc_ids`
- `source_evidence_ids`

### entity_type 建议值

- `device`
- `component`
- `interface`
- `loop`
- `detection_point`
- `signal`
- `connector`

### 示例

- CC1
- CC2
- CP
- 检测点2
- 车辆插头
- 车辆插座
- 充电机

---

## 3.3 Parameter

表示参数实例或参数规格。

### 关键字段

- `parameter_id`
- `canonical_name`
- `symbol`
- `parameter_type`
- `value_nominal`
- `value_min`
- `value_max`
- `unit`
- `state_scope`
- `loop_scope`
- `interface_scope`
- `detection_points`
- `scope_confidence`
- `source_table_id`
- `source_figure_id`
- `source_doc_ids`
- `source_evidence_ids`

### parameter_type 建议值

- `resistance`
- `voltage`
- `current`
- `frequency`
- `duty_cycle`
- `switch_state`
- `timing_value`

### 示例

- R4c' = 1000Ω
- U2 = 12V
- 输出频率 = 1000Hz

---

## 3.4 Constraint

表示规则、要求、阈值、适用条件。

### 关键字段

- `constraint_id`
- `constraint_type`
- `subject_ref`
- `predicate`
- `value`
- `condition_scope`
- `applies_to_entity_ids`
- `applies_to_concept_ids`
- `severity`
- `source_section`
- `source_doc_ids`
- `source_evidence_ids`

### constraint_type 建议值

- `requirement`
- `threshold`
- `prohibition`
- `compatibility_rule`
- `state_rule`
- `timing_rule`

### 示例

- 某状态下检测点2电压不应超过某值
- 某模式下必须具备锁止装置

---

## 3.5 Process

表示完整过程或子过程。

### 关键字段

- `process_id`
- `canonical_name`
- `process_type`
- `description`
- `belongs_to_concept_id`
- `precondition`
- `trigger`
- `result_state`
- `source_section`
- `source_doc_ids`
- `source_evidence_ids`

### process_type 建议值

- `charging_process`
- `handshake_process`
- `precharge_process`
- `shutdown_process`
- `fault_process`
- `timing_process`

### 示例

- 握手
- 预充
- 能量传输
- 紧急停机

---

## 3.6 State

表示系统状态。

### 关键字段

- `state_id`
- `canonical_name`
- `state_type`
- `system_scope`
- `description`
- `source_doc_ids`
- `source_evidence_ids`

### state_type 建议值

- `charging_state`
- `interface_state`
- `control_state`
- `fault_state`

### 示例

- 状态1
- 状态2
- 状态2'

---

## 3.7 Transition

表示状态间迁移。

### 关键字段

- `transition_id`
- `from_state_id`
- `to_state_id`
- `trigger`
- `action`
- `time_constraint`
- `related_process_id`
- `source_table_id`
- `source_doc_ids`
- `source_evidence_ids`

### 示例

- 状态1 -> 状态2
- 状态2 -> 状态2'

---

## 3.8 TableObject

表示表的逻辑对象。

### 关键字段

- `table_id`
- `table_title`
- `table_no`
- `table_type`
- `headers`
- `page_no`
- `belongs_to_section`
- `describes_concept_ids`
- `describes_entity_ids`
- `source_doc_ids`

### table_type 建议值

- `parameter_table`
- `timing_table`
- `constraint_table`
- `mapping_table`

---

## 3.9 FigureObject

表示图的逻辑对象。

### 关键字段

- `figure_id`
- `figure_title`
- `figure_no`
- `figure_type`
- `page_no`
- `caption`
- `describes_concept_ids`
- `describes_entity_ids`
- `describes_process_ids`
- `source_doc_ids`

### figure_type 建议值

- `circuit_diagram`
- `timing_diagram`
- `architecture_diagram`
- `structure_diagram`

---

## 4. graph edge schema

graph 的边是 V1 的关键。

### 4.1 基础字段

- `edge_id`
- `src_node_type`
- `src_node_id`
- `relation`
- `dst_node_type`
- `dst_node_id`
- `condition_scope`
- `version_scope`
- `confidence`
- `source_doc_ids`
- `source_evidence_ids`

### 4.2 推荐 relation 集合

#### 概念关系

- `has_entity`
- `instance_of`
- `related_to`
- `equivalent_to`

#### 参数关系

- `has_parameter`
- `belongs_to_loop`
- `belongs_to_interface`
- `measured_at_detection_point`
- `valid_under_state`

#### 约束关系

- `constrained_by`
- `valid_under`
- `applies_to`

#### 过程关系

- `has_process`
- `has_step`
- `has_state`
- `has_transition`
- `triggers`
- `acts_on`

#### 文档关系

- `defines`
- `references`
- `replaces`
- `described_in_table`
- `illustrated_by_figure`

---

## 5. wiki schema

wiki 页不是 Markdown 文件本身，而是逻辑对象。

### 5.1 基础字段

- `wiki_id`
- `wiki_type`
- `title`
- `slug`
- `primary_node_type`
- `primary_node_id`
- `summary`
- `source_fact_ids`
- `source_doc_ids`
- `related_node_ids`
- `render_path`
- `status`

### 5.2 wiki_type 建议值

- `concept_wiki`
- `entity_wiki`
- `process_wiki`
- `parameter_group_wiki`
- `standard_wiki`
- `document_wiki`

---

## 6. facts 在 V1 中的角色

V1 里 `facts` 不应再只是“抽出来的 JSON”。

它应成为统一的 typed statement 层。

### 推荐最小事实类型

- `concept_fact`
- `entity_fact`
- `parameter_fact`
- `constraint_fact`
- `process_fact`
- `transition_fact`
- `document_fact`

### 推荐字段

保留现有基础字段：

- `fact_id`
- `fact_type`
- `predicate`
- `object_value`
- `qualifiers_json`
- `source_doc_id`
- `confidence`

但要求 `object_value / qualifiers_json` 必须逐步对齐 V1 模型字段。

---

## 7. evidence 在 V1 中的角色

evidence 继续保留，但职责更清晰：

- 作为原文锚点
- 为 concept/entity/parameter/process 提供来源

### 推荐扩展字段

- `evidence_kind`
- `source_object_type`
- `source_object_id`
- `page_no`
- `block_id`
- `text`
- `image_ref`
- `table_ref`
- `figure_ref`
- `confidence`

---

## 8. 当前物理实现建议

V1 不建议立刻推翻数据库。

短期建议：

### 8.1 保留现有表

- `documents`
- `pages`
- `blocks`
- `evidence`
- `facts`
- `entities`
- `graph_edges`
- `wiki_pages`

### 8.2 通过 typed payload 演进

即：

- 在 `facts.object_value` 中逐步使用 V1 结构
- 在 `entities` 中扩展 entity_type
- 在 `graph_edges` 中扩展 relation 和 node_type
- 在 `wiki_pages` 中扩展 wiki_type

### 8.3 什么时候拆新表

当出现以下任一情况时再拆：

- 查询性能不足
- object_value / qualifiers_json 过于复杂
- graph 查询过重
- parameter / process 成为主查询对象

---

## 9. V1 与当前模块的对应关系

### 观察层

- `parse.py`
- `doc_ir.py`
- `layout_cleaner.py`
- `reading_order.py`

### 证据层

- `evidence.py`

### 语义解释层

- `knowledge_units.py`
- `facts.py`
- `entities.py`

### 图与主题层

- `graph.py`
- `wiki_compiler.py`

### 检索与答案层

- `retrieval.py`
- `retrieval_router.py`
- `answer_api.py`
- `answer_policy.py`

---

## 10. 第一批必须落的 V1 字段

为了快速进入 V1，最优先建议落地这些字段：

### parameter

- `loop_scope`
- `interface_scope`
- `detection_points`
- `source_table`
- `scope_confidence`

### process / transition

- `from_state`
- `to_state`
- `trigger`
- `action`
- `time_constraint`

### graph edge

- `src_node_type`
- `dst_node_type`
- `relation`

### wiki

- `wiki_type`
- `primary_node_type`
- `primary_node_id`

---

## 11. 查询层未来应该消费哪些对象

### 概念问题

消费：

- concept_wiki
- concept_fact
- concept graph neighborhood

### 参数问题

消费：

- parameter_fact
- parameter_group_wiki
- parameter graph neighborhood

### 规则问题

消费：

- constraint_fact
- constraint related evidence

### 过程问题

消费：

- process_fact
- transition_fact
- process_wiki
- process graph neighborhood

---

## 12. 最终结论

V1 schema 的核心不是加更多字段，而是：

- 明确一等知识对象
- 明确对象关系
- 明确 wiki / graph / facts / evidence 各自承载什么

短期最优策略是：

**保留现有物理骨架，用 V1 typed schema 逐步替换旧的语义载荷。**

这能最大化复用当前工程成果，同时让系统逐步进入真正的知识驱动状态。
