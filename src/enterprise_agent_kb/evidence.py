from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .db import connect
from .ids import next_prefixed_id


@dataclass(frozen=True)
class EvidenceBuildResult:
    doc_id: str
    evidence_count: int
    skipped_block_count: int
    export_path: Path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip()


def _confidence_for_block(block_type: str, risk_level: str) -> float:
    confidence = 0.95
    if block_type == "ocr_markdown":
        confidence = 0.85
    if risk_level == "medium":
        confidence -= 0.1
    elif risk_level == "high":
        confidence -= 0.2
    return max(0.1, round(confidence, 3))


def _should_skip_block(page_status: str, text: str) -> bool:
    if not text:
        return True
    return page_status == "blocked"


# Minimum meaningful content length (chars)
_MIN_EVIDENCE_LEN = 20

# Academic / publication header patterns (case-insensitive)
_ACADEMIC_NOISE_PATTERNS = (
    "doi:", "doi :", "DOI:",
    "http://", "https://", "www.",
    "@",  # email
    "copyright ©", "© ",
    "published online", "received ", "revised ", "accepted ",
    "issn", "isbn",
    "smart grid",  # journal name (lowercase check)
    "comprehensive energy systems",
    "vol. ", "vol.1", "vol 1", "vol. 1", "(eds)",
    # ISO/IEC standard copyright headers
    "all rights reserved",  # "© ISO 2015 - All rights reserved"
    "© iso", "© iec",  # "© ISO 2015", "© IEC 2017"
    "iso 201", "iec 201",  # "© ISO 2015", "© IEC 2017" (year prefix)
    "price based on",  # "Price based on xx pages"
    "reference number",  # "Reference number ISO 14229-7:2015(E)"
    "international standard",  # "INTERNATIONAL STANDARD"
)


def _is_academic_header_noise(text: str) -> bool:
    """Detect academic-paper / publication-header noise that should not be
    indexed as content evidence.

    These are typically the running header, copyright, journal name, DOI,
    author emails etc. that appear on the first 1-2 pages of a paper.
    """
    lowered = text.lower()
    # Pure header/journal-info line: matches a pattern AND is short (< 300 chars)
    if len(text) > 300:
        return False
    for pattern in _ACADEMIC_NOISE_PATTERNS:
        if pattern in lowered:
            # Make sure the text isn't also carrying real content
            # (real content would have many Chinese chars or be longer)
            cn_chars = sum(1 for c in text if "一" <= c <= "鿿")
            if cn_chars < 10 and len(text) < 200:
                return True
    return False


def _is_noise_block(text: str) -> bool:
    """Decide if a text block is noise (academic header, page number, etc.).

    Returns True if the block should be skipped during evidence extraction.
    """
    if not text or len(text) < _MIN_EVIDENCE_LEN:
        return True
    # Pure-punctuation / whitespace blocks
    stripped = text.strip()
    if not stripped:
        return True
    # Too few Chinese characters and too short = noise
    cn_chars = sum(1 for c in text if "一" <= c <= "鿿")
    if len(text) < 30 and cn_chars < 5:
        return True
    # Academic header / DOI / journal info
    if _is_academic_header_noise(text):
        return True
    return False


def build_evidence_for_document(workspace_root: Path, doc_id: str) -> EvidenceBuildResult:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    now = _utc_now()

    try:
        rows = connection.execute(
            """
            SELECT
                p.page_id,
                p.page_no,
                p.risk_level,
                p.page_status,
                b.block_id,
                b.block_type,
                b.text_content,
                b.raw_text
            FROM pages p
            JOIN blocks b ON b.page_id = p.page_id
            WHERE p.doc_id = ? AND b.doc_id = ?
            ORDER BY p.page_no, b.reading_order
            """,
            (doc_id, doc_id),
        ).fetchall()

        connection.execute("DELETE FROM evidence WHERE doc_id = ?", (doc_id,))

        exported: list[dict[str, object]] = []
        evidence_count = 0
        skipped_block_count = 0

        for row in rows:
            block_type = str(row["block_type"])
            # Previously all structure_markdown blocks were skipped, but
            # they often contain useful content (Foreword, Introduction,
            # Scope, full-text of standard clauses).  Now we keep them
            # unless they look like pure metadata (image-only, copyright).
            if block_type == "structure_markdown":
                text_check = (row["text_content"] or "").strip()
                # Skip pure-image or pure-copyright blocks
                lowered = text_check.lower()
                if (not text_check
                    or "<img " in lowered
                    or "copyright protected" in lowered
                    or "all rights reserved" in lowered):
                    skipped_block_count += 1
                    continue
            text = (row["text_content"] or "").strip()
            if _should_skip_block(str(row["page_status"]), text):
                skipped_block_count += 1
                continue
            # Skip noise blocks (academic headers, short/empty, etc.)
            if _is_noise_block(text):
                skipped_block_count += 1
                continue

            evidence_id = next_prefixed_id(connection, "evidence", "EV")
            normalized_text = _normalize_text(text)
            confidence = _confidence_for_block(row["block_type"], row["risk_level"])

            connection.execute(
                """
                INSERT INTO evidence (
                    evidence_id, doc_id, page_id, block_id, block_type, raw_text,
                    normalized_text, image_ref, table_ref, page_no, confidence,
                    risk_level, evidence_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    doc_id,
                    row["page_id"],
                    row["block_id"],
                    row["block_type"],
                    row["raw_text"],
                    normalized_text,
                    None,
                    None,
                    row["page_no"],
                    confidence,
                    row["risk_level"],
                    "review_required" if row["page_status"] != "ready" else "ready",
                    now,
                    now,
                ),
            )

            exported.append(
                {
                    "evidence_id": evidence_id,
                    "page_id": row["page_id"],
                    "block_id": row["block_id"],
                    "page_no": row["page_no"],
                    "block_type": row["block_type"],
                    "confidence": confidence,
                    "risk_level": row["risk_level"],
                    "text": normalized_text,
                }
            )
            evidence_count += 1

        export_path = paths.evidence / f"{doc_id}.evidence.json"
        export_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "generated_at": now,
                    "evidence_count": evidence_count,
                    "skipped_block_count": skipped_block_count,
                    "items": exported,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        connection.commit()
        return EvidenceBuildResult(
            doc_id=doc_id,
            evidence_count=evidence_count,
            skipped_block_count=skipped_block_count,
            export_path=export_path,
        )
    finally:
        connection.close()
