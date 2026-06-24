# Sprint 1 — Initial Snapshot (WP0)

> 只读快照，采集于 2026-06-24。**WP0 不修改任何代码。** 作为 Sprint 1 稳定化的基线参照。
> 执行依据：`docs/dev/sprint1-stabilization/kb1_next_development_guide.html`（Sprint 1 执行指导书）。

## 0. 环境与分支

| 项 | 值 |
|---|---|
| 工作目录 | `E:\AI_Project\opencode_workspace\KB1` |
| 当前分支 | `kb1-six-loop-rename` |
| HEAD | `df775a9 docs(eval): Phase 1 baseline v2 result (pass_rate 0.167)` |
| 远端跟踪 | **无 upstream / 不可达**（`git rev-list @{upstream}...HEAD` 报错） |
| 领先 origin/main | 52 commit（据历史盘点，全本地、未推送） |
| 已有 tag | **无**（→ WP1 需打 safety tag） |
| Python | `C:\Python314\python.exe`（3.14） |
| 知识库根 | `knowledge_base`（CLI 需 `--root knowledge_base`） |

**结论**：远端不可达 + 无任何 tag + 52 commit 全本地 = **最高风险**。WP1 优先打本地 safety tag 并分批 commit（本轮**不 push**，经用户确认）。

## 1. 工作区改动（已跟踪，tracked）

`git status`：25 个已跟踪文件修改、2 个删除。净 `+1922 / -8641`（删除主要来自旧的 `tools/sample_qa/*.json` 共 8202 行旧数据）。

核心改动（按影响面排序）：

| 文件 | 净变化 | 主题 |
|---|---|---|
| `src/enterprise_agent_kb/evaluation/evaluator.py` | +722 | **Eval 重设计 Phase 1**（WP1-eval） |
| `src/enterprise_agent_kb/pipeline.py` | +331 | **post_ingestion_gate**（WP1-pipeline / WP4） |
| `src/enterprise_agent_kb/retrieval.py` | +186 | retrieval 调整 |
| `src/enterprise_agent_kb/infrastructure/llm_client.py` | +98 | **LLM 路由 fallback**（WP1-llm / WP2） |
| `src/enterprise_agent_kb/api_server/_request_handlers.py` | +96 | API 处理 |
| `src/enterprise_agent_kb/evidence.py` | +88 | evidence 构建改动 |
| `src/enterprise_agent_kb/answer_constraint.py` | +76 | 约束答案 |
| `src/enterprise_agent_kb/query_semantic_parser.py` | +71 | **query repair / astron-minimax 路由**（WP2） |
| `src/enterprise_agent_kb/knowledge_units.py` | +58 | |
| `src/enterprise_agent_kb/query_api.py` | +59 | |
| `src/enterprise_agent_kb/schema.sql` | +29 | schema 新增（expected_points 等） |
| `examples/demo.html` | +158 | |
| `.github/workflows/tests.yml` | +50 | CI |
| `tests/test_workspace_doctor.py` `tests/test_retrieval_fts_guard.py` `tests/test_derived_state_rebuild.py` | 小改 | 测试更新 |
| `tools/build_expected_points.py` | +139 | expected_points 构建 |
| 删除 `tools/sample_qa/v1.json` `v1_golden.json` | -8202 | 旧 QA 数据下线 |

## 2. 未跟踪文件（untracked）分组

`git ls-files --others --exclude-standard` 共 **19,202** 个，但其中 **`.venv-paddle/`(1.6GB)是 venv，必须 gitignore，不属于工作成果**。剔除后真正需要处理的 untracked 工作文件如下：

| 分组 | 数量 | 说明 | → 归入 WP |
|---|---|---|---|
| `src/kb1_ontology/**` | 42 | 本体层包（class_registry / entity_manager / relation_registry / attribute_store + combined_query/legacy_bridge/router 等 + 自带 tests/） | WP1-ontology |
| `scripts/**` | 29 | 运维脚本（PDF/OCR/embedding/wiki/eval/regression 等）+ `scripts/ontology_demo/` + `scripts/check_health.py` | WP1-scripts |
| `docs/**` | 18 | `docs/ontology/`、`docs/operations/`、`docs/kb1_project_review_2026-06-24.html` | WP1-docs |
| `tests/**` | 2 | `tests/test_evaluator.py`、`tests/test_post_ingestion_gate.py` | WP1-eval/pipeline 测试 |
| `tools/**` | 1 | `tools/iso_14229_test_questions.json` | WP1-eval |
| `.venv-paddle/` | ~19110 | **venv，必须 gitignore，不提交** | WP5-hygiene |

**重目录体积**：`.venv-paddle` 1.6GB、`tmp` 514MB、`knowledge_base` 738MB（含 DB，按 .gitignore 已排除源 PDF）。

## 3. 健康检查（check_health.py）

```
[PASS] workspace_exists
[PASS] db_file_exists            knowledge.db
[PASS] db_connect
[PASS] active_documents          count=16
[PASS] facts_populated           count=7629
[PASS] evidence_populated        count=29988
[PASS] expected_points_populated distinct_docs=17
[PASS] fts_index_populated       facts_fts_rows=7629
[PASS] fact_type_diversity       types=15, zero_ratio=0.00%
[PASS] latest_eval_report_exists v9_golden_30_strong_match.json pass_rate=50.00%
Overall: PASS
```

**10/10 PASS**。系统可运行。注意：`latest_eval_report` 指向的是 `v9_golden_30_strong_match.json`（pass_rate 0.50），与 eval 历史中 v1-v11 多口径波动一致（见指导书第6节）。

## 4. 测试基线（pytest，默认 deselect integration+benchmark）

```
8 failed, 672 passed, 1 skipped, 1542 deselected in 373.54s
```

### 8 个失败项 + 现场根因（来自本次 traceback）

| # | 失败项 | 现场根因（已从 traceback 确认） | 类型 | → WP2 动作 |
|---|---|---|---|---|
| 1 | `test_cli_submodules::test_build_parser_registers_all_54_subcommands` | CLI 从 54 增至 55 个子命令，硬编码 54 失效 | 陈旧断言 | 改为相对当前注册数，不硬编码 |
| 2 | `test_evidence_auxiliary_blocks::test_build_evidence_skips_structure_markdown_blocks` | 结构 markdown block 过滤后 evidence_count=0（期望 1） | 行为/契约 | 确认产品语义后修测试或 evidence builder |
| 3 | `test_mcp_server::test_mcp_server_tools_call_answer_query` | MCP 响应契约变化，`result` 路径失效（KeyError/AssertionError） | 契约漂移 | 明确 MCP response schema |
| 4-6 | `test_post_ingestion_gate::{runs_on_existing_doc, result_to_dict, idempotent}` | **新 WIP**（pipeline.py +331 的 post_ingestion_gate），gate.passed=False、to_dict/schema/幂等未稳定 | 未完成功能 | WP4 稳定后修复 |
| 7-8 | `test_query_repair_regression::{uses_minimax_before_astron, falls_back_to_astron_after_minimax_failure}` | `_call_astron_text("ping")` **直接打 astron**，未先试 minimax；`calls==['astron...']` 而非 `['minimax...','astron...']` | 契约漂移 | 定 provider order policy（minimax-first），代码/测试/文档一致 |

### traceback 关键证据（query_repair，WP2 重点）

```
test_text_llm_uses_minimax_before_astron:
  assert str(calls[0]["api_base"]).startswith("https://minimax.example/anthropic")
  -> calls[0]["api_base"] 实际为 'https://astron.example/anthropic'

test_text_llm_falls_back_to_astron_after_minimax_failure:
  assert len(calls) == 2   -> 实际 len(['https://astron.example/anthropic']) == 1
```
即 `_call_astron_text` 当前实现**只打 astron、不经过 minimax-first**，与测试期望的「minimax 主、astron 兜底」契约不符。

## 5. WP0 结论与进入 WP1 的前置判断

1. **可运行**：check_health 10/10，系统在线。
2. **核心风险**：52 commit 全本地 + 无 tag + 远端不可达 → **必须先打 safety tag + 分批本地 commit**（本轮不 push）。
3. **WIP 分组清晰**：可按 eval / pipeline-gate / llm-routing / ontology / scripts / docs / cleanup 七组提交。
4. **测试红灯**：8 个失败全部已定位根因，3 类（陈旧断言 / 契约漂移 / 未完成 WIP），非生产性批量崩溃。
5. **必须 gitignore**：`.venv-paddle/`、`tmp/`、`test_runtime_*/`（见 WP5）。

→ **WP0 完成，进入 WP1（safety tag + 分批提交，本地不 push）**。提交计划见 WP1 报告。
