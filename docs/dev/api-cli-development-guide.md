---
doc_type: dev-guide
slug: api-cli-development-guide
component: api-cli
status: current
summary: KB1 CLI、API server、Workbench 数据出口和本地运行的开发指南
tags:
  - api
  - cli
  - workbench
last_reviewed: 2026-05-18
---

# API And CLI Development Guide

## 概述

CLI 是本地操作入口，API server 是 Workbench 和外部调用入口。开发时要保持同一能力在 CLI/API/Workbench 中的语义一致，尤其是查询上下文、答案输出、closed-loop dashboard 和 hygiene actions。

## 前置依赖

- 工作目录：`E:\AI_Project\opencode_workspace\KB1`
- Python：`C:\Python314\python.exe`
- 知识库根目录：`knowledge_base`
- 本地 API：`http://127.0.0.1:8000`

## 快速上手

启动 API：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base serve-api --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing | Select-Object -ExpandProperty Content
```

打开 Workbench：

```text
http://127.0.0.1:8000/demo
```

CLI 查询：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base answer-query --query "CC是什么意思" --limit 5
```

## 核心概念

| 概念 | 说明 |
|---|---|
| CLI parser | `enterprise_agent_kb.cli` 暴露 operator commands。 |
| API server | `enterprise_agent_kb.api_server` 暴露 HTTP endpoints。 |
| Workbench | `examples/demo.html` 消费 API 数据并展示调试界面。 |
| context payload | 查询上下文、retrieval metadata、evidence judgement。 |
| dashboard payload | six loop dashboard、parse_quality_loop、hygiene_loop、failure analysis。 |
| review payload | 只读审核数据，例如 golden candidates；可展示 readiness，但不能自动激活。 |
| ingestion_acceptance | 新文档构建后的通用入库验收摘要，来自 `validate_document_ingestion`。 |

## 模块入口

| 文件 | 责任 |
|---|---|
| `src/enterprise_agent_kb/cli.py` | 命令行参数和 operator-facing commands。 |
| `src/enterprise_agent_kb/api_server.py` | HTTP API、dashboard、Workbench 数据出口。 |
| `examples/demo.html` | Workbench 前端。 |
| `src/enterprise_agent_kb/ingestion_acceptance.py` | 新文档入库验收报告。 |
| `src/enterprise_agent_kb/parse_risk_actions.py` | 解析风险到修复任务/黄金候选请求的 dry-run 桥接层。 |
| `src/enterprise_agent_kb/query_api.py` | `/query-context` 类能力的数据来源。 |
| `src/enterprise_agent_kb/answer_api.py` | `/answer-query` 类能力的数据来源。 |

## 常见场景

### 新增 CLI 命令

1. 在 `cli.py` 增加 parser 参数和 handler。
2. 参数必须可脚本化，避免交互式输入。
3. 输出结构优先 JSON 可解析。
4. 为 parser 和最小执行路径加测试。
5. 更新 `docs/dev/api-cli-development-guide.md` 和必要的 user guide。

### 新增 API 字段

1. 确认字段来自已有结构化对象，不从 UI 文本反解析。
2. 保持旧字段兼容；新增字段优先 additive。
3. Workbench 展示只读状态，不自动执行破坏性操作。
4. 加 API server 测试。
5. 更新 API/Workbench 指南。

`/closed-loop-dashboard` 当前暴露六个同级闭环：`ingestion_loop`、`parse_quality_loop`、`retrieval_loop`、`answer_loop`、`regression_loop`、`hygiene_loop`。解析质量风险不要塞回入库健康判断；入库可保留 legacy parse fields，独立健康状态由 `parse_quality_loop` 决定。

### Parse View 对比出口

多解析视图是解析质量闭环的根因分析入口。Workbench 的 Parse Views tab 使用：

```http
POST /parse-view-detail
{"doc_id":"DOC-...","text_limit":1200}
```

返回结构包括：

- `summary`：`parse_views` 和 `page_parse_selection` 的候选/选择计数。
- `pages[].selected_view_id`：每页最终进入 `pages/blocks/normalized` 的 view。
- `pages[].selected_reason`：规则评分选择原因。
- `pages[].fallback_chain`：候选排序链。
- `pages[].candidates[]`：候选 view 的 parser、status、quality、structure 和文本预览。

该接口只读，不重跑 parser，不修复数据。新增 OCR-to-HTML 或 table-aware provider 后，必须先确认它在这个接口中作为候选出现，再观察 selection 是否合理。

解析风险行动计划使用：

```http
POST /parse-risk-actions
{"doc_id":"DOC-..."}
```

对应 CLI：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base parse-risk-actions --doc-id DOC-...
```

返回结构包括 `repair_tasks`、`golden_candidate_requests` 和 `guardrails`。该接口也是只读 dry-run：它会写 JSON/Markdown 报告，方便审查，但不会写 `repair_tasks` 表，也不会激活 golden。Workbench Parse Views 页面的“生成行动计划”按钮消费这个接口。

显式持久化：

```http
POST /parse-risk-actions
{"doc_id":"DOC-...","persist_repair_tasks":true}
```

对应 CLI 参数为 `--persist-repair-tasks`。持久化任务按 `reason + module + action` 生成稳定 ID，跨文档聚合；页面级证据保存在 `metadata.parse_risk_docs`。

已持久化任务的复核接口：

```http
POST /parse-risk-repair-review
{"doc_id":"DOC-..."}
```

对应 CLI：

```powershell
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base parse-risk-repair-review --doc-id DOC-...
```

返回 `reviews[].suggested_status`，包括 `done`、`improved`、`still_open`、`expanded`。该接口只读，不自动关闭 repair task。
`parse-risk-actions` 和 `parse-risk-repair-review` 都会写 latest 报告和 timestamped history 报告；API 返回中包含 `history_json_path` 和 `history_report_path`，用于趋势审计。
`/closed-loop-dashboard` 的 `parse_quality_loop.parse_risk_history` 读取这些 timestamped history 文件，按文档返回最新 action、最新 review、attribution delta 和汇总计数。

### 新文档构建验收

CLI 的 `build-document` / `build-file` 和 API 的 `/build-document`、`/build-document-and-test`、上传构建、异步构建完成后，响应中的 `ingestion_acceptance` 字段给出通用入库验收摘要：

- `status`
- `passed_count`
- `warn_count`
- `failed_count`
- `json_path`
- `report_path`
- `failed_checks`
- `warning_checks`

也可以单独调用：

```http
POST /validate-document-ingestion
{"doc_id":"DOC-..."}
```

该接口只生成验收报告，不重跑 pipeline，不修改主数据。

PDF 构建默认启用 fast-text-first provider routing。数字 PDF 文本层足够时，`parser_engine` 会是 `pymupdf_fast_text`，并继续把 `pymupdf_html` 作为候选 view 写入 `parse_views`；文本层不足时才使用 `minimax_primary+astron_backup+paddlevl` 慢路径。

临时关闭 fast path 做对比：

```powershell
$env:EAKB_PDF_FAST_TEXT_FIRST='0'
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base build-file --file "path\to\file.pdf" --progress
```

MiniMax/Astron 可用性不等于所有 PDF 都应走 VLM/OCR。新增 provider 必须作为 parse view 候选接入，并由 selection 写最终 pages/blocks。

### 暴露 Golden 候选

`/golden-candidates` 返回统一候选 review payload，来源可以是 `source_unit` 或 `eval_failure`。该接口默认 dry-run，只写 JSON/Markdown 报告，不激活 `golden_cases`。

Workbench Golden tab 展示：

- origin
- confidence tier
- readiness
- blocked reasons
- assertion contract
- activation gate

任何“确认进入 active golden”的动作都必须走后端 activation gate，不能只由前端按钮或 LLM 生成内容决定。

### 处理 clarification_required

后端返回 `clarification_required=true` 时，前端不能当普通答案渲染。Workbench 应展示可点击选项；点击后用 `option.example_query` 重新发起查询。

## 测试

```powershell
C:\Python314\python.exe -m pytest tests/test_api_server.py tests/test_delivery_assets.py -q
```

CLI parser 相关测试通常在对应功能测试文件中，例如：

```powershell
C:\Python314\python.exe -m pytest tests/test_derived_state_rebuild.py -q -k cli
```

## 已知限制与注意事项

- PowerShell here-string 直接写中文可能损坏查询文本。
- API 服务如果端口被占用，先确认旧服务是否仍在运行，不要盲目启动多个实例。
- Dashboard 和 Workbench hygiene actions 默认只展示建议，不自动执行 rebuild 或 prune。

## 相关文档

- `docs/user/kb1-workbench-user-guide.md`
- `docs/dev/query-chain-development-guide.md`
- `docs/dev/derived-state-governance-development-guide.md`
