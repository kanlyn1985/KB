from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .db import connect
from .ids import next_prefixed_id


@dataclass(frozen=True)
class RegisterResult:
    doc_id: str
    job_id: str | None
    deduplicated: bool
    stored_path: Path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _detect_source_type(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".txt", ".text"}:
        return "text"
    if suffix in {".doc", ".docx"}:
        return "word"
    if suffix in {".xls", ".xlsx"}:
        return "excel"
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        return "image"
    return "file"


def _display_filename_for_stored_file(file_path: Path) -> str:
    name = file_path.name
    if len(name) > 12 and name.startswith("DOC-") and "_" in name:
        _, remainder = name.split("_", 1)
        if remainder:
            return remainder
    return name


def _insert_document_record(
    db,
    *,
    source_filename: str,
    source_path: Path,
    source_type: str,
    mime_type: str | None,
    sha256: str,
    file_size: int,
    now: str,
) -> tuple[str, str]:
    doc_id = next_prefixed_id(db, "document", "DOC")
    job_id = next_prefixed_id(db, "job", "JOB")
    db.execute(
        """
        INSERT INTO documents (
            doc_id, source_filename, source_type, mime_type, sha256, file_size,
            page_count, language, version_label, source_path, ingest_time,
            update_time, parse_status, quality_status, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            doc_id,
            source_filename,
            source_type,
            mime_type,
            sha256,
            file_size,
            None,
            None,
            None,
            str(source_path),
            now,
            now,
            "queued",
            "pending",
            1,
        ),
    )
    return doc_id, job_id


def register_stored_document(
    workspace_root: Path,
    stored_file: Path,
    *,
    source_filename: str | None = None,
) -> RegisterResult:
    stored_file = stored_file.resolve()
    if not stored_file.exists() or not stored_file.is_file():
        raise FileNotFoundError(stored_file)

    paths = AppPaths.from_root(workspace_root)
    db = connect(paths.db_file)
    sha256 = _sha256(stored_file)
    mime_type, _ = mimetypes.guess_type(stored_file.name)
    now = _utc_now()

    try:
        existing = db.execute(
            """
            SELECT doc_id, source_path
            FROM documents
            WHERE sha256 = ? AND is_active = 1
            ORDER BY ingest_time DESC
            LIMIT 1
            """,
            (sha256,),
        ).fetchone()
        if existing is not None:
            return RegisterResult(
                doc_id=existing["doc_id"],
                job_id=None,
                deduplicated=True,
                stored_path=Path(existing["source_path"]),
            )

        display_name = source_filename or _display_filename_for_stored_file(stored_file)
        doc_id, job_id = _insert_document_record(
            db,
            source_filename=display_name,
            source_path=stored_file,
            source_type=_detect_source_type(stored_file),
            mime_type=mime_type,
            sha256=sha256,
            file_size=stored_file.stat().st_size,
            now=now,
        )

        db.execute(
            """
            INSERT INTO jobs (
                job_id, job_type, target_type, target_id, status, priority,
                payload_json, error_message, retry_count, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                "parse_document",
                "document",
                doc_id,
                "pending",
                5,
                json.dumps(
                    {
                        "doc_id": doc_id,
                        "source_file": str(stored_file),
                        "stored_path": str(stored_file),
                        "reused_raw_file": True,
                    },
                    ensure_ascii=False,
                ),
                None,
                0,
                now,
                now,
            ),
        )
        db.commit()
        return RegisterResult(
            doc_id=doc_id,
            job_id=job_id,
            deduplicated=False,
            stored_path=stored_file,
        )
    finally:
        db.close()


def register_document(workspace_root: Path, source_file: Path) -> RegisterResult:
    source_file = source_file.resolve()
    if not source_file.exists() or not source_file.is_file():
        raise FileNotFoundError(source_file)

    paths = AppPaths.from_root(workspace_root)
    db = connect(paths.db_file)
    sha256 = _sha256(source_file)
    mime_type, _ = mimetypes.guess_type(source_file.name)
    now = _utc_now()

    try:
        existing = db.execute(
            """
            SELECT doc_id, source_path
            FROM documents
            WHERE sha256 = ? AND is_active = 1
            ORDER BY ingest_time DESC
            LIMIT 1
            """,
            (sha256,),
        ).fetchone()
        if existing is not None:
            return RegisterResult(
                doc_id=existing["doc_id"],
                job_id=None,
                deduplicated=True,
                stored_path=Path(existing["source_path"]),
            )

        doc_id, job_id = _insert_document_record(
            db,
            source_filename=source_file.name,
            source_path=Path(paths.raw / f"PENDING_{source_file.name}"),
            source_type=_detect_source_type(source_file),
            mime_type=mime_type,
            sha256=sha256,
            file_size=source_file.stat().st_size,
            now=now,
        )
        target_name = f"{doc_id}_{source_file.name}"
        stored_path = paths.raw / target_name
        shutil.copy2(source_file, stored_path)
        db.execute(
            "UPDATE documents SET source_path = ? WHERE doc_id = ?",
            (str(stored_path), doc_id),
        )

        db.execute(
            """
            INSERT INTO jobs (
                job_id, job_type, target_type, target_id, status, priority,
                payload_json, error_message, retry_count, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                "parse_document",
                "document",
                doc_id,
                "pending",
                5,
                json.dumps(
                    {
                        "doc_id": doc_id,
                        "source_file": str(source_file),
                        "stored_path": str(stored_path),
                    },
                    ensure_ascii=False,
                ),
                None,
                0,
                now,
                now,
            ),
        )
        db.commit()
        return RegisterResult(
            doc_id=doc_id,
            job_id=job_id,
            deduplicated=False,
            stored_path=stored_path,
        )
    finally:
        db.close()
