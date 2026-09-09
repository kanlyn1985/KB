# Requirement Traceability Matrix — V0.3

> AKB-RTM-V03-001 · 基线：V0.2 RTM + SRS V0.3（20 需求）· 状态：Design Baseline
> 双向：SRS→REQ→Design→Interface→Impl(待)→Verification；反向 CMP→REQ。零孤立。

| REQ | 需求 | Design Ref | Interface | Invariant | Verification | Acceptance Criterion |
|---|---|---|---|---|---|---|
| V03-REQ-001 | Set 创建 | SET_SPEC/PIPELINE 1-2 | EvidenceSetManager | INV-001/005 | CMP-001/003/004 | 治理 Evidence 全可建 Set |
| V03-REQ-002 | Set 身份 | SET_SPEC/DETERMINISM D-09 | EvidenceSetManager | INV-004 | CMP-001/002/003 | 同成员同指纹；变化必新 |
| V03-REQ-003 | 基数 1..32 | SET_SPEC | EvidenceSetManager | — | CMP-004/022 | 边界全拒绝合法 |
| V03-REQ-004 | 兼容性五级 | ALIGNMENT_SPEC | AlignmentEngine | — | CMP-010 | 规则表全命中可审计 |
| V03-REQ-005 | 实体对齐 | ALIGNMENT_SPEC | AlignmentEngine | INV-004 | CMP-005 | 簇稳定编号 |
| V03-REQ-006 | 关系对齐 | ALIGNMENT_SPEC | AlignmentEngine | — | CMP-006 | 无孤儿 |
| V03-REQ-007 | 事件对齐 | TEMPORAL_SPEC | AlignmentEngine | — | CMP-007 | 缺时不猜测 |
| V03-REQ-008 | 状态对齐 | ALIGNMENT_SPEC | AlignmentEngine | — | CMP-008 | 矛盾转冲突 |
| V03-REQ-009 | 时间六态 | TEMPORAL_SPEC | AlignmentEngine | V0.2 T 系 | CMP-009 | 零时钟语义 |
| V03-REQ-010 | 冲突检测 7 类 | CONFLICT_SPEC | ConflictDetector | INV-002 | CMP-011..014 | 零静默丢弃 |
| V03-REQ-011 | 源权重 | SOURCE_WEIGHT_SPEC | SourceWeightResolver | — | CMP-013/018 | weight≠adjudication |
| V03-REQ-012 | 候选合成 | CANDIDATE_SPEC/PIPELINE 11 | SynthesisEngine | INV-002/004 | CMP-015/024 | evidence_refs=全成员 |
| V03-REQ-013 | candidate-only | CANDIDATE_SPEC | SynthesisEngine | INV-001/002/007/009 | CMP-016/024 | 恒 candidate |
| V03-REQ-014 | 全成员溯源 | PROVENANCE_SPEC | ProvenanceStore | INV-004 | CMP-017 | 缺一 P0 |
| V03-REQ-015 | 确定性 | DETERMINISM_SPEC | 全接口 | — | CMP-018/002 | 双跑全等 |
| V03-REQ-016 | provider 可溯 | ICD §8 | SynthesisEngine | INV-007 | CMP-021 | 无裁决面 |
| V03-REQ-017 | 幂等 | IDEMPOTENCY_SPEC | SynthesisEngine | — | CMP-019 | 锚语义五条 |
| V03-REQ-018 | 失败隔离 | ERROR_MODEL | 全接口 | INV-002 | CMP-020 | 三级隔离零半成品 |
| V03-REQ-019 | 合成 provenance | PROVENANCE_SPEC | ProvenanceStore | INV-004 | CMP-017/025 | 五级链+确定性 |
| V03-REQ-020 | 向后兼容 | 全部 | — | 全部 | CMP-023 | V0.1/V0.2 全 PASS |