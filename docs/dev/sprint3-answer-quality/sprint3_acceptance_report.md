# Sprint 3 验收报告

> Sprint 3: 答案质量驱动的 Eval 提分 (0.30 -> 0.65-0.85).
> Date 2026-06-30. Branch kb1-six-loop-rename, HEAD fa5667e.

## 1. Sprint 3 目标

把真实跨文档确定性 token_overlap baseline 从 Sprint 2 锁定的 0.30 提升到
0.65-0.85，不破坏证据约束边界。核心指令："你不是来重写 KB1 的。你是来把真实
答案质量提上去的。"

## 2. Exit Gates

| Gate | 要求 | 状态 | 证据 |
|---|---|---|---|
| Gate 0 | Baseline 可复现 (0.30 + 失败清单) | **达成** | WP0 报告 (d1ed846), WP1 taxonomy (9ae1abc) - 20-case 失败分桶, 13 失败 100% 分类 |
| Gate 1 | pass_rate 0.65-0.85 (不改 metric 不删样本) | **部分达成** | 0.30 -> 0.40 (诚实, 0 artifact). 距 0.65 仍差 0.25, 主因 P1 channel-weighting 需 full-payload anchor (deferred Sprint 4) |
| Gate 2 | Ontology A/B 安全 (shadow only, 无 evidence 回归) | **达成** | WP5 报告 (b59697f) - projected filtering 0, evidence_loss_rate=0.0, answer_changed_by_ontology=false |
| Gate 3 | 104 题 baseline 可跑 (分片或性能优化) | **达成** | WP8 (19b023d) shard-run/merge-shards + WP9 (fa5667e) 性能修复 (20+min -> 7.5min) |

## 3. 工作包完成情况

| WP | 内容 | 状态 | Commit |
|---|---|---|---|
| WP0 | baseline 快照+冻结 | 完成 | (baseline preserved at d1ed846) |
| WP1 | 失败样本分桶 (不写代码) | 完成 | 9ae1abc, 6 次根因修正 |
| WP2 | 答案质量修复 A | 完成 | e3e4da7 (P0 hard-degrade), 487a821 (doc-selection), e0d3bf8 (P3 noise+guard), cd9e5e2 (metadata penalty) |
| WP3 | 召回/rerank 证据覆盖 | 完成 | 2fcd94d (anchor split), fb82215 (_anchors CJK fallback) |
| WP4 | citation/unsupported-claim 安全门禁 | 完成 | 2127552 |
| WP5 | ontology shadow A/B | 完成 | b59697f |
| WP6 | guard warning 并入 warnings | 完成 | 7550038 |
| WP7 | orphan facts 治理 | 完成 | 85c4d98 |
| WP8 | 104 题 golden 分片 | 完成 | 19b023d |
| WP9 | eval 提分验收 + 性能修复 | 完成 | fa5667e |
| WP10 | CodeStable/ADR/验收收口 | 本报告 | - |

## 4. 关键诚实判断

1. **首提真实提分**: WP3 _anchors CJK fallback (fb82215) 把 [4][12] 从 degradation
   (cov=0.00) 转为真实答案 PASS, 20q pass_rate 0.35 -> 0.40 (0 artifact). 这是
   Sprint 3 的首次真实提分.
2. **反 metric-gaming**: P3 anti-degradation guard + noise-point 清理把假阳性 PASS
   (degradation 文本与英文 expected_point 共享 token) 正确归零, 导致表观 pass_rate
   0.45 -> 0.40 (诚实下降, 非 regression).
3. **Gate 1 未达**: 0.40 距 0.65 仍差 0.25. 主因是 P1 channel-weighting/rerank
   分数膨胀问题需要 full-payload (object_value/normalized_text) anchor 匹配, 而
   snippet 截断 (~120 字符) 不含锚点, snippet-based rescore 不可行. 这是 4 次根因
   迭代后的诚实结论, 需 Sprint 4 设计 full-payload 方案.
4. **性能修复解锁**: WP9 发现 WP7 facts_fts 排除导致 derived-state stale, 每次搜索
   触发 ~15s 全量重建. 修复后 20q 从 20+min 降到 7.5min, 使 104q 分片 baseline 可行.

## 5. 硬约束遵守

- evidence_judge 仍是唯一事实裁决边界: 是 (未绕过)
- 答案只来自候选证据/事实/上下文: 是
- 证据不足必须降级而非补充: 是 (P0 hard-degrade e3e4da7)
- 主 metric 仍 deterministic+token_overlap: 是 (未切换)
- 不删困难样本除非有噪声判定+审计: 是 (P3 仅在 generic_hint 路径清噪声, 不删数据)
- 每次提分记录 improved/regressed: 是 (各 WP 报告 case-level diff)
- 不重写 query_api/answer_api 主链路: 是 (仅加注入分支/降权/门禁)
- Sprint 3 不启用 ontology retrieval filtering 生产模式: 是 (仅 shadow A/B)
- answer_changed_by_ontology 全程 false: 是 (所有 WP 验证)

## 6. 测试与健康

- Fast suite: 716+ passed / 0 failed / 0 xfail (Sprint 3 期间持续绿灯, 各 WP 加测试)
- check_health: 10/10 PASS
- 20q eval: pass_rate=0.40, 453.6s, 0 artifact

## 7. Sprint 4 候选

1. P1 full-payload anchor 匹配方案 (object_value/normalized_text DB 读取 + rerank
   统一 rescore 在 injection 后的 final sort 点) - Gate 1 提分主路径
2. [6] V2G wording alignment (召回碎片化, 无单证据覆盖完整 expected_point 措辞)
3. ontology.db class 多样性补齐 (当前 364 entity 单类, A/B filtering 结构性 no-op)
4. full 104q golden baseline 正式运行 (WP8 分片机制已就绪, ~30-40min 总时长)
5. AUTO eval mode (promotion gate 达标后)

## 8. 结论

Sprint 3 诚实达成: Gate 0/2/3 全达成, Gate 1 部分达成 (0.30->0.40 真实提分,
距 0.65 deferred Sprint 4). 性能修复 + 分片机制使 eval 可持续迭代. 无硬约束违反.
