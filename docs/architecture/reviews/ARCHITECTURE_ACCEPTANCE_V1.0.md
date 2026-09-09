# Architecture Baseline Acceptance V1.0

- Review ID: AR-V1.0-ACCEPT
- Acceptance Date: 2026-09-01
- Branch: rebuild/agent-kb-core
- Base Commit: a57bb1f
- Accepted By: Architecture Owner (Human Reviewer) —— 本记录由 Local AI 依任务书 AKB-P0-ARCH-ACCEPT-001 A4 条款起草执行；
  任务书明确授权：A3 前置检查全部通过后允许将 ADR-001..010 状态改为 Accepted。Decision/Rationale/Consequences 零改动。

## Baselines Accepted

| 基线 | 文档 | 版本 | 核查 |
|---|---|---|---|
| SRS | docs/requirements/SRS/Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html | V1.1 | ✅ 需求族 9 族 10 条、不变量 10 条（INV-001..010） |
| Canonical Data Model | docs/architecture/data-model/Agentic_Knowledge_Base_Data_Model_V1.0.md | V1.0 | ✅ DM-001..018 |
| ICD | docs/architecture/interfaces/Agentic_Knowledge_Base_ICD_V1.0.md | V1.0 | ✅ 14 接口 |
| V&V Plan | docs/verification/Agentic_Knowledge_Base_VV_Plan_V1.0.md | V1.0 | ✅ V0-V6 / INV-T / Exit Criteria |
| RTM | docs/verification/REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md | V1.0（含 §2a 映射） | ✅ SRS↔RTM 10/10 |
| Golden Dataset | docs/verification/golden/（schema+30 cases+manifest） | V1.0 | ✅ validator PASS |
| Invariant Registry | docs/architecture/INVARIANT_REGISTRY_V1.0.md | V1.0 | ✅ INV-001..010 唯一权威 |
| ADR-001..010 | docs/architecture/decisions/ | V1.0 | ✅ 本记录签署时全部 Proposed→Accepted |

## Architecture Gate

```text
Gate Decision: APPROVED
```

含义：Architecture Baseline 获得进入 **详细设计与实施阶段** 的资格。
本 APPROVED **不**表示实现 Gap 已关闭（见下"Open Gaps"）。

## Conditions（已满足）

| 条件 | 状态 | 证据 |
|---|---|---|
| AG-007 = Resolved | ✅ | RTM §2a 映射表（SRS 10/10）+ test_srs_rtm_mapping_complete |
| AG-008 = Resolved | ✅ | INVARIANT_REGISTRY_V1.0 + 全仓引用一致（158 处扫描零未知）+ 4 项 INV 测试 |
| Golden validator | ✅ PASS | review-time 实测（见 Evidence） |
| Full pytest | ✅ 88 passed | 三入口实测（见 Evidence） |

## Open P1 Implementation Gaps（保持 Open，不因 Acceptance 关闭）

| Gap | 内容 | 目标增量 |
|---|---|---|
| AG-001 | graph_edges.assertion_ref 迁移 | V0.1 |
| AG-002 | Canonical Assertion 对象级实现（AssertionStore/Validator） | V0.1 |
| AG-003 | ReasoningTrace 对象级实现 | V0.1+ |
| AG-004 | Assertion transition 审计 | V0.1 |

## Open P2/P3 Gaps

AG-005（import lint）、AG-006（CI 门禁化）、AG-009（五需求验证补全）、AG-010（ICD 契约增补）、
AG-011（安全接线）、AG-012（性能分位数）、AG-013（Plan 对象裁决）、AG-014（derivation 版本字段）
—— 详见 ARCHITECTURE_GAP_REGISTER_V1.0.md。

## Evidence

```text
# Golden validator（review-time）
python agent_kb_core/tools/validate_golden_dataset.py
Golden Dataset validation: PASS
Cases: 30 | Invalid: 0 | Duplicate IDs: 0
Reasoning cases: 6 | Negative cases: 12 | Negative expectations: 16 | Categories 30/30

# Full regression（review-time，双入口）
python -m pytest agent_kb_core/tests -q   → 88 passed
python -m pytest -q                        → 88 passed（仓库根入口，同一测试面）
```

前置评审链：ARCHITECTURE_REVIEW_V1.0.md（Gate: APPROVED WITH ACTIONS）→
BASELINE_CLEANUP_REPORT_V1.0.md（A1/A2 关闭，AG-007/008 Resolved）→ 本 Acceptance。

## Acceptance Decision

```text
ACCEPTED
```

1. 七类基线 + Invariant Registry + ADR-001..010 全部接受为 V0.1 设计与实现的约束基线；
2. ADR-001..010 状态 Proposed → Accepted（仅 Status 行 + Acceptance Reference 行变更，
   Decision/Rationale/Consequences 零改动——git diff 可核）;
3. AG-001..004 保持 Open，进入 V0.1 Evidence Core Detailed Design 范围（Phase B）；
4. 任何对已接受基线的修改必须走 AKB-DEV-001 §7 变更分类流程。

## References

- ARCHITECTURE_REVIEW_V1.0.md（Gate: APPROVED WITH ACTIONS，2026-09-01）
- ARCHITECTURE_GAP_REGISTER_V1.0.md（AG-001..014）
- BASELINE_CLEANUP_REPORT_V1.0.md（AG-007/008 关闭证据）
- INVARIANT_REGISTRY_V1.0.md（INV-001..010）
- LOCAL_AI_VMODEL_WORKFLOW.md（角色与变更分类）