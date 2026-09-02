# ADR-007: KB1 as Epistemic / Evidence Governance Reference

- Status: Accepted
- Date: 2026-09-01
- Decision Owners: Architecture Owner (Human Reviewer)
- Related Requirements: SYS-003, SYS-005, SYS-011, SYS-013, SYS-018
- Related Data Model: DM-003 Evidence, DM-004 SemanticUnit, DM-005 governance semantics; Domain Pack as source of domain constraints
- Related ICD: EvidenceStore (5.3), AssertionValidator (5.4), RetrievalEngine (5.7) evaluation semantics
- Related V&V: V&V Plan section 6 (test data strategy: Golden/Representative/Adversarial), 13.3 (ablation vs frozen baseline), 14 (sufficiency/abstain)
- Acceptance Reference: docs/architecture/reviews/ARCHITECTURE_ACCEPTANCE_V1.0.md (AR-V1.0 Gate: APPROVED, 2026-09-01)

## Context

KB1 (the incumbent system in this repository) has hardened, production-proven governance semantics: evidence-first compilation (evidence to facts to cards to projections), answer sufficiency judgement (sufficient/partial/insufficient with gap disclosure), retrieval evaluation gates (skeleton/retrieval/production health gates, 234-case lexical golden), negative-case testing, golden dataset discipline, and domain-pack-based terminology control. The Agentic KB (rebuild) starts fresh on the Canonical Data Model but must not lose these earned semantics.

## Problem

A rebuild ignoring KB1 re-derives governance lessons expensively (what counts as evidence, when to abstain, how to freeze baselines, why negative cases matter). Conversely, copying KB1 directory structure and code wholesale imports legacy layout decisions (SQLite-specific stores, phase-numbered pipelines) that the Canonical Data Model supersedes.

## Decision

1. KB1 is adopted as the Epistemic / Evidence Governance Reference: its SEMANTICS - not its code layout - are the normative source for AKB governance.
2. Reference semantics carried over:
   - Evidence to SourceUnit to knowledge compilation discipline (traceability chain);
   - Assertion Governance (status transitions with recorded actor/reason - mirrors DM-005 9.4);
   - Validation discipline (gates with independence principle: rulers independent of the measured object);
   - Golden discipline (frozen baselines, no silent expected-result edits, statistics auto-computed);
   - Retrieval Evaluation (frozen ablation baselines, backend-aware comparability);
   - Answer Contract (evidence citation, gap disclosure, abstain semantics - already test-enforced in KB1);
   - Domain Pack (terminology/alias/slot constraints as governable configuration).
3. NOT carried over: KB1 directory layout, phase pipeline organization, SQLite-specific store implementations, legacy workflow naming.
4. Convergence plan for overlapping capabilities:
   - KB1 Graph (graph_edges): converges into AKB SemanticGraph projection (ADR-002) once assertions land; skeleton-import edges re-expressed as assertion projections;
   - KB1 Storage (SQLiteKnowledgeStore): converges into AKB Canonical Store behind AssertionStore/EvidenceStore interfaces; current tables remain as compilation-input sources until the V0.1 evidence core replaces them;
   - Retrieval gates: run against AKB RetrievalEngine via ICD contract; the three health gates become acceptance tools rather than KB1-internal scripts.
5. KB1 existing directories are NOT copied as-is into the new system.

## Alternatives Considered

- A. Greenfield with no KB1 reference: rejected - discards proven governance semantics and the measurement baselines grounding V&V 13.3/14.
- B. Fork KB1 entirely and rename: rejected - carries forward legacy structure contradicting the Canonical Data Model; the rebuild exists precisely to escape this.
- C. Keep both systems running in parallel indefinitely: rejected - dual maintenance without a convergence plan guarantees drift; this ADR pins the convergence targets.

## Rationale

KB1 governance semantics have been validated by real usage (234-case golden, production health gates, backend-ablation lessons). They map cleanly onto AKB ICD contracts. The cost asymmetry is decisive: adopting semantics is cheap and preserves institutional knowledge; re-deriving them is expensive and error-prone.

## Consequences

- AKB documentation and tests inherit KB1 vocabulary (sufficiency levels, gate names, invariant numbering) - reducing review friction.
- KB1 remains runnable during transition; its gates act as regression witnesses until AKB equivalents pass.
- Convergence items appear in V0.1+ backlogs with explicit completion criteria (assertion_ref migration, rebuild tooling).

## Rejected Alternatives

See Alternatives Considered.

## Verification Impact

V&V 14 scenarios correspond 1:1 to KB1 answer-contract tests (already passing); AKB re-expresses them as contract tests C-ANS-*. Golden negative cases mirror KB1 negative-case discipline (G030 directly encodes them). Retrieval baselines: AKB retrieval verification compares against KB1-frozen ablation data (retrieval gate doc sections 9-12).

## Change Impact

Documentation-level now; convergence engineering lands incrementally with V0.1 Evidence Core. KB1 code stays untouched until its replacement passes the same gates (no big-bang cutover).

## References

- SRS V1.1: docs/requirements/SRS/Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html
- Data Model V1.0: docs/architecture/data-model/Agentic_Knowledge_Base_Data_Model_V1.0.md
- ICD V1.0: docs/architecture/interfaces/Agentic_Knowledge_Base_ICD_V1.0.md
- V&V Plan V1.0: docs/verification/Agentic_Knowledge_Base_VV_Plan_V1.0.md
- RTM V1.0: docs/verification/REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md
- Golden Dataset V1.0: docs/verification/golden/GOLDEN_DATASET_V1.0_REPORT.md
- Workflow: docs/development/LOCAL_AI_VMODEL_WORKFLOW.md
