# V0.2 Semantic Compilation — Detailed Design Package

> Document Set: AKB-DD-V02 · Status: **READY FOR IMPLEMENTATION**（设计冻结基线，待架构评审确认）
> 前置：V0.1 Evidence Core ACCEPTED（base fc65370）
> 生产代码状态：**Not Changed**（本包纯设计；实现由后续任务按本包执行）
> 红线：V0.1 Governance Boundary 优先于实现便利

## 文件清单

| 文件 | 内容 |
|---|---|
| V0.2_SEMANTIC_COMPILATION_DETAILED_DESIGN.md | 考察结论/数据流红线/数据模型变化/文档索引 |
| V0.2_DATA_FLOW.md | 端到端对象流 + 层间契约 + V0.1 接缝 |
| V0.2_COMPILATION_PIPELINE.md | 8 层五要素规格 |
| V0.2_NORMALIZATION_SPEC.md | N-01..N-08 规则集 |
| V0.2_ENTITY_RELATION_EXTRACTION_SPEC.md | Entity/Relation candidate + R-01..R-06 |
| V0.2_TEMPORAL_SEMANTICS_SPEC.md | 五类时间 T-01..T-06 |
| V0.2_ONTOLOGY_MAPPING_SPEC.md | O-01..O-06 三段式 |
| V0.2_DETERMINISM_SPEC.md | 两级确定性 + 幂等 fingerprint |
| V0.2_ERROR_MODEL.md | 错误码族 + 失败不越界 |
| V0.2_INTERFACE_BEHAVIOR.md | 9 接口契约 + provider 边界 |
| V0.2_VERIFICATION_SPEC.md | CMP-001..019（19 verification cases）+ Golden 40 案例计划 |
| V0.2_MIGRATION_PLAN.md | migration 12 设计（只设计不执行） |
| V0.2_DESIGN_CONSISTENCY_MATRIX.md | 16 主题一致性矩阵（含 Repair A/B/C 四新行） |
| V0.2_SEMANTIC_COMPILATION_REVIEW_V1.0.md → reviews/ | 架构评审记录 |

## 设计关键决定

1. 归属 `evidence_core.compilation` 子包——复用连接/迁移/治理设施，**不建第二套管线**；
2. `akb_semantic_units` 加 4 列（provenance_ref/compiler_run_ref/configuration_hash/content_fingerprint）+
   新表 `akb_compilation_runs`——均有任务书条款级论证，V0.1 表零改动；
3. 默认 provider = BuiltinRuleExtractor（strict deterministic，R-01..R-06 从 facts.py 经验泛化移植）；
4. 幂等 = content_fingerprint UNIQUE 约束（数据层锚点）+ compiler 层幂等返回；
5. quarantine 队列处理 unknown ontology（不静默丢弃，治理复核入口）；
6. KB1 检索编译链保持不动（并行双链路裁决，合并留给 V0.3+）。