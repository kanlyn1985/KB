# KB1 Requirement Program Validation Gates

This document defines the automatic validation gates used by `scripts/run_requirement_program.py`.

## Gate Groups

### 1. Static preflight

Checks:

- repository root contains `pyproject.toml`
- `src/enterprise_agent_kb/config.py` exists
- `src/enterprise_agent_kb/db.py` exists
- `src/enterprise_agent_kb/requirements` exists after applying the package
- Python can import `enterprise_agent_kb.requirements`

### 2. Unit gates

Grouped unit tests:

```text
resolver
query_adapter
router
api
compliance
impact
approval
extraction
package_import
integration_scripts
```

The orchestrator can run all tests or a selected group.

### 3. Command smoke gates

Uses an isolated workspace under `.requirement_program_runtime/knowledge_base` unless another root is supplied.

Commands validated:

```bash
python -m enterprise_agent_kb.requirements.cli --root <root> init-schema
python -m enterprise_agent_kb.requirements.cli --root <root> seed-sample
python -m enterprise_agent_kb.requirements.cli --root <root> resolve --project-id CUST-A-P1 --atom-id REQATOM-DCDC-OUTPUT-RIPPLE
python -m enterprise_agent_kb.requirements.cli --root <root> resolve --project-id CUST-A-P2 --atom-id REQATOM-DCDC-OUTPUT-RIPPLE
python -m enterprise_agent_kb.requirements.cli --root <root> diff --project-id CUST-A-P1 --base-profile-id PROFILE-CUST-A-DCDC-COMMON
python -m enterprise_agent_kb.requirements.cli --root <root> ask --query "客户A P1项目 DCDC 输出纹波要求是多少？" --raw
python -m enterprise_agent_kb.requirements.cli --root <root> compliance --project-id CUST-A-P1
python -m enterprise_agent_kb.requirements.cli --root <root> impact --variant-id REQVAR-CUST-A-RIPPLE --new-value 20 --unit mV
python -m enterprise_agent_kb.requirements.cli --root <root> review --project-id CUST-A-P2
python -m enterprise_agent_kb.requirements.cli --root <root> extract-candidates --text "客户A要求DCDC输出纹波应不大于30mV。" --profile-id PROFILE-CUST-A-DCDC-COMMON
python -m enterprise_agent_kb.requirements.cli --root <root> import-package --customer-id CUST-A --customer-name 客户A --project-id CUST-A-P3 --project-code A-DCDC-P3 --product-family DCDC --text "项目要求DCDC输出纹波应不大于25mV。" --auto-promote --promoted-by validator --refresh-effective
```

### 4. Report gate

The runner writes:

```text
.requirement_program_runtime/reports/requirement_program_report.json
.requirement_program_runtime/reports/requirement_program_report.md
```

The report records:

- command
- exit code
- duration
- stdout/stderr excerpt
- parsed assertions
- pass/fail result

## Failure Policy

Default behavior is fail-fast. Use `--continue-on-error` only during diagnosis.

## Safety Policy

The orchestrator does not:

- push to GitHub
- modify production workspaces unless explicitly pointed there
- enable answer_api router by default
- auto-approve real project overrides
- mutate customer data outside the selected `--root`

---

## Baseline versioning gates

| Gate | Expected result |
|---|---|
| `smoke.baseline.freeze` | a project baseline can be frozen from resolver output |
| `smoke.baseline.list` | frozen baselines can be listed by project |
| `smoke.baseline.drift` | a fresh baseline has zero drift against current resolver output |
| `unit.baseline.compare` | changed requirement values are detected across baselines |
| `unit.baseline.rollback_plan` | drift produces a dry-run rollback plan |
| `unit.baseline.api` | baseline API routes return structured responses |
| `unit.baseline.query` | baseline natural-language intent is detected |


## Gate: smoke.release_gate

Validates that a seeded project with a frozen baseline can run the DV release readiness gate, receive a non-blocked result, and persist the gate run for audit lookup.


## ECO gates

```text
unit.test_requirement_eco
unit.test_requirement_eco_query_api
smoke.eco
```

Acceptance:

```text
ECO full cycle creates approval, applies approved variant change, freezes a post-change baseline, and reruns release gate.
```
