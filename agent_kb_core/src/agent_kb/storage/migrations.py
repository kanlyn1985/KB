from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


PHASE6_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="phase6_document_lifecycle",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS documents (
                logical_document_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_uri TEXT,
                active_version_id TEXT,
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS document_versions (
                version_id TEXT PRIMARY KEY,
                logical_document_id TEXT NOT NULL,
                compiler_document_id TEXT NOT NULL,
                version_label TEXT,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (logical_document_id) REFERENCES documents(logical_document_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_document_versions_document ON document_versions(logical_document_id)",
            "CREATE INDEX IF NOT EXISTS idx_document_versions_status ON document_versions(status)",
        ),
    ),
    Migration(
        version=2,
        name="phase6_vector_index",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS embedding_vectors (
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                object_id TEXT,
                provider_id TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                vector_json TEXT NOT NULL,
                text_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (source_type, source_id, provider_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_embedding_object ON embedding_vectors(object_id)",
            "CREATE INDEX IF NOT EXISTS idx_embedding_provider ON embedding_vectors(provider_id)",
        ),
    ),
    Migration(
        version=3,
        name="phase6_graph_index",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS graph_edges (
                edge_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                source_object_id TEXT NOT NULL,
                target_object_id TEXT NOT NULL,
                properties_json TEXT NOT NULL,
                evidence_ids_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_graph_source ON graph_edges(source_object_id)",
            "CREATE INDEX IF NOT EXISTS idx_graph_target ON graph_edges(target_object_id)",
            "CREATE INDEX IF NOT EXISTS idx_graph_relation ON graph_edges(relation_type)",
        ),
    ),
)


PHASE7_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=4,
        name="phase7_jobs_audit_backups",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS background_jobs (
                job_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                max_attempts INTEGER NOT NULL,
                available_at TEXT NOT NULL,
                locked_by TEXT,
                locked_at TEXT,
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_jobs_claim ON background_jobs(status, available_at, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_jobs_tenant ON background_jobs(tenant_id, status)",
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT,
                outcome TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_audit_tenant_created ON audit_events(tenant_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_audit_principal ON audit_events(principal_id, created_at)",
            """
            CREATE TABLE IF NOT EXISTS backup_history (
                backup_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_backup_tenant_created ON backup_history(tenant_id, created_at)",
        ),
    ),
    Migration(
        version=5,
        name="phase7_graph_extraction_governance",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS graph_extraction_runs (
                run_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                extractor_id TEXT NOT NULL,
                candidate_count INTEGER NOT NULL,
                accepted_count INTEGER NOT NULL,
                metrics_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_graph_extraction_tenant ON graph_extraction_runs(tenant_id, created_at)",
        ),
    ),
)


PHASE8_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=6,
        name="phase8_distributed_coordination",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS distributed_rate_limits (
                bucket_key TEXT NOT NULL,
                window_start TEXT NOT NULL,
                count INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (bucket_key, window_start)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_distributed_rate_window ON distributed_rate_limits(window_start)",
            """
            CREATE TABLE IF NOT EXISTS worker_heartbeats (
                worker_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                status TEXT NOT NULL,
                capabilities_json TEXT NOT NULL,
                heartbeat_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_worker_tenant_expiry ON worker_heartbeats(tenant_id, expires_at)",
        ),
    ),
    Migration(
        version=7,
        name="phase8_retention_and_legal_hold",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS legal_holds (
                hold_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                logical_document_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                released_at TEXT,
                metadata_json TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_legal_hold_document ON legal_holds(logical_document_id, status)",
            """
            CREATE TABLE IF NOT EXISTS retention_runs (
                run_id TEXT PRIMARY KEY,
                policy_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                evaluated_count INTEGER NOT NULL,
                eligible_json TEXT NOT NULL,
                held_json TEXT NOT NULL,
                purged_json TEXT NOT NULL,
                dry_run INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_retention_tenant_created ON retention_runs(tenant_id, created_at)",
        ),
    ),
    Migration(
        version=8,
        name="phase8_idempotency_and_replication",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS job_idempotency (
                tenant_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                job_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, idempotency_key)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_job_idempotency_job ON job_idempotency(job_id)",
            """
            CREATE TABLE IF NOT EXISTS backup_replications (
                replication_id TEXT PRIMARY KEY,
                backup_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                destination TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                verified INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_replication_backup ON backup_replications(backup_id, created_at)",
        ),
    ),
)


PHASE9_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=9,
        name="phase9_scheduler_leadership",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS leader_leases (
                lease_name TEXT PRIMARY KEY,
                holder_id TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                renewed_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_leader_lease_expiry ON leader_leases(expires_at)",
        ),
    ),
)


CORE_MIGRATIONS: tuple[Migration, ...] = (
    PHASE6_MIGRATIONS + PHASE7_MIGRATIONS + PHASE8_MIGRATIONS + PHASE9_MIGRATIONS
)
# v9 已并入 CORE_MIGRATIONS（2026-09-01 V0.1 实现期修正：v9 定义存在但此前未纳入 CORE，
# 且 PLATFORM 重复组合会导致 version 重复应用）
PLATFORM_MIGRATIONS: tuple[Migration, ...] = CORE_MIGRATIONS
V01_HARDENING_MIGRATION: Migration = Migration(
    version=11,
    name="v01_governance_hardening",
    statements=(
        # 11.1 transitions INSERT 白名单：DB 层状态机（伪造 new_status/previous 组合直接 ABORT）
        """
        CREATE TRIGGER IF NOT EXISTS trg_akb_astt_legal_pair
        BEFORE INSERT ON akb_assertion_transitions
        FOR EACH ROW
        WHEN NOT EXISTS (
            SELECT 1 FROM (
                SELECT 'candidate' AS p, 'validated' AS n UNION ALL
                SELECT 'candidate', 'rejected' UNION ALL
                SELECT 'validated', 'asserted' UNION ALL
                SELECT 'validated', 'disputed' UNION ALL
                SELECT 'validated', 'deprecated' UNION ALL
                SELECT 'asserted', 'disputed' UNION ALL
                SELECT 'asserted', 'deprecated' UNION ALL
                SELECT 'disputed', 'asserted' UNION ALL
                SELECT 'disputed', 'deprecated' UNION ALL
                SELECT 'disputed', 'rejected'
            ) legal
            WHERE legal.p = NEW.previous_status AND legal.n = NEW.new_status
        )
        BEGIN
          SELECT RAISE(ABORT, 'INV-005: illegal status pair in assertion_transitions');
        END
        """,
        # 11.1b type 联动：inferred 断言禁止出现 →asserted 的迁移行；hypothesized 禁止 →validated/asserted
        """
        CREATE TRIGGER IF NOT EXISTS trg_akb_astt_type_boundary
        BEFORE INSERT ON akb_assertion_transitions
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1 FROM akb_assertions a
            WHERE a.assertion_id = NEW.assertion_id
              AND ((a.assertion_type = 'inferred' AND NEW.new_status = 'asserted')
                OR (a.assertion_type = 'hypothesized'
                    AND NEW.new_status IN ('validated','asserted')))
        )
        BEGIN
          SELECT RAISE(ABORT, 'INV-002: type-boundary transition forbidden');
        END
        """,
        # 11.2 transitions INSERT 的 provenance 联动：必须指向存在的 provenance 行
        """
        CREATE TRIGGER IF NOT EXISTS trg_akb_astt_provenance_exists
        BEFORE INSERT ON akb_assertion_transitions
        FOR EACH ROW
        WHEN NEW.provenance_ref IS NULL OR NOT EXISTS (
            SELECT 1 FROM akb_provenance p WHERE p.provenance_id = NEW.provenance_ref
        )
        BEGIN
          SELECT RAISE(ABORT, 'INV-005: transition requires existing provenance record');
        END
        """,
        # 11.3 controlled UPDATE 的 provenance_ref 必须等于该 latest transitions 行的 provenance_ref
        #      （伪造 provenance_ref 直接 ABORT——攻击路径 3 修复）
        """
        CREATE TRIGGER IF NOT EXISTS trg_akb_assertions_status_provenance_pair
        BEFORE UPDATE OF status ON akb_assertions
        FOR EACH ROW
        WHEN NEW.status != OLD.status
          AND (SELECT provenance_ref FROM akb_assertion_transitions t
               WHERE t.assertion_id = NEW.assertion_id
                 AND t.new_status = NEW.status
                 AND t.previous_status = OLD.status
                 AND t.rowid = (SELECT MAX(t2.rowid) FROM akb_assertion_transitions t2
                                WHERE t2.assertion_id = NEW.assertion_id
                                  AND t2.new_status = NEW.status
                                  AND t2.previous_status = OLD.status))
              IS NOT NEW.provenance_ref
        BEGIN
          SELECT RAISE(ABORT, 'INV-005: status provenance_ref must match transition record');
        END
        """,
        # 11.4 provenance_ref 无审计改写守卫：status 不变时改 provenance_ref 必须有
        #      对应 transitions 行（防止绕过迁移历史）
        """
        CREATE TRIGGER IF NOT EXISTS trg_akb_assertions_prov_ref_guard
        BEFORE UPDATE OF provenance_ref ON akb_assertions
        FOR EACH ROW
        WHEN NEW.provenance_ref IS NOT OLD.provenance_ref
          AND (SELECT COUNT(*) FROM akb_assertion_transitions t
               WHERE t.assertion_id = NEW.assertion_id
                 AND t.provenance_ref = NEW.provenance_ref) = 0
        BEGIN
          SELECT RAISE(ABORT, 'INV-005: provenance_ref change requires transition record');
        END
        """,
    ),
)

V01_EVIDENCE_CORE_MIGRATION: Migration = Migration(
    version=10,
    name="v01_evidence_core",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS akb_sources (
            source_id       TEXT PRIMARY KEY,
            source_type     TEXT NOT NULL CHECK (source_type IN
                              ('document','database','api','sensor','human','agent','system')),
            name            TEXT NOT NULL CHECK (length(name) > 0),
            authority_score REAL CHECK (authority_score BETWEEN 0 AND 1),
            owner           TEXT,
            access_policy_ref TEXT,
            metadata_json   TEXT NOT NULL DEFAULT '{}',
            created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at      TEXT
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_akb_sources_name_type ON akb_sources(source_type, name)",
        """
        CREATE TABLE IF NOT EXISTS akb_documents (
            document_id   TEXT PRIMARY KEY,
            source_id     TEXT NOT NULL REFERENCES akb_sources(source_id),
            version       TEXT NOT NULL,
            content_hash  TEXT NOT NULL,
            mime_type     TEXT,
            title         TEXT,
            effective_at  TEXT,
            ingested_at   TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            UNIQUE (source_id, content_hash)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_akb_documents_source ON akb_documents(source_id)",
        """
        CREATE TABLE IF NOT EXISTS akb_evidence (
            evidence_id      TEXT PRIMARY KEY,
            document_id      TEXT NOT NULL REFERENCES akb_documents(document_id),
            location_page    INTEGER,
            location_section TEXT,
            location_start   INTEGER,
            location_end     INTEGER,
            content          TEXT NOT NULL,
            evidence_type    TEXT NOT NULL DEFAULT 'text'
                       CHECK (evidence_type IN ('text','table','image','observation','system_record')),
            observed_at      TEXT,
            extraction_method TEXT NOT NULL,
            confidence       REAL CHECK (confidence BETWEEN 0 AND 1),
            metadata_json    TEXT NOT NULL DEFAULT '{}',
            content_hash     TEXT NOT NULL,
            created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            UNIQUE (document_id, content_hash, location_start, location_end)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_akb_evidence_document ON akb_evidence(document_id)",
        """
        CREATE TABLE IF NOT EXISTS akb_semantic_units (
            unit_id        TEXT PRIMARY KEY,
            evidence_id    TEXT NOT NULL REFERENCES akb_evidence(evidence_id),
            unit_type      TEXT NOT NULL,
            normalized_text TEXT NOT NULL,
            entity_candidates_json TEXT NOT NULL DEFAULT '[]',
            relation_candidates_json TEXT NOT NULL DEFAULT '[]',
            temporal_parse_json    TEXT,
            ontology_mapping_json  TEXT,
            extraction_method TEXT NOT NULL,
            extraction_version TEXT NOT NULL,
            created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_akb_su_evidence ON akb_semantic_units(evidence_id)",
        """
        CREATE TABLE IF NOT EXISTS akb_provenance (
            provenance_id  TEXT PRIMARY KEY,
            actor_id       TEXT NOT NULL,
            actor_kind     TEXT NOT NULL CHECK (actor_kind IN ('human','system','agent','llm')),
            activity       TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            occurred_at    TEXT NOT NULL,
            inputs_json    TEXT NOT NULL DEFAULT '[]',
            metadata_json  TEXT NOT NULL DEFAULT '{}',
            created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS akb_assertions (
            assertion_id   TEXT PRIMARY KEY,
            subject_ref    TEXT NOT NULL,
            predicate_ref  TEXT NOT NULL,
            object_kind    TEXT NOT NULL CHECK (object_kind IN ('literal','entity_ref')),
            object_value   TEXT,
            object_datatype TEXT,
            object_unit    TEXT,
            object_entity_ref TEXT,
            assertion_type TEXT NOT NULL CHECK (assertion_type IN
                             ('extracted','observed','asserted','inferred','hypothesized')),
            status         TEXT NOT NULL CHECK (status IN
                             ('candidate','validated','asserted','disputed','rejected','deprecated')),
            confidence     REAL CHECK (confidence BETWEEN 0 AND 1),
            evidence_refs_json TEXT NOT NULL DEFAULT '[]',
            source_unit_refs_json TEXT NOT NULL DEFAULT '[]',
            provenance_ref TEXT REFERENCES akb_provenance(provenance_id),
            temporal_scope_json TEXT,
            ontology_scope TEXT NOT NULL,
            derivation_json TEXT,
            canonical_json TEXT NOT NULL,
            created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at     TEXT,
            CHECK (object_kind = 'literal'  OR object_entity_ref IS NOT NULL),
            CHECK (object_kind != 'literal' OR object_value IS NOT NULL),
            CHECK (status NOT IN ('validated','asserted','disputed') OR
                   json_array_length(evidence_refs_json) >= 1),
            CHECK (assertion_type != 'inferred' OR derivation_json IS NOT NULL)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_akb_assertions_subject ON akb_assertions(subject_ref)",
        "CREATE INDEX IF NOT EXISTS ix_akb_assertions_status  ON akb_assertions(status)",
        "CREATE INDEX IF NOT EXISTS ix_akb_assertions_spo    ON akb_assertions(subject_ref, predicate_ref, object_value)",
        """
        CREATE TABLE IF NOT EXISTS akb_assertion_transitions (
            transition_id   TEXT PRIMARY KEY,
            assertion_id    TEXT NOT NULL REFERENCES akb_assertions(assertion_id),
            previous_status TEXT NOT NULL,
            new_status      TEXT NOT NULL CHECK (new_status IN
                              ('candidate','validated','asserted','disputed','rejected','deprecated')),
            actor_id        TEXT NOT NULL,
            reason          TEXT NOT NULL CHECK (length(reason) > 0),
            policy_version  TEXT NOT NULL,
            provenance_ref  TEXT REFERENCES akb_provenance(provenance_id),
            created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_akb_astt_assertion ON akb_assertion_transitions(assertion_id)",
        # append-only 触发器（INV-005）
        """
        CREATE TRIGGER IF NOT EXISTS trg_akb_evidence_no_update
        BEFORE UPDATE ON akb_evidence
        BEGIN
          SELECT RAISE(ABORT, 'INV-005: akb_evidence is append-only');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_akb_evidence_no_delete
        BEFORE DELETE ON akb_evidence
        BEGIN
          SELECT RAISE(ABORT, 'INV-005: akb_evidence is append-only');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_akb_astt_no_update
        BEFORE UPDATE ON akb_assertion_transitions
        BEGIN
          SELECT RAISE(ABORT, 'INV-005: assertion transitions are append-only');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_akb_astt_no_delete
        BEFORE DELETE ON akb_assertion_transitions
        BEGIN
          SELECT RAISE(ABORT, 'INV-005: assertion transitions are append-only');
        END
        """,
        # akb_assertions 受控更新：不可变列守卫 + status 变更须有同事务 transitions 行
        """
        CREATE TRIGGER IF NOT EXISTS trg_akb_assertions_immutable
        BEFORE UPDATE ON akb_assertions
        FOR EACH ROW
        WHEN NEW.subject_ref != OLD.subject_ref
          OR NEW.predicate_ref != OLD.predicate_ref
          OR NEW.object_kind != OLD.object_kind
          OR NEW.object_value IS NOT OLD.object_value
          OR NEW.object_entity_ref IS NOT OLD.object_entity_ref
          OR NEW.object_datatype IS NOT OLD.object_datatype
          OR NEW.object_unit IS NOT OLD.object_unit
          OR NEW.assertion_type != OLD.assertion_type
          OR NEW.canonical_json != OLD.canonical_json
          OR NEW.created_at != OLD.created_at
          OR NEW.evidence_refs_json != OLD.evidence_refs_json
        BEGIN
          SELECT RAISE(ABORT, 'INV-005: immutable assertion columns changed');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_akb_assertions_controlled_status
        BEFORE UPDATE OF status ON akb_assertions
        FOR EACH ROW
        WHEN NEW.status != OLD.status
          AND (SELECT COUNT(*) FROM akb_assertion_transitions t
               WHERE t.assertion_id = NEW.assertion_id
                 AND t.new_status = NEW.status
                 AND t.previous_status = OLD.status
                 AND t.rowid = (SELECT MAX(t2.rowid) FROM akb_assertion_transitions t2
                                WHERE t2.assertion_id = NEW.assertion_id)) = 0
        BEGIN
          SELECT RAISE(ABORT,
            'INV-005: status change requires matching latest assertion_transitions row');
        END
        """,
        # graph_edges 加列（AG-001 / PATH A&B 共用列）
        "ALTER TABLE graph_edges ADD COLUMN assertion_ref TEXT REFERENCES akb_assertions(assertion_id)",
        "CREATE INDEX IF NOT EXISTS ix_graph_edges_ast ON graph_edges(assertion_ref)",
    ),
)

V02_SEMANTIC_COMPILATION_MIGRATION: Migration = Migration(
    version=12,
    name="v02_semantic_compilation",
    statements=(
        # akb_semantic_units 扩展列（V0.2_MIGRATION_PLAN：provenance 链 + 幂等锚点）
        "ALTER TABLE akb_semantic_units ADD COLUMN provenance_ref TEXT",
        "ALTER TABLE akb_semantic_units ADD COLUMN compiler_run_ref TEXT",
        "ALTER TABLE akb_semantic_units ADD COLUMN configuration_hash TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE akb_semantic_units ADD COLUMN content_fingerprint TEXT",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_akb_su_fingerprint ON akb_semantic_units(content_fingerprint)",
        # run 级聚合审计实体（provenance 八问的最小充分结构）
        """
        CREATE TABLE IF NOT EXISTS akb_compilation_runs (
            run_id             TEXT PRIMARY KEY,
            evidence_ids_json  TEXT NOT NULL DEFAULT '[]',
            compiler_version   TEXT NOT NULL,
            configuration_hash TEXT NOT NULL,
            ontology_version   TEXT,
            provider_id        TEXT NOT NULL,
            actor_id           TEXT NOT NULL,
            policy_version     TEXT NOT NULL,
            status             TEXT NOT NULL CHECK (status IN ('running','completed','failed','partial')),
            warnings_json      TEXT NOT NULL DEFAULT '[]',
            created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            finished_at        TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_akb_runs_status ON akb_compilation_runs(status)",
    ),
)

V03_MULTI_EVIDENCE_SYNTHESIS_MIGRATION: Migration = Migration(
    version=13,
    name="v03_multi_evidence_synthesis",
    statements=(
        # EvidenceSet：成员清单+Set 指纹锚（幂等载体；成员 canonical 字典序）
        """
        CREATE TABLE IF NOT EXISTS akb_evidence_sets (
            set_id             TEXT PRIMARY KEY,
            members_json       TEXT NOT NULL,
            set_fingerprint    TEXT NOT NULL,
            synthesis_version  TEXT NOT NULL,
            configuration_hash TEXT NOT NULL,
            actor_id           TEXT NOT NULL,
            created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_akb_sets_fingerprint ON akb_evidence_sets(set_fingerprint)",
        # SynthesisRun：run 聚合审计（对齐/冲突/权重随 run JSON 快照；fingerprint 锚）
        """
        CREATE TABLE IF NOT EXISTS akb_synthesis_runs (
            run_id             TEXT PRIMARY KEY,
            set_id             TEXT NOT NULL REFERENCES akb_evidence_sets(set_id),
            members_json       TEXT NOT NULL,
            synthesis_version  TEXT NOT NULL,
            configuration_hash TEXT NOT NULL,
            provider_id        TEXT NOT NULL,
            actor_id           TEXT NOT NULL,
            policy_version     TEXT NOT NULL,
            status             TEXT NOT NULL CHECK (status IN
                                ('running','completed','failed','partial','capped')),
            alignment_json     TEXT,
            conflicts_json     TEXT,
            weights_json       TEXT,
            fingerprint        TEXT,
            warnings_json      TEXT NOT NULL DEFAULT '[]',
            created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            finished_at        TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_akb_synruns_status ON akb_synthesis_runs(status)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_akb_synruns_fingerprint ON akb_synthesis_runs(fingerprint)",
    ),
)

ALL_MIGRATIONS: tuple[Migration, ...] = (
    CORE_MIGRATIONS
    + (V01_EVIDENCE_CORE_MIGRATION, V01_HARDENING_MIGRATION,
       V02_SEMANTIC_COMPILATION_MIGRATION, V03_MULTI_EVIDENCE_SYNTHESIS_MIGRATION)
)



class SchemaMigrator:
    """Monotonic SQLite migration runner used by production adapters."""

    def __init__(self, connection: sqlite3.Connection, migrations: Iterable[Migration] = ALL_MIGRATIONS) -> None:
        self.connection = connection
        self.migrations = tuple(sorted(migrations, key=lambda item: item.version))

    def migrate(self) -> list[int]:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {int(row[0]) for row in self.connection.execute("SELECT version FROM schema_migrations")}
        completed: list[int] = []
        with self.connection:
            for migration in self.migrations:
                if migration.version in applied:
                    continue
                for statement in migration.statements:
                    self.connection.execute(statement)
                self.connection.execute(
                    "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                    (migration.version, migration.name, _utc_now_iso()),
                )
                completed.append(migration.version)
        return completed

    def current_version(self) -> int:
        try:
            row = self.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        except sqlite3.OperationalError:
            return 0
        return int(row[0] or 0)
