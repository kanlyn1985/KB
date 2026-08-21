# ADR 0003: Ontology is a Constraint / Validation Layer Only (No Fact Generation)

**Date**: 2026-06-25
**Status**: Accepted
**Context**: Sprint 2 WP3/WP4 — minimal ontology integration into the main pipeline

## Context

Sprint 2 integrates the `kb1_ontology` system into the main `enterprise_agent_kb`
query/answer pipeline for the first time (previously fully isolated). The
integration must preserve KB1's core invariant: **every answer fact is
adjudicated by `evidence_judge` against evidence-bearing candidates, never by an
LLM or an auxiliary knowledge layer.** The question was: what role may the
ontology play without violating this invariant?

The Sprint 2 development guide (`docs/dev/sprint2-ontology-and-bugfix/kb1_sprint2_development_guide.html`)
mandates that the ontology may only be called `signal` / `constraint` /
`validation`, never `evidence` / `fact` / `source truth`, and that
`answer_changed_by_ontology` must remain `false` throughout Sprint 2.

## Decision

The ontology layer is a **read-only constraint / validation / recall-aid layer**.
Concretely, the `enterprise_agent_kb.ontology_adapter` integration observes the
following hard constraints:

1. **No fact generation.** The ontology may never produce, mutate, or augment
   facts. Its outputs are named `signal` / `constraint` / `check` / `validation`
   — never `evidence` / `fact` / `source_truth`.
2. **No bypass of `evidence_judge`.** The ontology is not a fact-adjudication
   layer. Answer facts continue to come solely from evidence-constrained
   candidates judged by `evidence_judge`.
3. **No answer mutation in Sprint 2.** `changed_retrieval` and
   `changed_answer` are always `False`. Guard-mode post-checks produce warnings
   only; they never rewrite `direct_answer`.
4. **No LLM in the adapter.** Entity detection is rule/lookup based against
   `ontology.db` only. The ontology's own LLM-backed `router`/`decomposer` are
   not wired into the main pipeline.
5. **No heavy graph DB / OWL / RDF.** The adapter reads `ontology.db` (SQLite,
   read-only) only. No new vector DB or distributed service is introduced.
6. **`ontology.db` is not the primary fact store.** It is an auxiliary
   constraint index; `knowledge.db` remains the system of record for
   evidence/facts.

## Considered Options

1. **Constraint/validation layer only (chosen).** Ontology observes and reports;
   it never generates facts or mutates answers. Preserves the evidence-constrained
   invariant with zero risk to answer correctness.
2. **Active recall filter.** Let the ontology filter/rewrerank retrieval
   candidates by entity-type constraints. Rejected for Sprint 2: it changes
   retrieval ordering (violates `changed_retrieval=False`) and risks dropping
   valid evidence before judgement. Candidate for Sprint 3 evaluation.
3. **Fact-source integration.** Let the ontology inject facts directly into the
   answer. Rejected permanently: violates the core invariant that all answer
   facts are evidence-adjudicated. This option is off the table for all sprints.

## Consequences

- The ontology integration is safe-by-construction: even if `ontology.db` is
  corrupt or missing, the main pipeline is unaffected (adapter returns an empty
  signal with errors, never raises).
- Answer quality in Sprint 2 is unchanged by the ontology (`answer_changed_by_ontology=False`).
  The ontology's value this sprint is plumbing, observability, and regression
  safety — not answer improvement.
- Sprint 3 may relax constraint 3 (allow ontology to influence retrieval as a
  *candidate enhancement channel*, like the graph) **only after** a separate ADR
  and evidence that it does not regress the eval baseline. Constraint 1, 2, 4, 6
  are permanent.
- The adapter exposes `ontology_post_check_status` and `ontology_post_checks`
  answer-envelope fields for observability; `answer_changed_by_ontology` is the
  canary that must stay `false`.

## References

- Sprint 2 guide: `docs/dev/sprint2-ontology-and-bugfix/kb1_sprint2_development_guide.html` § WP3/WP4/§05
- Implementation: `src/enterprise_agent_kb/ontology_adapter.py`, `answer_api._compose_final_answer`
- Feature design: `.codestable/features/2026-06-25-ontology-shadow-guard-adapter/ontology-shadow-guard-adapter-design.md`
- Related: ADR 0001 (meta-domain layer rule), ADR 0002 (two-level normalization)
