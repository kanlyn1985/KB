# WP3 — Ontology Shadow Adapter 报告

> Sprint 2 WP3（Gate 2 第一半）。依据：`docs/dev/sprint2-ontology-and-bugfix/kb1_sprint2_development_guide.html` § WP3。

## 交付物

1. **`src/enterprise_agent_kb/ontology_adapter.py`**（新增，只读 adapter）
   - 模式：`off`（默认）/ `shadow` / `guard`，经 `KB1_ONTOLOGY_MODE` 环境变量切换。
   - `analyze(query, workspace_root, mode)` → `OntologySignal`：
     - `query_entities`：规则（无 LLM）子串匹配 ontology.db `entity`/`term` 表，longest-match 去重，canonical 0.95 / term 0.9 / alias 0.7。
     - `relation_checks`：只读查 `relation`/`relation_def`，仅在 ≥2 个不同 class 时统计已知 relation 实例数（consistent/unknown）。
     - `changed_retrieval` / `changed_answer` **恒为 False**（Sprint 2 不变约束）。
     - 容错：DB 缺失/读失败 → 记入 `errors`，返回空 signal，**永不抛异常、不阻断主链路**。
   - `post_check(query, answer, signal, workspace_root)` → `AnswerPostCheck[]`（WP4 guard 用，只产生 warning，不改答案）。
   - **不调 LLM**；**只 `SELECT`**；输出字段名只用 signal/constraint/check/validation，绝不叫 evidence/fact。

2. **`query_api.build_query_context`** 末尾挂 `ontology_signal`（只读字段，不改 hits/evidence/facts 排序与答案）。

3. **`tests/test_ontology_adapter.py`**（14 用例，全绿）：off/shadow/guard 三模式、mode 解析、DB 缺失容错、longest-match 去重、guard post-check 出/不出 warning 的两类合成夹具、`to_dict` 形状。

4. **设计文档**：`.codestable/features/2026-06-25-ontology-shadow-guard-adapter/ontology-shadow-guard-adapter-design.md`。

## 验证

| 检查 | 结果 |
|---|---|
| `off` 模式 context.ontology_signal | 存在、空、零开销 |
| `shadow` 模式 `ISO 14229-1` | entities=1（Standard, conf 0.95），`ISO 14229`/`ISO` 被去重 |
| `changed_retrieval`/`changed_answer` | 均为 False |
| 定义查询答案 | 仍含「控制导引电路」（WP2 修复未回归） |
| DB 缺失 | errors 记录，不抛异常 |
| check_health | 10/10 PASS |
| fast suite | 694 passed, 1 skipped, 0 failed（+14 新 adapter 测试） |

## 边界遵守（Sprint 2 硬约束）

- ✅ ontology 只作约束/校验/召回辅助层，不生成事实、不改写答案、不绕过 `evidence_judge`。
- ✅ 未调任何 LLM（`_llm_route` / decomposer 未接入）。
- ✅ 未引入 OWL/RDF 或重图数据库。
- ✅ 未把 ontology.db 当主事实库。
- ✅ `answer_changed_by_ontology` 全程 False。
- ✅ 主链路（query_api/answer_api）仅在 context 末尾挂只读字段，未改主路径逻辑。

## 范围外（留 WP4）

- guard 模式 post-check 接入 answer 流程 + answer_run 日志字段（`ontology_post_check_status`、`answer_changed_by_ontology`）—— WP3 已实现 `post_check` 函数与测试，但尚未在 answer_api 接线，留给 WP4。
- 影子模式检索排序介入 —— Sprint 2 全程不做。
