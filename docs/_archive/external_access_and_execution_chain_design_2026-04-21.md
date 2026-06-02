# 外部访问与内部执行主链设计

## 1. 文档目的

本文档定义 `KB1` 对外访问的稳定边界，以及知识库内部的执行主链。

目标回答以下问题：

1. 外部系统访问知识库时，从哪一层进入
2. 外部接口应该分几层
3. 知识库内部收到请求后应该如何处理
4. 哪些内部对象不能直接暴露
5. 当前 KB1 已有接口如何映射到未来的标准分层

本文档是后续 API、MCP、Agent 接入和平台化改造的基线。

---

## 2. 基本原则

### 2.1 外部不直接访问内部中间层

外部调用方不应直接默认访问以下内部对象：

- `evidence`
- `facts`
- `wiki_pages`
- `graph_edges`
- `normalized/*.json`

原因：

- 这些对象是内部实现层
- schema 会继续演进
- 直接暴露会把内部实现锁死
- 外部系统会绕过统一的查询理解、路由和校验流程

### 2.2 对外暴露的是“语义入口”，不是“存储表”

知识库对外应提供的是：

- 任务入口
- 结构化知识入口
- 诊断入口

而不是数据库式入口。

### 2.3 外部接口必须稳定，内部执行可以演进

对外 API 需要尽量稳定。  
内部从 `facts/evidence` 升级到 `wiki/graph/knowledge-subgraph` 时，不应要求外部调用方跟着一起重写。

---

## 3. 对外访问三层模型

外部访问分三层。

## 3.1 Task API

这是默认入口，面向业务系统、产品系统、普通调用方。

外部关心的是：

- 帮我回答问题
- 帮我检索结果
- 帮我转换文档
- 帮我构建入库
- 帮我执行测试

Task API 的特点：

- 简单
- 稳定
- 不暴露内部复杂结构
- 直接返回任务结果

典型调用：

- `ask`
- `build`
- `convert`
- `build-and-test`

---

## 3.2 Knowledge API

面向 Agent、平台系统、中间服务。

外部关心的是：

- 这个概念是什么
- 这个对象有哪些参数
- 这个问题对应哪个知识子图
- 这个过程有哪些步骤

Knowledge API 的特点：

- 返回结构化知识对象
- 暴露概念、对象、参数、过程、约束等一等知识对象
- 允许上层系统进行二次编排

典型调用：

- `resolve_concept`
- `resolve_entity`
- `get_parameter_group`
- `get_process`
- `get_subgraph`

---

## 3.3 Trace API

面向开发、运维、评估、调试系统。

外部关心的是：

- 为什么这次没召回
- 命中了哪些证据
- 经过了哪些路由步骤
- 这次回答为什么这么生成

Trace API 的特点：

- 不面向终端业务用户
- 主要用于优化系统与排障
- 可以暴露更多内部执行细节

典型调用：

- `explain_query`
- `trace_retrieval`
- `trace_answer`
- `diagnose_document`

---

## 4. 外部请求进入后的内部执行主链

推荐内部主链如下：

```text
外部请求
-> Access Layer
-> Query Understanding
-> Knowledge Resolution
-> Retrieval
-> Validation
-> Response Assembly
-> 返回结果
```

下面分层解释。

---

## 4.1 Access Layer

职责：

- 识别入口类型
- 参数校验
- 权限校验
- 基础审计
- 调度到正确执行链

这里不做：

- 检索
- 推理
- 拼答案

这里只决定“这个请求应该走哪条链”。

---

## 4.2 Query Understanding

职责：

- 理解用户问题本质在问什么
- 提取问题约束
- 识别目标对象

至少要识别：

- 问题类型
  - 概念
  - 对象
  - 参数
  - 规则
  - 过程
- 主题对象
  - 例如 `CP`、`CC`、`检测点2`
- 显式约束
  - 文档、标准、附录、表号、状态
- 预期答案类型
  - 单值、枚举、步骤、解释、表名

这一层是整个系统最关键的分流点。

---

## 4.3 Knowledge Resolution

职责：

- 把 query 映射到知识空间中的概念或对象
- 定位候选知识子图

这一步不应该先全文搜索，而应该先尝试：

- wiki 概念归并
- graph 邻域扩展
- 对象识别
- 主题页/回路页/过程页定位

例如：

`CP 时序`

不应先搜 `CP 时序` 文本，而应先解析成：

- 概念：控制导引 / CP
- 类型：过程 / 时序

再找相关子图。

---

## 4.4 Retrieval

职责：

- 在已缩小的知识子空间内进行多通道检索

检索通道至少包括：

- concept space
- entity space
- parameter space
- constraint space
- process space
- evidence space

这里的重点不是“搜得多”，而是“只搜正确空间”。

---

## 4.5 Validation

职责：

- 检查命中的候选是否真的能回答问题

至少检查：

- 证据类型是否与问题类型一致
- 是否命中正确子图
- 证据之间是否冲突
- 是否存在更优候选
- 是否应触发二次检索或拒答

这是“准确召回”真正的安全阀。

---

## 4.6 Response Assembly

职责：

- 按请求类型组装最终输出

### 对 Task API

返回：

- 直接答案
- 摘要
- 置信度
- 可选证据

### 对 Knowledge API

返回：

- 结构化知识对象
- 子图
- 关系
- 约束

### 对 Trace API

返回：

- 查询理解结果
- 路由结果
- 命中候选
- 排序说明
- 失败原因

---

## 5. 不同外部调用方应从哪层进入

### 5.1 业务系统 / 产品系统

默认从 `Task API` 进入。

原因：

- 简单
- 稳定
- 不需要理解内部模型

### 5.2 Agent / 编排平台 / 工作流系统

优先从 `Knowledge API` 进入。

原因：

- 这些系统往往需要结构化知识对象，而不只是最终答案

### 5.3 开发 / 运维 / 评估系统

从 `Trace API` 进入。

原因：

- 这些系统关心的是“为什么”而不是“是什么”

---

## 6. 当前 KB1 已有接口与未来分层映射

## 6.1 当前已存在的 Task API 雏形

当前已经接近 Task API 的包括：

- `/answer-query`
- `/search`
- `/build-document`
- `/build-document-and-test`
- `/convert-document`

这些可以继续保留，但未来建议统一命名风格。

## 6.2 当前已存在的 Trace API 雏形

当前已经接近 Trace API 的包括：

- `/query-context`
- `/document-diagnostics`
- `/document-detail`
- `/job-status`

这些已经具备调试价值。

## 6.3 当前缺失的 Knowledge API

目前 KB1 最大缺口之一是：

**还没有正式的 Knowledge API 层。**

未来应新增这类接口：

- `/resolve-concept`
- `/resolve-entity`
- `/get-parameter-group`
- `/get-process`
- `/get-subgraph`

---

## 7. 推荐的对外 API 组织方式

推荐未来按语义分组组织：

### Task API

- `POST /task/ask`
- `POST /task/convert`
- `POST /task/build`
- `POST /task/build-and-test`

### Knowledge API

- `POST /knowledge/resolve-concept`
- `POST /knowledge/resolve-entity`
- `POST /knowledge/get-parameter-group`
- `POST /knowledge/get-process`
- `POST /knowledge/get-subgraph`

### Trace API

- `POST /trace/query`
- `POST /trace/retrieval`
- `POST /trace/answer`
- `POST /trace/document`

当前不一定需要马上改 URL，但逻辑上应向这个结构靠拢。

---

## 8. 外部调用时的推荐动作

### 8.1 如果目标是“给最终用户答案”

调用：

- Task API

不要直接访问：

- facts
- evidence
- graph

### 8.2 如果目标是“给 Agent 一个可操作知识对象”

调用：

- Knowledge API

### 8.3 如果目标是“理解系统为什么失败或为什么这么答”

调用：

- Trace API

---

## 9. 为什么这条路必须先定

如果不先定对外访问主链，后续会出现几个问题：

- API 越来越多但职责混乱
- 外部直接绑定内部结构
- wiki/graph 不知道怎么进入主链
- schema 改动会频繁破坏外部调用

所以：

**先定义外部访问层与内部执行主链，是所有后续知识化改造的前置条件。**

---

## 10. 实施建议

### 第一阶段

在现有 API 基础上明确：

- 哪些属于 Task API
- 哪些属于 Trace API

### 第二阶段

新增第一批 Knowledge API

优先建议：

- `resolve-concept`
- `get-parameter-group`
- `get-process`

### 第三阶段

让内部执行主链真正切换成：

`query understanding -> knowledge resolution -> retrieval -> validation -> answer`

而不是现在偏向：

`query -> facts/evidence -> answer`

---

## 11. 结论

外部访问知识库时，不应从内部存储层进入，而应从：

- Task API
- Knowledge API
- Trace API

三层之一进入。

而知识库内部应统一遵循：

`Access -> Understanding -> Resolution -> Retrieval -> Validation -> Response`

这条主链。

这就是 KB1 未来所有接口和执行逻辑的基础。
