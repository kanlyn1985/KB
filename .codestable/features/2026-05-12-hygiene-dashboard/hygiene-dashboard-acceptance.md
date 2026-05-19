---
doc_type: feature-acceptance
feature: 2026-05-12-hygiene-dashboard
status: completed
summary: Fifth loop hygiene status is visible in dashboard API and Workbench
tags:
  - derived-state
  - dashboard
  - data-hygiene
---

# Hygiene Dashboard 验收报告

> 阶段：阶段 3（验收闭环）
> 验收日期：2026-05-12
> 关联方案 doc：`.codestable/features/2026-05-12-hygiene-dashboard/hygiene-dashboard-design.md`

## 1. 接口契约核对

- [x] `/closed-loop-dashboard` 返回 `hygiene_loop`，与四个既有闭环同级。
- [x] `hygiene_loop` 复用 `run_workspace_doctor(scope="all")` 和 `prune_stale_runs(dry_run=True)`。
- [x] `prune_plan` 进入 dashboard 前压缩候选 ID，每类最多展示 10 个样例。
- [x] API 异常时返回 fail 风险，不影响其他 loop 字段结构。

## 2. 行为与决策核对

- [x] dashboard 只读：测试验证 `hygiene_loop` 生成后 `retrieval_runs`、`eval_runs`、`eval_results` 数量不变。
- [x] stale/unknown runs 可见：真实库 `hygiene_loop.status=warn`，stale summary 返回 retrieval/eval/eval_results 候选数量，删除计数均为 0。
- [x] recommended action 可见：`next_actions` 包含 `prune-stale-runs --keep-current-code-version --dry-run`。
- [x] Workbench Overview 显示 `Five Loop Dashboard` 和 `派生状态闭环`。
- [x] Workbench Hygiene tab 显示 Workspace Doctor Issues、Derived State Checks、Stale Run Prune Plan 和维护命令。

挂载点反向核查：本 feature 引用落在 `api_server.py`、`examples/demo.html`、`tests/test_api_server.py`、`tests/test_delivery_assets.py` 和 CodeStable 文档内，符合 design 第 2.3 节。

## 3. 验收场景核对

- [x] API 返回 `hygiene_loop`：`tests/test_api_server.py` 覆盖。
- [x] 复用 doctor 和 dry-run prune：`test_hygiene_loop_snapshot_reuses_doctor_and_dry_run_prune` 覆盖。
- [x] dashboard 不执行删除：同一测试检查 runs 和 eval_results 数量不变。
- [x] UI 暴露派生状态治理闭环：`tests/test_delivery_assets.py::test_demo_page_exists` 覆盖静态资产。
- [x] 浏览器真实渲染：Chrome headless 打开 `http://127.0.0.1:8000/demo`，切换 Hygiene tab，确认关键文本可见，截图保存到 `tmp/hygiene-dashboard.png`。

反向核对：

- [x] 未执行 `--execute`。
- [x] 未新增 schema。
- [x] 未修改查询、答案或评测策略。
- [x] 前端没有复制 freshness/orphan/stale run 判定规则，只渲染 API 返回。

## 4. 术语一致性

- `hygiene_loop`、`workspace doctor snapshot`、`prune plan snapshot`、`recommended action` 在 design、代码、测试和 architecture 中语义一致。
- `Five Loop Dashboard` 表示入库、召回、答案、回归、派生状态治理五个闭环，不替代任何单个闭环指标。

## 5. 架构归并

- [x] `.codestable/architecture/ARCHITECTURE.md` 已记录 `/closed-loop-dashboard` 与 Workbench 展示 `hygiene_loop`。
- [x] `.codestable/architecture/closed-loop-architecture.md` 已记录派生状态治理闭环 dashboard 数据流、只读边界和 Workbench Hygiene tab。
- [x] `docs/user/kb1-workbench-user-guide.md` 已更新五闭环和 Hygiene tab 使用说明。

## 6. requirement 回写

- [x] `.codestable/requirements/derived-state-governance-loop.md` 已补充 Workbench hygiene dashboard 已落地范围。
- [x] requirement 仍保持 `draft`，原因是 `residual-state-regression-suite` 尚未完成。

## 7. roadmap 回写

- [x] `.codestable/roadmap/kb1-derived-state-governance/kb1-derived-state-governance-items.yaml` 中 `hygiene-dashboard` 已改为 `done`。
- [x] roadmap 主文档子 feature 清单和变更日志已同步。

## 8. attention.md 候选盘点

无新增候选。本次使用的维护命令已在 dashboard 和 roadmap 记录；是否把 `workspace-doctor --scope all --json` 作为日常检查命令加入 attention.md，可在后续派生状态治理闭环收尾时统一决定。

## 9. 遗留

- `residual-state-regression-suite` 未做：残留态还未形成完整回归套件。
- graph/wiki/coverage rebuild scope 仍为 unsupported，等待各自 source/artifact/rebuild contract 落地。
- `api_server.py` 和 `examples/demo.html` 已偏大，后续继续扩展 Workbench 时建议另走 refactor 拆分 dashboard snapshot / render helpers。

## 验证

- `C:\Python314\python.exe -m pytest tests/test_api_server.py::test_hygiene_loop_snapshot_reuses_doctor_and_dry_run_prune tests/test_api_server.py::test_hygiene_health_flags_doctor_issue_actions tests/test_delivery_assets.py::test_demo_page_exists -q`：3 passed。
- `C:\Python314\python.exe -m pytest tests/test_api_server.py tests/test_delivery_assets.py tests/test_workspace_doctor.py tests/test_run_governance.py -q`：35 passed。
- `C:\Python314\python.exe -m pytest tests/test_query_repair_regression.py -q`：30 passed, 27 deselected。
- `C:\Python314\python.exe -m compileall -q src\enterprise_agent_kb tests\test_api_server.py tests\test_delivery_assets.py`：通过。
- 真实 API `/closed-loop-dashboard`：返回 `hygiene_loop`，真实库状态 `warn`，删除计数均为 0。
- 浏览器渲染检查：通过，截图 `tmp/hygiene-dashboard.png`。

说明：一次并行测试中 `test_api_health_and_answer_query` 的 `build-document` 临时返回 500；单独复现通过，顺序组合测试通过。判断为并行测试同时访问真实 `knowledge_base` 的临时冲突，不是本 feature 的行为失败。
