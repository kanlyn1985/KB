from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2
from uuid import uuid4

from .migrations import SchemaMigrator


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class BackupRecord:
    backup_id: str
    tenant_id: str
    path: str
    sha256: str
    size_bytes: int
    status: str
    created_at: str

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


class SQLiteBackupManager:
    def __init__(self, source_path: str | Path, *, tenant_id: str = "default") -> None:
        self.source_path = Path(source_path)
        self.tenant_id = tenant_id

    def create_backup(self, destination_dir: str | Path) -> BackupRecord:
        if not self.source_path.exists():
            raise FileNotFoundError(self.source_path)
        destination = Path(destination_dir)
        destination.mkdir(parents=True, exist_ok=True)
        backup_id = f"backup_{uuid4().hex}"
        target = destination / f"{self.tenant_id}-{backup_id}.sqlite3"
        source_connection = sqlite3.connect(self.source_path)
        target_connection = sqlite3.connect(target)
        try:
            source_connection.backup(target_connection)
            target_connection.execute("PRAGMA wal_checkpoint(FULL)")
            target_connection.commit()
        finally:
            target_connection.close()
            source_connection.close()
        status = "verified" if self.verify(target) else "invalid"
        record = BackupRecord(
            backup_id=backup_id,
            tenant_id=self.tenant_id,
            path=str(target),
            sha256=_sha256(target),
            size_bytes=target.stat().st_size,
            status=status,
            created_at=_utc_now_iso(),
        )
        self._record(record)
        if status != "verified":
            raise RuntimeError("backup integrity verification failed")
        return record

    def restore(self, backup_path: str | Path, *, overwrite: bool = False) -> None:
        backup = Path(backup_path)
        if not self.verify(backup):
            raise ValueError("backup failed SQLite integrity verification")
        if self.source_path.exists() and not overwrite:
            raise FileExistsError(self.source_path)
        self.source_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.source_path.with_suffix(self.source_path.suffix + ".restore.tmp")
        copy2(backup, temporary)
        temporary.replace(self.source_path)

    @staticmethod
    def verify(path: str | Path) -> bool:
        target = Path(path)
        if not target.exists() or target.stat().st_size == 0:
            return False
        connection = sqlite3.connect(target)
        try:
            row = connection.execute("PRAGMA integrity_check").fetchone()
            return bool(row and str(row[0]).lower() == "ok")
        except sqlite3.DatabaseError:
            return False
        finally:
            connection.close()

    def _record(self, record: BackupRecord) -> None:
        connection = sqlite3.connect(self.source_path)
        try:
            SchemaMigrator(connection).migrate()
            with connection:
                connection.execute(
                    """
                    INSERT INTO backup_history(
                        backup_id, tenant_id, path, sha256, size_bytes, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.backup_id,
                        record.tenant_id,
                        record.path,
                        record.sha256,
                        record.size_bytes,
                        record.status,
                        record.created_at,
                    ),
                )
        finally:
            connection.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
