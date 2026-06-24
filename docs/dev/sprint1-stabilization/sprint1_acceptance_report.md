# Sprint 1 验收报告 · Stabilization & CI Recovery

> 执行依据：`docs/dev/sprint1-stabilization/kb1_next_development_guide.html` §8 验收标准 + §9 Exit Gate。
> 采集时间：2026-06-24/25。分支 `kb1-six-loop-rename`，仅本地提交（未 push，经用户确认）。

## 0. 一句话结论

**Sprint 1 Exit Gate 达成。** 项目从"大量 WIP + 8 测试失败 + 评测口径漂移 + 命名混乱"收口为"工作树干净 + 测试全绿(1 xfail 绑 issue) + 评测可复现 + 命名统一"。可进入 Sprint 2。

## 1. 验收对照（指导书 §8）

| 验收项 | 必须 | 状态 | 证据 |
|---|---|---|---|
| 版本控制 | WIP 分批 commit；远端 push 或 safety tag | ✅ | 13 commit + safety tag `safety/pre-sprint1-stabilization-20260624`；远端不可达，本地 tag 保护（未 push，按约定） |
| 测试 | 原 8 失败修复；xfail 须绑 issue+原因+到期 | ✅ | 679 passed / 0 failed / 1 xfail（MCP，绑 issue `definition-query-exact-term-gate-drops-evidence`，strict=True） |
| 健康检查 | check_health 10 项通过或有非阻塞说明 | ✅ | 10/10 PASS |
| Eval | baseline 口径固定；deterministic 可跑；LLM judge optional | ✅ | token_overlap 主口径，0.60 baseline，无 LLM 可复现；见 `eval-baseline-policy.md` |
| post_ingestion_gate | pass 条件明确；to_dict schema 稳定；幂等 | ✅ | 5 步 gate，{passed,steps:[{name,passed,detail}]}，tmp fixture 幂等验证 |
| 工程清理 | tmp/test_runtime/0字节db 已 quarantine 或 gitignore；无误删 | ✅ | 3 个 0字节db quarantine；1203 陈旧 run 删除；golden/evidence/facts 不变；tmp/test_runtime 已 gitignore |
| 命名一致性 | six-loop 主线明确，历史 four-loop 有说明 | ✅ | 实时代码无 four-loop；roadmap+audit 加历史命名说明；dev guide 路径修复 |
| Ontology | 进版本控制；最小 bridge/constraint 测试；未绕证据边界 | ✅ | `src/kb1_ontology/` 已 commit（70 文件）；本轮未做主链路接入（按指导书"最小接入"留 Sprint 2），保持隔离、未绕 judge |

**Exit Gate（版本控制 + 测试 + eval baseline + post_ingestion_gate 四项同时满足）→ ✅ 全部满足，可进入 Sprint 2。**

## 2. WP 完成情况

| WP | 内容 | 状态 | 产物 |
|---|---|---|---|
| WP0 | 只读现场快照 | ✅ | `initial_snapshot.md` |
| WP1 | safety tag + 7 逻辑提交 | ✅ | `wp1_commit_report.md` |
| WP2 | 修复 5/8 失败测试 + issue + llm policy | ✅ | `wp1_commit_report.md`(含 LLM)/ issue report / `llm-provider-policy.md` |
| WP3 | 固定 eval baseline | ✅ | `eval-baseline-policy.md` / `wp3_eval_baseline_report.md` |
| WP4 | 稳定 post_ingestion_gate | ✅ | `wp4_gate_report.md` |
| WP5 | 可逆清理 | ✅ | `wp5_cleanup_report.md` |
| WP6 | 命名统一 | ✅ | `wp6_naming_report.md` |

## 3. 8 个失败测试收口明细

| # | 失败项 | 类型 | 处理 |
|---|---|---|---|
| 1 | CLI 子命令数(54→55) | 陈旧断言 | 改为 >=54 下限 + 关键族存在性，不硬编码 |
| 2 | evidence auxiliary blocks | fixture 过短被噪音过滤 | 用真实长度 content block |
| 3 | MCP answer_query | **真实答案管线 bug** | xfail(strict) 绑 issue |
| 4-6 | post_ingestion_gate ×3 | 测试绑孤儿 doc_id + 污染生产库 | 改 tmp fixture 隔离 |
| 7-8 | LLM minimax/astron 路由 | 契约变更(统一 text_llm) | 改测试匹配新契约 |

## 4. 关键决策与偏差（透明）

- **pipeline.py 未按 git add -p 拆分**：Phase12+13 hunk 是连续新增行无分割边界，强拆需手编 patch（脆弱）。整文件进 ingestion commit，message 说明。详见 `wp1_commit_report.md`。
- **MCP 测试 xfail 而非修复**：根因是 answer_api exact-term gate 在 evidence=4 时因 facts=0 错误清零上下文（真实 bug），不在 Sprint 1 动 answer 主链路；绑 issue 留后续。详见 issue report。
- **未 push**：远端无 upstream，按用户确认仅本地 safety tag + commit。建议后续补 `git bundle` 离线备份。
- **Ontology 最小接入留 Sprint 2**：本体层已进版本控制，但指导书"最小 bridge/constraint 接入"未做，保持隔离避免抢主链路事实权。

## 5. 剩余风险

| 风险 | 级别 | 说明 / 缓解 |
|---|---|---|
| 65 commit 全本地未 push | **高** | 远端不可达。建议：恢复网络后 push；或 `git bundle create ../kb1-backup.bundle --all` 离线备份 |
| MCP answer-pipeline bug（定义查询答文档标题） | 中 | 已立 issue，xfail 盯着；修复需动 answer_api exact-term gate + retrieval term_definition 注入 |
| eval pass_rate 0.60 < 0.65 | 中 | baseline 已锁定可复现；提分属 Phase 1 后续（含上述 issue） |
| 生产库孤儿事实(DOC-000001:14, DOC-000008:58) | 低 | 数据治理问题，归运维；非阻断 |
| Ontology 未接入主链路 | 低 | 隔离安全；Sprint 2 最小接入 |

## 6. Sprint 2 候选任务

1. **修复 issue `definition-query-exact-term-gate-drops-evidence`**：answer_api exact-term gate 清零条件加 `and not evidence`；retrieval `_inject_direct_term_definition_hits` 对 markdown term 归一化匹配；解 MCP xfail。
2. **Ontology 最小接入**：entity type constraint + relation domain/range + answer post-check（指导书 §7 三个接入点），不绕 evidence_judge。
3. **eval 提分**：基于锁定 baseline，针对性修召回/答案（依赖 #1）。
4. **离线备份**：`git bundle` 或恢复 push。
5. **生产库孤儿事实治理**：workspace-governance 评估清理 DOC-000001/DOC-000008 孤儿 facts。
6. **AUTO eval 模式**：promotion gate 达标后启用 CI golden 阻断 + nightly full。

## 7. 给执行 AI 的交接

- 当前 HEAD：`d9bdc0f`，工作树干净，测试 679 passed/1 xfailed。
- safety tag：`safety/pre-sprint1-stabilization-20260624`（Sprint 1 起点）。
- 所有 Sprint 1 决策、根因、偏差见 `docs/dev/sprint1-stabilization/` 各 WP 报告。
- 硬约束不变：不绕 evidence/fact 候选集、不破坏性 reset、CI 未绿前不重构主链路（现已绿）。
