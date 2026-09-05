# V0.3 Multi-Evidence Semantic Synthesis — Detailed Design Package

> Document Set: AKB-DD-V03 · Status: **DESIGN READY FOR IMPLEMENTATION**（待架构评审确认）
> 上游：V0.2 RELEASE BASELINE（310f345）· V0.1 ACCEPTED（INV-001..010 不变）
> 生产代码状态：**Not Changed**（纯设计包；实现由后续任务执行）
> 铁律：V0.3 只扩展不改变 V0.1/V0.2 语义；create_candidate 仍是唯一候选边界

## 文件清单

| 文件 | 内容 |
|---|---|
| V0.3_MULTI_EVIDENCE_DETAILED_DESIGN.md | 主详设：考察/红线/决定 |
| V0.3_DATA_MODEL.md | 数据模型（新表/列/论证） |
| V0.3_DATA_FLOW.md | 端到端数据流 |
| V0.3_PIPELINE.md | 11 阶段管线五要素 |
| V0.3_EVIDENCE_SET_SPEC.md | Set 身份/基数/指纹 |
| V0.3_ALIGNMENT_SPEC.md | 五级兼容性 + 四类对齐 |
| V0.3_CONFLICT_SPEC.md | 7 类冲突模型 |
| V0.3_TEMPORAL_SYNTHESIS_SPEC.md | 六态时间对齐 |
| V0.3_SOURCE_WEIGHT_SPEC.md | 权重（weight≠adjudication） |
| V0.3_CANDIDATE_SYNTHESIS_SPEC.md | 合成规则 + 唯一边界 |
| V0.3_PROVENANCE_SPEC.md | 五级链 |
| V0.3_DETERMINISM_SPEC.md | 两级确定性 + 成员 canonical 序 |
| V0.3_IDEMPOTENCY_SPEC.md | SynthesisFingerprint + 持久化锚 |
| V0.3_ERROR_MODEL.md | 错误分类 + 三级隔离 |
| V0.3_INTERFACE_BEHAVIOR.md | 7 接口契约 |
| V0.3_MIGRATION_PLAN.md | migration 13 设计（只设计） |
| V0.3_VERIFICATION_SPEC.md | V03-CMP-001..025 |
| V0.3_DESIGN_CONSISTENCY_MATRIX.md | 一致性矩阵 |

外部关联文档：
- SRS：docs/requirements/V0.3/Agentic_Knowledge_Base_V0.3_SRS_V1.0.md（20 需求）
- ICD：docs/architecture/interfaces/V0.3_Multi_Evidence_Synthesis_ICD_V1.0.md（7 接口）
- 验证设计：docs/verification/V0.3/（plan/golden plan/RTM/trace matrix）
- 评审：docs/architecture/reviews/V0.3_ARCHITECTURE_REVIEW_V1.0.md

## 设计关键决定

1. **位置**：`evidence_core/synthesis/` 子包（与 compilation 平级）——复用连接/迁移/治理/AssertionStore；
2. **EvidenceSet 与 SynthesisRun 双 canonical 表**（akb_evidence_sets / akb_synthesis_runs）——
   Set 是幂等锚载体（可跨 run 复用），Run 是每次合成聚合审计体；成员清单嵌入行 JSON（不建 link 表）；
3. **对齐/冲突/权重为 derived runtime**（随 run 留 JSON 快照），SynthesisCandidate 无独立持久化
   （经 create_candidate 后即 KnowledgeAssertion）；
4. **成员序 canonical**：evidence_id 字典序——Set 身份对 [A,B]==[B,A] 不敏感（V03-CMP-002）；
5. **兼容性五级规则表驱动**：禁止模糊语义相似度单独裁决；冲突 7 类全溯源字段；
6. **weight ≠ adjudication**：权重只影响排序/置信度合成；
7. **create_candidate 唯一边界不变**：SynthesisEngine 是第二个调用方，但不是第二条写入路径
   （仍走 V0.1 状态机/triggers/INV-001..010）；
8. **V0.2 compile 零改动**：synthesis 消费 V0.2 产物，缺 SemanticUnit 报错不静默补编译。