from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from .config import AppPaths
from .logging_config import get_logger

_logger = get_logger(__name__)
from .db import connect
from .parse_views import list_parse_view_pages, summarize_parse_view_selection


def build_document_diagnostics(workspace_root: Path, doc_id: str) -> dict[str, object]:
    """Build a comprehensive diagnostics snapshot for *doc_id*.

    Aggregates parse quality, evidence/fact coverage, and pipeline
    warnings into a single dict suitable for the API server's
    ``/document-diagnostics`` endpoint. Sections are individually
    fail-soft: a missing table or empty result is recorded but does
    not abort the whole report.
    """
    _logger.info("doc_diagnostics:start doc_id=%s", doc_id)
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
            SELECT fact_id, fact_type, predicate, object_value, qualifiers_json
            FROM facts
            WHERE source_doc_id = ?
            ORDER BY fact_id
            """,
            (doc_id,),
        ).fetchall()
        source_unit_rows = _query_rows(
            connection,
            "source_units",
            """
            SELECT unit_id, page_no, status
            FROM source_units
            WHERE doc_id = ?
            ORDER BY page_no, unit_id
            """,
            (doc_id,),
        )
        source_unit_fact_rows = _query_rows(
            connection,
            "source_unit_fact_map",
            """
            SELECT unit_id, count(DISTINCT fact_id) AS linked_fact_count
            FROM source_unit_fact_map
            WHERE doc_id = ?
            GROUP BY unit_id
            """,
            (doc_id,),
        )
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
        parse_view_summary = summarize_parse_view_selection(connection, doc_id)
        parse_view_detail = list_parse_view_pages(connection, doc_id, text_limit=0)

        page_count = int(document["page_count"] or 0)
        evidence_page_set = {int(row["page_no"]) for row in evidence_rows if int(row["page_no"] or 0) > 0}
        effective_text_page_count = len(evidence_page_set)
        empty_or_weak_pages = [page["page_no"] for page in page_rows if page["page_status"] != "ready"]
        high_risk_pages = [page["page_no"] for page in page_rows if page["risk_level"] == "high"]
        parse_quality_profile = _build_parse_quality_profile(
            page_rows=page_rows,
            evidence_rows=evidence_rows,
            fact_rows=fact_rows,
            source_unit_rows=source_unit_rows,
            source_unit_fact_rows=source_unit_fact_rows,
            quality_payload=quality_payload,
            parse_view_pages=parse_view_detail.get("pages", []),
            coverage_summary=coverage_summary,
        )

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
        if parse_quality_profile["actionable_parse_risk_pages"]:
            warnings.append("存在没有 evidence 支撑的高风险页面，解析质量闭环需要处理。")
        if parse_quality_profile["chain_gap_pages"]:
            warnings.append("存在高风险页面证据链未闭合，需检查 source_units 或 fact 映射。")

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
            "parse_quality": parse_quality_profile,
            "parse_views": parse_view_summary,
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


def _query_rows(connection: sqlite3.Connection, table: str, sql: str, params: tuple[object, ...]) -> list[sqlite3.Row]:
    if not _table_exists(connection, table):
        return []
    return list(connection.execute(sql, params).fetchall())


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _build_parse_quality_profile(
    *,
    page_rows,
    evidence_rows,
    fact_rows,
    source_unit_rows,
    source_unit_fact_rows,
    quality_payload: dict[str, object],
    parse_view_pages: list[dict[str, object]] | None = None,
    coverage_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    quality_by_page = _quality_pages_by_no(quality_payload)
    high_pages = [
        row
        for row in page_rows
        if str(row["risk_level"] or "").lower() == "high"
        or _quality_page_has_risk(quality_by_page.get(int(row["page_no"] or 0), {}))
    ]
    high_page_numbers = [int(row["page_no"] or 0) for row in high_pages if int(row["page_no"] or 0) > 0]
    evidence_counts = _count_by_page(evidence_rows)
    fact_counts = _fact_counts_by_page(fact_rows)
    source_units_by_page: dict[int, list[str]] = {}
    for row in source_unit_rows:
        page_no = int(row["page_no"] or 0)
        unit_id = str(row["unit_id"] or "")
        status = str(row["status"] or "")
        if page_no <= 0 or not unit_id or status in {"rejected", "ignored", "noise"}:
            continue
        source_units_by_page.setdefault(page_no, []).append(unit_id)

    units_with_facts = {str(row["unit_id"] or "") for row in source_unit_fact_rows if int(row["linked_fact_count"] or 0) > 0}

    root_cause_counts = {
        "no_evidence": 0,
        "evidence_without_source_unit": 0,
        "source_unit_without_fact": 0,
        "fully_backed": 0,
    }
    attribution_counts = {
        "provider_quality_issue": 0,
        "selection_rule_issue": 0,
        "extraction_chain_issue": 0,
        "structural_navigation_noise": 0,
        "review_only": 0,
        "test_coverage_gap": 0,
    }
    parse_views_by_page = _parse_views_by_page(parse_view_pages or [])
    doc_has_test_gap = _doc_has_test_gap(coverage_summary or {})
    pages: list[dict[str, object]] = []
    evidence_backed = 0
    source_unit_backed = 0
    fact_backed = 0

    for row in high_pages:
        page_no = int(row["page_no"] or 0)
        if page_no <= 0:
            continue
        quality_page = quality_by_page.get(page_no, {})
        source_unit_ids = source_units_by_page.get(page_no, [])
        linked_fact_count = fact_counts.get(page_no, 0) + sum(1 for unit_id in source_unit_ids if unit_id in units_with_facts)
        evidence_count = evidence_counts.get(page_no, 0)
        source_unit_count = len(source_unit_ids)
        if evidence_count:
            evidence_backed += 1
        if source_unit_count:
            source_unit_backed += 1
        if linked_fact_count:
            fact_backed += 1

        if evidence_count == 0:
            category = "no_evidence"
            action = "确认页面是否空白或扫描图；若不是空白页，补解析/OCR 回填。"
        elif source_unit_count == 0 and linked_fact_count == 0:
            category = "evidence_without_source_unit"
            action = "已有 evidence，但未形成 source unit 或 fact；作为复核 backlog，必要时检查知识单元抽取。"
        elif linked_fact_count == 0:
            category = "source_unit_without_fact"
            action = "检查 fact 抽取或 source_unit_fact_map，同步重建覆盖映射。"
        else:
            category = "fully_backed"
            action = "证据链完整，作为人工复核 backlog，不阻塞入库验收。"
        attribution, recommended_action = _attribute_parse_risk_page(
            root_cause=category,
            parse_view_page=parse_views_by_page.get(page_no),
            source_unit_count=source_unit_count,
            linked_fact_count=linked_fact_count,
            doc_has_test_gap=doc_has_test_gap,
        )
        attribution_counts[attribution] += 1
        root_cause_counts[category] += 1
        pages.append(
            {
                "page_no": page_no,
                "page_status": row["page_status"],
                "risk_level": row["risk_level"],
                "risk_flags": list(quality_page.get("risk_flags", [])) if isinstance(quality_page, dict) else [],
                "readability_score": quality_page.get("readability_score") if isinstance(quality_page, dict) else None,
                "evidence_count": evidence_count,
                "source_unit_count": source_unit_count,
                "linked_fact_count": linked_fact_count,
                "root_cause": category,
                "attribution": attribution,
                "suggested_action": action,
                "recommended_action": recommended_action,
            }
        )

    high_risk_count = len(high_page_numbers)
    chain_gap_pages = root_cause_counts["source_unit_without_fact"]
    return {
        "high_risk_page_count": high_risk_count,
        "actionable_parse_risk_pages": root_cause_counts["no_evidence"],
        "chain_gap_pages": chain_gap_pages,
        "review_only_pages": root_cause_counts["evidence_without_source_unit"] + root_cause_counts["fully_backed"],
        "evidence_backed_high_risk_pages": evidence_backed,
        "source_unit_backed_high_risk_pages": source_unit_backed,
        "fact_backed_high_risk_pages": fact_backed,
        "fully_backed_high_risk_pages": root_cause_counts["fully_backed"],
        "evidence_backed_rate": round(evidence_backed / high_risk_count, 6) if high_risk_count else 0.0,
        "source_unit_backed_rate": round(source_unit_backed / high_risk_count, 6) if high_risk_count else 0.0,
        "fully_backed_rate": round(root_cause_counts["fully_backed"] / high_risk_count, 6) if high_risk_count else 0.0,
        "root_cause_counts": root_cause_counts,
        "attribution_counts": attribution_counts,
        "recommended_actions": _recommended_actions_from_attribution(attribution_counts),
        "pages": pages[:50],
        "metric_contract": {
            "high_risk_page_count": "pages.risk_level = high plus quality pages with risk_flags",
            "actionable_parse_risk_pages": "high-risk pages with no evidence rows",
            "chain_gap_pages": "high-risk pages with source_units but no linked facts",
            "review_only_pages": "high-risk pages with evidence but no parse-chain blocker",
            "attribution_counts": "rule-based next-action attribution across parse views and evidence/source_unit/fact chain",
        },
    }


def _parse_views_by_page(parse_view_pages: list[dict[str, object]]) -> dict[int, dict[str, object]]:
    result: dict[int, dict[str, object]] = {}
    for page in parse_view_pages:
        if not isinstance(page, dict):
            continue
        page_no = int(page.get("page_no") or 0)
        if page_no > 0:
            result[page_no] = page
    return result


def _attribute_parse_risk_page(
    *,
    root_cause: str,
    parse_view_page: dict[str, object] | None,
    source_unit_count: int,
    linked_fact_count: int,
    doc_has_test_gap: bool,
) -> tuple[str, str]:
    candidates = parse_view_page.get("candidates", []) if isinstance(parse_view_page, dict) else []
    candidate_items = [item for item in candidates if isinstance(item, dict)]
    selected = next((item for item in candidate_items if item.get("selected")), None)
    best = _best_parse_view_candidate(candidate_items)

    if _is_structural_navigation_noise_page(candidate_items):
        return (
            "structural_navigation_noise",
            "页面主要是目录/图表目录/导航点线条目；不应要求生成 source unit 或 fact，保留为结构性噪声复核。",
        )
    if candidate_items and _all_candidates_low_quality(candidate_items):
        return (
            "provider_quality_issue",
            "所有解析候选质量都偏低；优先增强 PDF/HTML/OCR provider 或检查页面是否扫描/噪声页。",
        )
    if selected and best and str(selected.get("view_id")) != str(best.get("view_id")):
        return (
            "selection_rule_issue",
            "存在分数更高或风险更低的候选未被选中；检查 parse view selection 评分规则。",
        )
    if root_cause in {"no_evidence", "source_unit_without_fact"}:
        return (
            "extraction_chain_issue",
            "解析候选已产生，但 evidence/source_unit/fact 链路未闭合；检查抽取和映射阶段。",
        )
    if root_cause == "evidence_without_source_unit" and not source_unit_count and not linked_fact_count:
        return (
            "extraction_chain_issue",
            "页面已有 evidence 但没有 source unit/fact；检查知识单元切分和事实抽取边界。",
        )
    if root_cause == "fully_backed" and doc_has_test_gap:
        return (
            "test_coverage_gap",
            "证据链完整但测试覆盖仍有缺口；进入 golden/corpus 候选生成和激活流程。",
        )
    return (
        "review_only",
        "证据链没有阻断；保留为人工复核 backlog，不阻塞入库验收。",
    )


def _best_parse_view_candidate(candidates: list[dict[str, object]]) -> dict[str, object] | None:
    if not candidates:
        return None
    return max(candidates, key=lambda item: _candidate_quality_rank(item))


def _candidate_quality_rank(candidate: dict[str, object]) -> tuple[float, int]:
    quality = candidate.get("quality") if isinstance(candidate.get("quality"), dict) else {}
    risk_flags = quality.get("risk_flags") if isinstance(quality.get("risk_flags"), list) else []
    return (float(quality.get("score") or 0.0), -len(risk_flags))


def _all_candidates_low_quality(candidates: list[dict[str, object]]) -> bool:
    if not candidates:
        return False
    for candidate in candidates:
        quality = candidate.get("quality") if isinstance(candidate.get("quality"), dict) else {}
        score = float(quality.get("score") or 0.0)
        chars = int(quality.get("total_chars") or 0)
        risk_flags = set(quality.get("risk_flags") if isinstance(quality.get("risk_flags"), list) else [])
        if score >= 0.45 and chars >= 80 and not {"no_text", "low_text_density", "weak_table_structure"} & risk_flags:
            return False
    return True


def _is_structural_navigation_noise_page(candidates: list[dict[str, object]]) -> bool:
    text = " ".join(
        str(candidate.get("text_preview") or "")
        for candidate in candidates
        if isinstance(candidate, dict)
    ).lower()
    if not text:
        return False
    navigation_markers = (
        "contents",
        "sommaire",
        "table of contents",
        "list of figures",
        "list of tables",
        "annex ",
        "annexe ",
        "figure ",
        "table ",
        "tableau ",
        "foreword",
        "avant-propos",
        "introduction",
    )
    marker_count = sum(1 for marker in navigation_markers if marker in text)
    dot_leader_count = len(re.findall(r"\.{5,}", text))
    navigation_entry_count = len(
        re.findall(
            r"(?:annex|annexe|figure|table|tableau|[a-z]\.\d+|\d+(?:\.\d+)+).{0,100}\.{5,}.{0,30}\d{1,3}",
            text,
        )
    )
    return dot_leader_count >= 3 and (marker_count >= 2 or navigation_entry_count >= 2)


def _doc_has_test_gap(coverage_summary: dict[str, object]) -> bool:
    uncovered = coverage_summary.get("uncovered_counts") if isinstance(coverage_summary.get("uncovered_counts"), dict) else {}
    return int(uncovered.get("u3_not_tested") or 0) > 0 or float(coverage_summary.get("test_coverage_rate") or 0.0) < 1.0


def _recommended_actions_from_attribution(attribution_counts: dict[str, int]) -> list[str]:
    actions: list[str] = []
    if attribution_counts.get("provider_quality_issue"):
        actions.append("provider_quality_issue: 增强 PDF/HTML/OCR provider，优先处理所有候选都低质量的页面。")
    if attribution_counts.get("selection_rule_issue"):
        actions.append("selection_rule_issue: 调整 parse view selection 评分，使高质量候选被选中。")
    if attribution_counts.get("extraction_chain_issue"):
        actions.append("extraction_chain_issue: 检查 evidence、source_units、facts 和映射构建。")
    if attribution_counts.get("structural_navigation_noise"):
        actions.append("structural_navigation_noise: 目录/图表目录类导航页不生成知识单元，保留为结构性噪声复核。")
    if attribution_counts.get("test_coverage_gap"):
        actions.append("test_coverage_gap: 从已闭合证据链生成 golden/corpus 候选并走 activation gate。")
    if attribution_counts.get("review_only"):
        actions.append("review_only: 保留人工复核 backlog，不阻塞入库验收。")
    return actions


def _quality_pages_by_no(quality_payload: dict[str, object]) -> dict[int, dict[str, object]]:
    result: dict[int, dict[str, object]] = {}
    for page in quality_payload.get("pages", []):
        if not isinstance(page, dict):
            continue
        page_no = int(page.get("page_no") or 0)
        if page_no > 0:
            result[page_no] = page
    return result


def _quality_page_has_risk(page: dict[str, object]) -> bool:
    flags = page.get("risk_flags", [])
    actionable_flags = {
        "glyph_anomaly",
        "control_char_noise",
        "rare_ocr_glyph_noise",
        "symbol_noise",
        "fragmented_text",
        "low_readability",
    }
    return str(page.get("risk_level") or "").lower() == "high" or bool(set(flags) & actionable_flags)


def _count_by_page(rows) -> dict[int, int]:
    counts: dict[int, int] = {}
    for row in rows:
        page_no = int(row["page_no"] or 0)
        if page_no > 0:
            counts[page_no] = counts.get(page_no, 0) + 1
    return counts


def _fact_counts_by_page(rows) -> dict[int, int]:
    counts: dict[int, int] = {}
    for row in rows:
        qualifiers = _safe_json(row["qualifiers_json"], {})
        if not isinstance(qualifiers, dict):
            continue
        page_no = int(qualifiers.get("page_no") or 0)
        if page_no > 0:
            counts[page_no] = counts.get(page_no, 0) + 1
    return counts


def _safe_json(value: object, default: object) -> object:
    if not value:
        return default
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return default
