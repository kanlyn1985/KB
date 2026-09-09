# AKB-P0-ADR-001 — Architecture Decision Records Task

- Task ID: AKB-P0-ADR-001
- Branch: `rebuild/agent-kb-core`
- Status: Implementation Task Specification
- Inputs: SRS V1.1 / Data Model V1.0 / ICD V1.0 / V&V V1.0 / RTM V1.0 / Golden Dataset V1.0

## Objective
建立 Agentic Knowledge Base V1.0 架构决策记录（ADR）并对当前 Golden Dataset 报告中的 negative coverage 统计口径进行一致化修正。

## ADRs to establish
- ADR-001: `KnowledgeAssertion` is the Canonical Knowledge Unit.
- ADR-002: Graph is a projection of Canonical Assertions, not the source of truth.
- ADR-003: Asserted/Validated Knowledge requires valid Evidence.
- ADR-004: Asserted Knowledge and Derived Knowledge are distinct epistemic types.
- ADR-005: Canonical Store and derived projections are separated; projections are rebuildable.
- ADR-006: Semantica is an implementation candidate/foundation for Semantic Runtime capabilities, subject to interface/data-model compatibility.
- ADR-007: KB1 evidence/provenance/governance/evaluation semantics are the reference basis for the Epistemic Layer.
- ADR-008: Agent Runtime is decoupled from Semantic Runtime.
- ADR-009: Provider-neutral interfaces are mandatory for replaceable Graph/Vector/Parser/Reasoner/Connector implementations.
- ADR-010: Development uses V-Model + incremental local-AI implementation with GitHub as the coordination/audit layer.

## Required ADR content
Each ADR must contain:
1. Context
2. Decision
3. Rationale
4. Alternatives considered
5. Consequences
6. Requirements/Data Model/ICD/V&V references
7. Status

## Golden Dataset correction
The current Golden report/manifest has inconsistent negative-case counts. Fix this without changing the 30 cases or architectural baselines.

Required fields:
- `negative_case_count`: number of cases containing `negative_expectations`
- `negative_expectation_count`: total number of negative expectation entries

The report and manifest must use the same values and terminology. Add/update automated tests for this consistency.

## Constraints
- Do not modify SRS/Data Model/ICD/V&V semantics.
- Do not introduce production implementation for Reasoning/Agent Runtime.
- Do not delete or weaken existing tests.
- Keep changes limited to ADR documents and Golden Dataset reporting/validation consistency.

## Verification
Required:
- Golden validator PASS
- Full existing test suite PASS
- New ADR/document consistency test where appropriate

## Completion Evidence
Return:
- changed files
- validation commands
- test commands/results
- architecture issues discovered
- commit SHA
