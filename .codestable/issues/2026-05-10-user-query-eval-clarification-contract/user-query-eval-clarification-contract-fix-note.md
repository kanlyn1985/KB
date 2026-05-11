---
doc_type: issue-fix-note
issue: 2026-05-10-user-query-eval-clarification-contract
status: fixed
summary: user query eval 已支持 clarification 非召回契约
tags:
  - regression
  - clarification
  - fix
---

# User Query Eval Clarification Contract Fix Note

## 修复

- `src/enterprise_agent_kb/user_query_retrieval_eval.py`
  - clarification context 使用 neutral retrieval quality。
  - contract 支持 `expected_clarification_required` 和 `expected_clarification_options`。
  - eval run 写入 runtime `code_version`。
- `tests/generated/real_user_query_retrieval_cases_2026-05-01.json`
  - `CC是什么意思` 改为 clarification contract。
- `tests/test_retrieval_quality.py`
  - 覆盖 clarification 作为非召回契约。

## 验证

命令：

`C:\Python314\python.exe -m pytest tests/test_retrieval_quality.py -q`

结果：

`7 passed`

命令：

`C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base run-user-query-retrieval-eval --case-file tests\generated\real_user_query_retrieval_cases_2026-05-01.json --suite-id regression:user_query_retrieval:current-code --limit 8`

结果：

`8 passed, 0 failed`

Dashboard 当前状态：

- retrieval status: `ok`
- latest eval pass rate: `1.0`
- retrieval quality ok count: `8`
