"""Case validation helpers: anchor checks, low-value filters, trace validators.

Extracted from `generated_tests._impl` to group all gating/validation
predicates and the case-against-trace validation routines in one place.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from ..config import AppPaths
from ..db import connect
from ._case_helpers import _normalize_compare, _safe_json, _strip_html

def _is_structured_clause_anchor(value: str) -> bool:
    compact = re.sub(r"\s+", " ", value or "").strip()
    return bool(re.search(r"\b[A-Z]?\d+(?:\.\d+)+\b", compact) and re.search(r"[\u4e00-\u9fff]{2,}", compact))
def _is_usable_golden_anchor(value: str) -> bool:
    if _is_low_value_golden_text(value):
        return False
    text = re.sub(r"\s+", "", value or "")
    if len(text) < 6:
        return False
    if any((ord(ch) < 32 or 127 <= ord(ch) <= 159) for ch in text):
        return False
    if any(marker in text for marker in ("!!!", "!!!!!", "----", "����")):
        return False
    if re.search(r"[犀-狿]{4,}", text):
        return False
    semantic_chars = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", text)
    if len(semantic_chars) < 4:
        return False
    if len(re.findall(r"\d", text)) / max(len(semantic_chars), 1) > 0.6:
        return False
    symbol_count = len(re.findall(r"[^A-Za-z0-9\u4e00-\u9fff]", text))
    if symbol_count / max(len(text), 1) > 0.25:
        return False
    if re.search(r"[A-Z]{4,}", text) and not re.search(r"[a-z\u4e00-\u9fff]", text) and not _is_valid_standard_code(text):
        return False
    has_language_run = bool(re.search(r"[A-Za-z]{3,}", text) or re.search(r"[\u4e00-\u9fff]{2,}", text))
    if not has_language_run:
        return False
    return len(semantic_chars) / max(len(text), 1) >= 0.65
def _is_valid_standard_code(value: str) -> bool:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    match = re.search(r"\b(GB/T|GBT|GB|QC/T|QC|ISO/IEC|ISO|IEC)\s*([\d.]+(?:[-—]\d+)*)(?:[-—:]\d{4})?\b", text, re.I)
    if not match:
        return False
    prefix = match.group(1).upper()
    number = match.group(2).replace("—", "-")
    if prefix in {"ISO", "IEC"} and re.fullmatch(r"(?:19|20)\d{2}", number):
        return False
    return True
def _is_low_value_evidence_text(text: str) -> bool:
    cleaned = html.unescape(str(text or "")).strip()
    if not cleaned:
        return True
    compact = re.sub(r"\s+", " ", cleaned).lower()
    if "<div" in compact or "<img" in compact or "</" in compact:
        return True
    if "copyright protected document" in compact or "all rights reserved" in compact:
        return True
    if "iso copyright office" in compact or "published in switzerland" in compact:
        return True
    if re.search(r"^©\s*(iso|iec)\s+(?:19|20)\d{2}$", compact):
        return True
    if compact.startswith("contents") or compact.startswith("## contents"):
        return True
    if compact.startswith("# foreword") or compact.startswith("## foreword"):
        return True
    if len(re.findall(r"\.{4,}", cleaned)) >= 3:
        return True
    return False
def _is_low_value_golden_text(text: str) -> bool:
    cleaned = html.unescape(str(text or "")).strip()
    compact = re.sub(r"\s+", " ", cleaned).lower()
    if _is_low_value_evidence_text(cleaned):
        return True
    boilerplate_patterns = [
        r"unless otherwise specified",
        r"permission can be requested",
        r"case postale",
        r"tel\.",
        r"fax\.",
        r"e-mail",
        r"www\.",
        r"second edition\s+\d{4}-\d{2}-\d{2}",
        r"the international organization",
        r"member body interested in a subject",
        r"international organizations, governmental",
        r"collaborates closely with the international",
        r"international standards are drafted",
        r"the work of preparing international standards",
        r"normative references\s*\.{2,}",
        r"terms, definitions, symbols",
        r"annex [a-z]\s*\(informative\)\s*\.{2,}",
    ]
    return any(re.search(pattern, compact) for pattern in boilerplate_patterns)
def _looks_like_person_name(term: str) -> bool:
    if not term:
        return False
    cleaned = re.sub(r"\s+", "", term)
    parts = re.split(r"[,，、;；]", cleaned)
    if len(parts) >= 2:
        all_cjk = all(re.fullmatch(r"[\u4e00-\u9fff]{2,4}", p) for p in parts if p)
        if all_cjk and len(parts) >= 2:
            return True
    if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", cleaned):
        return bool(re.search(r"[技术方法系统设备装置器电压电流功率温度]", cleaned))
    return False
def _is_usable_parameter_label(label: str) -> bool:
    if not label or len(label) < 2 or len(label) > 50:
        return False
    if re.search(r"[·•\u2022\u2023\u25E6\uff65]", label):
        return False
    if label.startswith(")") or label.startswith("-"):
        return False
    return True
def _validate_into(
    workspace_root: Path,
    cases: list[dict[str, str]],
    limit: int,
    selected_keys: set[tuple[str, str, str]],
) -> list[dict[str, str]]:
    accepted: list[dict[str, str]] = []
    if limit <= 0:
        return accepted
    for case in cases:
        key = (
            case.get("query", ""),
            _normalize_compare(case.get("must_include", "")),
            case.get("assert_mode", ""),
        )
        if key in selected_keys:
            continue
        if _validate_case(workspace_root, case):
            accepted.append(case)
            selected_keys.add(key)
        if len(accepted) >= limit:
            break
    return accepted
def _validate_page_coverage(
    workspace_root: Path,
    cases: list[dict[str, str]],
    limit: int,
    selected_keys: set[tuple[str, str, str]],
) -> list[dict[str, str]]:
    accepted: list[dict[str, str]] = []
    covered_pages: set[int] = set()
    if limit <= 0:
        return accepted
    for case in cases:
        page_no = int(case.get("page_no") or 0)
        if page_no in covered_pages:
            continue
        key = (
            case.get("query", ""),
            _normalize_compare(case.get("must_include", "")),
            case.get("assert_mode", ""),
        )
        if key in selected_keys:
            continue
        if _validate_case(workspace_root, case):
            accepted.append(case)
            covered_pages.add(page_no)
            selected_keys.add(key)
        if len(accepted) >= limit:
            break
    return accepted
def _validate_case(workspace_root: Path, case: dict[str, str]) -> bool:
    expected = _normalize_compare(case.get("must_include", ""))
    if not expected:
        return False
    target_doc_id = str(case.get("target_doc_id") or "").strip() or None

    try:
        if case.get("assert_mode") == "context_contains":
            context = build_query_context(workspace_root, case["query"], limit=EVAL_RETRIEVAL_LIMIT, preferred_doc_id=target_doc_id)
            blob = json.dumps(context, ensure_ascii=False)
        else:
            answer = answer_query(workspace_root, case["query"], limit=EVAL_RETRIEVAL_LIMIT, preferred_doc_id=target_doc_id)
            blob = "\n".join(
                [
                    str(answer.get("direct_answer", "")),
                    *[str(item) for item in answer.get("summary", [])],
                    *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_facts", [])],
                    *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_evidence", [])],
                    *[json.dumps(item, ensure_ascii=False) for item in answer.get("related_wiki_pages", [])],
                ]
            )
    except (DatabaseError, EvaluationError, LLMError, NetworkError, QueryError, RetrievalError, TimeoutError, ValidationError, RuntimeError, ValueError):
        return False

    normalized_blob = _normalize_compare(blob)
    if target_doc_id and _normalize_compare(target_doc_id) not in normalized_blob:
        return False
    return _matches_expected_anchor(expected, normalized_blob)
def _validate_draft_golden_case(workspace_root: Path, case: dict[str, str], mode: str) -> bool:
    if mode == "trace":
        return _validate_case_source_trace(workspace_root, case)
    if mode == "answer":
        return _validate_case(workspace_root, case)
    if mode == "hybrid":
        return _validate_case_source_trace(workspace_root, case) and _validate_case(workspace_root, case)
    raise ValueError(f"unsupported validation mode: {mode}")
def _validate_case_source_trace(workspace_root: Path, case: dict[str, str]) -> bool:
    expected = _normalize_compare(str(case.get("must_include") or ""))
    target_doc_id = str(case.get("target_doc_id") or "").strip()
    if not expected or not target_doc_id:
        return False

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        evidence_rows = connection.execute(
            """
            SELECT normalized_text
            FROM evidence
            WHERE doc_id = ?
            """,
            (target_doc_id,),
        ).fetchall()
        fact_rows = connection.execute(
            """
            SELECT predicate, object_value, qualifiers_json
            FROM facts
            WHERE source_doc_id = ?
            """,
            (target_doc_id,),
        ).fetchall()
        wiki_rows = connection.execute(
            """
            SELECT title, slug
            FROM wiki_pages
            WHERE json_extract(source_doc_ids_json, '$[0]') = ?
            """,
            (target_doc_id,),
        ).fetchall()
    finally:
        connection.close()

    blob = "\n".join(
        [
            *[str(row["normalized_text"] or "") for row in evidence_rows],
            *[f"{row['predicate']} {row['object_value'] or ''} {row['qualifiers_json'] or ''}" for row in fact_rows],
            *[f"{row['title'] or ''} {row['slug'] or ''}" for row in wiki_rows],
        ]
    )
    return _matches_expected_anchor(expected, _normalize_compare(blob))
def _matches_expected_anchor(expected: str, normalized_blob: str) -> bool:
    if not expected:
        return False
    if expected in normalized_blob:
        return True
    compact = expected.strip()
    if len(compact) >= 18 and compact[:18] in normalized_blob:
        return True
    semantic_expected = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]", "", compact)
    semantic_blob = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]", "", normalized_blob)
    if len(semantic_expected) >= 16 and semantic_expected[:16] in semantic_blob:
        return True
    tokens = [token for token in re.split(r"[^A-Za-z0-9\u4e00-\u9fff]+", compact) if len(token) >= 2]
    if len(tokens) >= 2:
        matched = sum(1 for token in tokens[:6] if _normalize_compare(token) in normalized_blob)
        return matched >= min(2, len(tokens))
    return False
def _validate_coverage_case(
    workspace_root: Path,
    doc_id: str,
    case: dict[str, str],
    *,
    validation_mode: str,
) -> dict[str, object]:
    mode = validation_mode if validation_mode in {"trace", "context", "rich", "hybrid"} else "trace"

    if mode == "trace":
        return _validate_coverage_case_trace(workspace_root, doc_id, case)

    if mode == "context":
        context_case = dict(case)
        context_case["assert_mode"] = "context_contains"
        return {
            "passed": _validate_case(workspace_root, context_case),
            "mode": "context_contains",
        }

    if _validate_case(workspace_root, case):
        return {"passed": True, "mode": str(case.get("assert_mode") or "rich_answer")}
    if mode == "rich":
        return {"passed": False, "mode": "failed"}

    context_case = dict(case)
    context_case["assert_mode"] = "context_contains"
    if _validate_case(workspace_root, context_case):
        return {"passed": True, "mode": "context_fallback"}
    return {"passed": False, "mode": "failed"}
def _validate_coverage_case_trace(workspace_root: Path, doc_id: str, case: dict[str, str]) -> dict[str, object]:
    unit_id = str(case.get("coverage_unit_id") or "").strip()
    semantic_key = str(case.get("coverage_semantic_key") or case.get("must_include") or "").strip()
    if not unit_id:
        return {"passed": False, "mode": "trace_missing_unit_id"}

    paths = AppPaths.from_root(workspace_root)
    matrix_path = paths.coverage_reports / f"{doc_id}.coverage_matrix.json"
    if not matrix_path.exists():
        build_coverage_for_document(workspace_root, doc_id)
    if not matrix_path.exists():
        return {"passed": False, "mode": "trace_missing_matrix"}

    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    rows = [row for row in payload.get("items", []) if isinstance(row, dict)]
    for row in rows:
        if str(row.get("unit_id") or "") != unit_id:
            continue
        return _validate_coverage_matrix_row(row, semantic_key, mode="trace_matrix")

    semantic_anchor = _normalize_compare(semantic_key)
    if semantic_anchor:
        for row in rows:
            row_semantic_key = _normalize_compare(str(row.get("semantic_key") or ""))
            if _matches_expected_anchor(semantic_anchor, row_semantic_key):
                return _validate_coverage_matrix_row(row, semantic_key, mode="trace_matrix_semantic_fallback")
    return {"passed": False, "mode": "trace_unit_not_found"}
def _validate_coverage_matrix_row(row: dict[str, object], semantic_key: str, *, mode: str) -> dict[str, object]:
    covered_by = row.get("covered_by") if isinstance(row.get("covered_by"), dict) else {}
    has_trace = bool(covered_by.get("evidence_ids")) and bool(covered_by.get("fact_ids"))
    has_object = bool(covered_by.get("entity_ids") or covered_by.get("wiki_page_ids"))
    row_semantic_key = str(row.get("semantic_key") or "")
    semantic_match = not semantic_key or _matches_expected_anchor(
        _normalize_compare(semantic_key),
        _normalize_compare(row_semantic_key),
    )
    return {
        "passed": has_trace and has_object and semantic_match,
        "mode": mode,
    }
