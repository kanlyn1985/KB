---
doc_type: feature-design
slug: ontology-shadow-guard-adapter
title: Ontology 最小接入：Shadow / Guard 只读 adapter
status: approved
created: 2026-06-25
roadmap: kb1-next-phase
sprint: sprint2-ontology-and-bugfix
tags: [ontology, shadow, guard, evidence-constrained]
---

# Ontology Shadow/Guard Adapter — Design

> Sprint 2 WP3/WP4。执行依据：`docs/dev/sprint2-ontology-and-bugfix/kb1_sprint2_development_guide.html` § WP3/§ WP4/§ 05。
> 硬约束：Ontology 只作 **约束层 / 校验层 / 召回辅助层**，不得成为事实来源；不绕过 `evidence_judge`。

## 1. 目标

让 `kb1_ontology` 以**最小可逆**方式进入主系统，第一步只做**只读信号**：
- 默认 `off`：完全不影响主链路。
- `shadow`：记录 ontology 信号（entity constraint / relation domain-range），不改变检索排序、不改变答案。
- `guard`（WP4）：在答案生成后做一致性 post-check，输出 warning/risk，不生成事实、不改写答案正文。

`answer_changed_by_ontology` 在 Sprint 2 必须**始终 False**。

## 2. 接入架构（主系统调用只读 adapter）

```
user query
  ├─ query_semantic_parser / build_query_context     # 主链路不变
  ├─ ontology_adapter.analyze(query)   # off/shadow/guard, 只读 ontology.db, 无 LLM
  │      ├─ entity_constraints   (规则提取 entity 提及 → class_id)
  │      └─ relation_checks      (relation_def domain/range 合理性)
  ├─ retrieval / rerank            # 主链路不变
  ├─ evidence_judge                # 事实裁决仍在这里，ontology 不介入
  ├─ answer_policy                 # 主链路不变
  └─ ontology_post_check(answer)   # WP4: guard 模式输出 warning，不改答案
```

## 3. 新增对象（`enterprise_agent_kb/ontology_adapter.py`）

```python
OntologyMode = Literal["off", "shadow", "guard"]

@dataclass(frozen=True)
class EntityConstraint:
    mention: str
    class_id: str | None
    class_name: str | None
    confidence: float

@dataclass(frozen=True)
class RelationCheck:
    relation: str
    status: str  # "consistent" | "unknown" | "conflict"
    note: str

@dataclass(frozen=True)
class AnswerPostCheck:
    type: str
    severity: str  # "info" | "warning"
    message: str

@dataclass(frozen=True)
class OntologySignal:
    mode: OntologyMode
    query_entities: list[EntityConstraint]
    relation_checks: list[RelationCheck]
    post_checks: list[AnswerPostCheck]
    changed_retrieval: bool = False   # Sprint 2 始终 False
    changed_answer: bool = False      # Sprint 2 始终 False
    errors: list[str]
```

## 4. 关键设计决策

- **无 LLM**：adapter 用规则（正则 + 字典查找 ontology.db）提取 entity，不调 `_llm_route` / decomposer。
  Sprint 2 影子模式的价值是验证接口/日志/指标/回归风险，不是推理能力。
- **只读**：只 `SELECT` ontology.db，永不写。失败（DB 缺失/表缺）→ 记入 `errors`，返回空 signal，不抛异常、不阻断主链路。
- **模式开关**：`KB1_ONTOLOGY_MODE` 环境变量（默认 `off`）。`off` 时 `analyze` 直接返回空 signal（mode=off），零开销。
- **不接 evidence/fact**：signal 字段名只用 constraint/check/validation，绝不叫 evidence/fact。
- **接入点**：WP3 只实现 `analyze(query)` 并在 `build_query_context` 末尾把 signal 挂到 context 的 `ontology_signal` 字段（shadow 记录，不改 hits/evidence/facts）。WP4 在 answer 组装后调 post-check（guard）。

## 5. entity 提取规则（无 LLM）

从 query 文本按 ontology.db `entity`/`term` 表的 `canonical_name` + aliases 做子串匹配：
- 加载 entity/term 的 (name, aliases, class_id) 到内存（364+410 条，小）。
- 对 query 做大小写不敏感子串匹配，命中的取其 class_id → EntityConstraint。
- confidence：精确 canonical 命中 0.95，alias 命中 0.7。

## 6. relation domain/range 检查

ontology.db `relation_def` 当前 4 条（is-a/part-of/has-attribute/references），`relation` 700 条。
- shadow：列出 query 涉及 entity 间的已知 relation（status=consistent），无 relation 标 unknown。
- guard：若 answer 引用了某 entity 但 ontology 显示该 entity 与 query entity 无任何已知 relation，输出 warning（不改答案）。
- **不做 OWL/RDF 推理**，不引入重图数据库。

## 7. 不做（范围外）

- 不让 ontology 生成新 fact / 改写答案正文 / 改变检索排序（Sprint 2）。
- 不集成 decomposer / router 的 LLM 路径。
- 不把 ontology.db 当主事实库。
- 不改 query_api/answer_api 主链路（仅在 context 挂只读 signal 字段 + WP4 post-check）。

## 8. 验收（对照 Sprint 2 Gate 2）

- [ ] off 模式：旧答案完全不变，零 signal。
- [ ] shadow 模式：context 出现 `ontology_signal`，hits/evidence/facts 不变，答案不变。
- [ ] guard 模式（WP4）：输出 post-check warning，`answer_changed_by_ontology=False`。
- [ ] ontology.db 缺失/损坏时不抛异常、不阻断主链路（errors 记录）。
- [ ] fast suite 全绿（off/shadow/guard 三模式各有测试）。
- [ ] check_health 不受影响。

## 9. Checklist（实现步骤）

- [ ] 9.1 新增 `enterprise_agent_kb/ontology_adapter.py`：类型 + `analyze(query, mode, db_path)` + entity/relation 只读查询。
- [ ] 9.2 `KB1_ONTOLOGY_MODE` 读取（默认 off）；off 早返回。
- [ ] 9.3 `build_query_context` 末尾挂 `ontology_signal`（shadow 记录，不改其它字段）。
- [ ] 9.4 测试 `tests/test_ontology_adapter.py`：off/shadow/guard 三模式 + DB 缺失容错。
- [ ] 9.5（WP4）guard post-check + answer_run 日志字段。
- [ ] 9.6 文档同步（attention.md + 架构 ADR：ontology 只作约束层）。
