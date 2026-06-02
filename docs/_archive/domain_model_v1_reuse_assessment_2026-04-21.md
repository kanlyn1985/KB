# 领域知识模型 V1 与现有项目复用评估

## 1. 目的

本文档基于《领域知识模型 V1》评估当前 `KB1` 代码和数据结构的可复用性。

目标回答：

1. 现有项目里哪些可以直接复用
2. 哪些只能部分复用
3. 哪些应该重构或降级为过渡层

---

## 2. 评估原则

评估时按四层看：

1. 观察层
2. 语义解释层
3. 知识图层
4. 查询与答案层

只要某模块仍然主要围绕“文本块/关键词命中”工作，就不算完全可复用。

---

## 3. 可直接复用的部分

这些部分已经具备较强工程价值，可直接保留。

### 3.1 工作区与存储基础设施

模块：

- `config.py`
- `bootstrap.py`
- `db.py`
- `workspace_admin.py`

原因：

- 它们负责目录结构、SQLite 初始化、路径管理和工作区重置
- 与知识模型类型无强绑定
- 属于稳定基础设施

结论：

- 直接复用

### 3.2 接入与任务外壳

模块：

- `cli.py`
- `api_server.py`
- `jobs.py`
- `pipeline.py`

原因：

- 已提供统一入口、任务轮询和工作流编排
- 虽然内部调用的知识构建步骤未来会变化，但外部入口模式可保留

结论：

- 外壳复用
- 内部阶段顺序未来可调整

### 3.3 PDF 观察层能力

模块：

- `parse.py`
- `pdf_chunking.py`
- `doc_ir.py`
- `layout_cleaner.py`
- `reading_order.py`

原因：

- 它们属于文档观察层
- V1 仍然需要 OCR、布局恢复、页图缓存、分块等能力
- 这些不是“旧路线”，而是知识恢复前的必经步骤

结论：

- 高复用
- 作为观察层保留

### 3.4 质量与诊断外壳

模块：

- `quality.py`
- `doc_diagnostics.py`

原因：

- 文档质量、风险页、解析状态始终需要
- 虽然未来评分项会变，但质量层概念本身应保留

结论：

- 保留
- 评分模型后续重构

### 3.5 页面与交互外壳

模块：

- `examples/demo.html`

原因：

- 当前页面已经具备工程化工作台形态
- 可继续演进，不需要推翻

结论：

- 保留
- 继续围绕知识模型升级前端表达

---

## 4. 可部分复用的部分

这些模块方向没错，但内部语义需要升级。

### 4.1 evidence 层

模块：

- `evidence.py`

问题：

- 当前 evidence 仍以页面块文本为核心
- 更像“可引用片段”
- 还不是知识对象的证据锚点

V1 需求：

- evidence 仍要保留
- 但应更明确地绑定：
  - concept
  - entity
  - parameter
  - process
  - transition

结论：

- 部分复用
- 需要升级 evidence schema 和映射方式

### 4.2 knowledge_units

模块：

- `knowledge_units.py`

问题：

- 当前已经把文档拆成 definition / requirement / table_requirement / procedure
- 这是朝正确方向走的一步
- 但仍然是“表现形式导向”，不是“知识对象导向”

V1 需求：

- 从 knowledge unit 继续向 concept/entity/constraint/process 演化

结论：

- 部分复用
- 作为中间过渡层保留

### 4.3 facts 层

模块：

- `facts.py`

问题：

- 当前 facts 已经开始结构化
- 但大量事实类型仍然是文档导向或抽取导向
- 还没有完全对齐领域知识模型

V1 需求：

- facts 不应只是“抽取结果”
- 应升级成：
  - concept fact
  - entity fact
  - parameter fact
  - constraint fact
  - process fact
  - transition fact

结论：

- 部分复用
- 需要重构事实类型体系

### 4.4 entities 层

模块：

- `entities.py`

问题：

- 当前实体主要集中在：
  - document
  - standard
  - term
- 对领域组件实体支持明显不足

V1 需求：

- 支持 component / loop / interface / state / process node

结论：

- 保留实体构建框架
- 需要大幅扩展实体类型

### 4.5 wiki 层

模块：

- `wiki_compiler.py`

问题：

- 当前 wiki 主要是标准页、术语页、文档页
- 还没有 concept wiki / loop wiki / process wiki / parameter group wiki

V1 需求：

- wiki 成为概念归并层，而不是展示附属层

结论：

- 复用生成器框架
- 重构 wiki 类型体系

### 4.6 graph 层

模块：

- `graph.py`

问题：

- 当前边类型太少
- 主要还是 document-level 和少量 term relation

V1 需求：

- graph 成为领域模型骨架

结论：

- 可复用图谱生成入口
- 边类型和节点来源需要重做

---

## 5. 需要重构或降级的部分

这些部分不应再作为未来主架构核心。

### 5.1 查询改写中的关键词补丁路线

模块：

- `query_rewrite.py`
- `synonyms.py`

问题：

- 当前大量逻辑仍是“查不到就加词”
- 只能作为过渡手段
- 不适合作为通用知识库的长期核心

V1 方向：

- 查询理解应从关键词补丁升级为知识意图识别

结论：

- 暂时保留
- 中长期应降级为辅助手段

### 5.2 主要依赖文本片段命中的 retrieval 路线

模块：

- `retrieval.py`
- `retrieval_router.py`
- `reranker.py`

问题：

- 当前仍然是文本/事实混合检索为主
- wiki / graph 没真正进入主链

V1 方向：

- retrieval 应升级为多空间检索：
  - concept
  - entity
  - parameter
  - constraint
  - process
  - evidence

结论：

- 保留框架
- 召回逻辑需要重构

### 5.3 当前 answer 组合方式

模块：

- `answer_api.py`
- `answer_policy.py`

问题：

- 当前回答逻辑仍然偏向：
  - 命中 -> 组装
- 还没有做到：
  - 先定位知识子图
  - 再类型一致性校验
  - 再答案合成

结论：

- 当前代码只适合作为过渡实现
- 后续应按概念/对象/规则/过程四类答案重构

---

## 6. 现有 schema 的复用结论

### 当前 schema 可保留的表

- `documents`
- `pages`
- `blocks`
- `quality_reports`
- `jobs`
- `dependencies`
- `system_counters`

这些属于观察层或基础设施层。

### 当前 schema 可保留但需增强的表

- `evidence`
- `entities`
- `facts`
- `graph_edges`
- `wiki_pages`

这些是知识层外壳，但语义需要升级。

### 当前 schema 不足之处

未来可能需要新增或隐式表达的对象包括：

- `concepts`
- `parameters`
- `constraints`
- `processes`
- `states`
- `transitions`
- `table_objects`
- `figure_objects`

注意：

不一定必须新建物理表，也可以先在 `facts/entities/graph_edges/wiki_pages` 上扩展实现。  
但逻辑上这些对象必须存在。

---

## 7. 推荐复用策略

### 7.1 短期策略：保留外壳，替换语义核心

建议：

- 保留 parse / quality / evidence / CLI / API / 页面 / pipeline
- 逐步替换 facts / entities / wiki / graph / retrieval / answer 的内部语义

### 7.2 不建议的策略

不建议：

- 推翻整个项目重写
- 或继续在现有 query 补丁路线上堆逻辑

原因：

- 前者浪费已有工程资产
- 后者会让系统越来越难维护

---

## 8. 最推荐的演进路径

### Step 1

保留现有观察层和工作台层

### Step 2

用领域知识模型 V1 重新定义 facts / entities / graph / wiki 的语义对象

### Step 3

让 retrieval 优先走：

- wiki concept resolution
- graph neighborhood expansion
- typed retrieval

### Step 4

让 answer 以知识子图为中心，而不是以文本片段为中心

---

## 9. 最终判断

当前 KB1 并不是“全部都得推倒重来”，相反：

### 可以直接复用的很多

- 工作区
- 存储
- 页面
- API
- CLI
- 任务体系
- PDF 解析与中间层

### 真正要重构的是语义中层和检索中枢

也就是：

- facts
- entities
- wiki
- graph
- retrieval
- answer

换句话说：

**当前项目最值得保留的是工程骨架，最需要升级的是知识表达和召回主链。**
