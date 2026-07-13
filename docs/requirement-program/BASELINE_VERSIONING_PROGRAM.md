# Project Requirement Baseline Versioning Program

## Objective

Add a complete baseline-versioning closed loop on top of the existing KB1 requirement resolver program.

The new loop freezes a project's resolved effective requirements at decision points, compares baseline versions, detects drift from current resolver output, and produces dry-run rollback plans. It does not bypass the resolver, approvals, evidence binding, or compliance matrix.

## Scope

Included:

- `requirement_baselines`
- `requirement_baseline_items`
- `requirement_baseline_events`
- project baseline freeze
- baseline list/show
- baseline-to-baseline comparison
- current-state drift detection
- dry-run rollback planning
- CLI commands
- framework-neutral API routes
- natural-language baseline listing intent
- automated unit and smoke gates

Excluded from this program:

- destructive rollback that mutates requirement profiles automatically
- full PLM integration
- electronic signature workflow
- multi-user approval UI

## End-to-end chain

```text
Project effective requirements
  -> frozen requirement baseline v1
  -> later project/profile changes
  -> frozen requirement baseline v2
  -> baseline diff
  -> drift detection
  -> dry-run rollback plan
  -> review / approval / profile update
  -> freeze new baseline
```

## Gate policy

A baseline may be frozen even when conflicts exist, because the point of a baseline is to record the project requirement state at a decision point. However, `conflict_count`, `verification_gap_count`, and compliance summary are captured in the baseline header. A release baseline should enforce business gates externally, for example:

- `conflict_count == 0`
- `verification_gap_count == 0`
- compliance matrix has no `fail`
- all high-risk approvals are approved

## CLI

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement freeze-baseline \
  --project-id CUST-A-P1 \
  --name "P1 DV baseline" \
  --frozen-by chief-engineer

python -m enterprise_agent_kb.cli --root knowledge_base requirement list-baselines \
  --project-id CUST-A-P1

python -m enterprise_agent_kb.cli --root knowledge_base requirement show-baseline \
  --baseline-id RBL-CUST-A-P1-v1

python -m enterprise_agent_kb.cli --root knowledge_base requirement diff-baselines \
  --base-baseline-id RBL-CUST-A-P1-v1 \
  --head-baseline-id RBL-CUST-A-P1-v2

python -m enterprise_agent_kb.cli --root knowledge_base requirement baseline-drift \
  --baseline-id RBL-CUST-A-P1-v1

python -m enterprise_agent_kb.cli --root knowledge_base requirement rollback-baseline \
  --baseline-id RBL-CUST-A-P1-v1
```

## API

```text
GET  /requirements/baselines?project_id=CUST-A-P1
POST /requirements/projects/{project_id}/baselines
GET  /requirements/baselines/{baseline_id}
GET  /requirements/baselines/compare?base_baseline_id=...&head_baseline_id=...
GET  /requirements/baselines/{baseline_id}/drift
POST /requirements/baselines/{baseline_id}/rollback-plan
```

## Natural-language baseline intent

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement ask \
  --query "P1 项目有哪些需求基线版本？"
```

## Validation

The program runner includes a `smoke.baseline` gate. It freezes a P1 baseline, lists baselines, and checks that a freshly frozen baseline has zero drift.
