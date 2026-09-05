from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import copy2
from typing import Any, Protocol
from urllib import error, request

from .backup import BackupRecord, SQLiteBackupManager


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


@dataclass(frozen=True)
class ReplicationResult:
    destination: str
    sha256: str
    size_bytes: int
    verified: bool

    def to_dict(self) -> dict[str, str | int | bool]:
        return asdict(self)


class BackupReplicator(Protocol):
    def replicate(self, backup: BackupRecord) -> ReplicationResult: ...


@dataclass(frozen=True)
class FilesystemBackupReplicator:
    destination_root: Path

    def replicate(self, backup: BackupRecord) -> ReplicationResult:
        source = Path(backup.path)
        if not SQLiteBackupManager.verify(source):
            raise ValueError("source backup failed integrity verification")
        self.destination_root.mkdir(parents=True, exist_ok=True)
        target = self.destination_root / source.name
        copy2(source, target)
        digest = _sha256(target)
        verified = SQLiteBackupManager.verify(target) and digest == backup.sha256
        if not verified:
            raise RuntimeError("replicated backup verification failed")
        return ReplicationResult(
            destination=str(target),
            sha256=digest,
            size_bytes=target.stat().st_size,
            verified=True,
        )


@dataclass(frozen=True)
class HTTPBackupReplicator:
    endpoint: str
    api_key: str = ""
    timeout_seconds: float = 60.0

    def replicate(self, backup: BackupRecord) -> ReplicationResult:
        source = Path(backup.path)
        if not SQLiteBackupManager.verify(source):
            raise ValueError("source backup failed integrity verification")
        headers = {
            "Content-Type": "application/octet-stream",
            "X-Backup-ID": backup.backup_id,
            "X-Backup-SHA256": backup.sha256,
            "X-Backup-Tenant": backup.tenant_id,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        outbound = request.Request(
            self.endpoint,
            data=source.read_bytes(),
            headers=headers,
            method="PUT",
        )
        try:
            with request.urlopen(outbound, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"backup replication failed: {type(exc).__name__}") from exc
        remote_sha = str(payload.get("sha256") or backup.sha256)
        verified = bool(payload.get("verified", remote_sha == backup.sha256)) and remote_sha == backup.sha256
        if not verified:
            raise RuntimeError("remote backup verification failed")
        return ReplicationResult(
            destination=str(payload.get("destination") or self.endpoint),
            sha256=remote_sha,
            size_bytes=int(payload.get("size_bytes") or source.stat().st_size),
            verified=True,
        )


@dataclass(frozen=True)
class BackupRetentionPolicy:
    keep_last: int = 5
    keep_days: int = 30

    def __post_init__(self) -> None:
        if self.keep_last < 1 or self.keep_days < 0:
            raise ValueError("keep_last must be positive and keep_days non-negative")

    def prune(self, directory: str | Path, *, now: datetime | None = None) -> list[str]:
        root = Path(directory)
        files = sorted(
            (path for path in root.glob("*.sqlite3") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        cutoff = (now or _utc_now()) - timedelta(days=self.keep_days)
        deleted: list[str] = []
        for index, path in enumerate(files):
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            if index < self.keep_last or modified >= cutoff:
                continue
            path.unlink()
            deleted.append(str(path))
        return deleted


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
