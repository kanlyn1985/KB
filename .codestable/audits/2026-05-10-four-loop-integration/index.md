---
doc_type: audit-index
slug: four-loop-integration
status: fixed
created: 2026-05-10
scope:
  - src/enterprise_agent_kb/query_api.py
  - src/enterprise_agent_kb/closed_loop_store.py
  - src/enterprise_agent_kb/api_server.py
  - src/enterprise_agent_kb/generated_tests.py
  - src/enterprise_agent_kb/user_query_retrieval_eval.py
  - examples/demo.html
tags:
  - audit
  - four-loop
  - regression
  - metrics
---

# Four Loop Integration Audit

> **历史命名说明**：本次审计（2026-05-10）在四闭环时期执行，审计名为 `four-loop-integration`，保留原名以维持 `source_audit:` 引用链（多个 issue fix-note 指向本审计）。项目已于 2026-05 升级为六闭环（commit `0b23bbe`），当前主线命名统一为 six-loop。本审计记录的是四闭环时期的集成现状，结论已被后续 six-loop 重构覆盖。

## Scope

本次审计聚焦四个闭环的集成点：入库覆盖、召回记录、答案质量、失败归因和 golden 沉淀。目标是检查“看起来接上了”的链路是否能产生可信指标。

## Summary

四个闭环的主流程已经存在并可运行，相关回归测试通过。本次审计发现的 3 个指标/维护性断点均已处理。

验证命令：

`C:\Python314\python.exe -m pytest tests/test_closed_loop_schema.py tests/test_api_server.py tests/test_query_repair_regression.py -q -k "retrieval_runs or failure_analysis or query_context_requires_clarification"`

结果：

`5 passed, 76 deselected`

数据抽样：

- `retrieval_runs`: 1638
- `retrieval_runs` 中 `retrieved_evidence_ids_json=[]` 但 `linked_evidence_count>0`: 1356
- `source_units`: covered 1308, u3_not_tested 944, u1_text_only 1
- `eval_runs`: 30
- failed `eval_results`: 131

## Findings Matrix

| ID | Severity | Type | Confidence | Finding | Suggested workflow |
|---|---|---|---|---|---|
| F01 | P1 | bug / arch-drift | high | `retrieval_runs.evidence_hit_count` 只统计直接 evidence hit，忽略 fact linked evidence，导致召回诊断被系统性低估。 | fixed |
| F02 | P1 | arch-drift | high | Dashboard 的 `evidence_coverage_rate` 实际来自 `source_units.status`，不是 evidence/fact 覆盖；`fact_coverage_rate` 永远为空。 | fixed |
| F03 | P2 | maintainability | high | `_must_hit_from_retrieved_items()` 已变成死代码，且语义与新的安全约束相冲突。 | fixed |

## Recommended Next Steps

本轮审计发现已全部关闭。后续建议进入下一轮专项评估：统计 graph requested、graph candidates、graph retained after rerank、graph-supported answer 的比例，用数据判断 graph 在召回闭环中的实际贡献。
