from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .documents import DocumentRecord


@dataclass(frozen=True)
class EvidenceBlock:
    """Traceable evidence unit compiled from a source document."""

    evidence_id: str
    document_id: str
    block_no: int
    text: str
    normalized_text: str
    page_no: int | None = None
    section_path: str | None = None
    block_type: str = "text"
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_text(text: str) -> str:
    """Normalize whitespace without changing domain tokens, numbers, or units."""

    cleaned = text.replace("\u3000", " ")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def build_evidence_blocks(
    document: DocumentRecord,
    text: str,
    *,
    max_chars: int = 900,
    overlap_chars: int = 0,
) -> list[EvidenceBlock]:
    """Build deterministic evidence blocks from plain text.

    The splitter is deliberately conservative: it prefers paragraph boundaries
    and never rewrites numbers, units, acronyms, or table-like rows. Production
    parsers can pass already segmented page/table/paragraph text into this same
    contract later.
    """

    normalized = normalize_text(text)
    if not normalized:
        return []

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(paragraph) <= max_chars:
            current = paragraph
        else:
            chunks.extend(_split_long_text(paragraph, max_chars=max_chars, overlap_chars=overlap_chars))
    if current:
        chunks.append(current)

    blocks: list[EvidenceBlock] = []
    for index, chunk in enumerate(chunks, start=1):
        section_path = _guess_section_path(chunk)
        evidence_id = _evidence_id(document.document_id, index, chunk)
        blocks.append(
            EvidenceBlock(
                evidence_id=evidence_id,
                document_id=document.document_id,
                block_no=index,
                text=chunk,
                normalized_text=normalize_text(chunk),
                section_path=section_path,
                block_type="table_like" if _looks_table_like(chunk) else "text",
                confidence=1.0,
            )
        )
    return blocks


def _split_long_text(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = max(text.rfind("。", start, end), text.rfind("；", start, end), text.rfind(";", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap_chars, end)
    return [chunk for chunk in chunks if chunk]


def _guess_section_path(text: str) -> str | None:
    first_line = text.splitlines()[0].strip() if text.splitlines() else ""
    if re.match(r"^(?:第\s*)?\d+(?:\.\d+)*[、.\s]+", first_line):
        return first_line[:120]
    if re.match(r"^[A-Z]?(?:\d+\.)+\d+\s+", first_line):
        return first_line[:120]
    return None


def _looks_table_like(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    pipe_rows = sum(1 for line in lines if "|" in line or "\t" in line)
    aligned_rows = sum(1 for line in lines if len(re.split(r"\s{2,}", line.strip())) >= 3)
    return pipe_rows >= 1 or aligned_rows >= 2


def _evidence_id(document_id: str, block_no: int, text: str) -> str:
    digest = hashlib.sha256(f"{document_id}:{block_no}:{text}".encode("utf-8")).hexdigest()
    return f"evd_{digest[:16]}"
