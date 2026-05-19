---
doc_type: issue-fix-note
issue: 2026-05-10-retrieval-run-code-version-boundary
status: fixed
summary: retrieval_runs 已记录 code_version，dashboard 可识别旧运行污染
tags:
  - retrieval
  - dashboard
  - fix
---

# Retrieval Run Code Version Boundary Fix Note

## 修复

- `src/enterprise_agent_kb/schema.sql`
  - `retrieval_runs` 新增 `code_version TEXT`。
- `src/enterprise_agent_kb/closed_loop_store.py`
  - `record_retrieval_run()` 写入 runtime code version。
  - runtime code version 优先使用 `EAKB_CODE_VERSION`，否则使用 `src/enterprise_agent_kb` 源码签名；不依赖 `git status`，避免大脏工作区阻塞服务。
  - list/detail retrieval run 输出 `code_version`。
  - 旧库自动补 `code_version` 列。
- `src/enterprise_agent_kb/api_server.py`
  - graph contribution 输出 code version 统计。
  - graph contribution 增加 `current_version_graph`，当前版本有样本时优先用当前版本 graph retention 判断健康。
  - 召回健康检查增加 `retrieval_runs_mixed_code_versions`。
- `examples/demo.html`
  - Graph 指标摘要显示当前版本样本数。
- `tests/test_api_server.py`
  - 覆盖 graph contribution code version 字段和混合版本风险。

## 验证

命令：

`C:\Python314\python.exe -m pytest tests/test_api_server.py -q -k "graph_contribution or retrieval_health or retrieval_runs"`

结果：

`5 passed, 10 deselected`

命令：

`C:\Python314\python.exe -m pytest tests/test_delivery_assets.py -q`

结果：

`2 passed`

命令：

`C:\Python314\python.exe -m py_compile src\enterprise_agent_kb\closed_loop_store.py src\enterprise_agent_kb\api_server.py`

结果：通过。
