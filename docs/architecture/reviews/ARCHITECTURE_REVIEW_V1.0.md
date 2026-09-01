# Architecture Review V1.0

- Review ID: AR-V1.0
- Review Date: 2026-09-01
- Review Branch: rebuild/agent-kb-core
- Review Base Commit: baf26c6
- Status: COMPLETED
- Review Owner: Architecture Owner (Human Reviewer) — 本记录由 Local AI 依据 AKB-DEV-001 职责边界起草，供架构负责人批准
- Scope: SRS V1.1 / Data Model V1.0 / ICD V1.0 / V&V Plan V1.0 / RTM V1.0 / Golden Dataset V1.0 / ADR-001..010 七类基线的一致性审核，及基线与当前实现（agent_kb）之间的差距识别

## 1. Review Objectives

1. 验证七类基线内部及相互之间的一致性（编号、引用、语义）；
2. 核对不变量 INV-001..007 的 documented/designed/testable/runtime-enforced 四级状态；
3. 识别 Canonical Data Model 与 ICD 的完整性缺口；
4. 评估 ADR-006（Semantica）与 ADR-007（KB1 收敛）的适配边界；
5. 以 review-time 实测（validator + 全量 pytest + 静态依赖扫描）为证据，而非引用旧报告；
6. 产出 Gap Register 与 Gate Decision，为 Architecture Review 批准提供依据。

## 2. Baseline Documents

| 基线 | 文档 | 状态核查 |
|---|---|---|
| SRS | docs/requirements/SRS/Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html | ✅ 存在；需求族 SYS-EVD/AST/CTX/GRAPH/OBS/REASON/RET/SEM/AGENT；不变量 9 条（见 Gap AG-008） |
| Data Model | docs/architecture/data-model/Agentic_Knowledge_Base_Data_Model_V1.0.md | ✅ 存在；DM-001..018；无 Plan 对象（见 AG-013） |
| ICD | docs/architecture/interfaces/Agentic_Knowledge_Base_ICD_V1.0.md | ✅ 存在；14 接口；契约字段深度不均（见 AG-010） |
| V&V Plan | docs/verification/Agentic_Knowledge_Base_VV_Plan_V1.0.md | ✅ 存在；V0-V6 七级验证；INV-T01..T06；Exit Criteria 8 条 |
| RTM | docs/verification/REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md | ✅ 存在；SYS-001..020 双向追踪；与 SRS 族号无映射（AG-007） |
| Golden Dataset | docs/verification/golden/（README/manifest/schema/cases 30） | ✅ 存在；validator review-time PASS |
| ADR | docs/architecture/decisions/ADR-001..010 + README | ✅ 存在；10 条全部 Proposed；引用路径全部有效 |

## 3. System Architecture Review (AR-001)

评审对象：Evidence → Knowledge Core → Knowledge Runtime → Agent 四层。

| # | 检查项 | 结论 | 依据 |
|---|---|---|---|
| 1 | 四层职责重叠 | **PASS** | Evidence 层（intake/compilation）与 Knowledge Core（assertion/governance）职责边界在 DM-004（SemanticUnit 为中间 IR）明确划分；Runtime 消费 Canonical，Agent 消费 Runtime 接口 |
| 2 | 循环依赖 | **PASS** | ICD 接口图（§3 Logical Interface Map）为 DAG：Agent→Context→Retrieval/Reasoning→Store；无反向边 |
| 3 | 职责缺失 | **GAP→AG-002/003** | Knowledge Core 的 Assertion/Trace 对象未实现（预期 Implementation Gap）；除此无缺层 |
| 4 | 不必要基础设施 | **PASS** | 无向量数据库服务依赖（SQLite+numpy 快速路径）；单节点约束符合 AGENTS.md 开发规则 |
| 5 | Agent 绕过 Knowledge Runtime | **PASS（设计）/GAP（强制）→AG-005** | ADR-008 冻结接口边界；当前代码（answer_query/service）经扫描未直连 SDK，但无 lint 防回归 |
| 6 | Projection 反向污染 Canonical | **PASS（设计）/GAP（实现）→AG-001** | ADR-002 冻结单向数据流；当前 graph_edges 无 assertion_ref，投影与断言不可核对 |
| 7 | Semantic Runtime 与 Agent Runtime 解耦 | **PASS（设计）/RISK（实现）→AG-005/011** | 解耦原则成立；静态边界 lint 缺失为唯一风险敞口 |

**结论: PASS（附 2 项预期实现 Gap）**——四层架构设计自洽，无循环依赖，全部已知问题属实现进度而非设计缺陷。

## 4. Canonical Data Model Review (AR-002)

逐项核查 DM-001..018 的 identity/ownership/lifecycle/versioning/provenance/references/mutability/canonical-status：

| 对象 | identity | lifecycle | provenance | 判定 |
|---|---|---|---|---|
| Source (DM-001) | source_id 全局唯一不可变 | 注册制 | authority_score/owner/access_policy | ✅ 完整 |
| Document (DM-002) | document_id+version+content_hash | 版本不可变，变更=新版本 | source_id | ✅ 完整 |
| Evidence (DM-003) | evidence_id，可由 content_hash+版本+位置确定性导出 | 持久不可变 | document_id/location | ✅ 完整 |
| SemanticUnit (DM-004) | 明确为中间 IR | 可重放 | evidence_id | ✅ 完整（明确不得视为 authoritative） |
| **Assertion (DM-005)** | assertion_id | candidate→validated→asserted→disputed/deprecated；candidate→rejected | evidence_refs+provenance_ref+derivation | ✅ 最完整（核心治理对象） |
| Entity/Relation (DM-006/007) | 明确为 Semantic projection/registry | 随断言投影 | 断言引用 | ✅ 定位正确（投影，非第二真相源） |
| Event (DM-008) | event_id+event_time | 持久 | targets+evidence | ✅ 完整 |
| State (DM-009) | subject+state_name+observed_at | 观测历史 | observation 链 | ✅ 完整 |
| Ontology/Rule (DM-010/011) | 版本化 | 版本演进 | ontology_ref/rule_ref | ✅ 完整 |
| Memory (DM-013) | 运行时记忆 | 持久但非权威 | — | ✅ 与 INV-007 一致 |
| Context (DM-014) | ephemeral/versioned | 派生 | 引用快照 | ✅ 正确标为 Derived |
| Goal/Decision/Action/Observation (DM-015..018) | 明确 | 决策可重放（DM-016） | 引用上下文 | ✅ 完整 |
| ReasoningTrace (DM-012) | audit/trace | 持久 | rule+parent+reasoner | ✅ 完整 |

**语义重叠专项核查（Assertion/Evidence/Entity/Relation/Event/State）**：
- Entity/Relation 是 Assertion 的投影（ADR-002），不是第二真相源——无重叠；
- Event/State 与 Assertion 职责清晰：Event=发生的事（时点），State=处于的状态（时段），Assertion=命题（治理对象）；
- **确认 KnowledgeAssertion 是唯一 Canonical Knowledge Unit，无第二套"事实真相对象"**（ADR-001 已冻结；facts/cards 在 ADR-001 中明确降位）；
- Plan 对象不存在于 DM-001..018（任务书 AR-002 清单包含 Plan）→ 记 AG-013，需架构负责人裁决。

**结论: PASS（附 1 项文档裁决项 AG-013）**

## 5. Interface Architecture Review (AR-003)

ICD 14 接口按 12 项契约字段（Input/Output/Precondition/Postcondition/Error/Idempotency/Transaction/Timeout/Retry/Version/Security Context/Provenance）核查：

- **契约完整度不均**：SourceProvider/AssertionValidator/RetrievalEngine 有较完整的行为契约（SRS §8 与 ICD §5 双处定义）；KnowledgeCompiler/ReasoningEngine/MemoryStore/StateStore/DecisionEngine/ObservationStore/AgentRuntime 仅有一句签名——记 **AG-010（P2）**；
- **"定义接口但没有调用边界"检查**：未发现——每个接口都标注了 Consumer/Provider 两端（ICD §3）；
- **接口依赖具体实现检查**：未发现——接口定义均为抽象签名；
- **Provider 泄漏检查**：ICD 接口签名无 provider 类型字段；SemanticGraph 未绑定 Neo4j、RetrievalEngine 未绑定 Qdrant——PASS；
- **Canonical Model 泄漏检查**：接口返回值均为 canonical 引用（assertion/evidence/object refs）——PASS。

**结论: PASS（附 1 项文档增补 Gap AG-010）**

## 6. Semantica Integration Review (AR-004)

以 ADR-006 为基准审查适配边界（本评审不写 Adapter）：

| Semantica 能力 | 适配方式 | 说明 |
|---|---|---|
| Entity Resolution | **可直接适配**（经 Adapter 归一） | 产出映射到 DM-006 Entity；置信度进 candidate 断言 |
| Graph 存储/遍历 | **需 Adapter** | Semantica 图结构须映射到 SemanticGraph 投影（ADR-002）；边须补 assertion_ref |
| Temporal 语义 | **可直接适配** | 映射到 DM-005 temporal_scope；Golden G008 已定义期望 |
| Pipeline（ingestion） | **需 Adapter** | 必须接入 Evidence→SemanticUnit→Assertion 治理链，不能绕过 AssertionValidator |
| Reasoning 机制 | **需 Adapter + 严格约束** | 产出必须是 inferred 断言+derivation（ADR-004），Semantica 原生输出不满足 |
| Provenance 机制 | **可直接适配** | 与 DM-003/012 语义兼容 |
| Storage abstraction | **可直接适配** | ADR-005 投影层可由其承载 |
| **Semantica KnowledgeGraph 作为 Canonical Model** | **不能采用** | 无 assertion_type/status/evidence_refs/derivation 治理语义——违反 ADR-001/003/004（ADR-006 已禁止） |
| **Semantica 作为 Agent Runtime / 整个 AKB** | **不能采用** | 违反 ADR-008 分层（ADR-006 已禁止） |

**结论: PASS**——ADR-006 的"机制层复用、治理层自建"边界清晰，全部四条适配路径可执行。

## 7. KB1 Convergence Review (AR-005)

以 ADR-007 为基准，建立迁移矩阵：

| KB1 能力 | 目标模块 | 迁移方式 | 风险 |
|---|---|---|---|
| Evidence 体系（29528 条证据、evidence_id 稳定标识） | Evidence Engine | **preserve**（evidence_id 语义直接继承） | low——已验证可复现导入 |
| Facts（434 条，term/procedure/table_row） | Assertion pipeline | **transform**（fact→candidate assertion，治理链升位） | medium——需映射规则与人工抽查 |
| Graph（467 骨架边） | SemanticGraph 投影 | **converge**（边重建为断言投影+assertion_ref 回填） | medium——依赖 AG-001 迁移 |
| Retrieval（三通道+门控+权重） | Retrieval Engine | **adapt**（通道语义保留，接口转 ICD 5.7） | low——消融基线已冻结可对照 |
| Answer Contract（sufficient/partial/insufficient+披露） | Context/Answer | **preserve**（7 项契约测试已存在） | low——直接通过 |
| Golden 纪律（冻结基线/自动统计） | Evaluation Plane | **preserve**（V1.0 已按此建立） | low |
| 三层体检门（骨架/检索/生产） | 验收工具 | **adapt**（转 ICD 契约测试） | medium——AG-006 CI 化 |
| 遗留目录结构/SQLite 专用存储/phase 管道命名 | — | **不迁移**（ADR-007 §3 明确排除） | — |

**结论: PASS**——继承的是语义而非结构，与 ADR-007 决策一致；收敛依赖 AG-001/002 落地。
## 8. Agent Runtime Review (AR-006)

检查 Goal/Plan/Decision/Action/Observation/State/Memory/Context 与依赖方向：

- **设计层**：ADR-008 冻结 Agent→ICD 接口（Context/Memory/State/Decision/Observation）→Knowledge/Retrieval/Reasoning 的单向依赖；DM-015..018 提供全部 Agent 平面对象；
- **代码层静态扫描（review-time 实测）**：agent_kb 全包扫描 `import neo4j|qdrant|openai|anthropic` —— **零 SDK 直连**。`retrieval/qdrant.py` 为自研 REST 适配器（stdlib urllib），非 Qdrant SDK；LLM 调用经 `llm_client.py` 动态加载网关客户端，属 Reasoning 接口实现而非 Agent 直连；
- **潜在直接依赖（记录为 Gap 不修复）**：
  - `service/api.py` 直接持有 `SQLiteKnowledgeStore` —— 服务层目前承担了部分 Agent 平面职责，Agent Runtime 正式实现时须改走 ICD 接口（AG-005 静态 lint 一并防护）；
  - `commands/answer_query.py` 经 `validation/llm_client.py` 全局网关函数调 LLM —— 属 Reasoning 接口前身，V0.1 收编为 ICD 接口实现；
- **写路径治理**：当前 Agent 平面无任何 Authoritative Knowledge 写代码（反馈只写 feedback 表）——INV-006/007 现状天然满足，运行时强制待 AG-002。

**结论: PASS（设计+现状扫描），RISK 一项（无 lint 防回归）→ AG-005 (P2)**

## 9. Verification Architecture Review (AR-007)

要求链：Requirement → Design → Interface → Implementation → Test → Acceptance。

RTM SYS-001..020 逐条核查 architecture/data model/interface/verification 四列引用：**20/20 条全部有四列引用**（RTM §3 表）——链路在文档层完整。

**重点搜索四类断链（review-time 实测证据）**：

| 检查 | 结果 |
|---|---|
| 需求存在但没有测试 | SYS-001/009/018/019/020 五条无 Golden case 覆盖（golden 覆盖 15/20 SYS）→ AG-009 (P2)；其中 SYS-018/019 为元需求（回归/schema 由其自身履行） |
| 接口存在但没有测试 | 14 ICD 接口的 C-*/I-* 测试全部待实现（与 AG-002/003 同源）→ 预期 Implementation Gap |
| 数据对象存在但没有 invariant | DM-001..018 中：Assertion/Evidence 有 schema+validator 双重 invariant（golden）；Source/Document invariant 在 RTM 有测试号（T-SOURCE/T-DOC）待实现 → 预期 Gap |
| 架构原则无可执行验证 | INV-001/002 在 golden schema+validator 双层可执行 ✅；INV-003/006/007 待运行时（AG-001/002）；INV-005 由 ADR-005 恢复顺序承载，测试待 V0.1（INV-T05） |

**结论: PASS（文档链完整），GAP 2 项（AG-009 文档增补、运行时验证随 V0.1）**

## 10. Golden Dataset Review (AR-008)

Review-time 实测（非引用旧报告）：

```text
$ python agent_kb_core/tools/validate_golden_dataset.py
Golden Dataset validation: PASS
Cases: 30 | Invalid: 0 | Duplicate IDs: 0
Reasoning cases: 6 (>=5) | Negative cases: 12 (>=3) | Negative expectations: 16
Categories covered: 30/30
```

- Schema（jsonschema Draft2020-12）对 30 case 全量校验通过；
- 统计口径已统一（AKB-P0-ADR-001 修正）：manifest 4 字段由验证器自动计算对照，test_golden_manifest.py 钉死；
- Evidence 双轨引用（evd:node:* 生产库 / evd:gold:* 本地精选）合法性全部通过；
- INV-001（asserted 必带 evidence_refs）与 INV-002（inferred 必带 derivation）在 schema allOf + validator 双层强制；
- reasoning 六例四型（graph multi-hop/temporal/conflict-aware/rule/multi-step）满足 V&V §15.1；
- 与旧检索面 golden_cases.json（234 条）层次分离、manifest 交叉引用，无双套目录问题。

**结论: PASS**

## 11. Traceability Review (AR-009)

（并入 §9 详述）双向追踪：Requirement→Test 20/20 有验证引用；Test→Requirement：现有 80 项 pytest 全部可回指（golden tests→SYS-018/INV-001/002；answer contract→SYS-013；context selection→SYS-014；production gate→SYS-012）。孤立测试：无（test_answer_contract/test_golden_* 均带 requirement_refs 或 invariant 注释）。

编号双轨问题（SRS 族号 vs RTM 顺序号）见 **AG-007/AG-008 (P1)**——这是本次评审发现的最高优先级文档一致性问题：**不变量编号在 SRS（9 条）与任务书/ADR 引用（7 条）之间存在错位**，若不修正，INV-T06（SRS INV-006=Index 不丢）与 ADR 引用的 INV-006（Agent 写权限）将在后续测试命名中冲突。

**结论: PASS（结构）/ GAP（编号体系）→ AG-007/AG-008**

## 12. Security Architecture Review (AR-010)

| 检查项 | 现状 | 判定 |
|---|---|---|
| RBAC/ABAC | security 模块代码齐备（Principal/APIKeyRecord/AuditLog）但**未接线**到 webui/API | RISK→AG-011 |
| Tenant | 多租户表结构存在（tenants/），单节点定位未启用 | 可接受（定位 B） |
| Source/Assertion permissions | access_policy_ref 字段已定义（DM-001），运行时无 enforcement | GAP（随 AG-002） |
| Memory permissions | 无 Memory 实现即无权限面 | N/A→V0.1 |
| **Agent 能否写 Canonical Knowledge** | 现状不能（无写路径代码）；设计层 ADR-008 禁止 + INV-006；运行时强制待 AssertionStore | PASS（现状）/ 强制待 V0.1 |
| **Graph driver 是否可能从 Agent 代码直接获得** | 静态扫描零 SDK 直连；无 lint 防回归 | RISK→AG-005 |
| **LLM provider 能否绕过 Reasoning interface** | llm_client 为模块级全局（chat 直接可 import）——理论上可被 agent 代码绕过 Reasoning 接口直接调用 | RISK→AG-005（lint 需覆盖 llm_client import） |
| Audit | AuditEvent/AuditLog 类已备未接线；断言迁移审计待 AG-004 | GAP |

**结论: RISK 3 项（AG-005/011/004），无 P0**——当前定位（团队工具、Tailscale 内网、无真实 Agent 自主写路径）下风险可控；V0.1 Agent Runtime 落地前必须关闭 AG-004/005。

## 13. Failure / Recovery Review (AR-011)

| 失败场景 | 现有处置 | 与 ADR-005 一致性 |
|---|---|---|
| Parser failure | 编译期失败不入库（evidence-first 链路天然阻断） | ✅ |
| Embedding failure | 服务失败→hash 通道回退（webui 已实现）；批量失败→断点续传 runbook | ✅ 投影层事件 |
| Graph failure | 图通道门控关闭（graph_gate=False 回退） | ✅ 可重建（AG-001 后需补 INV-T05 实测） |
| Vector failure | 纯 Python 回退路径（AGENT_KB_VECTOR_NO_NUMPY）+ 空向量行过滤 | ✅ 可重建（fastembed 换后端已实战验证） |
| Reasoner timeout | llm_client retries=2 + 失败回退规则理解 | ✅ |
| Storage failure | storage 模块含 backup/recovery（BackupManager）；三门禁可验证恢复 | ✅ 待 INV-T05 形式化 |
| Duplicate/Partial ingestion | source_id 幂等 upsert（向量导入 100% 对齐校验先例） | ✅ 幂等性有实战验证 |
| **恢复顺序 Canonical→Projection→Cache** | ADR-005 冻结；当前 DB 单库物理一体，逻辑分界清晰（canonical 表 vs 投影表） | ✅ 一致，物理分库决策延后（单节点规则） |

**结论: PASS**——恢复顺序与 ADR-005 一致；INV-T05 形式化测试列入 V0.1。

## 14. Performance Architecture Review (AR-012)

- 现有度量（review-time 记录）：热查询端到端 ~2.1s（嵌入 17ms + numpy 矩阵毫秒级 + 内存基线 ~1s）；向量检索 19.6s→毫秒（类级缓存）；嵌入吞吐 24ms/条（ONNX CPU）；批量导入 31557 条 ~10min（远程 Ollama 本地直连）；
- **P50/P95/P99/并发口径未建立** → AG-012 (P3)，V&V §5 环境基线要求已明确，Provider swap 必须重测（ADR-009 §4 绑定）；
- **Provider Swap 与 Canonical Model**：fastembed↔Ollama 实战切换中 Canonical 零变更（仅投影重建+基线重锚）——实证 PASS。

**结论: PASS（含 1 项优化 Gap AG-012）**
## 15. Architecture Gaps

全部 14 项 Gap 已入册 [ARCHITECTURE_GAP_REGISTER_V1.0.md](ARCHITECTURE_GAP_REGISTER_V1.0.md)，此处汇总：

| 严重度 | 数量 | Gap IDs |
|---|---|---|
| P0（阻断批准） | **0** | — |
| P1（V0.1 前必须） | **6** | AG-001 assertion_ref, AG-002 Assertion 实现, AG-003 ReasoningTrace 实现, AG-004 迁移审计, AG-007 需求编号映射, AG-008 不变量编号统一 |
| P2（V0.2+） | **5** | AG-005 import lint, AG-006 CI 门禁化, AG-009 五需求验证覆盖, AG-010 ICD 契约增补, AG-011 安全接线 |
| P3（优化） | **3** | AG-012 性能分位数, AG-013 Plan 对象裁决, AG-014 derivation 版本字段 |

**预期 Implementation Gap 与设计缺口的判定**：
- AG-001/002/003/004 为**预期 Implementation Gap**——ADR-001..005 已冻结设计，Golden 已编码期望，属"设计先行、实现未至"的正常 V-Model 位置，不构成架构缺陷；
- AG-007/008 为**文档级设计缺口**（P1）——不变量编号错位会在 V0.1 测试命名时产生实际冲突（INV-T06 双义），必须在 V0.1 动工前统一；
- AG-005/006/009/010/011 为**防护性缺口**——当前无实际事故，缺的是防回归机制；
- AG-012/013/014 为**优化/裁决项**。

## 16. Risks

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R1 | 不变量编号错位（SRS 9 条 vs 引用 7 条）导致 V0.1 测试命名冲突 | 高（时间性） | AG-008：V0.1 动工前统一注册表 |
| R2 | ReasoningEngine 实现时若绕过 derivation 约束，Golden 期望与运行时脱节 | 中 | AG-003 实现必须对照 R001..R006；validator 已强制数据层 |
| R3 | Semantica 适配层引入后 invariant 测试不达标被"降低标准通过" | 中 | ADR-006 已绑定 INV-T01..T06 为验收套件；评审时核对 |
| R4 | KB1 与 AKB 长期并行导致治理语义漂移 | 中 | ADR-007 收敛表 + V0.1 完成判据 |
| R5 | LLM 网关（llm_client）被未来 agent 代码绕过 Reasoning 接口直接 import | 低→中 | AG-005 lint 覆盖 llm_client；ADR-008 评审检查单 |
| R6 | 嵌入后端更换引发检索基线漂移被误判为回归 | 低 | ADR-009 §4 + 门禁文档 §12 重锚协议（已实战一次） |

## 17. Required Actions

P1（V0.1 动工前必须完成，Owner=架构负责人，除注明外）：

| # | Action | 对应 Gap | 目标增量 |
|---|---|---|---|
| A1 | 建立统一不变量注册表（INV-001..009），修正 ADR/Golden/RTM 引用编号 | AG-008 | V0.1 动工前 |
| A2 | RTM 增加 SRS 族号 ↔ SYS-NNN 映射列 | AG-007 | V0.1 动工前 |
| A3 | V0.1 Evidence Core Detailed Design 输入确认：assertions 表 + assertion_transitions 审计 + graph_edges.assertion_ref 迁移设计（ADDITIVE） | AG-001/002/004 | V0.1 设计 |
| A4 | ReasoningEngine 最小实现范围确认（RULE 传递闭包级，对照 Golden R001..R006） | AG-003 | V0.1 |
| A5 | （架构负责人）批准/驳回本评审的 Gate Decision；批准后逐条将 ADR 状态 Proposed→Accepted | 全部 ADR | 批准即生效 |

P2（V0.1+ 排期）：A6 import-lint（AG-005）；A7 CI 门禁化（AG-006）；A8 五需求验证补全（AG-009）；A9 ICD V1.1 契约增补（AG-010）；A10 安全接线（AG-011，随定位演进）。

## 18. Gate Decision

```text
Gate Decision: APPROVED WITH ACTIONS
```

理由：
1. 七类基线间**无设计自相矛盾**：ADR 决策互不冲突且全部可回指 SRS/DM/ICD 条目；Golden 期望与 Data Model 语义一致；RTM 链路结构完整；
2. 全部 14 项 Gap 中 **0 项 P0**——没有任何问题阻断架构批准；6 项 P1 中 4 项为预期实现进度（设计已定），2 项为文档统一（V0.1 动工前可完成）；
3. Review-time 实测全部通过（validator PASS / 80 pytest PASS / 零 SDK 直连 / CI pytest 矩阵 PASS）；
4. **条件**：A1/A2（不变量与需求编号统一）必须在 V0.1 Evidence Core 动工前完成，否则测试命名冲突将把 AG-008 放大为实现事故。

**权限声明**：本评审按 AKB-DEV-001 由 Local AI 起草。Local AI **不将任何 ADR 标记为 Accepted**——批准行为（含逐条 ADR 状态流转、SRS/RTM 文档修订）属架构负责人职权，需在 GitHub 上以评审批注或基线修订提交完成。

## 19. Review Evidence

| 证据项 | 内容 |
|---|---|
| Review base commit | `baf26c6`（工作树干净，fetch --ff-only 确认） |
| Baseline files verified | 7 类基线 10+ 文档全部存在并通读（§2 表）；10 ADR 模板完整性+引用有效性脚本校验通过（10/10，无断链，状态均 Proposed） |
| Golden validator（review-time） | PASS：30/30/0 dup/6 reasoning/12 negative case/16 expectations/30 categories |
| Full test（review-time） | `python -m pytest agent_kb_core/tests -q` → **80 passed**（golden 11 + manifest 2 + answer contract 7 + 既有 60） |
| CI（review-time） | GitHub Actions pytest 矩阵 3.11/3.12/3.13 全 PASS（run 33510281535/33510288284） |
| 静态依赖扫描 | `import neo4j|qdrant|openai|anthropic` 全包扫描零命中；qdrant.py 为自研 REST 适配器（stdlib urllib）；llm_client 经 Reasoning 前身接口调用 |
| RTM 覆盖统计 | golden 覆盖 SYS 15/20（未覆盖：001/009/018/019/020 → AG-009）；INV 覆盖 6/7 引用体系 |
| 编号体系核查 | SRS 不变量 9 条、需求族 9 族（SYS-EVD/AST/CTX/GRAPH/OBS/REASON/RET/SEM/AGENT）vs RTM SYS-001..020 —— 映射缺失（AG-007/008） |
| Data Model 完整性 | DM-001..018 齐备；无 Plan 对象（AG-013 裁决项） |

## 20. References

- SRS V1.1: docs/requirements/SRS/Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html
- Data Model V1.0: docs/architecture/data-model/Agentic_Knowledge_Base_Data_Model_V1.0.md
- ICD V1.0: docs/architecture/interfaces/Agentic_Knowledge_Base_ICD_V1.0.md
- V&V Plan V1.0: docs/verification/Agentic_Knowledge_Base_VV_Plan_V1.0.md
- RTM V1.0: docs/verification/REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md
- Golden Dataset V1.0: docs/verification/golden/（README / REPORT / manifest / schema / 30 cases）
- ADR-001..010: docs/architecture/decisions/
- Workflow: docs/development/LOCAL_AI_VMODEL_WORKFLOW.md
- Gap Register: docs/architecture/reviews/ARCHITECTURE_GAP_REGISTER_V1.0.md
- 上一任务证据: docs/verification/golden/GOLDEN_DATASET_V1.0_REPORT.md