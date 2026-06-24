# Sprint 1 — WP1 报告：WIP 分批本地提交

> 执行依据：`kb1_next_development_guide.html` § WP1。**仅本地 commit + safety tag，不 push**（远端无 upstream / 不可达，经用户确认）。
> 采集时间：2026-06-24。

## 0. 保护动作

| 动作 | 结果 |
|---|---|
| safety tag | `safety/pre-sprint1-stabilization-20260624` → `df775a9`（Sprint 1 开始前的 HEAD） |
| 远端 push | **未执行**（无 upstream、用户确认仅本地） |
| 工作树最终状态 | **干净**（`git status --short` 为空，0 个未跟踪工作文件） |

## 1. 提交链（7 个逻辑提交，按依赖顺序）

| # | commit | 主题 | 文件 / 行 |
|---|---|---|---|
| 1 | `57c4f07` | chore(hygiene): ignore `.venv-paddle` virtualenv | 1 文件（.gitignore） |
| 2 | `29e5cfd` | feat(ontology): 隔离的本体知识层 | 70 文件 / +14215 |
| 3 | `f889ed9` | feat(wiki): wiki_chunks 表 + 向量召回 | 10 文件 / +1549 |
| 4 | `ecc6794` | feat(ingestion): post-ingestion 质量门禁 + 本体抽取钩子 | 3 文件 / +590 |
| 5 | `cdf51d9` | refactor(llm): 统一 text_llm provider 路由 | 2 文件 / +100 -69 |
| 6 | `82e1c70` | feat(eval): Phase1 evaluator + expected_points + CI 门禁 | 8 文件 / +1605 -271 |
| 7 | `48bc744` | chore: 解析/证据质量过滤 + wiki_chunks 测试契约 + ops 脚本 + sprint1 文档 | 26 文件 / +5140 -8218 |

提交顺序遵循依赖：ontology(2) → wiki(3) → ingestion(4，依赖 retrieval._refresh_fts_index 与 scripts.ontology_demo) → llm(5) → eval(6) → misc(7)。

## 2. 偏差说明：pipeline.py 未按原计划 git add -p 拆分

指导书建议把 `pipeline.py` 的 ontology 抽取段与 post_ingestion_gate 段拆成两个 commit。**实际未拆**，原因：

- `pipeline.py` 的 hunk `@@ -243,6 +266,35`（Phase 12 gate 调用 + Phase 13 ontology 抽取调用）是**连续的纯新增行**，中间无未改动行作为分割边界。
- `git add -p` 的 `s`(split) 只能在未改动行处分割，**无法分割该 hunk**；强拆需手工编辑 unified-diff 片段（脆弱、有破坏 index 的风险）。
- 两段都是 `_run_document_pipeline_unprotected` 里的**后入库管道增强**，概念同源。

**决策**：`pipeline.py` 整文件进 commit 4（ingestion），message 明确说明两段同船及原因。独立的 `src/kb1_ontology/` 包仍单独成 commit 2。符合指导书"先 commit 再优化 / 保护成果优先"。

## 3. 关键契约漂移（已记入 commit message，留给 WP2 收口）

- **LLM 路由**（commit 5）：`query_semantic_parser._call_astron_text` 现在直接委托给 `_call_minimax_text`（单一 text_llm provider），但 `tests/test_query_repair_regression.py` 仍断言旧的"minimax 主、astron 兜底"两段式契约 → 2 个测试失败。WP2 需把代码/测试/文档统一到**一个显式 provider-order 策略**。
- **post_ingestion_gate**（commit 4）：gate 的 `passed`/`to_dict`/幂等尚未稳定 → 3 个测试失败。WP4 收口。
- **CLI 子命令数**（commit 6 带入）：54→55，硬编码断言失效。WP2。
- **MCP result schema** / **evidence auxiliary blocks**：契约/行为变化。WP2。

## 4. 验收（对照指导书 §8 验收项之"版本控制"）

| 验收项 | 状态 | 证据 |
|---|---|---|
| WIP 已分批 commit | ✅ | 7 个逻辑提交，工作树干净 |
| 远端已 push **或** 离线有 safety tag + bundle | ⚠️ 部分 | 有 safety tag；**未做 bundle**（远端无 upstream，本轮不 push）。建议后续补 `git bundle` 离线备份 |
| 提交不混主题 | ✅（一处说明） | 见 §2 pipeline.py 偏差说明 |

**遗留建议**：执行 `git bundle create ../kb1-sprint1-backup.bundle --all` 做一份离线全量备份（本轮未做，因用户仅要求本地提交；WP5 或后续可补）。

→ **WP1 完成，进入 WP2（修复 8 个失败测试）**。
