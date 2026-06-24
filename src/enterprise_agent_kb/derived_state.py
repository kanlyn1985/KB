from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from sqlite3 import Connection
from typing import Iterable

from .config import AppPaths
from .db import connect


@dataclass(frozen=True)
class DerivedStateSpec:
    state_id: str
    kind: str
    source_tables: tuple[str, ...]
    source_files: tuple[str, ...]
    artifact_tables: tuple[str, ...]
    artifact_files: tuple[str, ...]
    freshness_policy: str
    rebuild_command: str
    description: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DerivedStateCheck:
    state_id: str
    status: str
    severity: str
    source_version: str
    artifact_version: str
    source_count: int | None
    artifact_count: int | None
    orphan_count: int
    missing_count: int
    message: str
    recommended_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_FTS_STAMP = "logs/fts_index.stamp"

_SPECS: tuple[DerivedStateSpec, ...] = (
    DerivedStateSpec(
        state_id="facts_fts",
        kind="fts_index",
        source_tables=("facts",),
        source_files=(),
        artifact_tables=("facts_fts",),
        artifact_files=(_FTS_STAMP,),
        freshness_policy="source_signature_and_count",
        rebuild_command="rebuild-derived-state --scope fts",
        description="Full-text search index derived from facts.",
    ),
    DerivedStateSpec(
        state_id="evidence_fts",
        kind="fts_index",
        source_tables=("evidence",),
        source_files=(),
        artifact_tables=("evidence_fts",),
        artifact_files=(_FTS_STAMP,),
        freshness_policy="source_signature_and_count",
        rebuild_command="rebuild-derived-state --scope fts",
        description="Full-text search index derived from evidence.",
    ),
    DerivedStateSpec(
        state_id="wiki_fts",
        kind="fts_index",
        source_tables=("wiki_pages", "entities"),
        source_files=(),
        artifact_tables=("wiki_fts",),
        artifact_files=(_FTS_STAMP,),
        freshness_policy="source_signature_and_count",
        rebuild_command="rebuild-derived-state --scope fts",
        description="Full-text search index derived from non-stale wiki pages.",
    ),
    DerivedStateSpec(
        state_id="wiki_chunks_fts",
        kind="fts_index",
        source_tables=("wiki_chunks",),
        source_files=(),
        artifact_tables=("wiki_chunks_fts",),
        artifact_files=(_FTS_STAMP,),
        freshness_policy="source_signature_and_count",
        rebuild_command="rebuild-derived-state --scope fts",
        description="Full-text search index derived from wiki chunk sections.",
    ),
)


def derived_state_specs() -> tuple[DerivedStateSpec, ...]:
    return _SPECS


def get_derived_state_spec(state_id: str) -> DerivedStateSpec | None:
    for spec in _SPECS:
        if spec.state_id == state_id:
            return spec
    return None


def check_derived_state(
    workspace_root: Path,
    state_id: str | None = None,
    connection: Connection | None = None,
) -> list[DerivedStateCheck]:
    specs = _selected_specs(state_id)
    paths = AppPaths.from_root(workspace_root)
    if connection is None and not paths.db_file.exists():
        return [_missing_database_check(spec) for spec in specs]

    own_connection = connection is None
    if own_connection:
        connection = connect(paths.db_file)

    try:
        assert connection is not None
        return [_check_spec(paths, connection, spec) for spec in specs]
    finally:
        if own_connection and connection is not None:
            connection.close()


def _selected_specs(state_id: str | None) -> tuple[DerivedStateSpec, ...]:
    if state_id is None:
        return _SPECS
    spec = get_derived_state_spec(state_id)
    if spec is None:
        raise ValueError(f"Unknown derived state id: {state_id}")
    return (spec,)


def _missing_database_check(spec: DerivedStateSpec) -> DerivedStateCheck:
    return DerivedStateCheck(
        state_id=spec.state_id,
        status="missing",
        severity="fail",
        source_version="db:missing",
        artifact_version="db:missing",
        source_count=None,
        artifact_count=None,
        orphan_count=0,
        missing_count=0,
        message=f"{spec.state_id} cannot be checked because the workspace database is missing",
        recommended_actions=(spec.rebuild_command,),
    )


def _check_spec(
    paths: AppPaths,
    connection: Connection,
    spec: DerivedStateSpec,
) -> DerivedStateCheck:
    missing_source_tables = [table for table in spec.source_tables if not _table_exists(connection, table)]
    missing_artifact_tables = [table for table in spec.artifact_tables if not _table_exists(connection, table)]
    stamp_path = _artifact_file_path(paths, spec)
    source_version = (
        "source-table:missing"
        if missing_source_tables
        else _source_version(paths, connection, spec.state_id)
    )
    artifact_version = _artifact_version_for_state(stamp_path, spec.state_id)

    if missing_source_tables:
        return DerivedStateCheck(
            state_id=spec.state_id,
            status="missing",
            severity="fail",
            source_version=source_version,
            artifact_version=artifact_version,
            source_count=None,
            artifact_count=None,
            orphan_count=0,
            missing_count=0,
            message=(
                f"{spec.state_id} cannot be checked because source table(s) are missing: "
                f"{', '.join(missing_source_tables)}"
            ),
            recommended_actions=(),
        )

    if missing_artifact_tables:
        return DerivedStateCheck(
            state_id=spec.state_id,
            status="missing",
            severity="fail",
            source_version=source_version,
            artifact_version=artifact_version,
            source_count=_source_count(connection, spec.state_id),
            artifact_count=None,
            orphan_count=0,
            missing_count=0,
            message=(
                f"{spec.state_id} artifact table(s) are missing: "
                f"{', '.join(missing_artifact_tables)}"
            ),
            recommended_actions=(spec.rebuild_command,),
        )

    source_ids = _source_ids(connection, spec.state_id)
    artifact_ids = _artifact_ids(connection, spec.state_id)
    source_id_set = set(source_ids)
    artifact_id_set = set(artifact_ids)
    missing_ids = source_id_set - artifact_id_set
    orphan_ids = artifact_id_set - source_id_set

    stale_reasons: list[str] = []
    if not stamp_path.exists():
        stale_reasons.append("stamp file is missing")
    elif artifact_version != source_version:
        stale_reasons.append("source signature differs from stamp")
    if len(source_ids) != len(artifact_ids):
        stale_reasons.append(
            f"count mismatch: source={len(source_ids)}, artifact={len(artifact_ids)}"
        )
    if missing_ids:
        stale_reasons.append(f"missing indexed rows: {len(missing_ids)}")
    if orphan_ids:
        stale_reasons.append(f"orphan indexed rows: {len(orphan_ids)}")

    if stale_reasons:
        return DerivedStateCheck(
            state_id=spec.state_id,
            status="stale",
            severity="warn",
            source_version=source_version,
            artifact_version=artifact_version,
            source_count=len(source_ids),
            artifact_count=len(artifact_ids),
            orphan_count=len(orphan_ids),
            missing_count=len(missing_ids),
            message=f"{spec.state_id} is stale: {'; '.join(stale_reasons)}",
            recommended_actions=(spec.rebuild_command,),
        )

    return DerivedStateCheck(
        state_id=spec.state_id,
        status="fresh",
        severity="ok",
        source_version=source_version,
        artifact_version=artifact_version,
        source_count=len(source_ids),
        artifact_count=len(artifact_ids),
        orphan_count=0,
        missing_count=0,
        message=f"{spec.state_id} is fresh",
        recommended_actions=(),
    )


def _table_exists(connection: Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view') AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _artifact_file_path(paths: AppPaths, spec: DerivedStateSpec) -> Path:
    if not spec.artifact_files:
        return paths.root
    return paths.root / spec.artifact_files[0]


def _source_version(paths: AppPaths, connection: Connection, state_id: str) -> str:
    if not paths.db_file.exists():
        return "db:missing"
    return _source_signature(connection, state_id)


def write_fts_freshness_stamp(paths: AppPaths, connection: Connection) -> None:
    stamp_path = paths.logs / "fts_index.stamp"
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    states = {
        spec.state_id: _source_signature(connection, spec.state_id)
        for spec in _SPECS
        if spec.kind == "fts_index"
    }
    stamp_path.write_text(
        json.dumps({"version": 1, "states": states}, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _artifact_version_for_state(stamp_path: Path, state_id: str) -> str:
    if not stamp_path.exists():
        return "stamp:missing"
    try:
        payload = json.loads(stamp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return f"stamp-legacy-mtime:{stamp_path.stat().st_mtime_ns}"
    if not isinstance(payload, dict):
        return f"stamp-legacy-mtime:{stamp_path.stat().st_mtime_ns}"
    states = payload.get("states")
    if not isinstance(states, dict):
        return f"stamp-legacy-mtime:{stamp_path.stat().st_mtime_ns}"
    value = states.get(state_id)
    if value is None:
        return "stamp-state:missing"
    return str(value)


def _source_signature(connection: Connection, state_id: str) -> str:
    rows = _source_signature_rows(connection, state_id)
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        digest.update(b"\n")
    return f"source-signature:{len(rows)}:{digest.hexdigest()[:16]}"


def _source_signature_rows(connection: Connection, state_id: str) -> list[dict[str, object]]:
    if state_id == "facts_fts":
        rows = connection.execute(
            """
            SELECT fact_id, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
                   predicate, object_value
            FROM facts
            ORDER BY fact_id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    if state_id == "evidence_fts":
        rows = connection.execute(
            """
            SELECT evidence_id, doc_id, page_no, normalized_text
            FROM evidence
            ORDER BY evidence_id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    if state_id == "wiki_fts":
        rows = connection.execute(
            """
            SELECT w.page_id, json_extract(w.source_doc_ids_json, '$[0]') AS doc_id,
                   w.title, w.slug, COALESCE(w.trust_status, '') AS trust_status,
                   COALESCE(e.entity_status, '') AS entity_status
            FROM wiki_pages w
            LEFT JOIN entities e ON e.entity_id = w.entity_id
            WHERE COALESCE(w.trust_status, '') NOT IN ('stale', 'deprecated')
              AND (w.entity_id IS NULL OR e.entity_status = 'ready')
            ORDER BY w.page_id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    if state_id == "wiki_chunks_fts":
        rows = connection.execute(
            """
            SELECT chunk_id, doc_id, source_standard, section_title, body_text
            FROM wiki_chunks
            ORDER BY chunk_id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    raise ValueError(f"Unsupported derived state id: {state_id}")
    return f"stamp-mtime:{stamp_path.stat().st_mtime_ns}"


def _source_count(connection: Connection, state_id: str) -> int:
    return len(_source_ids(connection, state_id))


def _source_ids(connection: Connection, state_id: str) -> tuple[str, ...]:
    if state_id == "facts_fts":
        rows = connection.execute("SELECT fact_id FROM facts").fetchall()
        return _row_values(rows, "fact_id")
    if state_id == "evidence_fts":
        rows = connection.execute("SELECT evidence_id FROM evidence").fetchall()
        return _row_values(rows, "evidence_id")
    if state_id == "wiki_fts":
        rows = connection.execute(
            """
            SELECT w.page_id
            FROM wiki_pages w
            LEFT JOIN entities e ON e.entity_id = w.entity_id
            WHERE COALESCE(w.trust_status, '') NOT IN ('stale', 'deprecated')
              AND (w.entity_id IS NULL OR e.entity_status = 'ready')
            """
        ).fetchall()
        return _row_values(rows, "page_id")
    if state_id == "wiki_chunks_fts":
        rows = connection.execute("SELECT chunk_id FROM wiki_chunks").fetchall()
        return _row_values(rows, "chunk_id")
    raise ValueError(f"Unsupported derived state id: {state_id}")


def _artifact_ids(connection: Connection, state_id: str) -> tuple[str, ...]:
    artifact_table = state_id
    id_column = "chunk_id" if state_id == "wiki_chunks_fts" else "result_id"
    rows = connection.execute(f"SELECT {id_column} FROM {artifact_table}").fetchall()
    return _row_values(rows, id_column)


def _row_values(rows: Iterable[object], key: str) -> tuple[str, ...]:
    values: list[str] = []
    for row in rows:
        value = row[key]
        if value is not None:
            values.append(str(value))
    return tuple(values)
