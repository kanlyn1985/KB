-- Migration 001: expected_points table for Phase 1 evaluation framework.
--
-- expected_points stores the "what points should this document's sections
-- cover" baseline, produced by LLM-driven section→point decomposition
-- (see tools/build_expected_points.py).  Each row pins one (doc_id, version)
-- pair to a JSON list of points, so the QA evaluator can later mark which
-- points the system's answer covered.
--
-- Schema:
--   doc_id          TEXT  -- documents.doc_id
--   version         TEXT  -- "v1", "v2", ... pinned by human spot-check
--   points_json     TEXT  -- JSON: [{"section": "3.5", "page": 9,
--                                  "point": "...", "kind": "definition|param|process|..."}]
--   point_count     INTEGER -- denormalized count for fast queries
--   created_at      TEXT  -- ISO-8601 timestamp
--   created_by      TEXT  -- "tools/build_expected_points.py" or "manual"
--   PRIMARY KEY (doc_id, version)
--
-- Indexed on version for "latest per doc" queries.

CREATE TABLE IF NOT EXISTS expected_points (
    doc_id        TEXT    NOT NULL,
    version       TEXT    NOT NULL,
    points_json   TEXT    NOT NULL,
    point_count   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL,
    created_by    TEXT    NOT NULL DEFAULT 'tools/build_expected_points.py',
    PRIMARY KEY (doc_id, version)
);

CREATE INDEX IF NOT EXISTS idx_expected_points_version
    ON expected_points (version);
