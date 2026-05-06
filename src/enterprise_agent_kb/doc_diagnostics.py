from __future__ import annotations

import json
from pathlib import Path

from .config import AppPaths
from .db import connect


def build_document_diagnostics(workspace_root: Path, doc_id: str) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)

    try:
        document = connection.execute(
            """
            SELECT doc_id, source_filename, source_type, page_count, parse_status, quality_status
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        if document is None:
            raise ValueError(f"document not found: {doc_id}")

        page_rows = connection.execute(
            """
            SELECT page_no, risk_level, page_status
            FROM pages
            WHERE doc_id = ?
            ORDER BY page_no
            """,
            (doc_id,),
        ).fetchall()
        evidence_rows = connection.execute(
            """
            SELECT page_no, confidence, risk_level, normalized_text
            FROM evidence
            WHERE doc_id = ?
            ORDER BY page_no, evidence_id
            """,
            (doc_id,),
        ).fetchall()
        fact_rows = connection.execute(
            """
            SELECT fact_type, predicate, object_value, qualifiers_json
            FROM facts
            WHERE source_doc_id = ?
            ORDER BY fact_id
            """,
            (doc_id,),
        ).fetchall()
        quality_row = connection.execute(
            """
            SELECT overall_score, high_risk_page_count, review_required_count, blocked_count, report_json
            FROM quality_reports
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        quality_payload = {}
        if quality_row and quality_row["report_json"]:
            try:
                quality_payload = json.loads(quality_row["report_json"])
            except json.JSONDecodeError:
                quality_payload = {}
        coverage_summary = _load_coverage_summary(paths, doc_id)

        page_count = int(document["page_count"] or 0)
        evidence_page_set = {int(row["page_no"]) for row in evidence_rows if int(row["page_no"] or 0) > 0}
        effective_text_page_count = len(evidence_page_set)
        empty_or_weak_pages = [page["page_no"] for page in page_rows if page["page_status"] != "ready"]
        high_risk_pages = [page["page_no"] for page in page_rows if page["risk_level"] == "high"]

        fact_types: dict[str, int] = {}
        for row in fact_rows:
            fact_types[row["fact_type"]] = fact_types.get(row["fact_type"], 0) + 1

        metadata_coverage = {
            "has_standard": fact_types.get("document_standard", 0) > 0,
            "has_title": fact_types.get("document_title", 0) > 0,
            "has_publication_date": _has_fact(fact_rows, "document_lifecycle", "publication_date"),
            "has_effective_date": _has_fact(fact_rows, "document_lifecycle", "effective_date"),
            "has_section_heading": fact_types.get("section_heading", 0) > 0,
            "has_term_definition": fact_types.get("term_definition", 0) > 0 or fact_types.get("concept_definition", 0) > 0,
            "has_abstract": fact_types.get("document_abstract", 0) > 0,
        }

        metadata_score = sum(1 for value in metadata_coverage.values() if value) / max(len(metadata_coverage), 1)
        fact_coverage = min(len(fact_rows) / max(page_count, 1), 10.0)
        evidence_coverage = len(evidence_rows) / max(page_count, 1)
        answerability_score = round(
            min(
                1.0,
                metadata_score * 0.45
                + min(evidence_coverage / 2.0, 1.0) * 0.3
                + min(fact_coverage / 4.0, 1.0) * 0.25,
            ),
            3,
        )

        warnings: list[str] = []
        if not metadata_coverage["has_standard"] and document["source_type"] == "pdf":
            warnings.append("未抽取到标准号。")
        if not metadata_coverage["has_title"]:
            warnings.append("未抽取到标题。")
        if not metadata_coverage["has_term_definition"]:
            warnings.append("未抽取到术语/概念定义。")
        if effective_text_page_count < max(1, page_count // 3):
            warnings.append("有效文本页占比偏低。")
        if page_count and len(high_risk_pages) / page_count >= 0.3:
            warnings.append("高风险页占比偏高。")
        low_readability_pages = [
            page.get("page_no")
            for page in quality_payload.get("pages", [])
            if isinstance(page, dict) and "low_readability" in page.get("risk_flags", [])
        ]
        if low_readability_pages:
            warnings.append("存在低可读性页面，可能是 OCR/编码解析异常。")

        return {
            "doc_id": doc_id,
            "document": dict(document),
            "quality": _diagnostic_quality_payload(quality_row),
            "counts": {
                "page_count": page_count,
                "effective_text_page_count": effective_text_page_count,
                "evidence_count": len(evidence_rows),
                "fact_count": len(fact_rows),
                "term_definition_count": fact_types.get("term_definition", 0) + fact_types.get("concept_definition", 0),
                "section_heading_count": fact_types.get("section_heading", 0),
                "empty_or_weak_page_count": len(empty_or_weak_pages),
                "high_risk_page_count": len(high_risk_pages),
            },
            "coverage": {
                "metadata_coverage": metadata_coverage,
                "metadata_score": round(metadata_score, 3),
                "evidence_per_page": round(evidence_coverage, 3),
                "facts_per_page": round(fact_coverage, 3),
                "answerability_score": answerability_score,
                "source_unit_count": int(coverage_summary.get("source_unit_count", 0)),
                "text_coverage_rate": float(coverage_summary.get("text_coverage_rate", 0.0)),
                "semantic_coverage_rate": float(coverage_summary.get("semantic_coverage_rate", 0.0)),
                "object_coverage_rate": float(coverage_summary.get("object_coverage_rate", 0.0)),
                "knowledge_page_coverage_rate": float(coverage_summary.get("knowledge_page_coverage_rate", 0.0)),
                "test_coverage_rate": float(coverage_summary.get("test_coverage_rate", 0.0)),
                "uncovered_counts": dict(coverage_summary.get("uncovered_counts", {})),
            },
            "artifacts": {
                "coverage_summary_path": str(paths.coverage_reports / f"{doc_id}.summary.json"),
                "coverage_report_path": str(paths.coverage_reports / f"{doc_id}.coverage_report.md"),
            },
            "page_sets": {
                "effective_text_pages": sorted(evidence_page_set),
                "empty_or_weak_pages": empty_or_weak_pages,
                "high_risk_pages": high_risk_pages,
            },
            "fact_types": fact_types,
            "warnings": warnings,
        }
    finally:
        connection.close()


def _has_fact(rows, fact_type: str, predicate: str) -> bool:
    for row in rows:
        if row["fact_type"] == fact_type and row["predicate"] == predicate:
            return True
    return False


def _diagnostic_quality_payload(row) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "overall_score": row["overall_score"],
        "high_risk_page_count": row["high_risk_page_count"],
        "review_required_count": row["review_required_count"],
        "blocked_count": row["blocked_count"],
    }


def _load_coverage_summary(paths: AppPaths, doc_id: str) -> dict[str, object]:
    summary_path = paths.coverage_reports / f"{doc_id}.summary.json"
    if not summary_path.exists():
        return {}
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
