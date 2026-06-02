"""Coverage orchestrator: build per-document source-unit coverage and
test-gap candidates.

The actual implementation of gap detection, candidate matching, scoring,
and report rendering lives in the focused submodules:
- `_gap_detection`: source-unit extraction, fact/wiki/test matching,
  test-gap candidate construction
- `_report_rendering`: coverage summary, sorted-uncovered-rows, markdown
  report rendering

This module wires them together into the public ``build_coverage_for_document``
and ``build_test_gap_candidates_for_document`` entry points, and defines
the ``CoverageBuildResult`` / ``TestGapCandidateBuildResult`` dataclasses.
"""
from __future__ import annotations

import json
import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..closed_loop_store import sync_source_units_from_matrix
from ..config import AppPaths
from ..db import connect
from ..knowledge_units import _normalize_unit_metadata

from ._gap_detection import (
    _augment_source_units_from_facts,
    _build_source_units,
    _build_test_gap_candidates,
    _clean_test_gap_label,
    _is_actionable_test_gap_row,
    _coverage_status,
    _dedupe_test_gap_rows,
    
    _load_fact_evidence_map,
    _load_test_cases,
    _match_evidence_for_unit,
    _match_facts_for_unit,
    _match_test_cases_for_unit,
    _match_wiki_pages_for_unit,
    _recommended_test_seed,
    _row_to_fact,
    _row_to_wiki_page,
    _sort_test_gap_rows,
    _sort_uncovered_rows,
    _test_case_blob,
    _test_gap_candidate_from_row,
    _unit_with_canonical_metadata,
    _fact_text_candidates,
    _source_unit_text_matches_fact,
    _definition_matches_fact,
    _requirement_matches_fact,
    _parameter_row_matches_fact,
    _process_unit_matches_fact,
    _definition_source_unit,
    _requirement_source_unit,
    _procedure_source_unit,
    _parameter_row_source_units,
    
    _is_potentially_misaligned,
    _is_source_unit_inventory_noise,
    _looks_like_boilerplate_definition_pair,
    _looks_like_clause_reference_noise,
    _looks_like_figure_legend_definition,
    _looks_like_low_value_parameter_gap,
    _looks_like_structural_inventory_noise,
    _looks_like_table_syntax_source,
    _looks_like_test_gap_noise,
    _looks_like_toc_entry_noise,
    _parameter_row_aliases,
    _requirement_importance,
    _stable_fact_fallback_unit_id,
)
from ._report_rendering import (
    _best_nonempty,
    _build_summary,
    _clean_label,
    _clean_text,
    _compare_key,
    _first_sentence,
    _group_summary,
    _normalize_header_name,
    _normalize_unit,
    _rate,
    _render_report,
    _render_test_gap_report,
    _row_value,
    _safe_json,
    _soft_contains,
    _string_list,
    _unique_strings,
    _utc_now,
)



V0_UNIT_TYPES = {"definition_unit", "parameter_row_unit", "process_unit", "requirement_unit"}
SOURCE_UNIT_EXPORT_VERSION = "coverage-v1"



@dataclass(frozen=True)
class CoverageBuildResult:
    doc_id: str
    source_unit_count: int
    text_coverage_rate: float
    semantic_coverage_rate: float
    object_coverage_rate: float
    test_coverage_rate: float
    uncovered_counts: dict[str, int]
    source_units_path: Path
    matrix_path: Path
    uncovered_path: Path
    summary_path: Path
    report_path: Path


@dataclass(frozen=True)
class TestGapCandidateBuildResult:
    doc_id: str
    candidate_count: int
    candidates_path: Path
    report_path: Path


def build_coverage_for_document(
    workspace_root: Path,
    doc_id: str,
    *,
    tests_generated_dir: Path | None = None,
) -> CoverageBuildResult:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    now = _utc_now()

    try:
        paths.coverage_reports.mkdir(parents=True, exist_ok=True)
        document = connection.execute(
            """
            SELECT doc_id, source_filename
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        if document is None:
            raise ValueError(f"document not found: {doc_id}")

        facts = [_row_to_fact(row) for row in connection.execute(
            """
            SELECT
                fact_id,
                fact_type,
                subject_entity_id,
                predicate,
                object_value,
                object_entity_id,
                qualifiers_json,
                confidence
            FROM facts
            WHERE source_doc_id = ?
            ORDER BY fact_id
            """,
            (doc_id,),
        ).fetchall()]
        source_units = _augment_source_units_from_facts(_build_source_units(paths, doc_id), facts, doc_id)
        evidence_rows = connection.execute(
            """
            SELECT evidence_id, page_no, normalized_text
            FROM evidence
            WHERE doc_id = ?
            ORDER BY page_no, evidence_id
            """,
            (doc_id,),
        ).fetchall()
        fact_evidence_map = _load_fact_evidence_map(connection, doc_id)
        entity_rows = {
            row["entity_id"]: {
                "entity_id": row["entity_id"],
                "canonical_name": row["canonical_name"],
                "entity_type": row["entity_type"],
            }
            for row in connection.execute(
                """
                SELECT entity_id, canonical_name, entity_type
                FROM entities
                ORDER BY entity_id
                """
            ).fetchall()
        }
        wiki_rows = [_row_to_wiki_page(row) for row in connection.execute(
            """
            SELECT page_id, page_type, title, entity_id, source_fact_ids_json
            FROM wiki_pages
            WHERE json_extract(source_doc_ids_json, '$[0]') = ?
            ORDER BY page_id
            """,
            (doc_id,),
        ).fetchall()]
        test_cases = _load_test_cases(
            tests_generated_dir
            or workspace_root.resolve().parent / "tests" / "generated",
            doc_id,
        )

        matrix_rows: list[dict[str, object]] = []
        uncovered_rows: list[dict[str, object]] = []

        for unit in source_units:
            matched_facts = _match_facts_for_unit(unit, facts)
            fact_ids = [fact["fact_id"] for fact in matched_facts]

            evidence_ids = sorted({
                evidence_id
                for fact_id in fact_ids
                for evidence_id in fact_evidence_map.get(fact_id, [])
            })
            if not evidence_ids:
                evidence_ids = _match_evidence_for_unit(unit, evidence_rows)

            entity_ids = sorted({
                entity_id
                for fact in matched_facts
                for entity_id in [fact.get("subject_entity_id"), fact.get("object_entity_id")]
                if entity_id
            })
            wiki_page_ids = _match_wiki_pages_for_unit(unit, fact_ids, entity_ids, wiki_rows)
            matched_tests = _match_test_cases_for_unit(unit, test_cases)
            golden_case_ids = [item["case_id"] for item in matched_tests if item["suite"] == "golden"]
            regression_case_ids = [item["case_id"] for item in matched_tests if item["suite"] == "regression"]
            misaligned = _is_potentially_misaligned(unit, matched_facts, entity_ids, wiki_page_ids, entity_rows, wiki_rows)
            coverage_status = _coverage_status(evidence_ids, fact_ids, entity_ids, golden_case_ids, regression_case_ids, misaligned)

            row = {
                "unit_id": unit.unit_id,
                "unit_type": unit.unit_type,
                "page_no": unit.page_no,
                "semantic_key": unit.semantic_key,
                "aliases": unit.aliases,
                "canonical_title": unit.canonical_title,
                "canonical_key": unit.canonical_key,
                "content_role": unit.content_role,
                "quality_flags": unit.quality_flags,
                "importance": unit.importance,
                "source_text": unit.source_text,
                "source_locator": unit.source_locator,
                "metadata": unit.metadata,
                "covered_by": {
                    "evidence_ids": evidence_ids,
                    "fact_ids": fact_ids,
                    "entity_ids": entity_ids,
                    "wiki_page_ids": wiki_page_ids,
                    "golden_case_ids": golden_case_ids,
                    "regression_case_ids": regression_case_ids,
                },
                "coverage_flags": {
                    "text_covered": bool(evidence_ids),
                    "semantic_covered": bool(fact_ids),
                    "object_covered": bool(entity_ids),
                    "knowledge_page_covered": bool(wiki_page_ids),
                    "test_covered": bool(golden_case_ids or regression_case_ids),
                },
                "coverage_status": coverage_status,
                "semantic_misaligned": misaligned,
            }
            matrix_rows.append(row)
            if coverage_status != "covered":
                uncovered_rows.append(row)

        summary = _build_summary(
            doc_id=doc_id,
            source_filename=str(document["source_filename"]),
            generated_at=now,
            matrix_rows=matrix_rows,
        )

        source_units_path = paths.coverage_reports / f"{doc_id}.source_units.json"
        matrix_path = paths.coverage_reports / f"{doc_id}.coverage_matrix.json"
        uncovered_path = paths.coverage_reports / f"{doc_id}.uncovered_units.json"
        summary_path = paths.coverage_reports / f"{doc_id}.summary.json"
        report_path = paths.coverage_reports / f"{doc_id}.coverage_report.md"
        test_gap_candidates = _build_test_gap_candidates(doc_id, now, matrix_rows)
        test_gap_candidates_path = paths.coverage_reports / f"{doc_id}.test_gap_candidates.json"
        test_gap_report_path = paths.coverage_reports / f"{doc_id}.test_gap_candidates.md"

        source_units_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "generated_at": now,
                    "version": SOURCE_UNIT_EXPORT_VERSION,
                    "source_unit_count": len(source_units),
                    "items": [unit.to_dict() for unit in source_units],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        matrix_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "generated_at": now,
                    "version": SOURCE_UNIT_EXPORT_VERSION,
                    "items": matrix_rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        uncovered_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "generated_at": now,
                    "version": SOURCE_UNIT_EXPORT_VERSION,
                    "items": _sort_uncovered_rows(uncovered_rows),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        report_path.write_text(_render_report(summary, _sort_uncovered_rows(uncovered_rows)), encoding="utf-8")
        test_gap_candidates_path.write_text(json.dumps(test_gap_candidates, ensure_ascii=False, indent=2), encoding="utf-8")
        test_gap_report_path.write_text(_render_test_gap_report(test_gap_candidates), encoding="utf-8")
        sync_source_units_from_matrix(connection, doc_id, matrix_rows, generated_at=now)
        connection.commit()

        return CoverageBuildResult(
            doc_id=doc_id,
            source_unit_count=int(summary["source_unit_count"]),
            text_coverage_rate=float(summary["text_coverage_rate"]),
            semantic_coverage_rate=float(summary["semantic_coverage_rate"]),
            object_coverage_rate=float(summary["object_coverage_rate"]),
            test_coverage_rate=float(summary["test_coverage_rate"]),
            uncovered_counts=dict(summary["uncovered_counts"]),
            source_units_path=source_units_path,
            matrix_path=matrix_path,
            uncovered_path=uncovered_path,
            summary_path=summary_path,
            report_path=report_path,
        )
    finally:
        connection.close()


def build_test_gap_candidates_for_document(
    workspace_root: Path,
    doc_id: str,
    *,
    limit: int | None = None,
    rebuild: bool = False,
    excluded_unit_ids: set[str] | None = None,
) -> TestGapCandidateBuildResult:
    paths = AppPaths.from_root(workspace_root)
    paths.coverage_reports.mkdir(parents=True, exist_ok=True)
    matrix_path = paths.coverage_reports / f"{doc_id}.coverage_matrix.json"
    if rebuild or not matrix_path.exists():
        build_coverage_for_document(workspace_root, doc_id)

    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    generated_at = _utc_now()
    candidates = _build_test_gap_candidates(
        doc_id,
        generated_at,
        list(payload.get("items") or []),
        limit=limit,
        excluded_unit_ids=excluded_unit_ids,
    )
    candidates_path = paths.coverage_reports / f"{doc_id}.test_gap_candidates.json"
    report_path = paths.coverage_reports / f"{doc_id}.test_gap_candidates.md"
    candidates_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(_render_test_gap_report(candidates), encoding="utf-8")
    return TestGapCandidateBuildResult(
        doc_id=doc_id,
        candidate_count=len(candidates["items"]),
        candidates_path=candidates_path,
        report_path=report_path,
    )


