# 当前会话状态

## 项目目标

这是一个本地单机运行的企业知识库工作台，核心不是普通 RAG，而是“知识对象系统”：

- PDF 解析入库
- `evidence -> facts -> wiki -> graph` 的可追溯链
- 查询时先做语义解析，再做 `topic object / topic entity resolution`，再展开知识子图，再取 `facts / evidence`，最后生成答案

## 当前后端架构结论

已经明确并基本落地的主链是：

```text
query -> semantic parse -> topic resolution -> topic entity -> subgraph -> facts/evidence -> answer
```

几个关键原则：

- 不要从答案倒推对象
- 不要为单个问句做补丁
- 要先有知识对象，再围绕对象检索
- `wiki` 是主题视图
- `graph` 是关系骨架
- `facts` 是结构化知识
- `evidence` 是原文依据

## 当前系统状态

系统已经不是 demo 级文本检索系统，已经做成“知识对象驱动”的主骨架。

已基本建立：

- LLM 前置语义解析
- `topic object / topic entity` 显式返回
- `knowledge_subgraph` 显式返回
- `parameter / process / constraint / comparison / definition` 五类主链
- `topic resolution` 前置层
- `wiki / graph / facts / evidence` 协同
- 多套专项回归

## 重要代码模块

主要都在：

- [query_semantic_parser.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/query_semantic_parser.py)
- [topic_resolution.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/topic_resolution.py)
- [query_api.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/query_api.py)
- [answer_api.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/answer_api.py)
- [entities.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/entities.py)
- [graph.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/graph.py)
- [wiki_compiler.py](E:/AI_Project/opencode_workspace/KB1/src/enterprise_agent_kb/wiki_compiler.py)

## 重要设计文档

这些文档已经形成体系：

- [knowledge_first_principles_architecture_2026-04-21.md](E:/AI_Project/opencode_workspace/KB1/docs/knowledge_first_principles_architecture_2026-04-21.md)
- [domain_knowledge_model_v1_2026-04-21.md](E:/AI_Project/opencode_workspace/KB1/docs/domain_knowledge_model_v1_2026-04-21.md)
- [internal_data_flow_across_wiki_graph_facts_evidence_2026-04-21.md](E:/AI_Project/opencode_workspace/KB1/docs/internal_data_flow_across_wiki_graph_facts_evidence_2026-04-21.md)
- [v1_schema_design_2026-04-21.md](E:/AI_Project/opencode_workspace/KB1/docs/v1_schema_design_2026-04-21.md)
- [v1_implementation_roadmap_2026-04-21.md](E:/AI_Project/opencode_workspace/KB1/docs/v1_implementation_roadmap_2026-04-21.md)
- [architecture_deviation_review_2026-04-21.md](E:/AI_Project/opencode_workspace/KB1/docs/architecture_deviation_review_2026-04-21.md)

## 当前回归与验证

关键专项回归已经做过：

- 知识主链回归
- parameter 回归
- timing 回归
- wiki 回归
- graph 回归
- subgraph 回归
- topic object / topic entity 回归

其中 topic object 主链最终已经做到：

- [topic_object_regression_report_2026-04-21.json](E:/AI_Project/opencode_workspace/KB1/docs/topic_object_regression_report_2026-04-21.json)

## UI 当前任务

当前最新任务已经切换到 UI，不要再回去继续架构讨论。

用户要求：

- 根据参考文件 [1.html](D:/000043ce/Desktop/1.html)
- 改 KB1 当前 UI
- 不是做静态图，而是要改现有工作台 UI，并保留功能

## UI 已做的事情

已经开始改：

- [examples/demo.html](E:/AI_Project/opencode_workspace/KB1/examples/demo.html)

已完成：

1. 重写了 style，整体参考 `1.html` 的企业中台风格
2. 重写了 body 结构，变成：
   - 顶部 header
   - 左侧 dark sidebar
   - 中间主工作区
   - 右侧 query / trace sidebar
3. 尽量保留了原 JS 依赖的 DOM id

## UI 当前未完成事项

还没做完整验证，下一会话建议优先做：

1. 检查 `examples/demo.html` 是否还有重复 id
2. 检查 HTML 结构完整性
3. 启动并验证 [http://127.0.0.1:8000/demo](http://127.0.0.1:8000/demo)
4. 修复因为 DOM 改造导致的脚本报错
5. 再继续按 `1.html` 做视觉细化

## 当前最重要的文件

- 参考 UI：
  - [1.html](D:/000043ce/Desktop/1.html)
- 当前要改的 UI：
  - [examples/demo.html](E:/AI_Project/opencode_workspace/KB1/examples/demo.html)

## 新会话建议开场

可以直接说：

```text
继续改 KB1 的 UI。参考文件是 D:/000043ce/Desktop/1.html，目标文件是 E:/AI_Project/opencode_workspace/KB1/examples/demo.html。之前已经重写了 style 和 body 结构，但还没完整验证。请先检查重复 id、HTML 结构和页面实际运行，再继续按参考页细化 UI，同时保留现有功能入口和脚本兼容性。
```
