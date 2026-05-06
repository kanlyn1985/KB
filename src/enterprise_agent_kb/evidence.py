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
            if str(row["block_type"]) == "structure_markdown":
                skipped_block_count += 1
                continue
            text = (row["text_content"] or "").strip()
            if _should_skip_block(str(row["page_status"]), text):
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
