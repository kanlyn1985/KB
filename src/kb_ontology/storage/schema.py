"""SQL DDL for the ontology storage four-table model.

Tables:
  entities    — Entity nodes (domain concepts)
  attributes  — Entity attributes as typed triples
  relations   — Typed edges between entities
  evidence    — Traceability links to source documents

See ARCHITECTURE.md §4.1 and CONTEXT.md for design rationale.
"""

SCHEMA_SQL = """
-- ── Entities ──
CREATE TABLE IF NOT EXISTS entities (
    id              TEXT PRIMARY KEY,
    class           TEXT NOT NULL,
    canonical_name  TEXT NOT NULL,
    domain          TEXT NOT NULL DEFAULT 'default',
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entities_class ON entities(class);
CREATE INDEX IF NOT EXISTS idx_entities_canonical_name ON entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_entities_domain ON entities(domain);

-- ── Attributes ──
CREATE TABLE IF NOT EXISTS attributes (
    id              TEXT PRIMARY KEY,
    entity_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    value           TEXT,
    value_type      TEXT NOT NULL,
    confidence      REAL,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);
CREATE INDEX IF NOT EXISTS idx_attributes_entity_id ON attributes(entity_id);
CREATE INDEX IF NOT EXISTS idx_attributes_name ON attributes(name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_attributes_entity_name ON attributes(entity_id, name);

-- ── Relations ──
CREATE TABLE IF NOT EXISTS relations (
    id              TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL,
    relation_type   TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    confidence      REAL,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES entities(id),
    FOREIGN KEY (target_id) REFERENCES entities(id)
);
CREATE INDEX IF NOT EXISTS idx_relations_source_id ON relations(source_id);
CREATE INDEX IF NOT EXISTS idx_relations_target_id ON relations(target_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_relations_triple ON relations(source_id, relation_type, target_id);

-- ── Evidence ──
CREATE TABLE IF NOT EXISTS evidence (
    id              TEXT PRIMARY KEY,
    ref_type        TEXT NOT NULL,
    ref_id          TEXT NOT NULL,
    document_id     TEXT NOT NULL,
    text_span       TEXT,
    location        TEXT,
    confidence      REAL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_ref ON evidence(ref_type, ref_id);
CREATE INDEX IF NOT EXISTS idx_evidence_document ON evidence(document_id);
"""
