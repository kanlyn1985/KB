# V0.1 Evidence Core — Detailed Design Package

> Document Set: AKB-DD-V01 · Status: **Ready for Implementation**（设计冻结基线，非实现声明）
> 前置：ARCHITECTURE_ACCEPTANCE_V1.0（Gate: APPROVED，ADR-001..010 Accepted）
> 生产代码状态：**Not Changed**（本包纯设计；实现由后续编码任务按本包执行）

## 文件清单

| 文件 | 内容 | 任务书条款 |
|---|---|---|
| [V0.1_EVIDENCE_CORE_DETAILED_DESIGN.md](V0.1_EVIDENCE_CORE_DETAILED_DESIGN.md) | 范围边界/架构位置/治理链/不变量落实/实现顺序 | §B1 |
| [V0.1_DATABASE_DESIGN.md](V0.1_DATABASE_DESIGN.md) | 7 new AKB canonical storage tables + 1 existing projection table altered (assertion_ref), DDL 级（列/类型/约束/CHECK/索引/append-only 触发器） | §B2/B3 |
| [V0.1_STATE_MACHINE.md](V0.1_STATE_MACHINE.md) | type×status 合法矩阵/Evidence Gate/非法迁移表/权限矩阵/幂等/投影联动 | §B4/B5/B6 |
| [V0.1_INTERFACE_BEHAVIOR.md](V0.1_INTERFACE_BEHAVIOR.md) | 9 方法级契约（10 字段/方法）+ Semantica Adapter 边界 + 错误码 | §B11/B12 |
| [V0.1_VERIFICATION_SPEC.md](V0.1_VERIFICATION_SPEC.md) | V0.1-EVD/AST/PROV/GRAPH/MIG/REG 15 条用例 + Golden 映射 + Exit Criteria | §B13/B14/B15 |
| [V0.1_MIGRATION_PLAN.md](V0.1_MIGRATION_PLAN.md) | 影子映射策略/回填/幂等/回滚/校验门禁 | §B9/B10 |

## 兼容映射速览（任务书 §B10 三问的回答）

| Existing | Target | 判定 |
|---|---|---|
| facts | SemanticUnit（编译 IR）+ Assertion(candidate)（治理对象） | **两者都是**——fact 的内容进 unit，治理形态进 assertion |
| retrieval_cards | **Retrieval Projection**（不是 Assertion） | 卡是检索优化聚合（ADR-001 明确非 Canonical） |
| graph_edges | **Assertion Projection**（断言投影产物 + assertion_ref 回指） | ADR-002 |

## 设计关键决定记录

1. **表名前缀 `akb_`**：与既有 KB1 同名表（evidence/documents）存储层隔离，语义不变；
2. **存量 evidence 影子映射**：29528 条 evd:node:* 原位保留、Validator 双格式解析，
   完整搬运延至 V0.2（回归安全优先）；
3. **append-only 三表**：akb_evidence / akb_assertions(核心列) / akb_assertion_transitions
   由触发器强制（INV-005 物质基础）；
4. **INV-001/002 双层强制**：API 层 Validator + DB 层 CHECK 约束（绕过 API 亦无法违规）；
5. **V0.1 无 Semantica import**（ADR-006 边界 + ADR-008 解耦边界），lint 清单预留。