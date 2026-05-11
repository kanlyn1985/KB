---
doc_type: issue-analysis
issue: 2026-05-09-short-acronym-query-expansion-llm-gate
status: confirmed
root_cause_type: logic
related:
  - short-acronym-query-expansion-llm-gate-report.md
tags:
  - query-expansion
  - ambiguity
  - llm-boundary
  - root-cause
---

# 短缩写定义查询进入 LLM 扩写根因分析

## 1. 问题定位

| 关键位置 | 说明 |
|---|---|
| `src/enterprise_agent_kb/answer_api.py:24` | `answer_query()` 会先调用 `detect_query_ambiguity()`，命中短缩写歧义后直接返回澄清响应。 |
| `src/enterprise_agent_kb/query_api.py:131` | `build_query_context()` 先执行 `rewrite_query(query)`。 |
| `src/enterprise_agent_kb/query_api.py:132` | `build_query_context()` 随后执行 `expand_query(query)`，此前没有短缩写歧义或规则准入拦截。 |
| `src/enterprise_agent_kb/query_expansion.py:162` | `_should_use_rule_expansion()` 是 LLM 扩写准入门，但原先没有覆盖“短缩写 + 是什么意思/定义/含义”这一类查询。 |

## 2. 失败路径还原

**正常路径**：用户输入 `CP是什么意思` → `answer_query()` 先调用歧义检测 → 命中短缩写多义 → 返回 `clarification_required=true` → 不进入召回和 LLM 扩写。

**失败路径**：用户输入 `CP是什么意思` → `query-context` 直接调用 `build_query_context()` → `build_query_context()` 调用 `expand_query()` → `_should_use_rule_expansion()` 未识别短缩写定义查询 → 进入 LLM 扩写 → 查询入口变慢或超时。

**分叉点**：`src/enterprise_agent_kb/query_expansion.py:162` — LLM 扩写准入门缺少短缩写定义查询规则，导致调试/召回入口和答案入口的边界不一致。

## 3. 根因

**根因类型**：logic

**根因描述**：系统把“是否允许 LLM 参与扩写”的规则放在 `query_expansion` 中，但规则集合只覆盖了标准号、过程活动、参数、电压、电阻、PWM、时序等显式结构化问题，没有覆盖“短缩写 + 定义问法”这一高风险输入类型。答案层虽然有歧义澄清，但 query-context 属于更底层的召回调试入口，不经过答案层，因此暴露了扩写准入门的缺口。

**是否有多个根因**：否。主要根因是扩写准入门缺少通用短缩写定义规则；CLI 参数误用和 PowerShell 中文编码只是运行文档问题，不是该超时的业务根因。

## 4. 影响面

- **影响范围**：影响所有类似 `XX是什么意思`、`XX定义是什么`、`XX代表什么意思` 的短缩写定义问题，不限于 CP。
- **潜在受害模块**：`query-context`、`/query-context` API、Query Lab、Raw retrieval metadata 调试链路、后续依赖 query context 的评测链路。
- **数据完整性风险**：无直接写入数据风险，但会污染 retrieval_runs 的扩写元数据，并可能让不该进入 LLM 的查询产生漂移扩写。
- **严重程度复核**：维持 P1。该问题不破坏数据库，但会破坏查询链路一致性和可解释性原则。

## 5. 修复方案

### 方案 A：在 `query_expansion` 准入门补通用短缩写定义规则

- **做什么**：在 `_should_use_rule_expansion()` 中识别 `[A-Z]{1,6}\d* + 定义问法`，命中后直接返回规则回退，不调用 LLM 扩写。
- **优点**：位于 LLM 扩写统一入口，覆盖 CLI、API、Query Lab、测试等所有调用 `expand_query()` 的入口；不绑定 CP 或 CC 单个词。
- **缺点 / 风险**：只处理短缩写定义类查询，不替代完整的歧义澄清注册或 KB 驱动歧义索引。
- **影响面**：修改 `src/enterprise_agent_kb/query_expansion.py` 和对应回归测试。

### 方案 B：在 `build_query_context()` 前置歧义澄清短路

- **做什么**：在 `build_query_context()` 开头调用歧义检测，命中后返回类似 answer 的 clarification context。
- **优点**：query-context 的输出语义和 answer-query 更一致。
- **缺点 / 风险**：会改变 query-context 作为召回调试工具的行为，旧测试中有“CC是什么意思仍可构建 topic_resolution”的用例，需要重新定义接口边界。
- **影响面**：修改 `src/enterprise_agent_kb/query_api.py`，需要调整更多测试和 UI 调试预期。

### 推荐方案

**推荐方案 A**，理由：本次根因在 LLM 扩写准入门，应该在统一入口阻断不适合 LLM 扩写的查询类型。该方案不针对 CP 单点打补丁，也不改变 `query-context` 的既有返回结构，风险更小。
