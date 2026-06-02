"""Coverage report rendering and shared string/number utilities.

Extracted from `coverage._impl` to isolate the workspace-status report
rendering (summary, group summary, markdown report, test-gap report)
and the shared string/number/JSON utilities used by both the gap
detection logic and the orchestrators.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SOURCE_UNIT_EXPORT_VERSION = "coverage-v1"

V0_UNIT_TYPES = {"definition_unit", "parameter_row_unit", "process_unit", "requirement_unit"}

def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _build_summary(
    *,
    doc_id: str,
    source_filename: str,
    generated_at: str,
    matrix_rows: list[dict[str, object]],
) -> dict[str, object]:
    total = len(matrix_rows)
    text_covered = sum(1 for row in matrix_rows if row["coverage_flags"]["text_covered"])
    semantic_covered = sum(1 for row in matrix_rows if row["coverage_flags"]["semantic_covered"])
    object_covered = sum(1 for row in matrix_rows if row["coverage_flags"]["object_covered"])
    knowledge_page_covered = sum(1 for row in matrix_rows if row["coverage_flags"]["knowledge_page_covered"])
    test_covered = sum(1 for row in matrix_rows if row["coverage_flags"]["test_covered"])

    uncovered_counts = {
        "u0_full_miss": sum(1 for row in matrix_rows if row["coverage_status"] == "u0_full_miss"),
        "u1_text_only": sum(1 for row in matrix_rows if row["coverage_status"] == "u1_text_only"),
        "u2_fact_no_object": sum(1 for row in matrix_rows if row["coverage_status"] == "u2_fact_no_object"),
        "u3_not_tested": sum(1 for row in matrix_rows if row["coverage_status"] == "u3_not_tested"),
        "u4_misaligned": sum(1 for row in matrix_rows if row["coverage_status"] == "u4_misaligned"),
    }

    return {
        "doc_id": doc_id,
        "source_filename": source_filename,
        "generated_at": generated_at,
        "version": SOURCE_UNIT_EXPORT_VERSION,
        "source_unit_count": total,
        "unit_types": sorted(V0_UNIT_TYPES),
        "text_coverage_rate": _rate(text_covered, total),
        "semantic_coverage_rate": _rate(semantic_covered, total),
        "object_coverage_rate": _rate(object_covered, total),
        "knowledge_page_coverage_rate": _rate(knowledge_page_covered, total),
        "test_coverage_rate": _rate(test_covered, total),
        "uncovered_counts": uncovered_counts,
        "unit_type_summary": _group_summary(matrix_rows, "unit_type"),
        "importance_summary": _group_summary(matrix_rows, "importance"),
    }


def _group_summary(rows: list[dict[str, object]], key: str) -> dict[str, dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        groups.setdefault(str(row.get(key) or "unknown"), []).append(row)

    summary: dict[str, dict[str, object]] = {}
    for group_key, items in sorted(groups.items()):
        count = len(items)
        summary[group_key] = {
            "count": count,
            "text_coverage_rate": _rate(sum(1 for row in items if row["coverage_flags"]["text_covered"]), count),
            "semantic_coverage_rate": _rate(sum(1 for row in items if row["coverage_flags"]["semantic_covered"]), count),
            "object_coverage_rate": _rate(sum(1 for row in items if row["coverage_flags"]["object_covered"]), count),
            "test_coverage_rate": _rate(sum(1 for row in items if row["coverage_flags"]["test_covered"]), count),
        }
    return summary


def _render_report(summary: dict[str, object], uncovered_rows: list[dict[str, object]]) -> str:
    top_uncovered = uncovered_rows[:20]
    lines = [
        "# Coverage Report",
        "",
        f"- doc_id: {summary['doc_id']}",
        f"- source_filename: {summary['source_filename']}",
        f"- source_unit_count: {summary['source_unit_count']}",
        f"- text_coverage_rate: {summary['text_coverage_rate']}",
        f"- semantic_coverage_rate: {summary['semantic_coverage_rate']}",
        f"- object_coverage_rate: {summary['object_coverage_rate']}",
        f"- knowledge_page_coverage_rate: {summary['knowledge_page_coverage_rate']}",
        f"- test_coverage_rate: {summary['test_coverage_rate']}",
        "",
        "## Uncovered Counts",
        "",
    ]
    for key, value in summary["uncovered_counts"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Top Uncovered Units", ""])
    if not top_uncovered:
        lines.append("- none")
    else:
        for row in top_uncovered:
            locator = row.get("source_locator") or {}
            page_no = locator.get("page_no") or row.get("page_no")
            lines.append(
                f"- [{row['coverage_status']}] {row['unit_id']} | {row['unit_type']} | page {page_no} | {row['semantic_key']}"
            )
    return "\n".join(lines) + "\n"


def _render_test_gap_report(payload: dict[str, object]) -> str:
    items = list(payload.get("items") or [])
    lines = [
        "# Test Gap Candidates",
        "",
        f"- doc_id: {payload['doc_id']}",
        f"- source_gap_count: {payload.get('source_gap_count', payload['candidate_count'])}",
        f"- skipped_candidate_count: {payload.get('skipped_candidate_count', 0)}",
        f"- excluded_candidate_count: {payload.get('excluded_candidate_count', 0)}",
        f"- candidate_count: {payload['candidate_count']}",
        f"- generated_at: {payload['generated_at']}",
        "",
        "## Candidates",
        "",
    ]
    if not items:
        lines.append("- none")
        return "\n".join(lines) + "\n"

    for item in items[:100]:
        lines.append(
            f"- {item['unit_id']} | {item['unit_type']} | page {item['page_no']} | "
            f"{item['semantic_key']} | query: {item['recommended_query_seed']}"
        )
    return "\n".join(lines) + "\n"


def _soft_contains(left: str, right: str) -> bool:
    left_key = _compare_key(left)
    right_key = _compare_key(right)
    if not left_key or not right_key:
        return False
    return left_key in right_key or right_key in left_key


def _compare_key(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = text.replace("—", "-").replace("–", "-").replace("／", "/")
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
    return text


def _clean_text(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _clean_label(value: object) -> str:
    text = _clean_text(value)
    text = re.sub(r"^\d+(?:\.\d+){0,6}\s*", "", text)
    text = re.sub(r"^[.。:：;；,，、\-–—•·]+\s*", "", text).strip()
    return text[:240]


def _first_sentence(value: str) -> str:
    if not value:
        return ""
    match = re.split(r"[。；.!?]", value, maxsplit=1)
    return match[0].strip()


def _safe_json(value: str | None) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _rate(covered: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(covered / total, 4)


def _best_nonempty(values: list[str]) -> str:
    for value in values:
        cleaned = _clean_label(value)
        if cleaned:
            return cleaned
    return ""


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_label(value)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _normalize_header_name(value: str) -> str:
    text = re.sub(r"\s+", "", value)
    text = re.sub(r"\$[^$]+\$", "", text)
    text = text.replace("^a", "").replace("^b", "").replace("^c", "")
    if "参数" in text:
        return "参数"
    if "符号" in text:
        return "符号"
    if "单位" in text:
        return "单位"
    if "标称值" in text:
        return "标称值"
    if "最大值" in text:
        return "最大值"
    if "最小值" in text:
        return "最小值"
    if "对应状态" in text:
        return "对应状态"
    if "状态" in text:
        return "状态"
    if "对象" in text:
        return "对象"
    return text


def _row_value(row: list[str], index: int | None) -> str:
    if index is None or index < 0 or index >= len(row):
        return ""
    return str(row[index]).strip()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _normalize_unit(value: str) -> str:
    unit = value.replace("\\Omega", "Ω").replace("Omega", "Ω").replace("ohm", "Ω")
    unit = unit.replace("\\mu", "μ")
    return re.sub(r"\s+", "", unit)
