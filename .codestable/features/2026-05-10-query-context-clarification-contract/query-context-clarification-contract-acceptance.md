---
doc_type: feature-acceptance
feature: 2026-05-10-query-context-clarification-contract
status: accepted
summary: query-context 与 answer-query 已统一短缩写歧义澄清契约
roadmap: kb1-four-loop-hardening
roadmap_item: query-context-clarification-contract
tags:
  - query
  - clarification
  - acceptance
---

# Query Context Clarification Contract Acceptance

## 1. 验收结果

通过。裸短缩写定义问题现在在 `query-context` 和 `answer-query` 两个入口都先返回澄清，不再由调试链路继续召回候选事实。

## 2. 代码改动

- `src/enterprise_agent_kb/query_ambiguity.py`
  - `detect_query_ambiguity_with_kb()` 支持传入 workspace 下的 ambiguity index path
  - 新增 `build_clarification_context()` 作为共享契约构造
- `src/enterprise_agent_kb/query_api.py`
  - `build_query_context()` 在 rewrite / expansion / retrieval 前执行歧义检测
  - 命中后返回 `retrieval_skipped` clarification context
- `src/enterprise_agent_kb/answer_api.py`
  - 改用 KB-driven ambiguity 检测
  - clarification response 复用共享 context
- `tests/test_query_repair_regression.py`
  - 更新 `CC是什么意思` query-context 期望
  - 新增 `CP是什么意思` query-context 澄清契约回归

## 3. 验证

命令：

`C:\Python314\python.exe -m pytest tests/test_ambiguity_index.py -q`

结果：

`12 passed`

命令：

`C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py -q -m integration -k "query_context_requires_clarification or contextual_cc_definition"`

结果：

`3 passed, 50 deselected`

命令：

`C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py -q -k "answer_query_asks_for_clarification_on_ambiguous_cc or answer_query_asks_for_clarification_on_ambiguous_cp"`

结果：

`2 passed, 51 deselected`

实际查询验证：

- `CP是什么意思`：`context_query_type=clarification`、`retrieval_run_id=null`、`answer_mode=clarification`
- `CC是什么意思`：`context_query_type=clarification`、`retrieval_run_id=null`、`answer_mode=clarification`
- `充电接口里的CC是什么意思`：`context_query_type=definition`、正常产生 retrieval run

## 4. Roadmap 回写

`kb1-four-loop-hardening-items.yaml` 中 `query-context-clarification-contract` 已更新为 `done`，关联 feature `2026-05-10-query-context-clarification-contract`。

## 5. 后续项

下一项 roadmap 是 `golden-case-auto-promotion`，用于把真实查询失败、测试失败和修复案例沉淀为 golden case 草稿。
