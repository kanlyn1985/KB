# Agentic Knowledge Base — V0.3 SRS V1.0（Multi-Evidence Semantic Synthesis Core）

- Document ID: AKB-SRS-V03-001 · Status: Design Baseline（DESIGN READY 待架构评审确认）
- 上游基线：V0.1 ACCEPTED（INV-001..010 不变量 registry）· V0.2 ACCEPTED — RELEASE BASELINE（310f345）
- 声明：本文档为需求规格，不含实现；V0.3 不削弱 INV-001..010 任何一条。

## 1. 系统上下文

V0.2 已交付单证据编译链（Evidence → SemanticUnit → Candidate Assertion，single-evidence 契约）。
V0.3 在其上新增**多证据合成**：把一个受治理的 Evidence Set（≥1 条 Evidence）经对齐/整合/
冲突检测，产出一组带完整 provenance 的 Candidate KnowledgeAssertion。
V0.3 不做知识裁决（治理仍在 V0.1 状态机），不做推理引擎（V0.4+）。

## 2. 需求条目（20 条）

每条格式：rationale / inputs / outputs / invariants / failure behavior / traceability /
verification method / V0.2 dependencies。

### V03-REQ-001 Evidence Set Creation
- rationale：多证据合成的输入必须是被治理的集合对象，而非散列 ID；
- inputs：evidence_id 列表（去重后）+ actor_id + 配置；
- outputs：EvidenceSet 对象（set_id + 成员清单 + fingerprint）；
- invariants：INV-001（成员必须是已治理 Evidence）、INV-005（成员引用不可变）；
- failure：任一 evidence_id 不存在 → E-V03-SET-MEMBER-NOT-FOUND，Set 不创建；
- traceability：AKB-SRS-V02-001 SYS-EVD-001 → 本条 → V0.3-MIG（set 表）；
- verification：V03-CMP-001/003/004；
- V0.2 依赖：EvidenceStore 读取面、akb_evidence 主键。

### V03-REQ-002 Evidence Set Identity
- rationale：同一 Set 的重复合成必须可识别（幂等锚）；
- inputs：成员 evidence_id 清单 + synthesis_version + configuration_hash；
- outputs：SynthesisFingerprint（CanonicalJSON 规则，V0.2 同款 dumps 约定）；
- invariants：INV-004（身份可溯源到成员清单）；
- failure：成员清单为空 → E-V03-SET-EMPTY；
- traceability：→ V0.3_IDEMPOTENCY_SPEC；
- verification：V03-CMP-001/002/003；
- V0.2 依赖：canonical_json、fingerprint 构造先例（fingerprint_spec=v1 延续）。

### V03-REQ-003 Evidence Set Cardinality
- rationale：V0.3 合成的合法输入基数；
- inputs：成员数；
- outputs：接受（1..MAX_SET_SIZE，默认 MAX=32）/拒绝；
- invariants：成员去重（重复成员 → 拒绝创建，E-V03-SET-DUPLICATE-MEMBER）；
- failure：超上限 → E-V03-SET-OVERSIZE；空 → E-V03-SET-EMPTY；
- traceability：→ ICD EvidenceSetManager；
- verification：V03-CMP-004/022；
- V0.2 依赖：无（纯集合约束）。

### V03-REQ-004 Evidence Compatibility Analysis
- rationale：合成前必须先判定证据间是否可比；
- inputs：各成员的 SemanticUnit（经 V0.2 编译产物）；
- outputs：五级兼容性分类 {COMPATIBLE, PARTIALLY_COMPATIBLE, CONFLICTING, INCOMPARABLE, INVALID}
  + 判定依据记录；
- invariants：判定规则 deterministic（规则表驱动，禁止模糊语义相似度单独裁决）；
- failure：成员缺失 SemanticUnit → 该成员标 INVALID（不阻断其他成员分析）；
- traceability：→ V0.3_ALIGNMENT_SPEC §compatibility；
- verification：V03-CMP-010；
- V0.2 依赖：akb_semantic_units（V0.2 编译产物为唯一语义输入）。

### V03-REQ-005 Entity Alignment
- rationale：跨证据同一实体的表面形/归一形不同必须对齐；
- inputs：各成员 EntityCandidate 集合；
- outputs：EntityAlignmentCluster 列表（cluster_id + 成员映射）；
- invariants：对齐是候选级（不写 authoritative entity）；排序稳定；
- failure：无对齐价值（单成员）→ 空聚类（合法）；
- traceability：→ ALIGNMENT_SPEC；
- verification：V03-CMP-005；
- V0.2 依赖：EntityCandidate.normalized_form/ontology_hint。

### V03-REQ-006 Relation Alignment
- rationale：同一（subj,predicate,obj) 关系的多证据表达须对齐；
- inputs：EntityAlignmentCluster + RelationCandidate 集合；
- outputs：RelationAlignmentCluster 列表；
- invariants：subject/object 经 entity cluster 解析后对齐；
- failure：孤儿 relation → 丢弃 + warning；
- traceability：→ ALIGNMENT_SPEC；
- verification：V03-CMP-006；
- V0.2 依赖：RelationCandidate。

### V03-REQ-007 Event Alignment
- rationale：同一事件的多证据记述须对齐（event_time + 参与实体）；
- inputs：TemporalParse.event_time + entity clusters；
- outputs：EventAlignmentCluster；
- invariants：event_time 缺失成员不参与 event 对齐（不猜测）；
- failure：时间无法解析 → 未对齐事件（合法输出）；
- traceability：→ TEMPORAL_SYNTHESIS_SPEC；
- verification：V03-CMP-007；
- V0.2 依赖：TemporalParse（V0.2 五类时间分离产物）。

### V03-REQ-008 State Alignment
- rationale：同一状态（实体在时间点的属性态）对齐；
- inputs：entity clusters + state 类 relation（predicate 语义）+ valid_time；
- outputs：StateAlignmentCluster；
- invariants：状态对齐不得跨越 contradictory validity（转 CONFLICTING）；
- failure：无状态语义 → 空；
- traceability：→ ALIGNMENT_SPEC；
- verification：V03-CMP-008；
- V0.2 依赖：RelationCandidate.predicate_candidate。

### V03-REQ-009 Temporal Alignment
- rationale：多证据时间区间对齐（same/overlap/sequential/contradictory/missing/unresolved 六态）；
- inputs：各成员 TemporalParse；
- outputs：TemporalAlignment（每对/每簇时间关系分类）；
- invariants：五类时间不合并（继承 V0.2）；锚定不用当前时钟；
- failure：成员时间全缺 → temporal_alignment=missing（合法）；
- traceability：→ TEMPORAL_SYNTHESIS_SPEC；
- verification：V03-CMP-009；
- V0.2 依赖：TemporalParse/T-01..T-06。

### V03-REQ-010 Conflict Detection
- rationale：合成前必须显式识别冲突——冲突不能被静默丢弃；
- inputs：对齐产物 + 原始候选值；
- outputs：ConflictSet（7 类分类 + 全溯源字段）；
- invariants：INV-002（冲突候选绝不直接晋升）；任何成员分歧必留记录；
- failure：冲突爆炸（>MAX_CONFLICTS 默认 128）→ run 级暂停转人工（不静默降级）；
- traceability：→ CONFLICT_SPEC；
- verification：V03-CMP-011..014；
- V0.2 依赖：无（新增分类逻辑）。

### V03-REQ-011 Source Weighting
- rationale：多证据下需要可审计的来源权重影响候选排序/置信度；
- inputs：成员 Evidence 的 source 元数据 + 配置权重策略；
- outputs：SourceWeight 记录（逐成员，维度分解）；
- invariants：**weight ≠ adjudication**——权重只影响 candidate 排序/置信度合成，
  绝不产生 validated/asserted；维度与公式版本化（weight_policy=v1）；
- failure：权重策略缺失 → 默认 uniform（可追溯）；
- traceability：→ SOURCE_WEIGHT_SPEC；
- verification：V03-CMP-013/018；
- V0.2 依赖：akb_sources 元数据。

### V03-REQ-012 Candidate Synthesis
- rationale：V0.3 的核心产出——基于对齐+冲突结果的候选断言合成；
- inputs：对齐簇 + ConflictSet + SourceWeight；
- outputs：SynthesisCandidate → 经唯一边界 create_candidate() 落为
  KnowledgeAssertion(status=candidate)；
- invariants：INV-002/007；CONFLICTING 簇产出的候选必须携带 conflict_ref（供治理复核），
  治理前不得自动晋升；synthesis 产物的 evidence_refs=**全部成员** evidence_id；
- failure：任一阶段失败按 ERROR_MODEL 隔离，零半成品 authoritative 写入；
- traceability：→ CANDIDATE_SYNTHESIS_SPEC；
- verification：V03-CMP-015/016/024；
- V0.2 依赖：AssertionStore.create_candidate（唯一边界——V0.3 不得新增第二条）。

### V03-REQ-013 Candidate-only Boundary
- rationale：合成产物绝不允许 validated/asserted；
- inputs：synthesis 管线全部输出路径；
- outputs：恒 status=candidate；
- invariants：INV-001/002/007/009；治理跃迁只能走 V0.1 transition；
- failure：任何试图直写 authoritative 的路径 = 设计红线（触发器兜底）；
- traceability：→ V0.1 INVARIANT_REGISTRY；
- verification：V03-CMP-016/024；
- V0.2 依赖：状态机/triggers 原样。

### V03-REQ-014 Evidence Traceability
- rationale：每个合成候选必须可溯源到全部参与 Evidence（INV-004 强化）；
- inputs：synthesis 产物；
- outputs：assertion.evidence_refs=全成员 + provenance(activity=synthesize)；
- invariants：缺任一成员溯源即 P0；
- failure：provenance 写失败 → run failed 回滚；
- traceability：→ PROVENANCE_SPEC；
- verification：V03-CMP-017/025；
- V0.2 依赖：Provenance/assertion.evidence_refs。

### V03-REQ-015 Determinism
- rationale：同 Set + 同版本 + 同配置 → 同结果（V0.2 两级确定性延续）；
- inputs：全部语义输入；
- outputs：deterministic 产物（builtin provider）；
- invariants：成员排序 canonical（按 evidence_id 字典序），禁止 set/dict 迭代序影响输出；
- failure：不可复现 → E-V03-SYNTH-NONDETERMINISTIC（debug 重放校验）；
- traceability：→ DETERMINISM_SPEC；
- verification：V03-CMP-018/002；
- V0.2 依赖：canonical_json/排序约定。

### V03-REQ-016 Provider Traceability
- rationale：LLM/外部 provider 参与时输出可追溯不必逐字节可复现；
- inputs：provider 元数据（id/version/参数/seed）；
- outputs：run 内完整记录；stochastic 输出标记 traceable；
- invariants：INV-007（provider 不裁决）；provider 只能产候选级对齐建议；
- failure：provider 异常 → 该成员输出弃用 + warning（不污染其他成员）；
- traceability：→ ICD SynthesisEngine provider 边界；
- verification：V03-CMP-021；
- V0.2 依赖：SemanticCompilerProvider 先例。

### V03-REQ-017 Idempotency
- rationale：重复合成不得无限增殖 run/candidate；
- inputs：SynthesisFingerprint；
- outputs：命中 → 返回既有 run 全产物（E-V03-SYNTH-DUPLICATE 语义=幂等返回）；
- invariants：持久化锚显式（锚 SynthesisRun 行持 fingerprint，关联经 synthesis_run_ref）；
- failure：锚缺失 → E-V03-SYNTH-PROVENANCE-MISSING；
- traceability：→ IDEMPOTENCY_SPEC；
- verification：V03-CMP-019/001；
- V0.2 依赖：V0.2 幂等先例（锚+关联模式）。

### V03-REQ-018 Failure Isolation
- rationale：任何失败不得产生半成品 authoritative 输出；
- inputs：全部错误路径；
- outputs：按错误模型隔离（成员级/簇级/run 级三级）；
- invariants：INV-002；冲突爆炸不静默降级；
- failure：→ E-V03-* 分类；
- traceability：→ ERROR_MODEL；
- verification：V03-CMP-020；
- V0.2 依赖：SAVEPOINT 事务先例。

### V03-REQ-019 Synthesis Provenance
- rationale：合成五级链 Candidate → SynthesisRun → EvidenceSet → Evidence[] → Document[] 全可溯；
- inputs：synthesis 产物；
- outputs：describe_synthesis_run/trace_candidate_synthesis 查询面；
- invariants：INV-004；provenance(activity=synthesize) 完整；
- failure：缺链 → E-V03-SYNTH-PROVENANCE-MISSING（P0）；
- traceability：→ PROVENANCE_SPEC；
- verification：V03-CMP-017/025；
- V0.2 依赖：Provenance/CompilationRun 先例。

### V03-REQ-020 Backward Compatibility
- rationale：V0.3 只扩展不改变；
- inputs：V0.1/V0.2 全部测试面；
- outputs：回归 PASS；
- invariants：V0.1 ACCEPTED / V0.2 ACCEPTED — RELEASE BASELINE 语义零变化；
  V0.2 single-evidence compile 行为不变（V0.3 synthesis 是**新增入口**，不改 V0.2 compile）；
- failure：任一 V0.1/V0.2 测试回归 = REJECT；
- traceability：→ REGRESSION 计划；
- verification：V03-CMP-023；
- V0.2 依赖：全部。

## 3. Canonical Concepts 分类（§7）

| 概念 | 分类 | 论证 |
|---|---|---|
| EvidenceSet | canonical persisted | 需要身份+成员清单持久化（幂等锚载体） |
| SynthesisRun | canonical persisted | run 级审计聚合（V0.2 CompilationRun 先例） |
| EvidenceMembership | canonical（Set 的成员清单，存于 set 行 JSON） | 不单独建表——1:N 嵌入 Set 行 |
| SemanticAlignment | derived runtime | 对齐簇是计算中间物，随 run 留 JSON 快照 |
| ConflictSet | canonical（随 run 留存 JSON + 逐冲突行可选） | 冲突是治理复核的一级对象 |
| SynthesisCandidate | derived（经 create_candidate 后即 KnowledgeAssertion） | 无独立持久化 |
| SynthesisProvenance | projection（复用 akb_provenance activity=synthesize） | 不新建 provenance 机制 |
| SourceWeight | derived（随 run 留 JSON，策略版本化） | 不单独建表 |