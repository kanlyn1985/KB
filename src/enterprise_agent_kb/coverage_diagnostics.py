from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .coverage import (
    _clean_test_gap_label,
    _looks_like_low_value_parameter_gap,
    _looks_like_test_gap_noise,
    build_coverage_for_document,
)
from .db import connect


PRIORITY_WEIGHTS = {
    "u0_full_miss": 100,
    "u4_misaligned": 80,
    "u1_text_only": 60,
    "u2_fact_no_object": 50,
    "u3_not_tested": 20,
}


@dataclass(frozen=True)
class UncoveredPriorityReportResult:
    document_count: int
    issue_count: int
    json_path: Path
    report_path: Path


def build_all_docs_uncovered_priority_report(
    workspace_root: Path,
    *,
    output_dir: Path | None = None,
    sample_limit_per_doc_status: int = 8,
    rebuild_missing_coverage: bool = True,
) -> UncoveredPriorityReportResult:
    paths = AppPaths.from_root(workspace_root)
    output_dir = (output_dir or paths.coverage_reports).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    connection = connect(paths.db_file)
    try:
        documents = [
            dict(row)
            for row in connection.execute(
                """
                SELECT doc_id, source_filename, parse_status, quality_status
                FROM documents
                WHERE is_active = 1
                ORDER BY doc_id
                """
            ).fetchall()
        ]
        page_evidence_counts = _load_page_evidence_counts(connection)
        page_block_counts = _load_page_block_counts(connection)
    finally:
        connection.close()

    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    doc_reports: list[dict[str, object]] = []
    all_issues: list[dict[str, object]] = []

    for document in documents:
        doc_id = str(document["doc_id"])
        matrix_path = paths.coverage_reports / f"{doc_id}.coverage_matrix.json"
        summary_path = paths.coverage_reports / f"{doc_id}.summary.json"
        if rebuild_missing_coverage and (not matrix_path.exists() or not summary_path.exists()):
            build_coverage_for_document(workspace_root, doc_id)

        matrix = _load_json(matrix_path)
        summary = _load_json(summary_path)
        items = list(matrix.get("items") or [])
        issues = [
            _classify_issue(
                doc_id=doc_id,
                source_filename=str(document["source_filename"]),
                row=row,
                page_evidence_counts=page_evidence_counts,
                page_block_counts=page_block_counts,
            )
            for row in items
            if row.get("coverage_status") != "covered"
        ]
        issues.sort(key=lambda item: (-int(item["priority_score"]), str(item["unit_id"])))
        all_issues.extend(issues)
        doc_reports.append(
            {
                "doc_id": doc_id,
                "source_filename": document["source_filename"],
                "parse_status": document["parse_status"],
                "quality_status": document["quality_status"],
                "summary": summary,
                "root_cause_counts": dict(Counter(str(issue["root_cause"]) for issue in issues)),
                "status_counts": dict(Counter(str(issue["coverage_status"]) for issue in issues)),
                "priority_score": sum(int(issue["priority_score"]) for issue in issues),
                "sample_issues": _sample_by_status(issues, sample_limit_per_doc_status),
            }
        )

    all_issues.sort(key=lambda item: (-int(item["priority_score"]), str(item["doc_id"]), str(item["unit_id"])))
    payload = {
        "generated_at": generated_at,
        "document_count": len(documents),
        "issue_count": len(all_issues),
        "root_cause_counts": dict(Counter(str(issue["root_cause"]) for issue in all_issues)),
        "status_counts": dict(Counter(str(issue["coverage_status"]) for issue in all_issues)),
        "documents": doc_reports,
        "top_issues": all_issues[:100],
    }

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    json_path = output_dir / f"all_docs_uncovered_priority_report_{stamp}.json"
    report_path = output_dir / f"all_docs_uncovered_priority_report_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(_render_priority_report(payload), encoding="utf-8")
    return UncoveredPriorityReportResult(
        document_count=len(documents),
        issue_count=len(all_issues),
        json_path=json_path,
        report_path=report_path,
    )


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_page_evidence_counts(connection) -> dict[tuple[str, int], int]:
    return {
        (str(row["doc_id"]), int(row["page_no"])): int(row["count"])
        for row in connection.execute(
            """
            SELECT doc_id, page_no, COUNT(*) AS count
            FROM evidence
            GROUP BY doc_id, page_no
            """
        ).fetchall()
    }


def _load_page_block_counts(connection) -> dict[tuple[str, int], int]:
    return {
        (str(row["doc_id"]), int(row["page_no"])): int(row["count"])
        for row in connection.execute(
            """
            SELECT doc_id, page_no, COUNT(*) AS count
            FROM pages
            GROUP BY doc_id, page_no
            """
        ).fetchall()
    }


def _classify_issue(
    *,
    doc_id: str,
    source_filename: str,
    row: dict[str, object],
    page_evidence_counts: dict[tuple[str, int], int],
    page_block_counts: dict[tuple[str, int], int],
) -> dict[str, object]:
    status = str(row.get("coverage_status") or "unknown")
    page_no = int(row.get("page_no") or 0)
    covered_by = dict(row.get("covered_by") or {})
    text = _short_text(str(row.get("source_text") or row.get("semantic_key") or ""), limit=220)
    semantic_key = _short_text(str(row.get("semantic_key") or ""), limit=160)
    evidence_on_page = page_evidence_counts.get((doc_id, page_no), 0)
    page_exists = page_block_counts.get((doc_id, page_no), 0) > 0
    root_cause = _root_cause_for_status(
        status=status,
        unit_type=str(row.get("unit_type") or ""),
        semantic_key=semantic_key,
        page_exists=page_exists,
        evidence_on_page=evidence_on_page,
        covered_by=covered_by,
        semantic_misaligned=bool(row.get("semantic_misaligned")),
        text=text,
    )
    return {
        "doc_id": doc_id,
        "source_filename": source_filename,
        "unit_id": row.get("unit_id"),
        "coverage_status": status,
        "root_cause": root_cause,
        "priority_score": _priority_score(status, root_cause, str(row.get("importance") or "")),
        "unit_type": row.get("unit_type"),
        "importance": row.get("importance"),
        "page_no": page_no,
        "semantic_key": semantic_key,
        "source_text": text,
        "page_exists": page_exists,
        "evidence_on_page": evidence_on_page,
        "covered_by_counts": {
            "evidence": len(covered_by.get("evidence_ids") or []),
            "facts": len(covered_by.get("fact_ids") or []),
            "entities": len(covered_by.get("entity_ids") or []),
            "wiki_pages": len(covered_by.get("wiki_page_ids") or []),
            "golden_cases": len(covered_by.get("golden_case_ids") or []),
            "regression_cases": len(covered_by.get("regression_case_ids") or []),
        },
    }


def _root_cause_for_status(
    *,
    status: str,
    unit_type: str,
    semantic_key: str,
    page_exists: bool,
    evidence_on_page: int,
    covered_by: dict[str, object],
    semantic_misaligned: bool,
    text: str,
) -> str:
    if unit_type == "parameter_row_unit" and (
        _looks_like_low_value_parameter_gap(_clean_test_gap_label(semantic_key))
        or _looks_like_low_value_parameter_gap(_clean_test_gap_label(text))
    ):
        return "source_unit_noise"
    if _looks_like_test_gap_noise(_clean_test_gap_label(semantic_key)):
        return "source_unit_noise"
    if _looks_like_noise(text):
        return "source_unit_noise"
    if status == "u0_full_miss":
        if not page_exists or evidence_on_page == 0:
            return "parse_missing"
        return "evidence_alignment_gap"
    if status == "u1_text_only":
        return "extraction_gap"
    if status == "u2_fact_no_object":
        return "object_gap"
    if status == "u3_not_tested":
        return "golden_gap"
    if status == "u4_misaligned" or semantic_misaligned:
        return "semantic_alignment_gap"
    if covered_by.get("fact_ids") and not covered_by.get("entity_ids"):
        return "object_gap"
    return "unknown"


def _priority_score(status: str, root_cause: str, importance: str) -> int:
    score = PRIORITY_WEIGHTS.get(status, 10)
    if importance == "high":
        score += 20
    if root_cause in {"parse_missing", "evidence_alignment_gap", "semantic_alignment_gap"}:
        score += 15
    if root_cause == "source_unit_noise":
        score -= 30
    return max(score, 1)


def _looks_like_noise(text: str) -> bool:
    lowered = text.lower()
    noise_terms = [
        "copyright",
        "iso/iec",
        "未经",
        "版权",
        "不得出售",
        "permission",
        "license",
    ]
    return any(term in lowered for term in noise_terms)


def _sample_by_status(issues: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for issue in issues:
        grouped[str(issue["coverage_status"])].append(issue)
    samples: list[dict[str, object]] = []
    for status in sorted(grouped, key=lambda value: -PRIORITY_WEIGHTS.get(value, 0)):
        samples.extend(grouped[status][:limit])
    return samples


def _short_text(text: str, *, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _render_priority_report(payload: dict[str, object]) -> str:
    lines: list[str] = []
    lines.append("# All Docs Uncovered Priority Report")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- document_count: {payload.get('document_count')}")
    lines.append(f"- issue_count: {payload.get('issue_count')}")
    lines.append("")
    lines.append("## Root Cause Counts")
    lines.append("")
    for cause, count in sorted(dict(payload.get("root_cause_counts") or {}).items(), key=lambda item: (-int(item[1]), item[0])):
        lines.append(f"- {cause}: {count}")
    lines.append("")
    lines.append("## Status Counts")
    lines.append("")
    for status, count in sorted(dict(payload.get("status_counts") or {}).items(), key=lambda item: (-int(item[1]), item[0])):
        lines.append(f"- {status}: {count}")
    lines.append("")
    lines.append("## Documents")
    lines.append("")
    lines.append("| doc_id | quality | source_units | priority_score | u0 | u1 | u2 | u3 | u4 | root causes |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for doc in list(payload.get("documents") or []):
        summary = dict(doc.get("summary") or {})
        status_counts = dict(doc.get("status_counts") or {})
        root_counts = dict(doc.get("root_cause_counts") or {})
        root_summary = ", ".join(f"{key}:{value}" for key, value in sorted(root_counts.items()))
        lines.append(
            "| {doc_id} | {quality} | {source_units} | {priority} | {u0} | {u1} | {u2} | {u3} | {u4} | {roots} |".format(
                doc_id=doc.get("doc_id"),
                quality=doc.get("quality_status"),
                source_units=summary.get("source_unit_count", 0),
                priority=doc.get("priority_score", 0),
                u0=status_counts.get("u0_full_miss", 0),
                u1=status_counts.get("u1_text_only", 0),
                u2=status_counts.get("u2_fact_no_object", 0),
                u3=status_counts.get("u3_not_tested", 0),
                u4=status_counts.get("u4_misaligned", 0),
                roots=root_summary,
            )
        )
    lines.append("")
    lines.append("## Top Issues")
    lines.append("")
    for issue in list(payload.get("top_issues") or [])[:40]:
        lines.append(
            "- [{status}/{cause}] {doc_id} {unit_id} page {page} score {score}: {text}".format(
                status=issue.get("coverage_status"),
                cause=issue.get("root_cause"),
                doc_id=issue.get("doc_id"),
                unit_id=issue.get("unit_id"),
                page=issue.get("page_no"),
                score=issue.get("priority_score"),
                text=issue.get("semantic_key") or issue.get("source_text"),
            )
        )
    lines.append("")
    lines.append("## Suggested Fix Order")
    lines.append("")
    lines.append("1. Fix parse_missing and evidence_alignment_gap before expanding golden tests.")
    lines.append("2. Fix extraction_gap by improving fact extraction rules for definitions, requirements, figure captions, tables, and appendices.")
    lines.append("3. Treat source_unit_noise as a source-unit inventory quality issue, not a retrieval failure.")
    lines.append("4. Expand golden tests only for golden_gap units that already have evidence, facts, entities, and wiki coverage.")
    lines.append("5. Rebuild coverage and rerun golden retrieval metrics after each framework-level fix.")
    return "\n".join(lines) + "\n"
