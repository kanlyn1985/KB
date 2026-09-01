# ADR-010: V-Model + Local-AI Development Workflow with GitHub as Coordination Layer

- Status: Proposed
- Date: 2026-09-01
- Decision Owners: Architecture Owner (Human Reviewer)
- Related Requirements: SYS-018, SYS-019
- Related Data Model: Process decision - no direct DM mapping; touches all DM objects via change control
- Related ICD: Process decision - all ICD interfaces are governed by this workflow change classification
- Related V&V: V&V Plan section 2.1 (dual V-model), 23 (regression strategy), 25 (release gates); RTM section 2 (traceability rules); AKB-DEV-001 workflow doc

## Context

AKB is developed by an architecture owner (human) plus local AI executors. The workflow doc (AKB-DEV-001) defines roles, the V-model increment loop, and GitHub as the single coordination/audit layer. The first two increments (Golden Dataset AKB-P0-GOLDEN-001, this ADR task) validated the loop in practice: task spec on GitHub, local AI pulls, implements, tests, commits evidence, architecture review. The Golden Dataset statistics divergence (negative_case_count 11 vs 12) was caught and fixed through this loop audit mechanisms - evidence the process self-corrects.

## Problem

Ad-hoc AI-assisted development fails in predictable ways: requirements drift into chat history (unauditable), AI-generated code arrives without requirement traceability, tests get fixed to pass, and baselines mutate silently. Without a frozen process, the architecture review required before V0.1 has no stable artifact to review.

## Decision

1. Freeze the development workflow per AKB-DEV-001: Design -> GitHub -> Local AI -> Implementation -> Tests -> Commit (evidence) -> Architecture Review.
2. Role split is normative:
   - Architecture side: requirements, architecture, data model, ICD, acceptance criteria, review/approval;
   - Local AI: implementation, tests, evidence reports, within task scope only - never altering requirement baselines;
   - GitHub: the single coordination/audit medium - chat is not a task source.
3. V-model increments: every increment follows Requirement -> Design -> Task -> Implementation -> Unit/Contract Test -> Integration Test -> Evidence Report -> Review -> Accept/Reject. Code-first-requirements-later is forbidden.
4. Change classification per AKB-DEV-001 section 7: P0/P1 requirement changes require SRS+RTM updates with CR/ADR; canonical model changes require Data Model+ICD+tests; implementation refactors must not change external contracts.
5. Baselines are frozen artifacts: expected results (Golden), thresholds (gates), and interface contracts change only through versioned reviewed updates - never silently.

## Alternatives Considered

- A. Pure chat-driven development: rejected - unauditable, and already proven lossy (long AI session compaction loses task context; GitHub survives).
- B. Full enterprise ALM tooling (Jira plus formal CM): rejected - disproportionate for a single-architect project; GitHub issues/PRs/commits provide the same audit trail at zero cost.
- C. Let each AI session define its own process: rejected - non-reproducible; evidence quality varied visibly between early sessions before this workflow was written down.

## Rationale

Two completed increments (GOLDEN-001, ADR-001) demonstrate the loop produces reviewable evidence: commit SHAs with scoped changes, validation output in mandated format, honest failure reporting (the Golden report known-limitations section, the negative_case_count divergence itself). The workflow converts AI speed into governed progress instead of ungoverned volume.

## Consequences

- Every future task must be a GitHub-anchored spec with acceptance criteria before implementation starts.
- AI executors must refuse out-of-scope changes (STOP-CHANGE protocol) and record conflicts - as exercised in GOLDEN-001 architecture-conflicts section.
- Architecture review becomes the bottleneck by design; this is accepted as the cost of correctness.

## Rejected Alternatives

See Alternatives Considered.

## Verification Impact

Process verification is inherent: every task returns TASK/STATUS/CHANGED FILES/VALIDATION/TESTS/COMMIT in the mandated format (GOLDEN-001 set the precedent). RTM section 2 rule 5: no release-candidate change without requirement/design/defect traceability - enforced at review. Gate compliance: V&V 25 gates G-01..G-12 map onto workflow stages.

## Change Impact

No code impact; future task specs reference this ADR for role boundaries. ADR status transitions (Proposed to Accepted) themselves follow this workflow.

## References

- SRS V1.1: docs/requirements/SRS/Agentic_Knowledge_Base_SRS_V1.1_Engineering_Baseline.html
- Data Model V1.0: docs/architecture/data-model/Agentic_Knowledge_Base_Data_Model_V1.0.md
- ICD V1.0: docs/architecture/interfaces/Agentic_Knowledge_Base_ICD_V1.0.md
- V&V Plan V1.0: docs/verification/Agentic_Knowledge_Base_VV_Plan_V1.0.md
- RTM V1.0: docs/verification/REQUIREMENT_TRACEABILITY_MATRIX_V1.0.md
- Golden Dataset V1.0: docs/verification/golden/GOLDEN_DATASET_V1.0_REPORT.md
- Workflow: docs/development/LOCAL_AI_VMODEL_WORKFLOW.md
