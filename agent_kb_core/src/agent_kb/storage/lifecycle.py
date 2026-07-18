from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agent_kb.core.documents import DocumentRecord
from agent_kb.storage.migrations import SchemaMigrator


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class DocumentVersion:
    version_id: str
    logical_document_id: str
    compiler_document_id: str
    version_label: str | None
    sha256: str
    size_bytes: int
    status: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DocumentLifecycleRecord:
    logical_document_id: str
    title: str
    source_type: str
    source_uri: str | None
    active_version_id: str | None
    status: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str
    versions: list[DocumentVersion]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["versions"] = [item.to_dict() for item in self.versions]
        return payload


class DocumentLifecycleStore:
    """Version and lifecycle controls over compiler document records."""

    VALID_STATUSES = {"active", "deprecated", "deleted"}

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        SchemaMigrator(connection).migrate()

    def register_version(
        self,
        document: DocumentRecord,
        *,
        logical_document_id: str | None = None,
        activate: bool = True,
    ) -> DocumentVersion:
        logical_id = logical_document_id or _logical_id(document)
        now = _utc_now_iso()
        version_id = f"ver_{uuid4().hex}"
        version = DocumentVersion(
            version_id=version_id,
            logical_document_id=logical_id,
            compiler_document_id=document.document_id,
            version_label=document.version_label,
            sha256=document.sha256,
            size_bytes=document.size_bytes,
            status="active" if activate else "candidate",
            created_at=now,
        )
        with self.connection:
            existing = self.connection.execute(
                "SELECT logical_document_id FROM documents WHERE logical_document_id = ?",
                (logical_id,),
            ).fetchone()
            if existing is None:
                self.connection.execute(
                    """
                    INSERT INTO documents(
                        logical_document_id, title, source_type, source_uri,
                        active_version_id, status, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        logical_id,
                        document.title,
                        document.source_type,
                        document.source_uri,
                        version_id if activate else None,
                        "active" if activate else "deprecated",
                        _json(document.metadata),
                        now,
                        now,
                    ),
                )
            elif activate:
                self.connection.execute(
                    "UPDATE document_versions SET status = 'superseded' WHERE logical_document_id = ? AND status = 'active'",
                    (logical_id,),
                )
                self.connection.execute(
                    """
                    UPDATE documents
                    SET title = ?, source_type = ?, source_uri = ?, active_version_id = ?,
                        status = 'active', metadata_json = ?, updated_at = ?
                    WHERE logical_document_id = ?
                    """,
                    (
                        document.title,
                        document.source_type,
                        document.source_uri,
                        version_id,
                        _json(document.metadata),
                        now,
                        logical_id,
                    ),
                )
            self.connection.execute(
                """
                INSERT INTO document_versions(
                    version_id, logical_document_id, compiler_document_id,
                    version_label, sha256, size_bytes, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version.version_id,
                    version.logical_document_id,
                    version.compiler_document_id,
                    version.version_label,
                    version.sha256,
                    version.size_bytes,
                    version.status,
                    version.created_at,
                ),
            )
        return version

    def set_status(self, logical_document_id: str, status: str) -> None:
        normalized = status.strip().lower()
        if normalized not in self.VALID_STATUSES:
            raise ValueError(f"unsupported document status: {status}")
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE documents SET status = ?, updated_at = ? WHERE logical_document_id = ?",
                (normalized, _utc_now_iso(), logical_document_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(logical_document_id)
            if normalized != "active":
                self.connection.execute(
                    "UPDATE document_versions SET status = ? WHERE logical_document_id = ? AND status = 'active'",
                    (normalized, logical_document_id),
                )

    def activate_version(self, logical_document_id: str, version_id: str) -> None:
        row = self.connection.execute(
            "SELECT version_id FROM document_versions WHERE logical_document_id = ? AND version_id = ?",
            (logical_document_id, version_id),
        ).fetchone()
        if row is None:
            raise KeyError(version_id)
        now = _utc_now_iso()
        with self.connection:
            self.connection.execute(
                "UPDATE document_versions SET status = 'superseded' WHERE logical_document_id = ? AND status = 'active'",
                (logical_document_id,),
            )
            self.connection.execute(
                "UPDATE document_versions SET status = 'active' WHERE version_id = ?",
                (version_id,),
            )
            self.connection.execute(
                "UPDATE documents SET active_version_id = ?, status = 'active', updated_at = ? WHERE logical_document_id = ?",
                (version_id, now, logical_document_id),
            )

    def get(self, logical_document_id: str) -> DocumentLifecycleRecord | None:
        row = self.connection.execute(
            "SELECT * FROM documents WHERE logical_document_id = ?",
            (logical_document_id,),
        ).fetchone()
        if row is None:
            return None
        versions = [
            _version_from_row(item)
            for item in self.connection.execute(
                "SELECT * FROM document_versions WHERE logical_document_id = ? ORDER BY created_at DESC",
                (logical_document_id,),
            )
        ]
        return DocumentLifecycleRecord(
            logical_document_id=row["logical_document_id"],
            title=row["title"],
            source_type=row["source_type"],
            source_uri=row["source_uri"],
            active_version_id=row["active_version_id"],
            status=row["status"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            versions=versions,
        )

    def list_documents(self, *, include_deleted: bool = False) -> list[DocumentLifecycleRecord]:
        query = "SELECT logical_document_id FROM documents"
        params: tuple[Any, ...] = ()
        if not include_deleted:
            query += " WHERE status != ?"
            params = ("deleted",)
        query += " ORDER BY updated_at DESC"
        records: list[DocumentLifecycleRecord] = []
        for row in self.connection.execute(query, params):
            record = self.get(row["logical_document_id"])
            if record is not None:
                records.append(record)
        return records


def _logical_id(document: DocumentRecord) -> str:
    source_key = str(document.source_uri or document.title or document.document_id).strip().lower()
    safe = "".join(char if char.isalnum() else "_" for char in source_key)
    safe = "_".join(part for part in safe.split("_") if part)
    return f"ldoc_{safe[:48]}" if safe else f"ldoc_{document.document_id}"


def _version_from_row(row: sqlite3.Row) -> DocumentVersion:
    return DocumentVersion(
        version_id=row["version_id"],
        logical_document_id=row["logical_document_id"],
        compiler_document_id=row["compiler_document_id"],
        version_label=row["version_label"],
        sha256=row["sha256"],
        size_bytes=int(row["size_bytes"]),
        status=row["status"],
        created_at=row["created_at"],
    )
