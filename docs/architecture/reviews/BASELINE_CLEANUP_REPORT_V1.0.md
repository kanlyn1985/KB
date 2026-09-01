# Baseline Cleanup Report V1.0

> Task: AKB-P0-BASELINE-CLEANUP-001 · Date: 2026-09-01 · Branch: rebuild/agent-kb-core

## Task

Architecture Review 后置整改：Requirement ID 一致性 + Invariant ID 一致性 + RTM 映射 + 全仓引用同步。

## Base Commit

`cfc4dcb`（docs: add architecture gap register v1.0）— fetch --ff-only，工作树干净。

## Requirement IDs before/after

| | before | after |
|---|---|---|
| SRS 需求（族式 SYS-XXX-nnn） | 10 条（9 族：EVD/AST/SEM/GRAPH/REASON/RET/CTX/AGENT/OBS） | 10 条（不变，仅建映射） |
| RTM 需求（顺序 SYS-001..020） | 20 条 | 20 条（不变，仅增 §2a 映射节） |
| SRS↔RTM 映射 | **无** | **RTM §2a：SRS 10/10 全覆盖**（EVD→001+002+003、AST-001→004、AST-002→005+006、SEM→007、GRAPH→008、REASON→010、RET→012、CTX→013+014、AGENT→016+017、OBS→017）；RTM 20 条中 14 条有 SRS 来源、6 条 RTM 独有（009/011/015/018/019/020，已在 §2a 声明） |

## RTM mapping coverage

- SRS → RTM：**10/10**（每族至少一条映射）
- RTM → SRS：14/20 有 SRS 来源 + 6 条平台/运营层 RTM 独有（已声明，不强行映射）
- 双向追踪：SRS→RTM→DM→ICD→Verification 链路保持完整（RTM §3 矩阵未改动）；Test→Verification→RTM→Requirement 反向链由新增测试钉死

## Invariant IDs before/after

| | before | after |
|---|---|---|
| SRS 不变量 | **10 条**（INV-001..010，评审时误报为 9 条——SRS §6 表实含 INV-010 Action Policy Gate） | 10 条（原义不动） |
| Registry | **不存在** | **docs/architecture/INVARIANT_REGISTRY_V1.0.md**：INV-001..010 唯一权威定义（Name/Normative Rule/Source/Verification），语义逐字取自 SRS，零新造 |
| 引用体系错位 | 旧引用体系 7 条：INV-005(Canonical 独立/overclaim)、INV-006(Agent 写)、INV-007(Memory) 与 SRS 同号异义 | 全部修正（见下） |

## Broken references found

review-time 全仓扫描（docs/** + tests/**，md/json/py/html）发现 24 处错位/未知引用：

| 类别 | 位置 | 错位内容 | 修正 |
|---|---|---|---|
| ADR | ADR-001/006 | "INV-001..007"（泛指全部不变量） | → "INV-001..010 (per INVARIANT_REGISTRY_V1.0)" |
| ADR | ADR-002 | "aligns with INV-006"（Agent 直写图） | → INV-008 |
| ADR | ADR-004 | "INV-007"（memory 晋升） | → INV-009 |
| ADR | ADR-008 | INV-006×3、INV-007×3（Agent 写/memory 晋升） | → INV-008 / INV-009 |
| ADR index | decisions/README.md | INV 对照表 7 行（含错位 005/006/007） | → 重写为 10 行 Registry 对齐表 |
| Golden | 8 处 invariant_ref/requirement_refs | INV-005（overclaim 类，6 处）→ 实为 Evidence Gate answer 层推论；INV-006（Agent 写，2 处） | → INV-001 / INV-008 |
| 测试 | test_golden_dataset.py | INV-001/INV-002 引用 | 与 Registry 同义同号，无需改 |

## Broken references fixed

**24/24 修复**。修复后全仓扫描：**0 处未知 INV 引用**（test_all_repo_inv_references_known 持续钉死）。

## Tests

新增 `agent_kb_core/tests/test_baseline_consistency.py`（7 项，全过）：

1. test_srs_requirement_ids_unique — SRS 需求表内 ID 唯一
2. test_rtm_requirement_ids_unique — RTM §3 矩阵 20 条唯一 + §2a 映射引用不造新号
3. test_srs_rtm_mapping_complete — §2a 存在且 SRS 每族全覆盖
4. test_invariant_registry_complete_and_unique — Registry 恰含 INV-001..010 且规则非空
5. test_all_repo_inv_references_known — 全仓 INV 引用 ∈ Registry（未知编号即 FAIL）
6. test_golden_invariant_refs_consistent — golden invariant_ref ∈ Registry + Agent 写类必为 INV-008
7. test_adr_invariant_refs_consistent — ADR 引用 ∈ Registry + ADR-008 写边界 = INV-008

回归（review-time 实测）：

```text
python agent_kb_core/tools/validate_golden_dataset.py
Golden Dataset validation: PASS
Cases: 30 | Invalid: 0 | Duplicate IDs: 0 | Reasoning 6 | Negative 12/16 | Categories 30/30

python -m pytest agent_kb_core/tests -q
87 passed（80 + 新增 7）
```

（仓库根无独立 pytest 入口：agent_kb_core/pyproject.toml 即唯一包配置，agent_kb_core/tests 即全部测试面；
`python -m pytest -q` 等价于上述命令。）

## Golden validation

PASS（30 case 语义零改动——本任务仅修正 8 处 invariant_ref 引用标注，业务语义/期望值/结构未动；
golden schema 与 validator 未改判定逻辑）。

## Remaining gaps

| Gap | 状态 | 说明 |
|---|---|---|
| AG-007 | **Resolved ✅** | RTM §2a 映射 + 测试钉死 |
| AG-008 | **Resolved ✅** | Registry 建立 + 24 处引用修正 + 4 项测试钉死 |
| AG-001..004 | Open（P1，预期 Implementation Gap） | 随 V0.1 Evidence Core 落地 |
| AG-005..014 | Open（P2/P3） | 见 Gap Register |

架构核心语义零修改（ KnowledgeAssertion 定位/Graph Projection/Evidence First/Asserted≠Derived/
Semantica/KB1/Agent Boundary 全部未动；Data Model/ICD/SRS 正文零改动——RTM 仅新增 §2a 映射节，
属任务书允许的映射范围）。

## Commit SHA

见 git log：`docs: repair baseline id consistency (invariant registry + rtm mapping)`（本次提交）。