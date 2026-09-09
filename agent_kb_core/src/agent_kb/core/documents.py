from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class DocumentRecord:
    """Registered source document metadata.

    This is intentionally smaller than the legacy KB schema. It is the stable
    compiler contract for any raw source, whether the actual bytes came from a
    PDF, Word file, Excel sheet, API connector, or plain text fixture.
    """

    document_id: str
    title: str
    source_type: str
    mime_type: str | None
    sha256: str
    size_bytes: int
    language: str | None = None
    source_uri: str | None = None
    version_label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def register_text_document(
    text: str,
    *,
    title: str,
    source_type: str = "text",
    mime_type: str | None = "text/plain",
    source_uri: str | None = None,
    version_label: str | None = None,
    language: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> DocumentRecord:
    """Register a text payload as a deterministic document record.

    Phase 2 uses plain text as the first compiler surface. Parsers for PDF,
    DOCX, XLSX, OCR and connector records should all eventually materialize
    into the same DocumentRecord + extracted text/table stream.
    """

    encoded = text.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    document_id = f"doc_{digest[:16]}"
    return DocumentRecord(
        document_id=document_id,
        title=title.strip() or document_id,
        source_type=source_type,
        mime_type=mime_type,
        sha256=digest,
        size_bytes=len(encoded),
        language=language,
        source_uri=source_uri,
        version_label=version_label,
        metadata=dict(metadata or {}),
    )
