# KB1 Requirement Program: Integrated Delivery Plan

## 0. Objective

Deliver one coherent OBC/DCDC custom-requirement subsystem instead of many isolated micro-steps.

The program goal is to support this full engineering loop:

```text
Customer / Project requirement package
  -> candidate extraction
  -> review / promote
  -> customer/project profiles
  -> effective requirement resolution
  -> diff / conflict scan
  -> compliance matrix
  -> change impact analysis
  -> approval governance
  -> API / answer routing
```

## 1. Architecture Boundary

The subsystem is additive. It does not replace the existing KB1 evidence/fact/query chain.

Hard boundaries:

1. EffectiveRequirement is derived state, not the source of truth.
2. RequirementVariant must be backed by evidence, sample data, or explicit manual approval.
3. Project overlay records only deltas; it must not duplicate full customer profiles.
4. `loosen`, `disable`, and `exception` require review/approval handling.
5. LLMs may help parse user questions later, but must not decide final effective values.
6. Existing `answer_api` is only soft-routed when explicitly enabled.

## 2. Delivery Streams

### Stream A — Data model and resolver

Tables:

- customers
- customer_projects
- requirement_atoms
- requirement_profiles
- requirement_profile_inheritance
- requirement_variants
- requirement_overrides
- effective_requirements
- requirement_evidence_bindings
- requirement_resolution_runs

Capabilities:

- resolve one requirement for one project
- resolve all effective requirements for one project
- compare project overlay against customer common profile
- scan conflicts and missing evidence

### Stream B — Query and answer adapter

Capabilities:

- plan natural-language requirement queries
- answer effective-requirement queries
- answer diff queries
- answer conflict/review/compliance/impact/candidate/package queries
- optional answer_api soft router controlled by `EAKB_ENABLE_REQUIREMENT_ROUTER=1`

### Stream C — HTTP API

Capabilities:

- framework-neutral request adapter
- optional FastAPI router factory
- optional integration script that patches only safe FastAPI-like entrypoints

### Stream D — Test coverage and compliance

Tables:

- requirement_test_methods
- requirement_test_cases
- requirement_test_results

Capabilities:

- build project compliance matrix
- evaluate one requirement against its test result
- report missing test methods/results and failed requirements

### Stream E — Change impact analysis

Capabilities:

- dry-run proposed customer/common requirement changes
- identify affected projects
- identify downstream overlays that become looser than the proposed customer requirement
- flag regression-test and review needs

### Stream F — Approval governance

Tables:

- requirement_approvals
- requirement_approval_events

Capabilities:

- surface review items
- submit approval requests
- approve/reject requests
- sync approved override status back to resolver input
- audit approval events

### Stream G — Candidate extraction and package import

Tables:

- requirement_candidate_batches
- requirement_candidates
- requirement_candidate_events
- requirement_import_packages
- requirement_import_package_events

Capabilities:

- extract review-only candidates from text or facts
- promote/reject candidates
- import customer/project requirement packages
- auto-create customer/project/profile scaffolding
- optionally auto-promote only for controlled validation scenarios

## 3. Execution Strategy

Do not manually run one tiny command at a time. Use the orchestrator:

```bash
python scripts/run_requirement_program.py --root knowledge_base --mode full
```

The orchestrator performs:

1. preflight checks
2. idempotent integration patching
3. grouped unit tests
4. smoke workspace creation
5. schema initialization
6. sample data seeding
7. resolver/diff/conflict validation
8. query/answer/router validation
9. API validation
10. compliance validation
11. impact validation
12. approval validation
13. extraction validation
14. package import validation
15. JSON report generation

## 4. Program Gates

A stage is acceptable only when all gates pass:

| Gate | Required result |
|---|---|
| Preflight | repo shape is compatible |
| Schema | all requirement tables exist |
| Resolver | P1 ripple resolves to 30mV; P2 loosen is approval_required |
| Diff | P1 differs from customer common by condition/overlay |
| Query | natural-language requirement query resolves without guessing |
| Router | disabled by default; enabled only by env var |
| API | health/effective/diff/query routes return structured payloads |
| Compliance | P1 passes seeded matrix; P2 ripple fails/incomplete as seeded |
| Impact | tightening customer ripple to 20mV impacts downstream projects |
| Approval | approved loosen override clears approval_required on re-resolve |
| Extraction | text generates pending candidates; promote creates variant |
| Package import | import package creates project/profile/candidates; refresh works |

## 5. After This Program

Only after the integrated program passes should the next product work start:

1. project requirement baseline versioning
2. baseline freeze / compare / rollback
3. real customer document ingestion profiles
4. UI review queue
5. PLM / test system integration
6. production-grade authorization and audit retention

---

## Addendum: Project Requirement Baseline Versioning

The integrated program now includes project baseline versioning as a first-class closed loop.

New chain:

```text
Project Effective Requirements
  -> Frozen Baseline v1
  -> Requirement/profile/test changes
  -> Frozen Baseline v2
  -> Baseline Compare
  -> Drift Detection
  -> Dry-run Rollback Plan
  -> Review / Approval
  -> New frozen baseline
```

This layer converts requirement management from a live-state resolver into a governed engineering decision record. It is required before connecting requirement outputs to release gates, customer sign-off, or formal compliance milestones.


## Release Readiness Gate

The program now includes DV/PV/SOP release readiness gates. The gate consumes frozen baselines, current resolver output, compliance matrices, approval status, evidence gaps, and baseline drift to produce a pass / conditional_pass / blocked decision.


## Phase: Engineering Change Order / ECO

ECO is the next full-loop capability after Release Readiness Gate. It binds:

```text
requirement change -> impact -> approval -> application -> effective refresh -> baseline -> release gate
```

The ECO layer is intentionally a coordinator. It should not duplicate resolver,
impact, approval, baseline, or release-gate logic.
