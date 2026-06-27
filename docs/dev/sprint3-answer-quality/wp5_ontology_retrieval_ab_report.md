# WP5: Ontology 主动召回过滤 Shadow A/B 报告

> Sprint 3 WP5。评估 Ontology 是否能帮助减少噪声召回、关系错配和实体类型混淆。
> Sprint 3 只允许 shadow A/B，不直接启用生产过滤。
> 日期：2026-06-26

## 1. 实验设计

三种模式（参考 Sprint 3 指南）：
- `KB1_ONTOLOGY_MODE=off`（control）：不过滤，记录 baseline pass_rate
- `KB1_ONTOLOGY_MODE=shadow`：**记录如果过滤会发生什么**（projected，不实际过滤）
- `KB1_ONTOLOGY_MODE=guard`：只输出 warning，不改变 answer

新增 `project_retrieval_filtering(query, candidates, workspace_root)`（只读，
不实际过滤）。一个候选被 projected-filter 当且仅当：
1. query 有至少一个已知 class 的实体，且
2. 候选文本提及一个**不同 class** 的 ontology 实体，且
3. 候选文本**不**提及 query class 的实体。

保守设计：只有当候选**完全是**关于不同 class 实体时才标记，永远不会删除唯一证据。

## 2. A/B 结果（20 题 cross-doc 样本）

| 指标 | 值 | 含义 |
|---|---|---|
| off pass_rate | 0.40 (8/20) | control baseline |
| candidates_total | 59 | 20 题候选总数 |
| **candidates_would_drop** | **0** | shadow projected 会过滤的候选数 |
| evidence_loss_cases | 0 | 被过滤候选中含真实所需 evidence 的 |
| false_positive_filter_cases | 0 | 误过滤 |
| safe_filter_candidates | 0 | 安全过滤候选 |
| **projected_precision_gain** | **0.000** | would_drop / candidates |
| **evidence_loss_rate** | **0.000** | 必须接近 0 ✓（但因为没有过滤）|

### reason 分布（为什么 projected filtering 不工作）

| reason | 题数 | 含义 |
|---|---|---|
| `single_class_ontology_no_diversity` | 10/20 | 所有 364 个 ontology 实体共享一个 class（CLS-OBC-STANDARD），type-mismatch 过滤结构上是 no-op |
| `query_has_no_known_entity_class` | 8/20 | query 实体不在 ontology 索引（温度范围/供电设备等中文术语不在 ontology）|
| `no_candidates` | 2/20 | 答案无候选 hits |

## 3. 根因分析

**Ontology 主动召回过滤在 Sprint 3 是 no-op**，两个结构性原因：

1. **class 多样性缺失**：ontology.db 的 364 个实体全部归属 CLS-OBC-STANDARD
   （Standard）。type-mismatch 过滤需要 >=2 个不同 class 才能区分候选，
   单 class 下任何候选都与 query class 相同 → 无法过滤。

2. **中文术语不在 ontology 索引**：8/20 题的 query 实体（温度范围、供电设备、
   车载充电机、V2G 等）不在 ontology.db 的 entity/term 表。ontology.db 当前
   主要覆盖 OBC/UDS/ISO 14229 领域标准编号，未覆盖中文标准内容术语。

## 4. 验收标准对照

| Sprint 3 WP5 验收 | 状态 |
|---|---|
| 产出 A/B 报告 | ✅ 本文档 |
| evidence_loss_rate 接近 0 | ✅ 0.000（因为没有过滤，安全）|
| 证明是否值得 Sprint 4 guard 化 | ✅ **不建议** Sprint 4 guard 化（见下）|
| Sprint 3 不直接生产启用过滤 | ✅ projected only，0 实际过滤 |

## 5. 结论与 Sprint 4 建议

### 结论
**Ontology 主动召回过滤在 Sprint 3 不产生任何收益**（projected_precision_gain=0），
且 **evidence_loss_rate=0**（安全）。这不是风险，是结构性的 no-op。

### Sprint 4 建议（不推荐 guard 化）
- ❌ **不建议** Sprint 4 启用 ontology retrieval guard：当前 class 多样性不足以
  区分候选，guard 化只会增加复杂度无收益。
- ✅ 前置条件：若要使主动过滤有意义，需先扩充 ontology.db 的 class 多样性
  （不只 Standard，加入 Parameter/Signal/Component/Activity 等 class）和中文术语覆盖。
- ✅ 扩充后重跑本 A/B：若 projected_precision_gain > 0 且 evidence_loss_rate ≈ 0，
  才值得 Sprint 4+ guard 化，且需先写单独 ADR（Sprint 3 禁止口头决策）。

### 边界合规
- ✅ projected only，0 实际过滤，0 证据丢失
- ✅ answer_changed_by_ontology = false（全程）
- ✅ 不绕过 evidence_judge（projected 不参与裁决）
- ✅ 只读，不生成事实

## 6. 测试

- tests/test_ontology_adapter.py: +4 projected filtering 单测
  （no_candidates、missing_db 不 raise、不 mutate input、结构化字段）
- fast suite 全量回归：见提交时验证

## 7. 交付物

- `src/enterprise_agent_kb/ontology_adapter.py`：新增 `project_retrieval_filtering`
- `tests/test_ontology_adapter.py`：+4 测试
- 本报告：`docs/dev/sprint3-answer-quality/wp5_ontology_retrieval_ab_report.md`
