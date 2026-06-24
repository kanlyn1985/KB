# definition-query-exact-term-gate-drops-evidence — Report

> Issue report (Sprint 1 WP2). 采集于 2026-06-24。
> 触发测试：`tests/test_mcp_server.py::test_mcp_server_tools_call_answer_query`（已临时标 xfail，绑定本 issue）。

## 1. 现象

通过 MCP（或 `answer_query`）提问 `什么是控制导引电路？`：

- `answer_mode = definition`（策略选对了）
- `direct_answer = '中华人民共和国国家标准：GB/T 18487.4—2025'`（**文档标题，非术语定义**）
- `hit_count = 0`，`evidence = []`，`facts = []`
- 最终答案降级为文档标题，**证据不足却未硬降级为"证据不足"**，而是回填了 standard metadata。

而 `build_query_context(...)` 单独跑同一查询得到 `hit_count = 4, evidence = 4, facts = 0` —— **召回层其实找到了 4 条 evidence**。

## 2. 复现

```python
from pathlib import Path
from enterprise_agent_kb.answer_api import answer_query
r = answer_query(Path('knowledge_base'), '什么是控制导引电路？', limit=4)
# direct_answer = '中华人民共和国国家标准：GB/T 18487.4—2025'
# answer_mode = 'definition', evidence_count = 0, hit_count = 0

from enterprise_agent_kb.query_api import build_query_context
c = build_query_context(Path('knowledge_base'), '什么是控制导引电路？', limit=4)
# hit_count = 4, evidence = 4, facts = 0
```

## 3. 根因（已定位到代码行）

`src/enterprise_agent_kb/answer_api.py` `answer_query()` 内的 **exact-term gate**（约 121-133 行）：

```python
exact_terms = _extract_exact_terms(query)        # 提取到 "控制导引电路"
if exact_terms and not _context_matches_exact_terms(context, exact_terms, ...):
    if not context.get("hits") and not context.get("facts"):
        context = { "hit_count": 0, ..., "evidence": [], "facts": [], ... }   # ← 整体清零
```

- 召回层 `build_query_context` 返回 `evidence=4` 但 `facts=0`、`hits` 为空。
- gate 的"是否清零"判定 **只看 `hits` 和 `facts`，不看 `evidence`**。
- 于是 `not hits and not facts == True` → 把已召回的 4 条 evidence 一并清零。
- 清零后 answer 层无任何 evidence/fact → 降级回填文档标题（standard metadata）。

KB 中确实存在该术语定义 fact：
```
term_definition | {"term": "**控制导引电路 control pilot circuit**",
                    "definition": "设计用于电动汽车和供电设备之间信号传输或通信的电路。..."}
```
但召回层 `facts=0`（`_inject_direct_term_definition_hits` 未把这条 term_definition 注入 facts），叠加 gate 清零，导致定义查询答非所问。

## 4. 两个叠加缺陷

1. **召回层**：定义查询 `控制导引电路` 没有把命中的 `term_definition` fact 注入 `context.facts`（`facts=0`）。`_inject_direct_term_definition_hits` 未触发或未匹配（term 文本带 markdown `**...**` 前缀，可能未对齐）。
2. **答案层 gate**：exact-term gate 的清零条件只看 `hits`/`facts` 不看 `evidence`，在有 4 条 evidence 时错误地把上下文整体清零。

## 5. 影响

- 定义类查询（"X是什么/X是什么意思"）在 term_definition fact 未被注入 facts 时，会答非所问地返回文档标题。
- 这正是评测 pass_rate 上不去的来源之一（定义题命中召回了但答案层丢弃）。
- 违反 evidence-constrained 边界精神：证据不足时应硬降级"证据不足以确认"，而非回填文档标题冒充答案。

## 6. 建议修复方向（留给后续 issue-fix，不在 Sprint 1 WP2 内动 answer 主链路）

- **最小修复（答案层）**：gate 清零条件改为 `not hits and not facts and not evidence`，避免丢弃已召回 evidence。
- **根因修复（召回层）**：让 `_inject_direct_term_definition_hits` 对 markdown 包裹的 term（`**控制导引电路 ...**`）做归一化匹配，把 term_definition fact 注入 facts。
- **降级语义**：证据为空时应返回"证据不足以确认"而非文档标题。
- 配套测试：去掉 `test_mcp_server_tools_call_answer_query` 的 xfail，断言 direct_answer 命中术语定义。

## 7. 约束

- 修复须保持 evidence-constrained answer 边界，不得让 LLM 直接补全定义。
- 不得为"变绿"削弱 MCP 测试断言。

## 8. 到期条件（xfail 解除条件）

当上述任一修复落地、`test_mcp_server_tools_call_answer_query` 在不削弱断言的前提下通过时，移除 xfail 并关闭本 issue。
