---
doc_type: feature-acceptance
feature: 2026-05-17-parse-risk-action-plan
status: accepted
accepted_at: 2026-05-17
---

# Parse Risk Action Plan Acceptance

## 验收结果

已完成解析风险到行动计划的桥接层：

- 新增 `enterprise_agent_kb.parse_risk_actions`。
- 新增 CLI：`parse-risk-actions`。
- 新增 API：`POST /parse-risk-actions`。
- Workbench Parse Views 增加“生成行动计划”。
- 默认只读 dry-run，不写 repair_tasks，不激活 golden。
- 显式传 `--persist-repair-tasks` 或 `persist_repair_tasks=true` 时，非 review-only 任务写入 `repair_tasks`，并按系统性问题跨文档聚合；`impact_count` 表示聚合后的风险页总数。
- 新增 `parse-risk-repair-review` 和 `POST /parse-risk-repair-review`，对已持久化任务输出只读状态建议，不自动关闭任务。
- action/review 报告同时写 latest 和 timestamped history，避免趋势证据被覆盖。
- 新增 `parse_risk_history` 汇总并接入 Six Loop Dashboard 的解析质量闭环。
- 目录/图表目录/contents/sommaire 页归因为 `structural_navigation_noise`，不再误生成 provider/extraction/test gap 修复任务。

## 验证

```powershell
C:\Python314\python.exe -m py_compile src/enterprise_agent_kb/parse_risk_actions.py src/enterprise_agent_kb/cli.py src/enterprise_agent_kb/api_server.py
C:\Python314\python.exe -m pytest tests/test_parse_risk_actions.py tests/test_doc_diagnostics.py -q
C:\Python314\python.exe -m pytest tests/test_api_server.py::test_api_parse_risk_actions_is_dry_run_unless_persist_requested tests/test_parse_risk_actions.py -q
C:\Python314\python.exe -m pytest tests/test_parse_risk_actions.py tests/test_api_server.py::test_api_parse_risk_actions_is_dry_run_unless_persist_requested tests/test_api_server.py::test_api_parse_risk_repair_review_returns_status_suggestions -q
C:\Python314\python.exe -m pytest tests/test_parse_risk_history.py tests/test_doc_diagnostics.py tests/test_parse_risk_actions.py tests/test_api_server.py::test_api_parse_risk_actions_is_dry_run_unless_persist_requested tests/test_api_server.py::test_api_parse_risk_repair_review_returns_status_suggestions -q
C:\Python314\python.exe -m pytest tests/test_api_server.py::test_api_health_and_answer_query -q
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base parse-risk-actions --doc-id DOC-000015
C:\Python314\python.exe -m enterprise_agent_kb.cli --root knowledge_base parse-risk-repair-review --doc-id DOC-000015
```

结果：

- `tests/test_parse_risk_actions.py`: 3 passed
- `tests/test_parse_risk_actions.py tests/test_doc_diagnostics.py`: 7 passed
- `tests/test_parse_risk_actions.py tests/test_api_server.py::test_api_parse_risk_actions_is_dry_run_unless_persist_requested`: 4 passed
- `tests/test_parse_risk_actions.py tests/test_api_server.py::test_api_parse_risk_actions_is_dry_run_unless_persist_requested tests/test_api_server.py::test_api_parse_risk_repair_review_returns_status_suggestions`: 6 passed
- `tests/test_doc_diagnostics.py tests/test_parse_risk_actions.py`: 11 passed
- `tests/test_parse_risk_history.py tests/test_doc_diagnostics.py tests/test_parse_risk_actions.py tests/test_api_server.py::test_api_parse_risk_actions_is_dry_run_unless_persist_requested tests/test_api_server.py::test_api_parse_risk_repair_review_returns_status_suggestions`: 14 passed
- `tests/test_api_server.py::test_api_health_and_answer_query`: 1 passed
- `DOC-000015` 行动计划：provider 8、extraction chain 5、test coverage 1；只为 test coverage 页生成 1 个 golden candidate request。
- `DOC-000015` repair review：当前真实库未持久化 parse-risk tasks，因此 `review_count=0`，报告正常输出。
- 重新归因后 `DOC-000015` 行动计划：`structural_navigation_noise=14`，provider/extraction/test gap 均为 0；旧误归因 repair tasks 已按 review 建议标记为 `done`。
- parse-risk history 真实汇总：`doc_count=1`、`action_report_count=3`、`review_report_count=2`、最新归因 `structural_navigation_noise=14`、最新 review `done=3`。

备注：后续一次 `test_api_health_and_answer_query` 在 120 秒超时，没有断言失败。该测试覆盖完整 API smoke、构建、coverage、answer 和异步任务，已不适合作为 parse-risk API 小改动的唯一验证；本 feature 新增了专门的轻量 API 测试覆盖 `/parse-risk-actions` 的 dry-run/persist 契约，并将重 smoke 标记为 `integration`，由阶段性验收显式运行。
