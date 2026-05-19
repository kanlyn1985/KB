# V1 实施路线图

## 1. 文档目的

本文档将已有的上位设计收敛为可执行的实施路线图。

已存在的上位设计包括：

- 第一性原理架构设计
- 领域知识模型 V1
- 内部数据流设计
- V1 schema 设计
- 现有项目复用评估

本路线图回答：

1. 第一阶段先改什么
2. 每阶段复用哪些现有模块
3. 每阶段产出什么
4. 每阶段如何验证
5. 哪些风险需要控制

---

## 2. 实施总原则

### 2.1 保留工程骨架，替换语义中层

当前系统最有价值的是工程骨架：

- workspace
- SQLite
- CLI
- API
- 页面
- jobs
- parse / doc_ir / quality

最需要升级的是语义中层：

- facts
- entities
- wiki
- graph
- retrieval
- answer

所以实施策略不是推倒重来，而是：

**保留外壳，逐步替换知识表达与召回主链。**

### 2.2 先落最值钱的对象，再扩全域

V1 不应一次性覆盖全部领域对象。  
应优先落最能提升召回准确性的对象：

1. parameter
2. process / transition
3. concept / wiki
4. graph relations

### 2.3 每一阶段必须可验证

每一阶段都必须能回答：

- 新增了什么能力
- 如何衡量它是否有效
- 如果失败，回滚或修正点在哪里

---

## 3. 总体阶段划分

建议分五个阶段：

### Phase 1

参数与归属模型升级

### Phase 2

过程 / 时序 / 状态模型升级

### Phase 3

wiki 升级为主题归并层

### Phase 4

graph 升级为领域关系骨架

### Phase 5

retrieval / answer 切换为知识子图驱动

---

## 4. Phase 1：参数与归属模型升级

## 4.1 目标

把当前“参数型问答依赖词命中”的状态，升级为：

- 参数对象一等化
- 参数归属可计算
- 参数答案可子集筛选

## 4.2 复用现有模块

直接复用：

- `parse.py`
- `doc_ir.py`
- `layout_cleaner.py`
- `knowledge_units.py`
- `facts.py`
- `answer_api.py`
- `answer_policy.py`

## 4.3 具体工作

### A. parameter payload 对齐 V1 schema

最少包含：

- `canonical_name`
- `symbol`
- `unit`
- `value_nominal`
- `value_min`
- `value_max`
- `loop_scope`
- `interface_scope`
- `detection_points`
- `scope_confidence`
- `source_table`

### B. 让 parameter 成为主查询对象

在 retrieval 和 answer 层明确：

- 参数问题优先 parameter 子空间
- 而不是全文 evidence / requirement 主导

### C. 构建参数回归基准

建立一批参数问题：

- 单参数
- 参数集合
- 检测点参数
- 接口参数
- 状态参数

## 4.4 验证标准

- 参数类问题能稳定命中 parameter facts
- 参数答案不再优先掉入目录/前言
- 至少一批参数回归样例稳定通过

## 4.5 当前状态

Phase 1 基本已启动，部分能力已存在，但还未完全按 V1 schema 统一。

---

## 5. Phase 2：过程 / 时序 / 状态模型升级

## 5.1 目标

把“时序/流程问题”从文本命中模式升级为：

- process
- state
- transition

三类对象驱动。

## 5.2 复用现有模块

部分复用：

- `knowledge_units.py`
- `facts.py`
- `query_rewrite.py`
- `retrieval_router.py`
- `answer_api.py`

## 5.3 具体工作

### A. 引入 process_fact / transition_fact

从：

- 时序表
- 控制过程说明
- 状态说明

抽取：

- 过程名称
- 状态
- 状态迁移
- 触发条件
- 动作
- 时间约束

### B. 建立时序类查询路由

例如：

- `CP 时序`
- `握手流程`
- `紧急停机过程`

要先进入 process 子空间，而不是 parameter 子空间。

### C. 建立时序回归测试

回归集要覆盖：

- 状态迁移
- 步骤顺序
- 时间约束
- 停机过程

## 5.4 验证标准

- 时序问题能优先命中 process / transition / timing table
- 参数表不再污染时序问答

---

## 6. Phase 3：wiki 升级为主题归并层

## 6.1 目标

把 wiki 从“展示页”升级为：

- concept 入口
- entity 入口
- process 入口
- parameter group 入口

## 6.2 复用现有模块

部分复用：

- `wiki_compiler.py`
- `entities.py`
- `facts.py`

## 6.3 具体工作

### A. 扩 wiki_type

新增：

- `concept_wiki`
- `entity_wiki`
- `process_wiki`
- `parameter_group_wiki`

### B. 增 primary node 语义

每个 wiki 页明确：

- `primary_node_type`
- `primary_node_id`

### C. 将 wiki 引入查询第一跳

query 进入后，先 resolve 到 wiki 主题页，再扩 graph 和 facts。

## 6.4 验证标准

- 概念型问题优先命中 concept wiki
- 参数问题能先命中 parameter group wiki
- 过程问题能先命中 process wiki

---

## 7. Phase 4：graph 升级为领域关系骨架

## 7.1 目标

让 graph 从“少量文档边”升级为真正的领域图。

## 7.2 复用现有模块

部分复用：

- `graph.py`
- `entities.py`
- `facts.py`

## 7.3 具体工作

### A. 扩 node type

graph 应支持：

- concept
- entity
- parameter
- constraint
- process
- state
- transition

### B. 扩 relation type

新增：

- `has_entity`
- `has_parameter`
- `belongs_to_loop`
- `belongs_to_interface`
- `measured_at_detection_point`
- `has_process`
- `has_transition`
- `constrained_by`

### C. graph 完整性检查

新增检查：

- 孤立节点
- 无归属参数
- 无过程归属的时序对象
- wiki 无法归并的图节点

## 7.4 验证标准

- 高频查询可被映射到图中的局部子图
- graph 能为 retrieval 提供裁剪作用

---

## 8. Phase 5：retrieval / answer 切换为知识子图驱动

## 8.1 目标

把当前：

`query -> facts/evidence`

升级为：

`query -> wiki resolution -> graph expansion -> typed retrieval -> validation -> answer`

## 8.2 复用现有模块

保留外壳：

- `query_api.py`
- `retrieval.py`
- `retrieval_router.py`
- `reranker.py`
- `answer_api.py`
- `answer_policy.py`

重写其主逻辑。

## 8.3 具体工作

### A. query route 重构

问题类型至少分为：

- concept
- entity
- parameter
- constraint
- process

### B. retrieval space 重构

检索空间至少分为：

- concept space
- entity space
- parameter space
- constraint space
- process space
- evidence space

### C. validation 层显式化

把当前隐式规则变成显式校验层。

### D. answer bundle 显式化

定义：

- `AnswerBundle`
- `EvidenceBundle`
- `KnowledgeSubgraph`

使答案组装不再依赖临时拼接。

## 8.4 验证标准

- query 能先落主题，再落子图，再取证
- 无关高频文本明显降权
- answer 更少依赖 query-specific patch

---

## 9. 每阶段的交付物

### Phase 1

- 参数 schema 升级
- 参数回归集
- 参数答案稳定性提升

### Phase 2

- process / transition facts
- 时序回归集

### Phase 3

- 新 wiki types
- wiki-driven resolve

### Phase 4

- 新 graph edge types
- graph 完整性检查

### Phase 5

- 新 retrieval 主链
- AnswerBundle 机制
- 查询稳定性回归

---

## 10. 风险与控制

### 风险 1：过早重构过多层

控制：

- 先做 Phase 1 / 2
- 再做 wiki / graph / retrieval 主链切换

### 风险 2：现有功能回归

控制：

- 保持现有 CLI / API / 页面入口不变
- 内部逐步替换

### 风险 3：回归集不足

控制：

- 每一阶段必须新增对应回归集
- 不能只靠人工试问

---

## 11. 当前最推荐的立即动作

如果从现在开始正式开发，建议顺序：

1. 完成 Phase 1 收尾
2. 立刻启动 Phase 2
3. 暂不继续做 query 级零散补丁
4. 以 V1 模型推进 wiki / graph / retrieval 重构

---

## 12. 最终结论

当前架构已经足够支撑正式开发。  
现在最需要的不是继续讨论抽象概念，而是：

**按阶段实施。**

V1 路线图建议：

- Phase 1 参数
- Phase 2 过程
- Phase 3 wiki
- Phase 4 graph
- Phase 5 retrieval / answer

这就是 KB1 从现状进入知识驱动系统的实际开发顺序。
