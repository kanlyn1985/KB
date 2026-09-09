# Invariant Registry V1.0

> Document ID: AKB-INVREG-001 · Version: V1.0 · Status: Draft（待架构负责人批准）
> 唯一性声明：**本表是 AKB 全仓 Invariant ID 的唯一权威来源。** 任何文档/测试/Golden case 引用
> INV-xxx 一律以本表语义为准；同号异义视为基线缺陷。
> 来源：逐字取自 SRS V1.1 §6 System Invariants 表（10 条），**不新增、不改写、不删除语义**。

## Registry

| ID | Name | Normative Rule | Source | Verification |
|---|---|---|---|---|
| INV-001 | Evidence Gate | No Evidence → No Asserted Knowledge。无有效 Evidence 不得创建 validated/asserted 断言（candidate/observed 等前治理状态不受限，见 ADR-003 epistemic boundary）。 | SRS V1.1 §6 INV-001 | V&V §7 INV-T01；golden schema allOf + validator（数据层已强制）；AssertionStore 运行时门（V0.1，AG-002） |
| INV-002 | Derived Isolation | Derived Knowledge ≠ Asserted Knowledge。inferred 断言必带 derivation 块且 status=candidate，禁止自动晋升。 | SRS V1.1 §6 INV-002 | V&V §7 INV-T02；golden schema + validator（已强制）；ReasoningEngine 契约（V0.1+，AG-003） |
| INV-003 | Graph Traceability | Graph Edge → Assertion 必须可追溯。每条边携带 assertion_ref。 | SRS V1.1 §6 INV-003 | V&V §7 INV-T03；golden relations[].assertion_id（数据层已表达）；graph_edges 迁移（V0.1，AG-001） |
| INV-004 | Evidence Traceability | Assertion → Evidence 必须可追溯。断言必须引用可定位 Evidence，Evidence 可回溯 Document/Source。 | SRS V1.1 §6 INV-004 | V&V §8 EVD-001..003；golden evidence_refs 格式校验（已强制）；Provenance 链（V0.1） |
| INV-005 | History Integrity | 历史 Knowledge 不得被原地覆盖。修订=新版本+可追溯 supersede 关系，禁止静默改写已发布知识。 | SRS V1.1 §6 INV-005 | V&V §7 INV-T06（命名待按本注册表统一）；golden G009（历史版本探针）；Document/Assertion versioning（V0.1+） |
| INV-006 | Index Independence | Index 丢失不得导致 Canonical Knowledge 丢失。图/向量/词法索引全部可从 Canonical 重建。 | SRS V1.1 §6 INV-006 | V&V §7 INV-T05；ADR-005 恢复顺序（Canonical→Projection→Cache）；rebuild CLI（V0.1+） |
| INV-007 | LLM Governance Gate | LLM 不得绕过 Governance Gate。LLM 产出的断言与人工/规则产出走同一治理链，无特权通道。 | SRS V1.1 §6 INV-007 | AssertionValidator 统一入口（V0.1，AG-002）；llm_understanding 输出经治理链落库设计（V0.1+） |
| INV-008 | Agent Write Boundary | Agent 不得直接修改 Authoritative Knowledge。Agent 写限 Memory/Action proposal/Observation。 | SRS V1.1 §6 INV-008 | V&V §19 E2E（golden G029/G030）；ADR-008 接口边界 + AG-005 lint（V0.1+） |
| INV-009 | Memory Promotion Gate | Memory 不得自动升级为 Knowledge。memory→knowledge 必须经显式治理晋升管道（actor/reason 记录）。 | SRS V1.1 §6 INV-009 | V&V §17（illegal promotion must fail）；ADR-004/008；MemoryStore 晋升管道（V0.1+） |
| INV-010 | Action Policy Gate | Action 不得绕过 Policy/Permission。Agent 动作必须过 policy/permission gate（对应 SYS-AGENT-001）。 | SRS V1.1 §6 INV-010 | V&V §19/§20；DecisionEngine→Policy hook（ICD 5.12/5.14，V0.1+） |

## 编号迁移对照（旧引用体系 → 本 Registry）

第一版基线文档（ADR-001..010、Golden Dataset V1.0、架构评审记录）曾使用"7 条不变量"引用体系，
与 SRS 正式 10 条存在编号错位。本注册表建立后，全仓引用统一如下：

| 旧引用（历史文档中出现的语义） | Registry 正确 ID | 语义核对 |
|---|---|---|
| INV-005 "Canonical 独立于索引 / 不得过度断言"（ADR-005/009、golden G002/009/015/016/025/028 的 overclaim 类引用） | **INV-006**（Index Independence）；overclaim 类 = **INV-001** 的 answer 层推论 | golden overclaim 类引用已改为 INV-001 |
| INV-006 "Agent 不可改 Authoritative Knowledge" | **INV-008** | golden G029/G030 已改 |
| INV-007 "Memory 不自动升级" | **INV-009** | ADR-004/008 文字引用已改 |
| "INV-001..007"（泛指全部不变量） | **INV-001..010** | ADR-001/006 表述已改 |

## 引用规则

1. 新文档一律引用本表 ID；禁止自行发明新编号（INV-nnn，nnn>10）（新增不变量必须走 SRS 修订 + 本表升版）；
2. 每条不变量的 Verification 列允许随实现进度更新状态，但 Normative Rule 列修改必须走 SRS 变更流程；
3. 测试命名以 INV-Txx 引用本表 ID（V&V Plan 的 INV-T01..T06 编号与本表 ID 的对应关系在 V&V 侧维护，不在本表重复）。