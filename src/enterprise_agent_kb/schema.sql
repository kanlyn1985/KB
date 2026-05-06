CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    source_filename TEXT NOT NULL,
    source_type TEXT NOT NULL,
    mime_type TEXT,
    sha256 TEXT NOT NULL,
    file_size INTEGER,
    page_count INTEGER,
    language TEXT,
    version_label TEXT,
    source_path TEXT NOT NULL,
    ingest_time TEXT NOT NULL,
    update_time TEXT NOT NULL,
    parse_status TEXT NOT NULL,
    quality_status TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS pages (
    page_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    page_no INTEGER NOT NULL,
    width REAL,
    height REAL,
    parser_confidence REAL,
    ocr_confidence REAL,
    risk_level TEXT NOT NULL,
    page_status TEXT NOT NULL,
    screenshot_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blocks (
    block_id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    block_type TEXT NOT NULL,
    reading_order INTEGER,
    text_content TEXT,
    raw_text TEXT,
    bbox_json TEXT,
    parser_confidence REAL,
    ocr_confidence REAL,
    risk_flags_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    page_id TEXT NOT NULL,
    block_id TEXT NOT NULL,
    block_type TEXT NOT NULL,
    raw_text TEXT,
    normalized_text TEXT,
    image_ref TEXT,
    table_ref TEXT,
    page_no INTEGER NOT NULL,
    confidence REAL,
    risk_level TEXT NOT NULL,
    evidence_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    alias_json TEXT,
    description TEXT,
    source_confidence REAL,
    entity_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY,
    fact_type TEXT NOT NULL,
    subject_entity_id TEXT,
    predicate TEXT NOT NULL,
    object_value TEXT,
    object_entity_id TEXT,
    qualifiers_json TEXT,
    confidence REAL,
    fact_status TEXT NOT NULL,
    source_doc_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_evidence_map (
    fact_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    support_type TEXT NOT NULL,
    PRIMARY KEY (fact_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id TEXT PRIMARY KEY,
    src_entity_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    dst_entity_id TEXT NOT NULL,
    version_scope TEXT,
    condition_scope TEXT,
    confidence REAL,
    edge_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edge_evidence_map (
    edge_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    PRIMARY KEY (edge_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS wiki_pages (
    page_id TEXT PRIMARY KEY,
    page_type TEXT NOT NULL,
    title TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    entity_id TEXT,
    source_fact_ids_json TEXT,
    source_doc_ids_json TEXT,
    trust_status TEXT NOT NULL,
    file_path TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quality_reports (
    doc_id TEXT PRIMARY KEY,
    overall_score REAL,
    ocr_avg_confidence REAL,
    structure_score REAL,
    table_score REAL,
    fact_alignment_score REAL,
    conflict_count INTEGER,
    high_risk_page_count INTEGER,
    review_required_count INTEGER,
    blocked_count INTEGER,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_units (
    unit_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    page_no INTEGER,
    block_id TEXT,
    unit_type TEXT NOT NULL,
    text TEXT,
    normalized_text TEXT,
    canonical_title TEXT,
    canonical_key TEXT,
    content_role TEXT,
    quality_flags_json TEXT NOT NULL DEFAULT '[]',
    importance TEXT,
    expected_knowledge_type TEXT,
    status TEXT NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retrieval_runs (
    run_id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    query_type TEXT,
    doc_scope TEXT,
    retrieved_evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    reranked_ids_json TEXT NOT NULL DEFAULT '[]',
    scores_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS golden_cases (
    case_id TEXT PRIMARY KEY,
    doc_id TEXT,
    assert_mode TEXT NOT NULL,
    query TEXT NOT NULL,
    must_hit_json TEXT NOT NULL DEFAULT '[]',
    negative_expected_json TEXT NOT NULL DEFAULT '[]',
    expected_pages_json TEXT NOT NULL DEFAULT '[]',
    expected_sections_json TEXT NOT NULL DEFAULT '[]',
    expected_evidence_shape TEXT,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_runs (
    eval_run_id TEXT PRIMARY KEY,
    suite_id TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    config_hash TEXT,
    code_version TEXT,
    result_summary_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_results (
    eval_run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    passed INTEGER NOT NULL,
    failure_reason TEXT,
    retrieved_items_json TEXT NOT NULL DEFAULT '[]',
    answer_text TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    PRIMARY KEY (eval_run_id, case_id)
);

CREATE TABLE IF NOT EXISTS repair_tasks (
    task_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    module TEXT NOT NULL,
    action TEXT NOT NULL,
    priority INTEGER NOT NULL,
    status TEXT NOT NULL,
    case_ids_json TEXT NOT NULL DEFAULT '[]',
    query_types_json TEXT NOT NULL DEFAULT '[]',
    impact_count INTEGER NOT NULL DEFAULT 0,
    source_eval_run_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5,
    payload_json TEXT,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dependencies (
    upstream_type TEXT NOT NULL,
    upstream_id TEXT NOT NULL,
    downstream_type TEXT NOT NULL,
    downstream_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    PRIMARY KEY (upstream_type, upstream_id, downstream_type, downstream_id)
);

CREATE TABLE IF NOT EXISTS system_counters (
    counter_key TEXT PRIMARY KEY,
    next_value INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pages_doc_id ON pages(doc_id);
CREATE INDEX IF NOT EXISTS idx_blocks_doc_id ON blocks(doc_id);
CREATE INDEX IF NOT EXISTS idx_blocks_page_id ON blocks(page_id);
CREATE INDEX IF NOT EXISTS idx_evidence_doc_id ON evidence(doc_id);
CREATE INDEX IF NOT EXISTS idx_evidence_page_id ON evidence(page_id);
CREATE INDEX IF NOT EXISTS idx_facts_source_doc_id ON facts(source_doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256);
CREATE INDEX IF NOT EXISTS idx_source_units_doc_id ON source_units(doc_id);
CREATE INDEX IF NOT EXISTS idx_source_units_status ON source_units(status);
CREATE INDEX IF NOT EXISTS idx_source_units_type ON source_units(unit_type);
CREATE INDEX IF NOT EXISTS idx_retrieval_runs_created_at ON retrieval_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_retrieval_runs_query_type ON retrieval_runs(query_type);
CREATE INDEX IF NOT EXISTS idx_golden_cases_doc_id ON golden_cases(doc_id);
CREATE INDEX IF NOT EXISTS idx_golden_cases_assert_mode ON golden_cases(assert_mode);
CREATE INDEX IF NOT EXISTS idx_golden_cases_status ON golden_cases(status);
CREATE INDEX IF NOT EXISTS idx_eval_runs_started_at ON eval_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_eval_runs_suite_id ON eval_runs(suite_id);
CREATE INDEX IF NOT EXISTS idx_eval_results_case_id ON eval_results(case_id);
CREATE INDEX IF NOT EXISTS idx_eval_results_passed ON eval_results(passed);
CREATE INDEX IF NOT EXISTS idx_repair_tasks_status ON repair_tasks(status);
CREATE INDEX IF NOT EXISTS idx_repair_tasks_reason ON repair_tasks(reason);
CREATE INDEX IF NOT EXISTS idx_repair_tasks_last_seen_at ON repair_tasks(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_jobs_target ON jobs(target_type, target_id, status);
CREATE INDEX IF NOT EXISTS idx_dependencies_upstream ON dependencies(upstream_type, upstream_id);
CREATE INDEX IF NOT EXISTS idx_dependencies_downstream ON dependencies(downstream_type, downstream_id);
