---
doc_type: feature-acceptance
feature: 2026-05-10-golden-case-auto-promotion
status: accepted
summary: Eval 失败已支持批量生成 golden draft，激活仍受 readiness gate 约束
roadmap: kb1-four-loop-hardening
roadmap_item: golden-case-auto-promotion
tags:
  - regression
  - golden
  - acceptance
---

# Golden Case Auto Promotion Acceptance

## 1. 验收结果

通过。Failure Analysis 中的 eval 失败现在可以批量生成 golden draft；没有明确期望锚点的失败会保持 blocked，不会把错误召回结果固化成 golden。

## 2. 代码改动

- `src/enterprise_agent_kb/closed_loop_store.py`
  - 新增 `draft_golden_cases_from_eval_failures()`
  - 草案生成不再从失败实际 retrieved items 推导 `must_hit`
- `src/enterprise_agent_kb/api_server.py`
  - 新增 `POST /draft-golden-from-failures`
- `examples/demo.html`
  - Failure Analysis 增加“生成全部 Golden 草案”按钮
- `tests/test_closed_loop_schema.py`
  - 覆盖批量生成、幂等和错误 top hit 不变成 must_hit
- `tests/test_api_server.py`
  - 覆盖批量 draft API
- `tests/test_delivery_assets.py`
  - 覆盖 Workbench 批量入口

## 3. 验证

命令：

`C:\Python314\python.exe -m pytest tests/test_closed_loop_schema.py tests/test_api_server.py -q -k "batch_drafts_all_eval_failures or failure_can_be_drafted or golden_draft_activation_blocks_missing_assertion or lists_eval_runs_and_details"`

结果：

`4 passed, 24 deselected`

命令：

`C:\Python314\python.exe -m pytest tests/test_delivery_assets.py -q`

结果：

`2 passed`

## 4. Roadmap 回写

`kb1-four-loop-hardening-items.yaml` 中 `golden-case-auto-promotion` 已更新为 `done`，关联 feature `2026-05-10-golden-case-auto-promotion`。
