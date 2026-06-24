# Sprint 1 — WP5 报告：工程债务清理（可逆）

> 执行依据：`kb1_next_development_guide.html` § WP5。**只做可逆清理**：quarantine（移动）+ prune-stale-runs（删陈旧 run）。tmp/test_runtime 仅记建议不删。经用户确认后执行。

## 1. 执行的清理（已 --execute）

### 1.1 quarantine-suspicious-db-files

`knowledge_base/` 根目录 3 个 **0 字节 db**（历史误产物）移入 `knowledge_base/quarantine/db/`（可逆，移动非删除）：

| 原路径 | → quarantine 路径 |
|---|---|
| `knowledge_base/facts.db` (0B) | `quarantine/db/facts.db` |
| `knowledge_base/kb.db` (0B) | `quarantine/db/kb.db` |
| `knowledge_base/knowledge.db` (0B, 根目录) | `quarantine/db/knowledge-1.db` |

真实库未受影响：`knowledge_base/db/knowledge.db`(272MB) 与 `knowledge_base/ontology/ontology.db` 完好。

### 1.2 prune-stale-runs（--keep-current-code-version --keep-latest-code-versions 3）

| 表 | 候选 | 删除 | 保留 |
|---|---|---|---|
| retrieval_runs | 1203 | 1203 | 11004（当前 + 最近3版本） |
| eval_results | 0 | 0 | — |
| eval_runs | 0 | 0 | 2（当前/受保护） |

**未触碰（架构边界）**：golden_cases=1466、evidence=29988、facts=7636、source_units=4266、expected_points=17 —— 全部不变。
> 注：facts 由 7629→7636（+7）是 WP4 调查时 gate 在 DOC-000006 上跑出的 term_definition 副作用，幂等，非本次清理造成。

## 2. 未执行（仅记建议，gitignored 临时划伤）

| 项 | 体积 | 性质 | 处理建议 |
|---|---|---|---|
| `tmp/` | 514MB | gitignored（`.gitignore` + `norecursedirs`），会话临时产物 | 可手动 `rm -rf tmp/*`，不影响版本控制/测试；本轮按用户要求不删 |
| `test_runtime_*/` (68 个) | ~35MB | gitignored，`test_pipeline_smoke.py` 等运行时创建 | 同上，可周期性清理；不删不影响功能 |

这些已被 git 忽略，**不属于版本控制债务**，仅占磁盘。留作运维侧周期清理。

## 3. .gitignore（WP1 已先行处理）

- WP1 commit `57c4f07` 已把 `.venv-paddle/`（1.6GB venv）加入 `.gitignore`，消除 19k 误报 untracked。
- `tmp/`、`test_runtime_*/`、`eakb_test_*/`、`*.db`、`knowledge_base/` 均已在 `.gitignore`。

## 4. 验证

- `scripts/check_health.py`：**10/10 PASS**（清理前后）。
- 回归测试（gate + cli + evidence + workspace_doctor + fts_guard + derived_state）：**53 passed**。
- 工作树仍干净（清理对象都在 gitignored 区或 DB 内，不产生 git 改动）。

## 5. 验收（对照指导书 §8 "工程清理" 项）

| 验收项 | 状态 |
|---|---|
| tmp/test_runtime/0字节db 已 quarantine 或 gitignore | ✅ 0字节db 已 quarantine；tmp/test_runtime 已 gitignore（未删，按用户要求） |
| 无误删主资产 | ✅ golden/evidence/facts/source_units/expected_points 全部不变 |

→ **WP5 完成。**
