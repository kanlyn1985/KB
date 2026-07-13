# KB1 Requirement Resolver Integrated Program

This package is no longer intended to be applied as many small manual steps. Use the one-shot program runner.

```bash
python scripts/run_requirement_program.py --root .requirement_program_runtime/knowledge_base --mode full --apply-integrations
```

Read first:

- `docs/REQUIREMENT_PROGRAM_PLAN.md`
- `docs/REQUIREMENT_VALIDATION_GATES.md`

The runner performs preflight checks, integration patching, grouped unit tests, command-level smoke tests, and writes JSON/Markdown reports under `.requirement_program_runtime/reports/`.

---

# KB1 Requirement Resolver MVP v5

This package adds a deterministic custom-requirement resolver for OBC/DCDC customer/project requirements.

## Scope

The MVP models:

- customer and project metadata
- reusable requirement profiles
- profile inheritance
- requirement atoms and variants
- project overlays
- effective requirement resolution
- requirement diff and conflict scan
- natural-language requirement query adapter
- optional answer_api soft router
- framework-neutral HTTP API adapter

The resolver is deterministic. It does not let an LLM decide the effective requirement value.

## Install / apply

From the repository root:

```bash
git checkout -b feature/requirement-resolver-mvp
unzip evt_requirement_resolver_mvp_v5.zip

python scripts/apply_requirement_cli_integration.py
python scripts/apply_requirement_answer_api_integration.py
# Optional: only when your api_server entrypoint is FastAPI-shaped.
python scripts/apply_requirement_api_integration.py

python -m unittest discover -s tests -v
```

## Initialize sample data

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement init-schema
python -m enterprise_agent_kb.cli --root knowledge_base requirement seed-sample
```

## CLI examples

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement resolve \
  --project-id CUST-A-P1 \
  --atom-id REQATOM-DCDC-OUTPUT-RIPPLE

python -m enterprise_agent_kb.cli --root knowledge_base requirement ask \
  --query "客户A P1项目 DCDC 输出纹波要求是多少？"

python -m enterprise_agent_kb.cli --root knowledge_base requirement diff \
  --project-id CUST-A-P1 \
  --base-profile-id PROFILE-CUST-A-DCDC-COMMON
```

## answer_api soft router

The answer_api integration is opt-in.

```bash
EAKB_ENABLE_REQUIREMENT_ROUTER=1 \
python -m enterprise_agent_kb.cli --root knowledge_base answer-query \
  --query "客户A P1项目 DCDC 输出纹波要求是多少？"
```

When the environment variable is not enabled, the normal answer chain is not changed.

## HTTP API adapter

v5 adds `enterprise_agent_kb.requirements.api`.

It exposes a framework-neutral adapter:

```python
from pathlib import Path
from enterprise_agent_kb.requirements.api import handle_requirement_api_request

response = handle_requirement_api_request(
    Path("knowledge_base"),
    "GET",
    "/requirements/projects/CUST-A-P1/effective/REQATOM-DCDC-OUTPUT-RIPPLE",
)
```

Supported routes:

```text
GET  /requirements/health
GET  /requirements/projects/{project_id}/effective
GET  /requirements/projects/{project_id}/effective/{atom_id}
GET  /requirements/projects/{project_id}/diff?base_profile_id=...
GET  /requirements/projects/{project_id}/conflicts
POST /requirements/query
```

For FastAPI-shaped API servers, the optional helper is:

```python
from enterprise_agent_kb.requirements.api import create_fastapi_router

app.include_router(create_fastapi_router(root))
```

The script `scripts/apply_requirement_api_integration.py` attempts this only when it finds a safe FastAPI-like entrypoint. If it cannot identify a safe insertion point, it refuses to patch and prints manual instructions.

## Safety boundaries

- Effective requirements are derived state.
- Project overlays store only deltas; they do not duplicate full customer profiles.
- `loosen`, `disable`, and `exception` require evidence/approval handling.
- The answer_api router is opt-in via `EAKB_ENABLE_REQUIREMENT_ROUTER=1`.
- The HTTP adapter is framework-neutral and can be mounted without changing the existing generic KB1 answer chain.


## v6: 测试覆盖与合规矩阵

v6 在 Requirement Resolver 之上增加测试验证层，形成：

```text
EffectiveRequirement
  -> RequirementTestMethod
  -> RequirementTestCase
  -> RequirementTestResult
  -> Compliance Matrix
```

新增 CLI：

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement compliance \
  --project-id CUST-A-P1

python -m enterprise_agent_kb.cli --root knowledge_base requirement compliance \
  --project-id CUST-A-P2 \
  --atom-id REQATOM-DCDC-OUTPUT-RIPPLE
```

新增 HTTP-style endpoint：

```text
GET /requirements/projects/{project_id}/compliance
GET /requirements/projects/{project_id}/compliance/{atom_id}
```

新增自然语言 intent：

```text
requirement_compliance
```

示例：

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement ask \
  --query "客户A P1项目是否满足DCDC输出纹波要求？"
```

注意：v6 的 compliance 只判断“测试结果是否满足已解析的 EffectiveRequirement”。如果 EffectiveRequirement 本身存在 `approval_required` 或 `hard_blocker`，合规矩阵会保留 `requirement_conflict_status`，但不会把需求冲突和测试结果混为一类事实。

---

# v7: Requirement Change Impact Analysis

v7 adds deterministic dry-run impact analysis for customer/common requirement changes.
It does not write the proposed change into the database. It simulates the new value and reports affected projects, downstream overrides, regression-test needs, and proposed-value test risk.

## New module

```text
src/enterprise_agent_kb/requirements/impact.py
```

## New CLI

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement impact \
  --variant-id REQVAR-CUST-A-RIPPLE \
  --new-value 20 \
  --unit mV
```

## New natural language query

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement ask \
  --query "如果客户A把输出纹波改成20mV，会影响哪些项目？"
```

## New API endpoints

```text
GET  /requirements/impact?variant_id=REQVAR-CUST-A-RIPPLE&new_value=20&unit=mV
POST /requirements/impact-analysis
```

POST body:

```json
{
  "variant_id": "REQVAR-CUST-A-RIPPLE",
  "new_value": 20,
  "unit": "mV"
}
```

## Impact report shape

The analyzer returns:

```text
source_profile
current_variant
proposed_variant
summary
affected_projects[]
```

Each affected project includes:

```text
impact_type
current_effective_requirement
proposed_requirement
proposed_vs_selected_comparison
regression_test_required
review_required
test_impact
current_compliance_summary
```

Important MVP impact types:

```text
effective_value_changed
downstream_override_looser_than_proposed
downstream_override_already_stricter
downstream_override_equivalent_or_clarified
downstream_override_needs_review
```

## Example

For the seeded sample:

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement impact \
  --variant-id REQVAR-CUST-A-RIPPLE \
  --new-value 20 \
  --unit mV
```

Expected behavior:

```text
CUST-A-P1: downstream override becomes looser than proposed customer requirement; regression/review required.
CUST-A-P2: downstream override becomes looser than proposed customer requirement; regression/review required.
```

The sample also estimates latest test results against the proposed value. P1 ripple measured 28mV, so a proposed ≤20mV customer requirement is flagged as failing against the proposed value.

## v7 self-test

In a scaffold that includes the existing repository files `enterprise_agent_kb.config` and `enterprise_agent_kb.db`, the v7 package test suite passes:

```text
35 tests OK
```

This package intentionally does not duplicate those existing repository files; apply it inside the current `evt` repository.

---

# v8: Review & Approval Governance MVP

v8 adds a deterministic human review / approval layer for risky requirement customization.

## New module

```text
src/enterprise_agent_kb/requirements/approval.py
```

## New tables

```text
requirement_approvals
requirement_approval_events
```

## What v8 covers

The approval layer surfaces and manages:

```text
loosen / disable / exception project overlays
missing evidence on risky overlays
effective requirements with approval_required / hard_blocker / evidence_missing
impact-analysis downstream overrides that need review
```

The MVP is intentionally not a full workflow/BPM system. It provides a minimal auditable state model:

```text
submitted -> approved
submitted -> rejected
```

When an approval request targets a `requirement_overrides.override_id` and is approved, the corresponding `requirement_overrides.approval_status` is updated to `approved`, allowing the deterministic resolver to clear the `approval_required` conflict where appropriate.

## New CLI

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement review --project-id CUST-A-P2

python -m enterprise_agent_kb.cli --root knowledge_base requirement request-approval \
  --target-type override \
  --target-id OVR-P2-RIPPLE-LOOSEN \
  --project-id CUST-A-P2 \
  --atom-id REQATOM-DCDC-OUTPUT-RIPPLE \
  --variant-id REQVAR-P2-RIPPLE \
  --override-id OVR-P2-RIPPLE-LOOSEN \
  --reason "Customer accepted P2 relaxation for sample stage"

python -m enterprise_agent_kb.cli --root knowledge_base requirement approve \
  --approval-id APR-override-OVR-P2-RIPPLE-LOOSEN \
  --approver chief-engineer

python -m enterprise_agent_kb.cli --root knowledge_base requirement list-approvals --project-id CUST-A-P2
```

## New natural-language query

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement ask \
  --query "P2 项目有哪些需求需要审批？"
```

New intent:

```text
requirement_review
```

## New API endpoints

```text
GET  /requirements/reviews?project_id=CUST-A-P2
GET  /requirements/approvals?project_id=CUST-A-P2&status=submitted
POST /requirements/approvals
POST /requirements/approvals/{approval_id}/approve
POST /requirements/approvals/{approval_id}/reject
```

## v8 test result

The v8 package was tested in a temporary harness with the repository's expected `config/db` interfaces available:

```text
42 tests OK
```

## v8 boundary

v8 does not implement:

```text
full approval workflow engine
role-based access control
email/calendar notifications
PLM/QMS integration
digital signatures
```

Those should come later after the approval object model is validated.

---

## v9: Requirement Candidate Extraction / Semi-automatic Classification

v9 adds a review-first extraction layer. It scans customer requirement text or existing `facts` rows and creates candidate records only. Candidates do **not** become active requirements until a reviewer promotes them into a `RequirementProfile`.

### New module

```text
src/enterprise_agent_kb/requirements/extraction.py
```

### New tables

```text
requirement_candidate_batches
requirement_candidates
requirement_candidate_events
```

### New CLI commands

Extract candidates from raw text:

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement extract-candidates \
  --text "客户A要求DCDC输出纹波应不大于30mV。满载效率应不低于95%。" \
  --profile-id PROFILE-CUST-A-DCDC-COMMON
```

Extract candidates from facts for a document:

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement extract-candidates \
  --doc-id DOC-000002 \
  --profile-id PROFILE-CUST-A-DCDC-COMMON \
  --limit 100
```

List pending candidates:

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement list-candidates \
  --status pending_review
```

Promote a reviewed candidate into `requirement_variants`:

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement promote-candidate \
  --candidate-id RCAND-... \
  --profile-id PROFILE-CUST-A-DCDC-COMMON \
  --promoted-by reviewer
```

Reject a candidate:

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement reject-candidate \
  --candidate-id RCAND-... \
  --reviewer reviewer \
  --reason "duplicate or not applicable"
```

### New API routes

```text
POST /requirements/candidates/extract
GET  /requirements/candidates
POST /requirements/candidates/{candidate_id}/promote
POST /requirements/candidates/{candidate_id}/reject
```

### New natural language intent

```text
requirement_candidates
```

Example:

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement ask \
  --query "有哪些候选需求需要评审？"
```

### Governance rule

Candidate extraction is intentionally not authoritative:

```text
raw customer text / facts
  → RequirementCandidate
  → human review
  → promote / reject
  → active RequirementVariant only after promotion
```

This preserves the KB1 principle that requirement facts must be traceable and reviewed before they influence resolver, compliance, impact, or approval outcomes.

## v10: 客户项目需求包导入

v10 在 v9 的候选需求抽取基础上增加了“客户项目需求包”导入层。它用于一次性导入一个客户项目的一组需求文本，自动创建/补齐：

- Customer
- CustomerProject
- Customer common RequirementProfile
- Project overlay RequirementProfile
- Requirement candidate batch
- Candidate review list
- 可选 promoted RequirementVariant
- 可选 EffectiveRequirement refresh

默认仍然是 review-first：导入只生成候选需求，不直接生效。

### CLI: 导入需求包

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement import-package \
  --customer-id CUST-A \
  --customer-name "客户A" \
  --project-id CUST-A-P3 \
  --project-code A-DCDC-P3 \
  --product-family DCDC \
  --package-name "P3 customer requirement pack" \
  --text "P3项目要求DCDC输出纹波应不大于25mV。休眠电流应不超过1mA。"
```

### CLI: 安全默认，不自动生效

导入后查看候选：

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement list-candidates \
  --profile-id PROFILE-CUST-A-P3 \
  --status pending_review
```

人工确认后再 promote：

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement promote-candidate \
  --candidate-id RCAND-... \
  --profile-id PROFILE-CUST-A-P3 \
  --promoted-by reviewer
```

### CLI: MVP 自动提升模式

仅用于样例验证或受控环境：

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement import-package \
  --customer-id CUST-A \
  --project-id CUST-A-P3 \
  --project-code A-DCDC-P3 \
  --product-family DCDC \
  --text "P3项目要求DCDC输出纹波应不大于25mV。" \
  --auto-promote \
  --promoted-by reviewer \
  --refresh-effective
```

### CLI: 查看导入包

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement list-import-packages \
  --project-id CUST-A-P3
```

### CLI: 刷新导入包对应项目的 EffectiveRequirement

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement refresh-import-package \
  --package-id RPKG-...
```

### API

```text
GET  /requirements/import-packages
POST /requirements/import-packages
POST /requirements/import-packages/{package_id}/refresh
```

POST 示例：

```json
{
  "customer_id": "CUST-A",
  "customer_name": "客户A",
  "project_id": "CUST-A-P3",
  "project_code": "A-DCDC-P3",
  "product_family": "DCDC",
  "package_name": "P3 customer requirement pack",
  "text": "P3项目要求DCDC输出纹波应不大于25mV。休眠电流应不超过1mA。",
  "profile_scope": "project_overlay",
  "auto_promote": false
}
```

### 自然语言查询

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement ask \
  --query "有哪些需求包导入记录？"
```

### v10 新增测试

- `tests/test_requirement_package_import.py`
- `tests/test_requirement_package_import_query_api.py`

v10 的目标闭环：

```text
客户项目需求包
  → Customer / Project / Profile 自动补齐
  → 候选需求批次
  → 人工 review / promote
  → 项目 overlay variants
  → EffectiveRequirement refresh
  → 后续 compliance / impact / approval
```

---

# Integrated extension: Project Requirement Baseline Versioning

This integrated program adds a complete project requirement baseline-versioning loop.

## New commands

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement freeze-baseline --project-id CUST-A-P1 --frozen-by reviewer
python -m enterprise_agent_kb.cli --root knowledge_base requirement list-baselines --project-id CUST-A-P1
python -m enterprise_agent_kb.cli --root knowledge_base requirement show-baseline --baseline-id RBL-CUST-A-P1-v1
python -m enterprise_agent_kb.cli --root knowledge_base requirement diff-baselines --base-baseline-id RBL-CUST-A-P1-v1 --head-baseline-id RBL-CUST-A-P1-v2
python -m enterprise_agent_kb.cli --root knowledge_base requirement baseline-drift --baseline-id RBL-CUST-A-P1-v1
python -m enterprise_agent_kb.cli --root knowledge_base requirement rollback-baseline --baseline-id RBL-CUST-A-P1-v1
```

## New validation gate

`smoke.baseline` is included in `scripts/run_requirement_program.py`. The full orchestrator now validates schema, resolver, diff, query/answer, API, compliance, impact, approval, extraction, package import, and baseline versioning in one run.


## Release Readiness Gate

Run a DV/PV/SOP gate after seeding or importing requirements and freezing a baseline:

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement release-gate \
  --project-id CUST-A-P1 \
  --stage DV \
  --evaluated-by chief-engineer
```

List persisted gate runs:

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement list-release-gates \
  --project-id CUST-A-P1
```

Show one run and findings:

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement show-release-gate \
  --run-id RGATE-...
```


## Engineering Change Order / ECO Program

This integrated package adds a full ECO workflow:

```text
ECO create
  -> impact analysis
  -> approval
  -> apply requirement variant change
  -> refresh effective requirements
  -> freeze post-change baseline
  -> rerun release gate
  -> close / gate_blocked
```

CLI example:

```bash
python -m enterprise_agent_kb.cli --root knowledge_base requirement run-eco-cycle   --project-id CUST-A-P1   --title "Tighten customer ripple to 20mV"   --variant-id REQVAR-CUST-A-RIPPLE   --new-value 20   --unit mV   --operator "<="   --actor chief-engineer   --stage DV
```

API endpoints:

```text
GET  /requirements/ecos
POST /requirements/ecos
GET  /requirements/ecos/{eco_id}
POST /requirements/ecos/{eco_id}/submit
POST /requirements/ecos/{eco_id}/approve
POST /requirements/ecos/{eco_id}/apply
POST /requirements/ecos/{eco_id}/close
POST /requirements/ecos/run-cycle
```

## System audit package note

This package is an overlay for the EVT repository, not a standalone repository snapshot. Run audit and unit tests after applying it in the actual EVT repo root.

Recommended merge-readiness command:

```bash
python scripts/audit_requirement_program.py --repo-root . --run-tests
python scripts/run_requirement_program.py --root .requirement_program_runtime/knowledge_base --mode smoke
```
