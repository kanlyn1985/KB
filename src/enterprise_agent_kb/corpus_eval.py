from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Row

from .closed_loop_store import _runtime_code_version, record_eval_run, sync_golden_cases, utc_now
from .config import AppPaths
from .db import connect
from .query_api import build_query_context
from .retrieval_quality import evaluate_retrieval_quality


CORPUS_EVAL_SCOPE_ID = "CORPUS-RETRIEVAL"
DEFAULT_CORPUS_SUITE_ID = "regression:corpus_retrieval"
SUPPORTED_CASE_TYPES = ("definition", "parameter", "process_activity")


@dataclass(frozen=True)
class CorpusEvalGenerationResult:
    case_count: int
    json_path: Path
    report_path: Path
    summary: dict[str, object]
    cases: list[dict[str, object]]


@dataclass(frozen=True)
class CorpusRetrievalEvalResult:
    eval_run_id: str
    suite_id: str
    case_count: int
    passed: int
    failed: int
    success: bool
    case_file: Path
    json_path: Path
    report_path: Path


def generate_corpus_eval_cases(
    workspace_root: Path,
    *,
    doc_ids: list[str] | None = None,
    limit_per_type: int = 20,
    output_dir: Path | None = None,
    case_types: list[str] | None = None,
) -> CorpusEvalGenerationResult:
    paths = AppPaths.from_root(workspace_root)
    timestamp = utc_now()
    selected_types = _selected_case_types(case_types)
    rows = _load_source_unit_rows(paths.db_file, doc_ids=doc_ids)
    cases: list[dict[str, object]] = []
    case_type_counts: dict[str, int] = {}
    skipped_counts: dict[str, int] = {}
    for row in rows:
        case = _case_from_source_unit(row, selected_types=selected_types)
        if not case:
            reason = _skip_reason(row, selected_types)
            skipped_counts[reason] = skipped_counts.get(reason, 0) + 1
            continue
        case_type = str(case.get("case_type") or "")
        if case_type_counts.get(case_type, 0) >= limit_per_type:
            skipped_counts["limit_per_type"] = skipped_counts.get("limit_per_type", 0) + 1
            continue
        case_type_counts[case_type] = case_type_counts.get(case_type, 0) + 1
        cases.append(case)

    report_dir = output_dir or paths.root.parent / "tests" / "generated"
    report_dir.mkdir(parents=True, exist_ok=True)
    date_token = timestamp[:10]
    json_path = report_dir / f"corpus_retrieval_cases_{date_token}.json"
    report_path = report_dir / f"corpus_retrieval_cases_{date_token}.md"
    summary = _generation_summary(cases, rows, skipped_counts, selected_types, doc_ids)
    payload = {
        "generated_at": timestamp,
        "suite": "corpus_retrieval",
        "summary": summary,
        "cases": cases,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(_render_generation_report(payload), encoding="utf-8")
    return CorpusEvalGenerationResult(
        case_count=len(cases),
        json_path=json_path,
        report_path=report_path,
        summary=summary,
        cases=cases,
    )


def run_corpus_retrieval_eval(
    workspace_root: Path,
    *,
    case_file: Path | None = None,
    suite_id: str = DEFAULT_CORPUS_SUITE_ID,
    limit: int = 10,
    output_dir: Path | None = None,
    doc_ids: list[str] | None = None,
    generation_limit_per_type: int = 20,
    case_limit: int | None = None,
    case_types: list[str] | None = None,
) -> CorpusRetrievalEvalResult:
    paths = AppPaths.from_root(workspace_root)
    timestamp = utc_now()
    generated = None
    if case_file:
        cases_path = case_file
        cases = _load_cases(cases_path)
    else:
        generated = generate_corpus_eval_cases(
            workspace_root,
            doc_ids=doc_ids,
            limit_per_type=generation_limit_per_type,
            output_dir=output_dir,
            case_types=case_types,
        )
        cases_path = generated.json_path
        cases = list(generated.cases)
    if case_limit is not None and case_limit >= 0:
        cases = cases[:case_limit]

    case_results = [
        _evaluate_case(paths.root, case, index=index, limit=limit)
        for index, case in enumerate(cases, start=1)
    ]
    passed = sum(1 for item in case_results if item.get("passed"))
    failed = len(case_results) - passed
    summary = _eval_summary(cases, case_results, cases_path, generated.summary if generated else None)

    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, CORPUS_EVAL_SCOPE_ID, cases, source="corpus_eval")
        eval_run_id = record_eval_run(
            connection,
            suite_id=suite_id,
            cases=cases,
            summary=summary,
            command=_eval_command(cases_path, limit, case_limit, generation_limit_per_type),
            success=failed == 0,
            output=json.dumps(summary, ensure_ascii=False),
            code_version=_runtime_code_version(),
            case_results=case_results,
        )
        connection.commit()
    finally:
        connection.close()

    report_dir = output_dir or paths.root.parent / "tests" / "generated"
    report_dir.mkdir(parents=True, exist_ok=True)
    date_token = timestamp[:10]
    json_path = report_dir / f"corpus_retrieval_eval_{date_token}.json"
    report_path = report_dir / f"corpus_retrieval_eval_{date_token}.md"
    payload = {
        "eval_run_id": eval_run_id,
        "suite_id": suite_id,
        "generated_at": timestamp,
        "case_file": str(cases_path),
        "summary": summary,
        "results": case_results,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(_render_eval_report(payload), encoding="utf-8")
    return CorpusRetrievalEvalResult(
        eval_run_id=eval_run_id,
        suite_id=suite_id,
        case_count=len(cases),
        passed=passed,
        failed=failed,
        success=failed == 0,
        case_file=cases_path,
        json_path=json_path,
        report_path=report_path,
    )


def _selected_case_types(case_types: list[str] | None) -> set[str]:
    selected = {str(item).strip() for item in (case_types or SUPPORTED_CASE_TYPES) if str(item).strip()}
    unknown = selected - set(SUPPORTED_CASE_TYPES)
    if unknown:
        raise ValueError(f"unsupported corpus case type(s): {', '.join(sorted(unknown))}")
    return selected or set(SUPPORTED_CASE_TYPES)


def _load_source_unit_rows(db_file: Path, *, doc_ids: list[str] | None) -> list[Row]:
    connection = connect(db_file)
    try:
        params: list[object] = []
        doc_filter = ""
        if doc_ids:
            placeholders = ",".join("?" for _ in doc_ids)
            doc_filter = f"AND su.doc_id IN ({placeholders})"
            params.extend(doc_ids)
        return connection.execute(
            f"""
            SELECT
                su.unit_id, su.doc_id, su.page_no, su.block_id, su.unit_type,
                su.text, su.normalized_text, su.canonical_title, su.canonical_key,
                su.content_role, su.quality_flags_json, su.importance,
                su.expected_knowledge_type, su.status, su.metadata_json,
                d.source_filename,
                EXISTS (
                    SELECT 1 FROM source_unit_fact_map sfm
                    WHERE sfm.unit_id = su.unit_id
                ) AS has_fact_link,
                EXISTS (
                    SELECT 1 FROM source_unit_evidence_map sem
                    WHERE sem.unit_id = su.unit_id
                ) AS has_evidence_link
            FROM source_units su
            LEFT JOIN documents d ON d.doc_id = su.doc_id
            WHERE COALESCE(d.is_active, 1) = 1
            {doc_filter}
            ORDER BY su.doc_id, COALESCE(su.page_no, 0), su.unit_id
            """,
            params,
        ).fetchall()
    finally:
        connection.close()


def _case_from_source_unit(row: Row, *, selected_types: set[str]) -> dict[str, object] | None:
    if _skip_reason(row, selected_types) != "":
        return None
    row_kind = _row_case_type(row)
    if row_kind == "definition":
        return _definition_case(row)
    if row_kind == "parameter":
        return _parameter_case(row)
    if row_kind == "process_activity":
        return _process_activity_case(row)
    return None


def _skip_reason(row: Row, selected_types: set[str]) -> str:
    row_kind = _row_case_type(row)
    if not row_kind:
        return "unsupported_unit_type"
    if row_kind not in selected_types:
        return "case_type_not_selected"
    if not _has_traceable_coverage(row):
        return "missing_traceable_coverage"
    if _is_noise_source_unit(row):
        return "noise_or_preface"
    if not _case_anchor(row, row_kind):
        return "missing_anchor"
    return ""


def _row_case_type(row: Row) -> str:
    blob = _row_descriptor_blob(row)
    if "definition" in blob or "term_definition" in blob:
        return "definition"
    if "parameter_row" in blob or "parameter" in blob and "|" in str(row["text"] or ""):
        return "parameter"
    if "process_practice" in blob or ("process" in blob and re.search(r"\b[A-Z]{2,6}\.\d+\.BP\d+\b", str(row["text"] or ""), re.I)):
        return "process_activity"
    return ""


def _row_descriptor_blob(row: Row) -> str:
    return " ".join(
        str(row[name] or "").casefold()
        for name in ("unit_type", "content_role", "expected_knowledge_type", "canonical_title", "canonical_key")
    )


def _has_traceable_coverage(row: Row) -> bool:
    if bool(row["has_fact_link"]) or bool(row["has_evidence_link"]):
        return True
    metadata = _json_object(row["metadata_json"])
    covered_by = metadata.get("covered_by") if isinstance(metadata.get("covered_by"), dict) else {}
    return bool(_string_list(covered_by.get("fact_ids")) or _string_list(covered_by.get("evidence_ids")))


def _is_noise_source_unit(row: Row) -> bool:
    title = _clean_text(row["canonical_title"])
    text = _clean_text(row["text"])
    role = str(row["content_role"] or "").casefold()
    unit_type = str(row["unit_type"] or "").casefold()
    status = str(row["status"] or "").casefold()
    if status in {"rejected", "noise", "ignored"}:
        return True
    if len(text) < 6 and len(title) < 2:
        return True
    if any(marker in role or marker in unit_type for marker in ("preface", "toc", "index", "catalog")):
        return True
    if re.search(r"^(前言|目次|目录|引言|参考文献)$", title):
        return True
    if re.search(r"(代替\s*GB|GB[：:]\s*代替|ICS\s*\d|中国标准出版社)", text):
        return True
    flags = [item.casefold() for item in _string_list(_json_value(row["quality_flags_json"], []))]
    return any(flag in {"noise", "preface", "index", "toc", "parse_noise"} for flag in flags)


def _case_anchor(row: Row, row_kind: str) -> str:
    if row_kind == "definition":
        return _definition_anchor(row)
    if row_kind == "parameter":
        return _parameter_anchor(row)[0]
    if row_kind == "process_activity":
        return _process_anchor(row)[0]
    return ""


def _definition_case(row: Row) -> dict[str, object] | None:
    anchor = _definition_anchor(row)
    if not anchor:
        return None
    query_anchor = _query_anchor(anchor)
    return _base_case(
        row,
        case_type="definition",
        query=f"{query_anchor}是什么意思",
        expected_query_type="definition",
        expected_evidence_shape="term_definition",
        retrieval_must_hit=_dedupe_anchors([anchor, query_anchor, _definition_definition_phrase(row)]),
    )


def _parameter_case(row: Row) -> dict[str, object] | None:
    parameter, symbol, object_name = _parameter_anchor(row)
    if not parameter:
        return None
    title = _clean_text(row["canonical_title"])
    key = _clean_text(row["canonical_key"])
    key_topic = _query_anchor(key) if key else ""
    title_topic = _query_anchor(title) if title else ""
    if key_topic and _normalize_for_contains(key_topic) != _normalize_for_contains(parameter):
        topic = key_topic
    else:
        topic = title_topic or key_topic
    object_part = _query_anchor(object_name) if object_name else ""
    if topic and _normalize_for_contains(parameter) not in _normalize_for_contains(topic):
        query = f"{topic}{object_part}{parameter}参数是什么"
    else:
        query = f"{topic or object_part or parameter}{parameter if object_part and parameter not in object_part else ''}参数是什么"
    return _base_case(
        row,
        case_type="parameter",
        query=query,
        expected_query_type="parameter_lookup",
        expected_evidence_shape="parameter_definition",
        retrieval_must_hit=_dedupe_anchors([parameter, symbol, object_name, key, title]),
    )


def _process_activity_case(row: Row) -> dict[str, object] | None:
    process_anchor, bp_code, bp_title = _process_anchor(row)
    if not process_anchor or not bp_code:
        return None
    title = _clean_text(row["canonical_title"])
    if title and not re.fullmatch(r"[A-Z]{2,6}\.\d+\s*基本实践", title, re.I):
        query = f"{_query_anchor(process_anchor)} {title}有哪些活动"
    else:
        query = f"{_query_anchor(process_anchor)}有哪些活动"
    case = _base_case(
        row,
        case_type="process_activity",
        query=query,
        expected_query_type="lifecycle_lookup",
        expected_evidence_shape="process_activity",
        retrieval_must_hit=_dedupe_anchors([bp_code, process_anchor, bp_title]),
    )
    case["expected_min_graph_candidates"] = 1
    return case


def _base_case(
    row: Row,
    *,
    case_type: str,
    query: str,
    expected_query_type: str,
    expected_evidence_shape: str,
    retrieval_must_hit: list[str],
) -> dict[str, object]:
    unit_id = str(row["unit_id"])
    doc_id = str(row["doc_id"])
    metadata = _json_object(row["metadata_json"])
    semantic_key = str(metadata.get("semantic_key") or row["canonical_key"] or "").strip()
    return {
        "case_id": _case_id(unit_id, case_type),
        "name": f"{case_type}:{unit_id}",
        "query": _clean_query(query),
        "assert_mode": "context_contains",
        "source": "corpus_eval",
        "status": "active",
        "case_type": case_type,
        "coverage_unit_id": unit_id,
        "coverage_semantic_key": semantic_key,
        "source_unit_type": str(row["unit_type"] or ""),
        "source_unit_role": str(row["content_role"] or ""),
        "expected_doc_id": doc_id,
        "expected_pages": [int(row["page_no"])] if row["page_no"] is not None else [],
        "expected_query_type": expected_query_type,
        "expected_evidence_shape": expected_evidence_shape,
        "retrieval_must_hit": retrieval_must_hit,
        "must_hit": retrieval_must_hit[:1],
        "negative_expected": [],
        "metadata": {
            "source_filename": str(row["source_filename"] or ""),
            "canonical_title": str(row["canonical_title"] or ""),
            "canonical_key": str(row["canonical_key"] or ""),
            "expected_knowledge_type": str(row["expected_knowledge_type"] or ""),
            "importance": str(row["importance"] or ""),
        },
    }


def _definition_anchor(row: Row) -> str:
    title = _strip_section_prefix(_clean_text(row["canonical_title"]))
    if _usable_anchor(title):
        return title
    text = _clean_text(row["text"])
    bold = re.search(r"\*\*([^*]{2,80})\*\*", str(row["text"] or ""))
    if bold and _usable_anchor(bold.group(1)):
        return _clean_text(bold.group(1))
    match = re.match(r"(.{2,50}?)(?:[:：]|是指|表示|means|refers to)", text, flags=re.I)
    if match and _usable_anchor(match.group(1)):
        return _clean_text(match.group(1))
    return ""


def _definition_definition_phrase(row: Row) -> str:
    text = _clean_text(row["text"])
    for phrase in re.split(r"[。；;:\n]", text):
        phrase = _clean_text(phrase)
        if 4 <= len(phrase) <= 40 and not phrase.startswith(_definition_anchor(row)):
            return phrase
    return ""


def _parameter_anchor(row: Row) -> tuple[str, str, str]:
    text = _clean_text(row["text"])
    parts = [_clean_text(part) for part in re.split(r"\s*\|\s*", text) if _clean_text(part)]
    object_name = parts[0] if len(parts) >= 3 and _usable_anchor(parts[0], allow_short=True) else ""
    if len(parts) >= 3:
        parameter = _strip_footnote_marker(parts[1])
    elif len(parts) >= 2:
        parameter = _strip_footnote_marker(parts[0])
    else:
        parameter = _strip_footnote_marker(_strip_section_prefix(_clean_text(row["canonical_key"]) or _clean_text(row["canonical_title"])))
    symbol = ""
    if len(parts) >= 3 and _usable_anchor(parts[2], allow_short=True):
        symbol = parts[2]
    elif len(parts) >= 2 and _usable_anchor(parts[1], allow_short=True):
        symbol = parts[1]
    if not _usable_anchor(parameter):
        return "", symbol, object_name
    return parameter, symbol, object_name


def _process_anchor(row: Row) -> tuple[str, str, str]:
    text = _clean_text(row["text"])
    title = _clean_text(row["canonical_title"])
    key = _clean_text(row["canonical_key"])
    bp_match = re.search(r"\b([A-Z]{2,6}\.\d+\.BP\d+)\b", text, flags=re.I)
    bp_code = bp_match.group(1).upper() if bp_match else ""
    process_match = re.search(r"\b([A-Z]{2,6}\.\d+)\b", key or title or text, flags=re.I)
    process_code = process_match.group(1).upper() if process_match else (bp_code.rsplit(".BP", 1)[0] if bp_code else "")
    bp_title = ""
    if bp_code:
        title_match = re.search(re.escape(bp_code) + r"\s*[:：]\s*([^。；;\n]{2,60})", text, flags=re.I)
        if title_match:
            bp_title = _clean_text(title_match.group(1))
    return process_code, bp_code, bp_title


def _case_id(unit_id: str, case_type: str) -> str:
    digest = hashlib.sha1(f"{unit_id}:{case_type}".encode("utf-8")).hexdigest()[:10].upper()
    suffix = re.sub(r"[^A-Za-z0-9]+", "-", unit_id).strip("-")[:28].upper()
    return f"CORPUS-{suffix}-{digest}" if suffix else f"CORPUS-{digest}"


def _load_cases(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(raw_cases, list):
        raise ValueError(f"case file must contain a list or cases array: {path}")
    cases: list[dict[str, object]] = []
    for index, item in enumerate(raw_cases, start=1):
        if not isinstance(item, dict):
            continue
        case = dict(item)
        case.setdefault("case_id", _case_id(str(case.get("coverage_unit_id") or index), str(case.get("case_type") or "case")))
        case.setdefault("assert_mode", "context_contains")
        case.setdefault("source", "corpus_eval")
        cases.append(case)
    return cases


def _evaluate_case(workspace_root: Path, case: dict[str, object], *, index: int, limit: int) -> dict[str, object]:
    case_id = str(case.get("case_id") or _case_id(str(index), str(case.get("case_type") or "case")))
    query = str(case.get("query") or "").strip()
    preferred_doc_id = str(case.get("expected_doc_id") or case.get("target_doc_id") or "").strip() or None
    try:
        context = build_query_context(workspace_root, query, limit=limit, preferred_doc_id=preferred_doc_id)
    except Exception as exc:
        return {
            "case_id": case_id,
            "passed": False,
            "failure_reason": f"evaluation_exception:{type(exc).__name__}",
            "retrieved_items": [],
            "answer": "",
            "metrics": {"exception": str(exc)[:500]},
        }
    retrieved_items = _retrieved_items_from_context(context)
    trace_metrics = _trace_metrics_from_context(context)
    retrieval_quality = evaluate_retrieval_quality(
        case=case,
        retrieved_items=retrieved_items,
        trace_metrics=trace_metrics,
    )
    contract = _case_contract_result(case, trace_metrics, retrieved_items)
    passed = bool(retrieval_quality.get("failure_attribution") == "ok" and contract["passed"])
    failure_reason = None if passed else _failure_reason(retrieval_quality, contract)
    return {
        "case_id": case_id,
        "query": query,
        "case_type": case.get("case_type"),
        "coverage_unit_id": case.get("coverage_unit_id"),
        "expected_doc_id": case.get("expected_doc_id"),
        "passed": passed,
        "failure_reason": failure_reason,
        "retrieved_items": retrieved_items,
        "answer": "",
        "metrics": {
            **trace_metrics,
            "retrieval_quality": retrieval_quality,
            "contract": contract,
            "expected_evidence_shape": case.get("expected_evidence_shape"),
            "shape_contract_matched": contract.get("evidence_shape_match"),
            "shape_contract_failure_reason": contract.get("shape_contract_failure_reason"),
        },
    }


def _case_contract_result(
    case: dict[str, object],
    trace_metrics: dict[str, object],
    retrieved_items: list[dict[str, object]],
) -> dict[str, object]:
    failures: list[str] = []
    expected_query_type = str(case.get("expected_query_type") or "").strip()
    actual_query_type = str(trace_metrics.get("query_type") or "").strip()
    if expected_query_type and actual_query_type != expected_query_type:
        failures.append("query_type_mismatch")

    expected_doc_id = str(case.get("expected_doc_id") or case.get("target_doc_id") or "").strip()
    top_doc_ids = [str(item.get("doc_id") or "") for item in retrieved_items[:5]]
    if expected_doc_id and expected_doc_id not in top_doc_ids:
        failures.append("expected_doc_missing")

    expected_shape = str(case.get("expected_evidence_shape") or case.get("evidence_shape") or "").strip()
    actual_shape = str(trace_metrics.get("evidence_shape") or "").strip()
    shape_match = None
    if expected_shape:
        shape_match = actual_shape == expected_shape
        if not shape_match:
            failures.append("evidence_shape_mismatch")

    min_graph = _int_or_none(case.get("expected_min_graph_candidates"))
    if min_graph is not None and int(trace_metrics.get("graph_candidate_count") or 0) < min_graph:
        failures.append("graph_missing")

    return {
        "passed": not failures,
        "failures": failures,
        "expected_query_type": expected_query_type,
        "actual_query_type": actual_query_type,
        "expected_doc_id": expected_doc_id,
        "top_doc_ids": top_doc_ids,
        "expected_evidence_shape": expected_shape,
        "actual_evidence_shape": actual_shape,
        "evidence_shape_match": shape_match,
        "expected_min_graph_candidates": min_graph,
        "actual_graph_candidate_count": trace_metrics.get("graph_candidate_count"),
        "shape_contract_failure_reason": trace_metrics.get("shape_contract_failure_reason"),
        "top_result_ids": [str(item.get("result_id") or "") for item in retrieved_items[:5]],
    }


def _failure_reason(retrieval_quality: dict[str, object], contract: dict[str, object]) -> str:
    failures = [str(item) for item in contract.get("failures") or []]
    priority = [
        "query_type_mismatch",
        "evidence_shape_mismatch",
        "graph_missing",
        "expected_doc_missing",
    ]
    for item in priority:
        if item in failures:
            return item
    if failures:
        return failures[0]
    return str(retrieval_quality.get("failure_attribution") or "retrieval_quality_failed")


def _retrieved_items_from_context(context: dict[str, object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for hit in list(context.get("hits") or [])[:10]:
        if not isinstance(hit, dict):
            continue
        items.append(
            {
                "result_type": hit.get("result_type"),
                "result_id": hit.get("result_id"),
                "doc_id": hit.get("doc_id"),
                "page_no": hit.get("page_no"),
                "score": hit.get("score"),
                "snippet": str(hit.get("snippet") or "")[:800],
                "graph_source": bool(hit.get("graph_source")),
                "channel": hit.get("channel"),
                "channels": hit.get("channels") or [],
            }
        )
    return items


def _trace_metrics_from_context(context: dict[str, object]) -> dict[str, object]:
    retrieval_plan = context.get("retrieval_plan") if isinstance(context.get("retrieval_plan"), dict) else {}
    topic_resolution = context.get("topic_resolution") if isinstance(context.get("topic_resolution"), dict) else {}
    candidates = topic_resolution.get("candidate_entities") if isinstance(topic_resolution.get("candidate_entities"), list) else []
    hits = context.get("hits") if isinstance(context.get("hits"), list) else []
    evidence_judgement = context.get("evidence_judgement") if isinstance(context.get("evidence_judgement"), dict) else {}
    shape_diagnostics = evidence_judgement.get("shape_diagnostics") if isinstance(evidence_judgement.get("shape_diagnostics"), dict) else {}
    shape_contract = shape_diagnostics.get("shape_contract") if isinstance(shape_diagnostics.get("shape_contract"), dict) else {}
    shape_contract_diagnosis = (
        shape_diagnostics.get("shape_contract_diagnosis")
        if isinstance(shape_diagnostics.get("shape_contract_diagnosis"), dict)
        else {}
    )
    return {
        "query_type": (context.get("rewrite") or {}).get("query_type") if isinstance(context.get("rewrite"), dict) else "",
        "retrieval_channels": retrieval_plan.get("channels") if isinstance(retrieval_plan.get("channels"), list) else [],
        "graph_candidate_count": int(retrieval_plan.get("graph_candidate_count") or 0),
        "routing_summary_hit_count": int(retrieval_plan.get("routing_summary_hit_count") or 0),
        "topic_resolution_confidence": float(topic_resolution.get("confidence") or 0.0),
        "topic_candidate_names": [
            str(item.get("canonical_name") or "")
            for item in candidates[:5]
            if isinstance(item, dict)
        ],
        "top_hit_ids": [
            str(item.get("result_id") or "")
            for item in hits[:5]
            if isinstance(item, dict)
        ],
        "top_hit_doc_ids": [
            str(item.get("doc_id") or "")
            for item in hits[:5]
            if isinstance(item, dict)
        ],
        "retrieval_run_id": context.get("retrieval_run_id"),
        "evidence_judge_sufficient": evidence_judgement.get("sufficient"),
        "evidence_judge_reason": evidence_judgement.get("reason"),
        "evidence_shape": str(evidence_judgement.get("evidence_shape") or ""),
        "evidence_shape_diagnostics": shape_diagnostics,
        "shape_contract_query_type": str(shape_contract.get("query_type") or ""),
        "shape_contract_allowed_shapes": _string_list(shape_contract.get("allowed_shapes")),
        "shape_contract_required": shape_contract.get("required") if isinstance(shape_contract, dict) else None,
        "shape_contract_matched": shape_contract.get("matched") if isinstance(shape_contract, dict) else None,
        "shape_contract_failure_reason": str(shape_contract_diagnosis.get("reason") or ""),
        "shape_contract_suggested_action": str(shape_contract_diagnosis.get("action") or ""),
    }


def _generation_summary(
    cases: list[dict[str, object]],
    rows: list[Row],
    skipped_counts: dict[str, int],
    selected_types: set[str],
    doc_ids: list[str] | None,
) -> dict[str, object]:
    return {
        "source_unit_count": len(rows),
        "case_count": len(cases),
        "selected_case_types": sorted(selected_types),
        "doc_ids": doc_ids or [],
        "case_type_counts": _count_by(cases, "case_type"),
        "doc_counts": _count_by(cases, "expected_doc_id"),
        "skipped_counts": dict(sorted(skipped_counts.items())),
    }


def _eval_summary(
    cases: list[dict[str, object]],
    case_results: list[dict[str, object]],
    case_file: Path,
    generation_summary: dict[str, object] | None,
) -> dict[str, object]:
    passed = sum(1 for item in case_results if item.get("passed"))
    failed = len(case_results) - passed
    failure_counts: dict[str, int] = {}
    query_type_counts: dict[str, int] = {}
    shape_counts: dict[str, int] = {}
    for item in case_results:
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        query_type = str(metrics.get("query_type") or "unknown")
        query_type_counts[query_type] = query_type_counts.get(query_type, 0) + 1
        shape = str(metrics.get("evidence_shape") or "unknown")
        shape_counts[shape] = shape_counts.get(shape, 0) + 1
        if not item.get("passed"):
            reason = str(item.get("failure_reason") or "unknown")
            failure_counts[reason] = failure_counts.get(reason, 0) + 1
    return {
        "suite": "corpus_retrieval",
        "case_file": str(case_file),
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / max(1, len(cases)), 6),
        "case_type_counts": _count_by(cases, "case_type"),
        "query_type_counts": dict(sorted(query_type_counts.items())),
        "evidence_shape_counts": dict(sorted(shape_counts.items())),
        "failure_counts": dict(sorted(failure_counts.items())),
        "generation_summary": generation_summary or {},
    }


def _render_generation_report(payload: dict[str, object]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    lines = [
        "# Corpus Retrieval Case Generation",
        "",
        f"- Generated at: {payload.get('generated_at')}",
        f"- Source units scanned: {summary.get('source_unit_count', 0)}",
        f"- Cases: {summary.get('case_count', 0)}",
        "",
        "## Case Types",
    ]
    lines.extend(_render_counts(summary.get("case_type_counts")))
    lines.extend(["", "## Skipped"])
    lines.extend(_render_counts(summary.get("skipped_counts")))
    lines.append("")
    return "\n".join(lines)


def _render_eval_report(payload: dict[str, object]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    lines = [
        "# Corpus Retrieval Eval",
        "",
        f"- Eval run: {payload.get('eval_run_id')}",
        f"- Case file: {payload.get('case_file')}",
        f"- Total: {summary.get('total', 0)}",
        f"- Passed: {summary.get('passed', 0)}",
        f"- Failed: {summary.get('failed', 0)}",
        f"- Pass rate: {summary.get('pass_rate', 0)}",
        "",
        "## Failure Counts",
    ]
    lines.extend(_render_counts(summary.get("failure_counts")))
    lines.extend(["", "## Evidence Shapes"])
    lines.extend(_render_counts(summary.get("evidence_shape_counts")))
    lines.extend(["", "## Failed Cases"])
    failed = [item for item in results if isinstance(item, dict) and not item.get("passed")]
    if not failed:
        lines.append("- none")
    for item in failed[:50]:
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        contract = metrics.get("contract") if isinstance(metrics.get("contract"), dict) else {}
        retrieval_quality = metrics.get("retrieval_quality") if isinstance(metrics.get("retrieval_quality"), dict) else {}
        lines.extend(
            [
                f"- {item.get('case_id')}: {item.get('failure_reason')}",
                f"  - query: {item.get('query')}",
                f"  - coverage_unit_id: {item.get('coverage_unit_id')}",
                f"  - query_type: {contract.get('actual_query_type')}",
                f"  - evidence_shape: {contract.get('actual_evidence_shape')}",
                f"  - missing_anchors: {retrieval_quality.get('must_hit_missing')}",
                f"  - top_result_ids: {contract.get('top_result_ids')}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _render_counts(value: object) -> list[str]:
    counts = value if isinstance(value, dict) else {}
    if not counts:
        return ["- none"]
    return [f"- {key}: {counts[key]}" for key in sorted(counts)]


def _eval_command(cases_path: Path, limit: int, case_limit: int | None, generation_limit_per_type: int) -> str:
    command = f"eakb run-corpus-retrieval-eval --case-file {cases_path} --limit {limit}"
    if case_limit is not None:
        command += f" --case-limit {case_limit}"
    command += f" --generation-limit-per-type {generation_limit_per_type}"
    return command


def _count_by(cases: list[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        value = str(case.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _query_anchor(anchor: str) -> str:
    value = _strip_footnote_marker(_strip_section_prefix(_clean_text(anchor)))
    value = re.sub(r"\s+", " ", value).strip()
    english_match = re.match(r"([\u4e00-\u9fff0-9（）()\-/ ]{2,40}?)(?:\s+[A-Za-z][A-Za-z0-9 ,/\-()]{1,})$", value)
    if english_match and re.search(r"[\u4e00-\u9fff]", english_match.group(1)):
        value = english_match.group(1).strip()
    if len(value) > 48:
        value = value[:48].rstrip()
    return value


def _strip_footnote_marker(value: str) -> str:
    return re.sub(r"\^[A-Za-z0-9]+$", "", value).strip()


def _clean_query(query: str) -> str:
    return re.sub(r"\s+", " ", _clean_text(query)).strip()


def _clean_text(value: object) -> str:
    text = str(value or "")
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[*`$]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \t\r\n;；,，")


def _strip_section_prefix(value: str) -> str:
    return re.sub(r"^(?:第?\d+(?:\.\d+)*[、.\s]+|[A-Z]\.\d+(?:\.\d+)*\s+)", "", value, flags=re.I).strip()


def _usable_anchor(value: str, *, allow_short: bool = False) -> bool:
    text = _clean_text(value)
    if not text:
        return False
    if not allow_short and len(text) < 2:
        return False
    if text in {"-", "—", "一", "无", "GB", "GB/T", "ISO", "IEC"}:
        return False
    if re.fullmatch(r"[-—_/\\.,，。;；:：\s]+", text):
        return False
    return True


def _dedupe_anchors(values: list[str]) -> list[str]:
    anchors: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if not _usable_anchor(text, allow_short=True):
            continue
        key = _normalize_for_contains(text)
        if key in seen:
            continue
        seen.add(key)
        anchors.append(text)
    return anchors[:5]


def _normalize_for_contains(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _json_value(value: object, default: object) -> object:
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _json_object(value: object) -> dict[str, object]:
    parsed = _json_value(value, {})
    return parsed if isinstance(parsed, dict) else {}


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
