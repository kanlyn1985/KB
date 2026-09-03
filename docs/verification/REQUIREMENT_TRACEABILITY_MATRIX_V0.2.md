# Requirement Traceability Matrix — V0.2 Semantic Compilation

> AKB-RTM-V02-001 · 基线：V0.1 RTM V1.0（§2a 映射）+ SRS V1.1 · 状态：设计冻结
> 双向追踪：SRS ↓ V0.2 需求 ↓ Detailed Design ↓ Interface ↓ Implementation(待) ↓ Verification；
> 反向：CMP-xxx ↑ Verification ↑ V0.2 需求 ↑ SRS。

| V0.2 Req | SRS 源 | 需求 | Design Ref | Interface Ref | Verification |
|---|---|---|---|---|---|
| V02-REQ-001 | SYS-EVD-001/SYS-SEM-001 | Evidence 可编译为可审计 SemanticUnit（N-01..08 规范化，五类候选） | DATA_FLOW §1, PIPELINE L1-L2, NORM SPEC | SemanticNormalizer | CMP-001 |
| V02-REQ-002 | SYS-AST-001/SYS-GRAPH-001 | SemanticUnit 可构建 Candidate Assertion（唯一入口 create_candidate） | PIPELINE L8, DATA_FLOW §4 | CandidateAssertionBuilder | CMP-002 |
| V02-REQ-003 | SYS-OBS-001 | 同 fingerprint 重复编译幂等（零重复产物） | DETERMINISM §idempotency | SemanticCompiler | CMP-003 |
| V02-REQ-004 | SYS-RET-001 | 不同 compiler version 产物可区分（fingerprint 组成） | DETERMINISM D-07 | SemanticCompiler | CMP-004 |
| V02-REQ-005 | INV-005 | 编译不修改 Evidence（immutable 保持） | DATA_FLOW §3 | 全接口 | CMP-005 |
| V02-REQ-006 | INV-001/002 | Candidate 不自动 validated；治理在 V0.1 | DATA_FLOW §4 | AssertionStore(既有) | CMP-006 |
| V02-REQ-007 | INV-002 | inferred 必带 derivation（rule_ref/parents/reasoner） | PIPELINE L8 | CandidateAssertionBuilder | CMP-007 |
| V02-REQ-008 | SYS-SEM-001 | Ontology mapping 默认 candidate，治理才 authoritative | ONTOLOGY SPEC | OntologyMapper | CMP-008 |
| V02-REQ-009 | SYS-AST-002/INV-004 | Compilation provenance 八问可回答 | DATA_FLOW §4, INTERFACE §7-8 | SemanticCompiler/Provenance | CMP-009 |
| V02-REQ-010 | SYS-020（RTM）/ADR-009 | Provider 中性：provider 可换，Canonical 不泄漏 | INTERFACE §1, PIPELINE L3 | SemanticCompilerProvider | CMP-010 |
| V02-REQ-011 | SYS-REASON-001 | strict deterministic 级可复现（排除审计字段） | DETERMINISM 全文 | 全接口 | CMP-011 |
| V02-REQ-012 | SYS-CTX-001 | Failure isolation（段级/run 级隔离，失败不越界） | ERROR MODEL | SemanticCompiler | CMP-012 |
| V02-REQ-013 | SYS-AGENT-001 | malformed provider 输出拒绝（schema validation） | INTERFACE §1 | provider 边界 | CMP-013 |
| V02-REQ-014 | SYS-SEM-001 | unknown ontology → quarantine（不静默丢弃） | ONTOLOGY O-04 | OntologyMapper | CMP-014 |
| V02-REQ-015 | SYS-018（RTM） | Golden semantic compilation regression（40 案例集） | VERIFICATION §golden | SemanticCompiler | CMP-015 |