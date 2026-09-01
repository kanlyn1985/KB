# Architecture Gap Register V1.0

> Review ID: AR-V1.0 · Base: baf26c6 · Date: 2026-09-01
> Category: G1=Documentation Gap · G2=Design Gap · G3=Interface Gap · G4=Implementation Gap ·
> G5=Verification Gap · G6=Security/Architecture Risk
> Severity: P0=阻断架构批准 · P1=V0.1 前必须解决 · P2=V0.2+ · P3=优化项
> 详细证据与逐项分析见 [ARCHITECTURE_REVIEW_V1.0.md](ARCHITECTURE_REVIEW_V1.0.md)。

| Gap ID | Severity | Category | Current | Target | Baseline | Action | Target Increment |
|---|---|---|---|---|---|---|---|
| AG-001 | P1 | G4 | graph_edges 无 assertion_ref 列，边不可反查断言 | 每条边带 assertion_ref，INV-003 运行时可查 | ADR-002 / Data Model DM-005/007 | ADDITIVE 迁移加列 + 回填脚本 + INV-T03 测试 | V0.1 |
| AG-002 | P1 | G4 | Canonical Assertion（DM-005）无对象级实现；facts/cards 为弱对应 | AssertionStore/AssertionValidator 按 ICD 5.4/5.5 落地 | ADR-001 / ICD 5.4/5.5 | 实现 assertions 表 + 治理链（V0.1 Evidence Core 主体） | V0.1 |
| AG-003 | P1 | G4 | ReasoningTrace（DM-012）无实现；golden reasoning 期望无执行器对照 | ReasoningEngine 按 ICD 5.8 产出 derivation+trace | ADR-004 / ICD 5.8 | 实现规则引擎最小版（RULE-001/002 传递闭包级），对照 Golden R001-R006 | V0.1+ |
| AG-004 | P1 | G4 | 断言状态迁移无审计记录（actor/timestamp/reason/policy_version） | 每次 transition 记录审计行（DM-005 §9.4） | ADR-003/004 / DM-005 §9.4 | assertion_transitions 审计表随 AG-002 一起设计 | V0.1 |
| AG-005 | P2 | G5 | agent 平面无 import 边界静态检查（当前代码未发现 SDK 直连，但无防回归机制） | CI lint 禁止 agent 模块 import neo4j/qdrant SDK/LLM SDK | ADR-008 | 增加 import-lint 测试（可纯 stdlib AST 实现） | V0.1+ |
| AG-006 | P2 | G5 | GitHub CI 仅跑单测矩阵；golden/production 门禁依赖本机环境（嵌入服务/318MB DB）未入 CI | 三门禁中可离线部分（骨架门/检索门/validator）入 CI | V&V §25 / LOCAL_AI_VMODEL_WORKFLOW | validator+golden 测试已在 CI（test_golden_dataset.py 11 项已入 pytest）；补检索门离线化或 CI artifact 传 DB | V0.2 |
| AG-007 | P1 | G1 | 需求编号双轨：SRS 用 SYS-EVD/SYS-AST/… 族式编号，RTM 用 SYS-001..020 顺序号，无映射表 | RTM 增加 SRS 族号 ↔ SYS-NNN 映射列 | SRS V1.1 §5 / RTM V1.0 §3 | RTM 增补映射表（文档级修订，架构负责人批准） | V0.1 前 |
| AG-008 | P1 | G1 | 不变量编号错位：SRS 列 9 条 INV（含历史完整性/Index 不丢失/LLM 不绕 Gate），任务书与 ADR 只引用 7 条且序号语义不一致（SRS INV-006=Index，ADR 引用的 INV-006=Agent 写权限=SRS INV-008） | 统一不变量注册表：INV-001..009，各文档引用同号 | SRS V1.1 §6 / ADR-001..010 / Golden schema | 建立不变量索引表，Golden/ADR/RTM 统一引用（文档级修订） | V0.1 前 |
| AG-009 | P2 | G1 | RTM 的 SYS-001/009/018/019/020 五条需求无 Golden case 覆盖（golden 覆盖 15/20 条 SYS） | 每条 P0/P1 需求至少映射一个验证工件（RTM §2 规则 1） | RTM V1.0 / V&V §24 | SYS-001(Source)/SYS-009(Ontology)/SYS-018(Golden 回归)/SYS-019(Schema)/SYS-020(Provider) 补验证用例或明确人工验证记录 | V0.2 |
| AG-010 | P2 | G3 | ICD 14 个接口仅 RetrievalEngine/AssertionStore 等少数有行为契约细节；多数接口缺 precondition/error/idempotency/timeout/transaction 字段 | 每接口补齐 12 项契约字段（任务书 AR-004 清单） | ICD V1.0 §5 | ICD V1.1 增补（架构负责人主导） | V0.2 |
| AG-011 | P2 | G6 | webui/API 服务无鉴权暴露（0.0.0.0+Tailscale）；Agent 写路径治理（INV-006/007）仅有文档无运行时强制 | 短期：网络边界文档化声明；长期：auth 中间件 + Agent 写路径 policy hook | ADR-008 / security 模块（已备未接线） | 依定位（B 团队工具）暂可接受，转入 V0.2 security gate | V0.2 |
| AG-012 | P3 | G5 | 性能度量无 P50/P95/P99/并发口径（现有为端到端均值：热查询 ~2s，向量检索毫秒级） | 建立分位数基准并冻结环境信息（V&V §5） | V&V §5/§22 | benchmark harness（Provider swap 时必须重测——ADR-009 已绑定） | V0.2+ |
| AG-013 | P3 | G1 | Data Model 无 Plan 对象（DM-001..018）；agent 任务书 AR-002 清单含 Plan | 明确 Plan 属 Goal-Decision 间派生对象或补 DM-019 | Data Model V1.0 | 架构负责人裁决：加对象或从清单除名（记录 ADR 级别说明即可） | V0.2 |
| AG-014 | P3 | G4 | Reasoner 版本字段（rule_version/reasoner_version）在 Golden schema 中缺失（ADR-004 要求 6 字段，schema 仅 3 字段） | golden schema derivation 块补 2 字段（optional→required 于运行时） | ADR-004 / golden schema | schema 升 V1.1（数据无破坏，ADDITIVE） | V0.2 |

## 统计

| Severity | 数量 | IDs |
|---|---|---|
| P0（阻断批准） | 0 | — |
| P1 | 6 | AG-001, AG-002, AG-003, AG-004, AG-007, AG-008 |
| P2 | 5 | AG-005, AG-006, AG-009, AG-010, AG-011 |
| P3 | 3 | AG-012, AG-013, AG-014 |

> 合计 14 项：P1 6 项 + P2 5 项 + P3 3 项。
> 无 P0——所有已知缺口均为"设计已定、实现未至"的预期 Implementation Gap，或文档级一致性问题，
> 不存在设计自相矛盾或不可恢复的架构缺陷。