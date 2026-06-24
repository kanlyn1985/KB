# 文本 LLM Provider 策略

> 同步约束：Sprint 1 WP2(refactor cdf51d9) 改变了文本 LLM 调用契约，按项目硬约束(行为/接口变更须同步文档)落档。

## 1. 现行契约（2026-06-24 起）

所有**文本 LLM** 调用点（`query_semantic_parser`、`advanced_query_planner`、`evidence_judge`、`query_expansion`）统一走**单一可配置 provider**，由 `infrastructure/llm_client.get_text_llm_settings()` 读取：

| 环境变量 | 用途 | 默认 |
|---|---|---|
| `ANTHROPIC_BASE_URL` | 文本 LLM 网关地址 | `AppEndpoints.from_env().anthropic_base_url` |
| `ANTHROPIC_AUTH_TOKEN` (或 `ANTHROPIC_API_KEY`) | 鉴权 token | 必填，缺失则 `RuntimeError` |
| `TEXT_LLM_MODEL` (或 `CLAUDE_MODEL`) | 模型名 | `claude-3-5-sonnet-20241022` |

`_call_astron_text` / `_call_minimax_text` / `_call_astron_backup_text` 现在都是**遗留别名**，均委托到同一个统一端点。`provider_name="text_llm"`。

## 2. 与旧契约的差异（重要）

旧契约（2026-06 前）：minimax 主、astron 兜底的两段式 fallback。
新契约：**单一 provider，无静默 fallback**。provider 失败时 `_mark_provider_failure` 后**抛出**，由调用方决定降级（`parse_semantic_query` 捕获后回退到规则型默认解析）。

> 注意：**OCR/parse provider 路由**（`minimax_primary+astron_backup+paddlevl`）与此无关，仍保留多 provider，见 `docs/dev/api-cli-development-guide.md`。

## 3. 测试约定

- 测试**不再硬编码 minimax/astron 两段顺序**，而是读取 `get_text_llm_settings()` 的配置后断言单次调用命中统一端点。
- 见 `tests/test_query_repair_regression.py::test_text_llm_routes_through_unified_text_llm_endpoint` 与 `test_text_llm_raises_when_unified_provider_fails`。

## 4. 为何去掉两段 fallback

本地唯一可用网关是 `ANTHROPIC_BASE_URL`（识别 Claude 模型名、路由到 GLM；拒绝 `astron-code-latest` 等厂商专用名）。维护两段 fallback 在当前部署下没有真实兜底意义，反而让"主失败→兜底成功"路径长期不可测。改为单一显式 provider 后，失败路径可测、可观测。

## 5. 后续

- 若将来引入第二可用文本 LLM 网关，恢复 fallback 时须同时改代码、配置、测试、本文档，保持四处一致。
- 讯飞/Xunfei 文本 LLM 在 eval Phase 1 baseline 期间出现 500，属 infra flaky，不应阻断 deterministic eval（见 WP3 eval-baseline-policy）。
