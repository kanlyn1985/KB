# Phase 1: 3-Loop 重设计 (in-progress)

## 背景

KB1 现有 6 个 loop (ingestion / parse_quality / retrieval / answer / regression / hygiene) 实测下来
**不是控制闭环, 是 6 个并行的 dashboard 指标**. 706 个 benchmark 失败 4 个月没人发现, retrieval
loop 81% 是空数据, answer loop 从未跑过 corpus eval. 这是"打补丁式"开发的典型后果.

2026-06-02 的 grill-me session (18 个问题) 重做 3-loop 设计, **正向开发**: 先定义产品目标,
再设计支持目标的 loop, 最后实现. 见 `docs/dev/refactoring-progress.md` 9-13 行.

## 3 Loop 重设计 (替代原 6 loop)

| 旧 6 loop | 新 3 loop | 关系 |
|---|---|---|
| ingestion_loop | **ingestion_loop** (重做) | 入库质量 = 抽样题库答对率 + 段落覆盖度 |
| parse_quality_loop | (删除) | 链完整性是层次 3 内部观测, 不是入库质量 |
| retrieval_loop | (并入 answer_loop) | 每次 query 必跑, 不再独立 |
| answer_loop | **answer_loop** (重做) | 答对率 = 段落覆盖度, 用户感知 |
| regression_loop | **regression_loop** (Phase 3) | 暂时不重做, 等 Phase 1+2 稳了再写 |
| hygiene_loop | (降级为 hygiene_report) | 不再是 loop, 只是辅助观测 |

## 入库质量 = 抽样题库 + 段落覆盖度

**核心决定** (grill-me Q5): 入库质量 = **用户感知 (层次 1) + 应有 vs 实际 fact (层次 2)**.
**不包含** 内部一致性 (层次 3) — 那是 hygiene 范畴.

### 抽样题库 (sample_qa)

- **5 文档 × 6 题 = 30 题 golden 集** (人工 spot-check, 锁版本, 永远不变)
- **16 文档 × ~10 题 = ~150 题 full 集** (LLM 自动出, 每月刷新)
- **30 题黄金进 CI 必跑**, 阻塞合并
- **150 题 full 集 cron 必跑**, 失败报警

### 段落覆盖度 (expected_points + coverage scoring)

- **expected_points 表**: 每文档每章节的"应有论点"列表, 锁版本
- **章节内 LLM 拆论点** (D3 范式: 章节内 LLM 拆 2-5 个粗粒度论点)
- **LLM 答题评估** (抽系统答案覆盖了哪些 expected_points)

## 评测机制设计

### 三道守门 (Q3 守门方案)

1. **题目守门**: LLM 出题必须引用真实 evidence_id, 否则丢弃
2. **跨 prompt 鲁棒性** (不是跨 LLM, 因为只有 MiniMax-M2): 同一题用 2 个 prompt 跑, 结果差 < 10% 才认为有效
3. **规则守门**: LLM 只抽"覆盖论点", 规则计算覆盖率 (covered/total), 不让 LLM 直接打分

### 评测器 (`eakb eval run-now`)

```
[题目 + 系统答案] → LLM 抽"覆盖了哪些 expected_points"
                  → 规则: coverage = covered / total
                  → pass_rate = (coverage >= 0.5) 的题目占比
```

## 触发矩阵 (开发期 vs 上线期)

| 触发器 | MANUAL 模式 (开发期, 当前) | AUTO 模式 (上线后) |
|---|---|---|
| `eakb eval run-now --suite golden` | ✅ 任意时 | ✅ 任意时 |
| `eakb eval run-now --suite full` | ✅ 任意时 | ✅ 任意时 |
| CI commit | ❌ 跳过 | ✅ golden 必跑, 阻塞 |
| cron nightly | ❌ 跳过 | ✅ full + trend, 失败报警 |
| release 前 | ❌ 仅 warn | ✅ full 阻塞 |

**切换**: `eakb eval-mode set manual|auto` (持久化到 `.eakb/eval_mode`).

## Phase 1 实施步骤 (1 人 × 2 天 + 半天)

| 步骤 | 工作量 | 状态 |
|---|---|---|
| 1.1 expected_points 表 + build 脚本 | 1 天 | ✅ 完成 (commit 11行前) |
| 1.2 sample QA 题库 + multi-prompt 守门 | 1 天 | 🟡 下一个 |
| 1.3 5%-spot-check 人工审核 | 半天 | 等待 1.2 |
| 1.4 评测器 (eakb eval run-now) | 半天 | 等待 1.2 |
| 1.5 跑 baseline, 验证 65-85% 区间 | 30 min | 等待 1.4 |
| 1.6 Phase 1 sign-off 判定 | 半天 | 等待 1.5 |

## Phase 1 成功判定 (3 criteria, 全部 ✓)

1. **pass_rate 在 65-85% 区间**:
   - < 65%: 题库太难, 评测失效
   - > 85%: 题库太水, 评测失效
   - 65-85%: 题库难度合理
2. **5% 人工 spot-check 通过**: 拆分质量 + 出题质量都过
3. **multi-prompt 一致性 < 10%**: 同一题用 2 个 prompt 跑, 覆盖度差 < 10%

## Phase 1 已知问题 (Step 1.1 跑出)

- 章节切分过细 (94 sections per doc, 重复 sec 1/2/3)
- LLM JSON 解析失败 (Chinese quotes, control chars in long text)
- 单个章节 49k chars (chapter 5.19.4 是 OCR 漏 dump, 不是真实内容)
- Naive splitter 把目录当论点

**Step 1.4 评测器必须处理这些噪声**:
- 重复论点去重
- 长度过滤 (论点 < 30 字符丢弃)
- 章节级 aggregation (避免单章节过长影响 coverage)

## Phase 2 (下一步, 待 Phase 1 sign-off)

入库质量稳了之后:
- 用 706 个 benchmark 失败当 Phase 2 的真实样本
- 修 `preferred_doc_id` 强制时 answer_mode 不切换
- 加 not-found 触发
- 跑 `eakb run-corpus-retrieval-eval` 真正激活 answer loop
- 写 SLO + regression_loop

## Phase 3 (远期)

只有 Phase 1 + 2 健康, 防退化才有意义:
- baseline 锁定 + SLO 监控
- AUTO 模式自动跑
- 跨 LLM 守门 (引入第二个 LLM)
