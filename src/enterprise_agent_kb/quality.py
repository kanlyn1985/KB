from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .db import connect


@dataclass(frozen=True)
class QualityResult:
    doc_id: str
    overall_score: float
    high_risk_page_count: int
    review_required_count: int
    blocked_count: int
    report_path: Path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _page_metrics(page: dict[str, object]) -> dict[str, object]:
    blocks = page.get("blocks", [])
    text_blocks = 0
    total_chars = 0
    has_ocr_markdown = False
    has_html_or_images = False
    anomaly_chars = 0
    control_chars = 0
    symbol_chars = 0
    semantic_chars = 0
    rare_ocr_glyph_chars = 0
    text_parts: list[str] = []
    counted_chars = 0

    for block in blocks:
        block_type = str(block.get("block_type", ""))
        if block_type == "structure_markdown":
            continue
        text = str(block.get("text", "")).strip()
        if text:
            text_parts.append(text)
            text_blocks += 1
            total_chars += len(text)
            for ch in text:
                if ch.isspace():
                    continue
                counted_chars += 1
                codepoint = ord(ch)
                name = unicodedata.name(ch, "")
                if codepoint < 32 or 127 <= codepoint <= 159:
                    control_chars += 1
                if re.match(r"[A-Za-z0-9\u4e00-\u9fff]", ch):
                    semantic_chars += 1
                else:
                    symbol_chars += 1
                if "\u7280" <= ch <= "\u72ff":
                    rare_ocr_glyph_chars += 1
                if "MATHEMATICAL" in name:
                    anomaly_chars += 1
        if block_type == "ocr_markdown":
            has_ocr_markdown = True
        if "<img" in text or "![image" in text or "<div" in text:
            has_html_or_images = True

    flags: list[str] = []
    risk_level = "low"
    page_status = "ready"

    if text_blocks == 0:
        flags.append("no_text")
        risk_level = "high"
        page_status = "review_required"
    elif total_chars < 80:
        flags.append("low_text_density")
        risk_level = "medium"
        page_status = "review_required"

    if has_ocr_markdown:
        flags.append("ocr_derived")
        if risk_level == "low":
            risk_level = "medium"

    if has_html_or_images:
        flags.append("embedded_image_markup")
        risk_level = "high"
        page_status = "review_required"

    text_blob = "\n".join(text_parts)
    anomaly_ratio = (anomaly_chars / counted_chars) if counted_chars else 0.0
    control_ratio = (control_chars / counted_chars) if counted_chars else 0.0
    symbol_ratio = (symbol_chars / counted_chars) if counted_chars else 0.0
    semantic_ratio = (semantic_chars / counted_chars) if counted_chars else 0.0
    rare_ocr_glyph_ratio = (rare_ocr_glyph_chars / counted_chars) if counted_chars else 0.0
    singleton_token_ratio = _singleton_token_ratio(text_blob)
    language_run_count = _language_run_count(text_blob)
    readability_score = _readability_score(
        semantic_ratio=semantic_ratio,
        symbol_ratio=symbol_ratio,
        control_ratio=control_ratio,
        rare_ocr_glyph_ratio=rare_ocr_glyph_ratio,
        singleton_token_ratio=singleton_token_ratio,
        language_run_count=language_run_count,
        total_chars=total_chars,
    )

    if anomaly_ratio > 0.08:
        flags.append("glyph_anomaly")
        risk_level = "high"
        page_status = "review_required"
    if control_ratio > 0.003:
        flags.append("control_char_noise")
        risk_level = "high"
        page_status = "review_required"
    if rare_ocr_glyph_ratio > 0.01:
        flags.append("rare_ocr_glyph_noise")
        risk_level = "high"
        page_status = "review_required"
    if symbol_ratio > 0.38:
        flags.append("symbol_noise")
        risk_level = "high"
        page_status = "review_required"
    if singleton_token_ratio > 0.55 and total_chars > 500:
        flags.append("fragmented_text")
        risk_level = "high"
        page_status = "review_required"
    if readability_score < 0.35 and total_chars > 500:
        flags.append("low_readability")
        risk_level = "high"
        page_status = "review_required"

    if text_blocks == 0 and has_ocr_markdown:
        page_status = "blocked"
        risk_level = "high"

    return {
        "page_no": page.get("page_no"),
        "text_blocks": text_blocks,
        "total_chars": total_chars,
        "has_ocr_markdown": has_ocr_markdown,
        "has_html_or_images": has_html_or_images,
        "anomaly_ratio": anomaly_ratio,
        "control_ratio": control_ratio,
        "symbol_ratio": symbol_ratio,
        "semantic_ratio": semantic_ratio,
        "rare_ocr_glyph_ratio": rare_ocr_glyph_ratio,
        "singleton_token_ratio": singleton_token_ratio,
        "language_run_count": language_run_count,
        "readability_score": readability_score,
        "risk_flags": flags,
        "risk_level": risk_level,
        "page_status": page_status,
    }


def _singleton_token_ratio(text: str) -> float:
    tokens = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", text)
    if not tokens:
        return 1.0
    singleton_count = sum(1 for token in tokens if len(token) == 1)
    return singleton_count / len(tokens)


def _language_run_count(text: str) -> int:
    cjk_runs = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    latin_words = [
        token
        for token in re.findall(r"[A-Za-z]{3,}", text)
        if re.search(r"[aeiouAEIOU]", token)
    ]
    return len(cjk_runs) + len(latin_words)


def _readability_score(
    *,
    semantic_ratio: float,
    symbol_ratio: float,
    control_ratio: float,
    rare_ocr_glyph_ratio: float,
    singleton_token_ratio: float,
    language_run_count: int,
    total_chars: int,
) -> float:
    if total_chars <= 0:
        return 0.0
    language_density = min(1.0, language_run_count / max(total_chars / 120.0, 1.0))
    penalty = min(0.85, symbol_ratio * 0.75 + control_ratio * 8.0 + rare_ocr_glyph_ratio * 6.0 + singleton_token_ratio * 0.25)
    score = semantic_ratio * 0.55 + language_density * 0.45 - penalty
    return max(0.0, min(1.0, score))


def _compute_scores(page_reports: list[dict[str, object]]) -> tuple[float, float, float]:
    if not page_reports:
        return 0.0, 0.0, 0.0

    total = len(page_reports)
    high_risk = sum(1 for page in page_reports if page["risk_level"] == "high")
    review_required = sum(
        1 for page in page_reports if page["page_status"] in {"review_required", "blocked"}
    )
    ocr_pages = sum(1 for page in page_reports if page["has_ocr_markdown"])
    avg_readability = sum(float(page.get("readability_score") or 0.0) for page in page_reports) / total

    structure_score = max(0.0, 1.0 - (high_risk / total))
    ocr_avg_confidence = 0.9 if ocr_pages else 0.0
    overall_score = max(
        0.0,
        min(
            1.0,
            0.45 * structure_score
            + 0.30 * (1.0 - review_required / total)
            + 0.25 * avg_readability,
        ),
    )
    return overall_score, ocr_avg_confidence, structure_score


def assess_document_quality(workspace_root: Path, doc_id: str) -> QualityResult:
    paths = AppPaths.from_root(workspace_root)
    normalized_path = paths.normalized / f"{doc_id}.json"
    if not normalized_path.exists():
        raise FileNotFoundError(normalized_path)

    normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
    page_reports = [_page_metrics(page) for page in normalized.get("pages", [])]
    now = _utc_now()

    overall_score, ocr_avg_confidence, structure_score = _compute_scores(page_reports)
    high_risk_page_count = sum(1 for page in page_reports if page["risk_level"] == "high")
    review_required_count = sum(
        1 for page in page_reports if page["page_status"] in {"review_required", "blocked"}
    )
    blocked_count = sum(1 for page in page_reports if page["page_status"] == "blocked")

    report = {
        "doc_id": doc_id,
        "generated_at": now,
        "parser_engine": normalized.get("parser_engine"),
        "page_count": normalized.get("page_count", len(page_reports)),
        "block_count": normalized.get("block_count", 0),
        "overall_score": overall_score,
        "ocr_avg_confidence": ocr_avg_confidence,
        "structure_score": structure_score,
        "table_score": None,
        "fact_alignment_score": None,
        "conflict_count": 0,
        "high_risk_page_count": high_risk_page_count,
        "review_required_count": review_required_count,
        "blocked_count": blocked_count,
        "pages": page_reports,
    }

    report_path = paths.quality_reports / f"{doc_id}.quality.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    connection = connect(paths.db_file)
    try:
        for page in page_reports:
            connection.execute(
                """
                UPDATE pages
                SET risk_level = ?, page_status = ?, updated_at = ?
                WHERE doc_id = ? AND page_no = ?
                """,
                (
                    page["risk_level"],
                    page["page_status"],
                    now,
                    doc_id,
                    page["page_no"],
                ),
            )

        quality_status = "blocked" if blocked_count else "review_required" if review_required_count else "passed"
        connection.execute(
            """
            INSERT INTO quality_reports (
                doc_id, overall_score, ocr_avg_confidence, structure_score, table_score,
                fact_alignment_score, conflict_count, high_risk_page_count, review_required_count,
                blocked_count, report_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                overall_score = excluded.overall_score,
                ocr_avg_confidence = excluded.ocr_avg_confidence,
                structure_score = excluded.structure_score,
                table_score = excluded.table_score,
                fact_alignment_score = excluded.fact_alignment_score,
                conflict_count = excluded.conflict_count,
                high_risk_page_count = excluded.high_risk_page_count,
                review_required_count = excluded.review_required_count,
                blocked_count = excluded.blocked_count,
                report_json = excluded.report_json,
                updated_at = excluded.updated_at
            """,
            (
                doc_id,
                overall_score,
                ocr_avg_confidence,
                structure_score,
                None,
                None,
                0,
                high_risk_page_count,
                review_required_count,
                blocked_count,
                json.dumps(report, ensure_ascii=False),
                now,
                now,
            ),
        )
        connection.execute(
            "UPDATE documents SET quality_status = ?, update_time = ? WHERE doc_id = ?",
            (quality_status, now, doc_id),
        )
        connection.commit()
    finally:
        connection.close()

    return QualityResult(
        doc_id=doc_id,
        overall_score=overall_score,
        high_risk_page_count=high_risk_page_count,
        review_required_count=review_required_count,
        blocked_count=blocked_count,
        report_path=report_path,
    )
