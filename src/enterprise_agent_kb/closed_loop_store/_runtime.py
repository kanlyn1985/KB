"""Runtime identification: code version hashing and short stable ids.

These functions identify the running code's version for eval/retrieval
provenance. They have no DB or LLM dependencies.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

SOURCE_TREE_GLOB = "*.py"
HASH_HEAD_LENGTH = 12
SHORT_HASH_LENGTH = 16
RUNTIME_UNAVAILABLE = "runtime-unavailable"


def utc_now() -> str:
    """Return current UTC time as ISO-8601 string with seconds precision."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _source_tree_content_hash(source_root: Path) -> str:
    digest = hashlib.sha1()
    for path in sorted(source_root.glob(SOURCE_TREE_GLOB)):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:HASH_HEAD_LENGTH]


@lru_cache(maxsize=1)
def _runtime_code_version() -> str:
    explicit = os.environ.get("EAKB_CODE_VERSION")
    if explicit:
        return explicit.strip()
    try:
        root = Path(__file__).resolve().parents[2]
        return f"src-{_source_tree_content_hash(root / 'src' / 'enterprise_agent_kb')}"
    except (FileNotFoundError, OSError, PermissionError):
        return RUNTIME_UNAVAILABLE


def _short_hash(value: object) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:SHORT_HASH_LENGTH].upper()
