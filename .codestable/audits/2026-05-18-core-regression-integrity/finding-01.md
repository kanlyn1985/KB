---
doc_type: audit-finding
slug: shared-kb-mutated-by-mcp-build-document-test
severity: P0
type:
  - bug
  - arch-drift
confidence: high
suggested_action: cs-issue
---

# F-01 Shared KB Mutated By MCP Build Document Test

## Finding

`tests/test_mcp_server.py` 通过 MCP `build_document` 工具直接对共享 `knowledge_base` 中的 `DOC-000003` 执行重建。该测试不是隔离 workspace，也不是只读验证；它会改写真实 pages/blocks/evidence/facts/wiki/graph/coverage 派生状态。

## Evidence

- `tests/test_mcp_server.py:92` 定义 `test_mcp_server_tools_call_build_document_exposes_coverage`
- `tests/test_mcp_server.py:117-118` 调用 MCP 工具 `build_document`，参数为 `{"doc_id": "DOC-000003"}`
- `src/enterprise_agent_kb/mcp_server.py:190-192` `_tool_build_document` 直接执行 `run_document_pipeline(workspace_root, doc_id)`
- 全量测试后 DB 状态显示：
  - `DOC-000003` pages=157
  - `DOC-000003` evidence=317
  - `DOC-000003` facts=185
  - `DOC-000003` source_units=0

## Impact

这是用户感受到“以前能用，现在突然 fail”的最高优先级根因之一。共享知识库被测试重建后，CP 控制导引事实缺失，`CP控制导引是什么意思` 从正确定义退化到 ASPICE/V2G/标准元数据噪声。

## Root Cause

测试层没有隔离真实数据；MCP 工具也没有 dry-run / staging / explicit destructive confirmation。测试验证的是 operator-facing destructive action，却把真实工作区当作临时 fixture。

## Suggested Fix

- MCP/API/CLI 的 build_document 测试必须使用临时 workspace 或复制出来的最小 fixture DB。
- 对真实 `knowledge_base` 的 destructive rebuild 在测试中默认禁用。
- MCP `build_document` 增加明确的 destructive action guard 或 dry-run mode。
- 把 `DOC-000003` 这类核心业务回归文档设为 read-only baseline，测试只能查询不能重建。

