-- Migration 002: Requirement Resolver program subsystem schema.
--
-- Creates 28 tables for the customer/project requirement governance layer
-- (Requirement Resolver overlay). All tables use IF NOT EXISTS so this
-- migration is idempotent: re-running on a DB where requirement_* tables
-- already exist (e.g. created by the legacy requirements/schema.py
-- SCHEMA_SQL executescript path) is a safe no-op.
--
-- Tables: customers, customer_projects, requirement_atoms,
-- requirement_profiles, requirement_profile_inheritance, requirement_variants,
-- requirement_overrides, effective_requirements, requirement_evidence_bindings,
-- requirement_test_methods, requirement_test_cases, requirement_test_results,
-- requirement_approvals, requirement_approval_events, requirement_candidate_batches,
-- requirement_candidates, requirement_candidate_events, requirement_import_packages,
-- requirement_import_events, requirement_resolution_runs, requirement_baselines,
-- requirement_baseline_items, requirement_baseline_events, requirement_release_gate_runs,
-- requirement_release_gate_findings, requirement_eco_orders, requirement_eco_actions,
-- requirement_eco_events.
--
-- Coexists with KB1's 30 base tables (documents, pages, blocks, evidence,
-- facts, ...) and the 001_expected_points migration. Shares the same
-- knowledge.db and PRAGMA user_version sequence.

CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    customer_code TEXT,
    region TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customer_projects (
    project_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    project_code TEXT NOT NULL,
    project_name TEXT,
    product_family TEXT NOT NULL,
    product_variant_id TEXT,
    platform_id TEXT,
    lifecycle_status TEXT,
    sop_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_atoms (
    atom_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    category TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    description TEXT,
    parameter_name TEXT,
    default_unit TEXT,
    constraint_kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_profiles (
    profile_id TEXT PRIMARY KEY,
    profile_type TEXT NOT NULL,
    owner_type TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT,
    description TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_profile_inheritance (
    child_profile_id TEXT NOT NULL,
    parent_profile_id TEXT NOT NULL,
    priority INTEGER NOT NULL,
    inheritance_type TEXT DEFAULT 'normal',
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    PRIMARY KEY (child_profile_id, parent_profile_id)
);

CREATE TABLE IF NOT EXISTS requirement_variants (
    variant_id TEXT PRIMARY KEY,
    atom_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    requirement_text TEXT NOT NULL,
    parameter_name TEXT,
    operator TEXT,
    value_numeric REAL,
    value_text TEXT,
    unit TEXT,
    condition_json TEXT,
    requirement_type TEXT,
    mandatory_level TEXT,
    priority INTEGER DEFAULT 100,
    source_type TEXT,
    source_id TEXT,
    evidence_id TEXT,
    fact_id TEXT,
    document_id TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_overrides (
    override_id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL,
    atom_id TEXT NOT NULL,
    base_variant_id TEXT,
    new_variant_id TEXT,
    override_type TEXT NOT NULL,
    reason TEXT,
    evidence_id TEXT,
    approval_status TEXT DEFAULT 'draft',
    approver TEXT,
    approved_at TEXT,
    risk_level TEXT DEFAULT 'medium',
    conflict_status TEXT DEFAULT 'unchecked',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS effective_requirements (
    effective_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    atom_id TEXT NOT NULL,
    selected_variant_id TEXT,
    effective_requirement_text TEXT NOT NULL,
    parameter_name TEXT,
    operator TEXT,
    value_numeric REAL,
    value_text TEXT,
    unit TEXT,
    condition_json TEXT,
    resolution_path_json TEXT NOT NULL,
    conflict_status TEXT DEFAULT 'none',
    verification_status TEXT DEFAULT 'unverified',
    approval_status TEXT DEFAULT 'none',
    computed_at TEXT NOT NULL,
    code_version TEXT,
    UNIQUE(project_id, atom_id)
);

CREATE TABLE IF NOT EXISTS requirement_evidence_bindings (
    binding_id TEXT PRIMARY KEY,
    atom_id TEXT,
    variant_id TEXT,
    override_id TEXT,
    effective_id TEXT,
    evidence_id TEXT NOT NULL,
    fact_id TEXT,
    document_id TEXT,
    page_no INTEGER,
    block_id TEXT,
    binding_type TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    created_at TEXT NOT NULL
);



CREATE TABLE IF NOT EXISTS requirement_test_methods (
    test_method_id TEXT PRIMARY KEY,
    atom_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    procedure_json TEXT,
    evidence_id TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_test_cases (
    test_case_id TEXT PRIMARY KEY,
    test_method_id TEXT NOT NULL,
    project_id TEXT,
    name TEXT NOT NULL,
    condition_json TEXT,
    priority INTEGER DEFAULT 100,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_test_results (
    result_id TEXT PRIMARY KEY,
    test_case_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    measured_value_numeric REAL,
    measured_value_text TEXT,
    unit TEXT,
    status TEXT DEFAULT 'recorded',
    evidence_id TEXT,
    executed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);



CREATE TABLE IF NOT EXISTS requirement_approvals (
    approval_id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    project_id TEXT,
    atom_id TEXT,
    variant_id TEXT,
    override_id TEXT,
    risk_level TEXT DEFAULT 'medium',
    approval_status TEXT DEFAULT 'draft',
    reason TEXT,
    requested_by TEXT,
    approver TEXT,
    evidence_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    submitted_at TEXT,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS requirement_approval_events (
    event_id TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    comment TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_candidate_batches (
    batch_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id TEXT,
    profile_id TEXT,
    document_id TEXT,
    status TEXT DEFAULT 'pending_review',
    candidate_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_candidates (
    candidate_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    candidate_type TEXT NOT NULL,
    status TEXT DEFAULT 'pending_review',
    source_type TEXT NOT NULL,
    source_id TEXT,
    document_id TEXT,
    fact_id TEXT,
    evidence_id TEXT,
    raw_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    suggested_atom_id TEXT,
    suggested_profile_id TEXT,
    operator TEXT,
    value_numeric REAL,
    value_text TEXT,
    unit TEXT,
    condition_json TEXT,
    confidence REAL DEFAULT 0.0,
    promoted_variant_id TEXT,
    review_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_candidate_events (
    event_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    candidate_id TEXT,
    event_type TEXT NOT NULL,
    actor TEXT,
    comment TEXT,
    created_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS requirement_import_packages (
    package_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    package_name TEXT,
    source_type TEXT NOT NULL,
    profile_scope TEXT DEFAULT 'project_overlay',
    customer_profile_id TEXT,
    project_profile_id TEXT,
    status TEXT DEFAULT 'pending_review',
    batch_ids_json TEXT,
    candidate_count INTEGER DEFAULT 0,
    promoted_count INTEGER DEFAULT 0,
    effective_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_import_events (
    event_id TEXT PRIMARY KEY,
    package_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    comment TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_resolution_runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    atom_id TEXT,
    run_mode TEXT NOT NULL,
    status TEXT NOT NULL,
    total_requirements INTEGER DEFAULT 0,
    conflict_count INTEGER DEFAULT 0,
    evidence_missing_count INTEGER DEFAULT 0,
    approval_required_count INTEGER DEFAULT 0,
    code_version TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_requirement_variants_atom_profile
    ON requirement_variants(atom_id, profile_id, status);
CREATE INDEX IF NOT EXISTS idx_requirement_profiles_owner
    ON requirement_profiles(owner_type, owner_id, profile_type, status);
CREATE INDEX IF NOT EXISTS idx_effective_requirements_project
    ON effective_requirements(project_id, conflict_status, verification_status);

CREATE INDEX IF NOT EXISTS idx_requirement_test_methods_atom
    ON requirement_test_methods(atom_id, status);
CREATE INDEX IF NOT EXISTS idx_requirement_test_cases_method_project
    ON requirement_test_cases(test_method_id, project_id, status);
CREATE INDEX IF NOT EXISTS idx_requirement_test_results_project_case
    ON requirement_test_results(project_id, test_case_id, executed_at);

CREATE INDEX IF NOT EXISTS idx_requirement_approvals_project_status
    ON requirement_approvals(project_id, approval_status, target_type);
CREATE INDEX IF NOT EXISTS idx_requirement_approvals_target
    ON requirement_approvals(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_requirement_approval_events_approval
    ON requirement_approval_events(approval_id, created_at);

CREATE INDEX IF NOT EXISTS idx_requirement_candidates_batch_status
    ON requirement_candidates(batch_id, status);
CREATE INDEX IF NOT EXISTS idx_requirement_candidates_atom_profile_status
    ON requirement_candidates(suggested_atom_id, suggested_profile_id, status);
CREATE INDEX IF NOT EXISTS idx_requirement_candidate_events_batch
    ON requirement_candidate_events(batch_id, created_at);


CREATE INDEX IF NOT EXISTS idx_requirement_import_packages_project_status
    ON requirement_import_packages(project_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_requirement_import_packages_customer_status
    ON requirement_import_packages(customer_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_requirement_import_events_package
    ON requirement_import_events(package_id, created_at);



CREATE TABLE IF NOT EXISTS requirement_baselines (
    baseline_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    baseline_name TEXT,
    baseline_version TEXT NOT NULL,
    parent_baseline_id TEXT,
    source_type TEXT DEFAULT 'manual_freeze',
    source_id TEXT,
    status TEXT DEFAULT 'frozen',
    frozen_by TEXT,
    frozen_at TEXT,
    requirement_count INTEGER DEFAULT 0,
    conflict_count INTEGER DEFAULT 0,
    verification_gap_count INTEGER DEFAULT 0,
    compliance_summary_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_baseline_items (
    baseline_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    atom_id TEXT NOT NULL,
    selected_variant_id TEXT,
    effective_requirement_text TEXT NOT NULL,
    operator TEXT,
    value_numeric REAL,
    value_text TEXT,
    unit TEXT,
    condition_json TEXT,
    conflict_status TEXT,
    verification_status TEXT,
    approval_status TEXT,
    effective_snapshot_json TEXT NOT NULL,
    signature TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (baseline_id, atom_id)
);

CREATE TABLE IF NOT EXISTS requirement_baseline_events (
    event_id TEXT PRIMARY KEY,
    baseline_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    comment TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_requirement_baselines_project_status
    ON requirement_baselines(project_id, status, frozen_at);
CREATE INDEX IF NOT EXISTS idx_requirement_baseline_items_project_atom
    ON requirement_baseline_items(project_id, atom_id, baseline_id);
CREATE INDEX IF NOT EXISTS idx_requirement_baseline_events_baseline
    ON requirement_baseline_events(baseline_id, created_at);


CREATE TABLE IF NOT EXISTS requirement_release_gate_runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    baseline_id TEXT,
    readiness_status TEXT NOT NULL,
    blocker_count INTEGER DEFAULT 0,
    warning_count INTEGER DEFAULT 0,
    check_count INTEGER DEFAULT 0,
    score_numeric REAL DEFAULT 0,
    evaluated_by TEXT,
    evaluated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_release_gate_findings (
    finding_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    finding_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    source_type TEXT,
    source_id TEXT,
    atom_id TEXT,
    message TEXT NOT NULL,
    recommendation TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_requirement_release_gate_runs_project_stage
    ON requirement_release_gate_runs(project_id, stage, evaluated_at);
CREATE INDEX IF NOT EXISTS idx_requirement_release_gate_runs_status
    ON requirement_release_gate_runs(readiness_status, evaluated_at);
CREATE INDEX IF NOT EXISTS idx_requirement_release_gate_findings_run
    ON requirement_release_gate_findings(run_id, severity, finding_type);


CREATE TABLE IF NOT EXISTS requirement_eco_orders (
    eco_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    change_type TEXT NOT NULL,
    status TEXT DEFAULT 'draft',
    target_variant_id TEXT NOT NULL,
    proposed_change_json TEXT NOT NULL,
    impact_summary_json TEXT,
    approval_summary_json TEXT,
    baseline_before_id TEXT,
    baseline_after_id TEXT,
    release_gate_before_id TEXT,
    release_gate_after_id TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    submitted_at TEXT,
    approved_at TEXT,
    applied_at TEXT,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS requirement_eco_actions (
    action_id TEXT PRIMARY KEY,
    eco_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    project_id TEXT,
    atom_id TEXT,
    status TEXT DEFAULT 'open',
    owner TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirement_eco_events (
    event_id TEXT PRIMARY KEY,
    eco_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    comment TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_requirement_eco_orders_project_status
    ON requirement_eco_orders(project_id, status, updated_at);
CREATE INDEX IF NOT EXISTS idx_requirement_eco_orders_variant
    ON requirement_eco_orders(target_variant_id, status, updated_at);
CREATE INDEX IF NOT EXISTS idx_requirement_eco_actions_eco
    ON requirement_eco_actions(eco_id, status, action_type);
CREATE INDEX IF NOT EXISTS idx_requirement_eco_events_eco
    ON requirement_eco_events(eco_id, created_at);
