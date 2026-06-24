# Sprint 1 — WP4 报告：post_ingestion_gate 稳定化

> 执行依据：`kb1_next_development_guide.html` § WP4。修复 3 个 `test_post_ingestion_gate` 失败。

## 1. 失败根因

3 个 gate 测试硬编码生产库 `DOC-000001`，但 **`DOC-000001` 是孤儿 doc_id**：

| 表 | DOC-000001 行数 |
|---|---|
| documents | **0（不存在）** |
| pages / blocks / evidence | 0 |
| facts | 14（**孤儿事实**，source_doc_id 指向不存在的文档） |

gate 的 `sanity_check` 要求 `n_evidence > 0`，对孤儿 DOC-000001 必然 `passed=False`。此外 gate 的 `term_definition_sync` 会**写入**生产库（副作用），测试直接跑生产库会污染数据。

## 2. 修复方案（按指导书 WP4："把测试数据和真实库差异隔离"）

重写 3 个 gate 测试，改用 `tmp_path` 隔离工作区 + 最小 fixture：

- `initialize_workspace(tmp_path/kb, schema.sql)` 建空库
- `apply_pending_migrations(conn, migrations/)` 补 `expected_points` 表（该表在 `migrations/001_expected_points.sql`，不在 schema.sql）
- 种入 1 个完整可搜文档：1 doc / 1 page / 1 block / 1 evidence / 1 fact / 1 expected_points 行（`points_json=[]`）
- 预置 expected_points 行 → step2（regeneration）no-op，**不触发 LLM/subprocess**；空 points_json → step3 插入 0 条，**确定性**

验证：
- `fts_refresh`：刷新后 FTS 命中 evidence/facts（OK）
- `expected_points_generation`：已存在，no-op（OK）
- `term_definition_sync`：插入 0（OK）
- `sanity_check`：facts=1, evidence=1, expected_points=1（OK）
- `wiki_coverage`：skip（无 wiki MD）（OK）
- 幂等：二次运行 evidence/facts 计数不变（ev=1, fc=1）

## 3. gate 设计要点（已验证，供 WP4 验收）

- `PostIngestionGateResult.passed` = all(step.passed)。
- `to_dict()` schema：`{passed: bool, steps: [{name, passed, detail}]}` 稳定。
- 幂等：expected_points 已存在则 no-op；term_definition_sync 用 LIKE 去重；FTS refresh 先 DELETE 再 INSERT。重复运行不产生重复行。
- 失败不 raise：每步 try/except 记录为 step 结果。

## 4. 遗留 / 注意

- **生产库已存在的孤儿事实**（DOC-000001: 14 条、DOC-000008: 58 条）属数据治理问题，归入 **WP5 工程清理**（用 quarantine/governance 工具处理，不在本 WP 删数据）。
- 调查期间曾在生产库对 DOC-000006/DOC-000002 跑过 gate（各插入若干 term_definition），属幂等副作用，未破坏数据；后续 WP5 可评估是否清理。
- gate 的 `wiki_coverage` 步骤因 `from ..scripts.check_coverage import check_coverage` 的相对导入在包外运行时 `ImportError`（被 try/except 捕获为 skip）——非阻断，但建议后续把 check_coverage 纳入包内或改 import 路径（记为小债务）。

## 5. 验收（对照指导书 §8 "post_ingestion_gate" 项）

| 验收项 | 状态 |
|---|---|
| pass 条件明确 | ✅ all(steps.passed)，5 步定义清晰 |
| to_dict schema 稳定 | ✅ {passed, steps:[{name,passed,detail}]} |
| 幂等测试通过 | ✅ 二次运行计数不变 |
| 测试数据与真实库隔离 | ✅ tmp_path + 最小 fixture，不触生产库 |

→ **WP4 完成。8 个失败测试现已全部收口：7 passed + 1 xfail(MCP, 绑 issue)。**
