# Sprint 2 验收报告

> Sprint 2：稳定化与恢复绿灯后的「定义查询修复 + Ontology 最小接入 + Eval 诚实基线」。
> 执行依据：`docs/dev/sprint2-ontology-and-bugfix/kb1_sprint2_development_guide.html`
> 验收日期：2026-06-25

## 0. 概述

Sprint 2 在 Sprint 1 稳定化基础上，完成 4 个 Exit Gate：成果保护、xfail 解除、Ontology 最小接入、Eval 诚实基线。全程遵守硬约束（ontology 不生成事实、不绕过 evidence_judge、`answer_changed_by_ontology=False`、不改 query_api/answer_api 主路径逻辑、不改评测指标）。

## 1. Exit Gate 达成情况

| Gate | 要求 | 结果 |
|---|---|---|
| **Gate 0 成果保护** | 67+ commit push 到远端 或 git bundle | ✅ push 成功（origin/kb1-six-loop-rename），另存 git bundle 双保险 |
| **Gate 1 xfail 解除** | 修复 definition-query 主路径 bug，MCP xfail 转 pass | ✅ Fix A（CJK term_definition 召回），xfail 移除并通过；696 passed/0 failed/0 xfail |
| **Gate 2 Ontology 最小接入** | entity constraint + relation domain/range + answer post-check（off/shadow/guard，默认保留旧行为） | ✅ 三模式 adapter + answer envelope 字段，默认 off 零开销，`answer_changed_by_ontology=False` 全程 |
| **Gate 3 Eval 提分** | token_overlap 0.60 → 0.65-0.85 不改指标 | ⚠️ 部分达成：发现 0.60 是单文档偶然值，真实跨文档基线 0.30；采样+提质修复后诚实锁定 0.30；0.65-0.85 需答案质量提升，移至 Sprint 3 |

## 2. 工作包交付

| WP | 交付物 | 状态 |
|---|---|---|
| WP0 | git bundle 备份 + push 到 origin + prework 报告 | ✅ commit f6b8c70/2c1b939 |
| WP1 | Sprint 2 baseline 确认（679 passed, health 10/10, eval 0.60） | ✅ commit b076bb1 |
| WP2 | definition-query 修复（Fix A: `_inject_direct_term_definition_hits` + `_definition_term_candidates`）+ analysis + xfail 解除 | ✅ commit 待查 |
| WP3 | `ontology_adapter.py`（off/shadow/guard 只读 adapter）+ query_api 挂 signal + 14 测试 + 设计文档 | ✅ commit eea0572 |
| WP4 | answer_api guard post-check 接线 + envelope 字段 + 2 测试 | ✅ commit f889241 |
| WP5 | `_round_robin_sample` 跨文档采样 + 问题提质过滤 + 诚实锁定 0.30 + 策略文档 | ✅ commit 16142de |
| WP6 | ADR 0003 + decision + 本验收报告 + 评审 HTML 更新 | ✅ 本提交 |

## 3. 硬约束遵守（全程零违反）

- ✅ `evidence_judge` 仍是唯一答案事实裁决边界。
- ✅ Ontology 输出只叫 signal/constraint/check/validation，绝不叫 evidence/fact/source truth。
- ✅ 未改写 query_api/answer_api 主路径逻辑（仅 context 末尾挂只读字段 + envelope 末尾加只读字段）。
- ✅ 未引入新向量 DB / 分布式服务 / OWL/RDF。
- ✅ 未改评测指标（token_overlap / COVERAGE_THRESHOLD=0.30 不变）。
- ✅ 未删测试换绿灯。
- ✅ `answer_changed_by_ontology` 全程 False（off/shadow/guard 三模式均验证）。

## 4. 测试与健康

- **fast suite**：696 passed, 1 skipped, 0 failed, 0 xfailed（Sprint 1 末 679+1xfail → +17 新测试，xfail 解除）。
- **check_health**：10/10 PASS（16 docs, 7636 facts, 29988 evidence, 17 expected_points docs, 15 fact types）。
- **eval**：token_overlap 跨文档 10 题 pass_rate=0.30（deterministic），CI smoke floor 0.20 通过。

## 5. 版本控制

- 分支 `kb1-six-loop-rename` 已 push 到 origin（upstream tracking 已配置）。
- Safety tag `safety/pre-sprint1-stabilization-20260624` 仍在（Sprint 1 前基线）。
- Sprint 2 commit 链：f6b8c70 (prework) → b076bb1 (baseline) → [WP2 fix] → eea0572 (WP3) → f889241 (WP4) → 16142de (WP5) → 本提交 (WP6)。

## 6. 未达成与后续（Sprint 3 候选）

1. **Eval 0.65-0.85 promotion gate**：需答案质量提升（召回措辞与 expected_points token 对齐、答案组装优化），Sprint 2 受「不改答案主路径」约束未做，移至 Sprint 3。
2. **Ontology 主动召回过滤**（entity-type 约束反向过滤候选）：需独立 ADR + 不回归基线证据，Sprint 3 评估。
3. **guard post_check warning 并入 answer `warnings` 列表**：当前独立字段 `ontology_post_checks`，未并入 `warnings`（避免影响 confidence 评分），Sprint 3 视情况合并。
4. **完整 104 题 golden 基线**：540s 超时，需分批或答案流水线提速后跑全。
5. **orphan facts 治理**（DOC-000001/DOC-000008 孤儿 facts）：Sprint 1 遗留，Sprint 3 处理。

## 7. 结论

Sprint 2 **4 个 Gate 中 3 个完全达成（Gate 0/1/2），1 个部分达成并诚实记录（Gate 3）**。核心成果：定义查询主路径 bug 修复（用户可见质量提升）、Ontology 安全最小接入（约束层 only，零答案风险）、Eval 基线从虚高 0.60 修正为真实 0.30（诚实可复现）。全程零硬约束违反。可进入 Sprint 3（答案质量提升 + eval 提分）。
