# WP4 — Ontology Guard 后置检查接入 报告

> Sprint 2 WP4（Gate 2 第二半）。依据：`docs/dev/sprint2-ontology-and-bugfix/kb1_sprint2_development_guide.html` § WP4 / § 05。

## 交付物

在 `answer_api._compose_final_answer` 末尾接入 guard 后置检查（只读、不改答案）：

- 新增 answer envelope 字段（**全部只读、不改 `direct_answer`**）：
  - `ontology_post_check_status`：`"skipped"`（off/shadow）/ `"completed"`（guard）/ `"error: ..."`（容错）
  - `ontology_post_checks`：guard 模式产生的 warning 列表（`[{type, severity, message}]`）
  - `answer_changed_by_ontology`：**Sprint 2 全程 `False`**

- 逻辑：仅 `guard` 模式调 `ontology_adapter.post_check(query, direct_answer, signal, workspace_root)`；shadow/off 不跑（`skipped`）。
- 容错：post_check 异常被捕获写入 `ontology_post_check_status`，**永不阻断 answer 输出**。

## 验证

| 检查 | 结果 |
|---|---|
| off 模式 `answer_query('什么是控制导引电路？')` | status=skipped，`answer_changed_by_ontology=False`，答案含「控制导引电路」 |
| guard 模式同查询 | status=completed，post_checks=[]，`answer_changed_by_ontology=False`，**答案未变** |
| `tests/test_ontology_adapter.py` | 16 passed（含 2 个 answer_query guard 接线测试：off skipped / guard completed 不改答案） |
| fast suite | 696 passed, 1 skipped, 0 failed（+2） |

## 硬约束遵守（Sprint 2）

- ✅ `answer_changed_by_ontology` 全程 False（off/shadow/guard 三模式均验证）。
- ✅ guard 只产出 warning，不生成事实、不改写答案正文、不绕过 `evidence_judge`。
- ✅ 未调 LLM；未引入 OWL/RDF / 重图数据库；ontology.db 非主事实库。
- ✅ 主链路（query_api/answer_api）未改主路径逻辑，仅在 envelope 末尾加只读字段。

## Sprint 2 Gate 2（Ontology 最小接入）达成

| Gate 2 条件 | 状态 |
|---|---|
| entity type constraint（shadow 读取） | ✅ `analyze()` 输出 `query_entities`（class_id/name） |
| relation domain/range 校验（shadow 读取） | ✅ `relation_checks`（consistent/unknown） |
| answer post-check（guard 模式） | ✅ `post_check()` + answer envelope 字段 |
| 默认保留旧行为 | ✅ 默认 `off`，零 signal 零开销 |
| off/shadow/guard 三模式 | ✅ 三模式均有测试 |
| answer_changed_by_ontology=False | ✅ 全程 False |

## 范围外（留后续 Sprint）

- guard 模式 post_check 产出的 warning 接入 answer envelope 的 `warnings` 列表（当前独立字段 `ontology_post_checks`，未并入 `warnings`，避免影响既有 confidence 评分）。
- shadow 模式检索排序介入 —— Sprint 2 不做。
- ontology entity constraint 反向过滤召回候选 —— Sprint 2 不做。
