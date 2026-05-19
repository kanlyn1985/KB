---
doc_type: feature-acceptance
feature: 2026-05-10-graph-contribution-dashboard
status: accepted
summary: 召回闭环已能量化 graph 候选是否真正进入最终 top 结果
roadmap: kb1-four-loop-hardening
roadmap_item: graph-contribution-dashboard
tags:
  - retrieval
  - graph
  - acceptance
---

# Graph Contribution Dashboard Acceptance

## 1. 验收结果

通过。Graph 现在不再只靠单次 Raw metadata 判断是否发挥作用，closed-loop dashboard 会聚合最近 retrieval runs，显示请求率、候选率、保留率和 rerank 后丢失样本。

## 2. 代码改动

- `src/enterprise_agent_kb/api_server.py`
  - 新增 `_graph_contribution_snapshot()`，从 `retrieval_runs.metadata_json` 聚合 graph contribution。
  - `_closed_loop_dashboard()` 返回 `retrieval_loop.graph_contribution`。
  - `_attach_retrieval_health()` 增加 graph retention 风险。
- `examples/demo.html`
  - Closed Loop Dashboard 顶部指标增加 Graph retention/lost 摘要。
- `tests/test_api_server.py`
  - 覆盖 graph retained/lost 聚合和 graph lost health risk。
- `tests/test_delivery_assets.py`
  - 覆盖 Workbench Graph 指标入口。

## 3. 验证

命令：

`C:\Python314\python.exe -m pytest tests/test_api_server.py -q -k "graph_contribution or retrieval_health"`

结果：

`2 passed, 11 deselected`

命令：

`C:\Python314\python.exe -m pytest tests/test_delivery_assets.py -q`

结果：

`2 passed`

命令：

`C:\Python314\python.exe -m py_compile src\enterprise_agent_kb\api_server.py`

结果：通过。

## 4. Roadmap 回写

`kb1-four-loop-hardening-items.yaml` 和 roadmap 子 feature 清单已增加 `graph-contribution-dashboard`，状态为 `done`。

## 5. 后续修复

Graph contribution 上线后发现后置 direct 注入会在同 ID 替换时丢失 graph provenance，已通过 issue `2026-05-10-post-rerank-injection-provenance` 修复。该修复不改变 graph/rerank 权重，只统一召回层 hit 合并契约。
