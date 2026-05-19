from __future__ import annotations

import json
import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .closed_loop_store import sync_source_units_from_matrix
from .config import AppPaths
from .db import connect
from .knowledge_units import _normalize_unit_metadata


V0_UNIT_TYPES = {"definition_unit", "parameter_row_unit", "process_unit", "requirement_unit"}
SOURCE_UNIT_EXPORT_VERSION = "coverage-v1"


@dataclass(frozen=True)
class SourceUnit:
    unit_id: str
    unit_type: str
    page_no: int
    semantic_key: str
    aliases: list[str]
    source_text: str
    canonical_title: str | None
    canonical_key: str | None
    content_role: str | None
    quality_flags: list[str]
    importance: str
    source_locator: dict[str, object]
    metadata: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


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


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _build_source_units(paths: AppPaths, doc_id: str) -> list[SourceUnit]:
    knowledge_units_path = paths.normalized / f"{doc_id}.knowledge_units.json"
    if not knowledge_units_path.exists():
        raise ValueError(f"knowledge units not found: {knowledge_units_path}")
    payload = json.loads(knowledge_units_path.read_text(encoding="utf-8"))

    source_units: list[SourceUnit] = []
    for unit in payload.get("units", []):
        unit_type = str(unit.get("type") or "").strip()
        if unit_type == "definition":
            source_unit = _definition_source_unit(unit)
            if source_unit:
                source_units.append(source_unit)
        elif unit_type == "requirement":
            source_unit = _requirement_source_unit(unit)
            if source_unit:
                source_units.append(source_unit)
        elif unit_type == "procedure":
            source_unit = _procedure_source_unit(unit)
            if source_unit:
                source_units.append(source_unit)
        elif unit_type == "table_requirement":
            source_units.extend(_parameter_row_source_units(unit))
    return source_units


def _augment_source_units_from_facts(
    source_units: list[SourceUnit],
    facts: list[dict[str, object]],
    doc_id: str,
) -> list[SourceUnit]:
    existing = {
        (unit.unit_type, unit.page_no, _compare_key(unit.semantic_key), _compare_key(unit.source_text[:80]))
        for unit in source_units
    }
    augmented = list(source_units)

    for fact in facts:
        page_no = int(fact.get("qualifiers_json", {}).get("page_no") or 0)
        payload = fact["object_value"]

        if fact["fact_type"] in {"term_definition", "concept_definition"}:
            semantic_key = _clean_label(payload.get("term"))
            source_text = _clean_text(payload.get("definition"))
            if _is_source_unit_inventory_noise(
                unit_type="definition_unit",
                semantic_key=semantic_key,
                source_text=source_text,
                quality_flags=[],
            ):
                continue
            unit = SourceUnit(
                unit_id=_stable_fact_fallback_unit_id(doc_id, "definition_unit", page_no, semantic_key, source_text),
                unit_type="definition_unit",
                page_no=page_no,
                semantic_key=semantic_key,
                aliases=_unique_strings([semantic_key]),
                source_text=source_text,
                canonical_title=semantic_key,
                canonical_key=semantic_key,
                content_role="definition",
                quality_flags=[],
                importance="high",
                source_locator={"page_no": page_no, "fact_id": fact["fact_id"]},
                metadata={"source": "fact_fallback", "fact_id": fact["fact_id"]},
            )
        elif fact["fact_type"] in {"requirement", "threshold", "table_requirement"}:
            semantic_key = _best_nonempty([
                str(payload.get("topic") or ""),
                str(payload.get("subject") or ""),
                str(payload.get("title") or ""),
            ])
            source_text = _best_nonempty([
                str(payload.get("content") or ""),
                str(payload.get("value") or ""),
            ])
            if not semantic_key:
                continue
            if _is_source_unit_inventory_noise(
                unit_type="requirement_unit",
                semantic_key=semantic_key,
                source_text=source_text,
                quality_flags=[],
            ):
                continue
            unit = SourceUnit(
                unit_id=_stable_fact_fallback_unit_id(doc_id, "requirement_unit", page_no, semantic_key, source_text),
                unit_type="requirement_unit",
                page_no=page_no,
                semantic_key=semantic_key,
                aliases=_unique_strings([semantic_key, str(payload.get("title") or ""), str(payload.get("value") or "")]),
                source_text=source_text,
                canonical_title=semantic_key,
                canonical_key=semantic_key,
                content_role=str(payload.get("scope_type") or "requirement"),
                quality_flags=[],
                importance=_requirement_importance(
                    str(payload.get("scope_type") or ""),
                    str(payload.get("content") or ""),
                    str(payload.get("value") or ""),
                ),
                source_locator={"page_no": page_no, "fact_id": fact["fact_id"]},
                metadata={"source": "fact_fallback", "fact_id": fact["fact_id"], "scope_type": payload.get("scope_type")},
            )
        elif fact["fact_type"] == "parameter_value":
            table_title = _clean_label(payload.get("table_title"))
            parameter = _clean_label(payload.get("parameter"))
            symbol = _clean_label(payload.get("symbol"))
            unit_name = _normalize_unit(str(payload.get("unit") or ""))
            state = _clean_label(payload.get("state"))
            aliases = _parameter_row_aliases(
                table_title=table_title,
                object_name=_clean_label(payload.get("object")),
                parameter=parameter,
                symbol=symbol,
                unit_name=unit_name,
                state=state,
            )
            semantic_key = aliases[0] if aliases else _best_nonempty([parameter, symbol, table_title])
            if not semantic_key:
                continue
            source_text = " | ".join(
                item
                for item in [
                    _clean_label(payload.get("object")),
                    parameter,
                    symbol,
                    unit_name,
                    _clean_label(payload.get("nominal_value")),
                    _clean_label(payload.get("max_value")),
                    _clean_label(payload.get("min_value")),
                    state,
                ]
                if item
            )
            if _is_source_unit_inventory_noise(
                unit_type="parameter_row_unit",
                semantic_key=semantic_key,
                source_text=source_text,
                quality_flags=[],
            ):
                continue
            unit = SourceUnit(
                unit_id=_stable_fact_fallback_unit_id(doc_id, "parameter_row_unit", page_no, semantic_key, source_text),
                unit_type="parameter_row_unit",
                page_no=page_no,
                semantic_key=semantic_key,
                aliases=aliases,
                source_text=source_text,
                canonical_title=table_title,
                canonical_key=semantic_key,
                content_role="parameter_row",
                quality_flags=[],
                importance="high",
                source_locator={"page_no": page_no, "fact_id": fact["fact_id"], "table_title": table_title},
                metadata={
                    "source": "fact_fallback",
                    "fact_id": fact["fact_id"],
                    "table_title": table_title,
                    "object": payload.get("object"),
                    "parameter": parameter,
                    "symbol": symbol,
                    "unit": unit_name,
                    "nominal_value": payload.get("nominal_value"),
                    "max_value": payload.get("max_value"),
                    "min_value": payload.get("min_value"),
                    "state": state,
                },
            )
        else:
            continue

        signature = (
            unit.unit_type,
            unit.page_no,
            _compare_key(unit.semantic_key),
            _compare_key(unit.source_text[:80]),
        )
        if signature in existing:
            continue
        existing.add(signature)
        augmented.append(unit)

    return augmented


def _stable_fact_fallback_unit_id(
    doc_id: str,
    unit_type: str,
    page_no: int,
    semantic_key: str,
    source_text: str,
) -> str:
    unit_label = unit_type.replace("_unit", "").replace("_", "-")
    digest = hashlib.sha1(
        "|".join(
            [
                doc_id,
                unit_type,
                str(page_no),
                _compare_key(semantic_key),
                _compare_key(source_text[:220]),
            ]
        ).encode("utf-8")
    ).hexdigest()[:12].upper()
    return f"{doc_id}:{unit_label}:{page_no}:{digest}"


def _definition_source_unit(unit: dict[str, object]) -> SourceUnit | None:
    unit = _unit_with_canonical_metadata(unit)
    title = _clean_label(unit.get("title"))
    canonical_title = _clean_label(unit.get("canonical_title")) or title
    content = _clean_text(unit.get("content"))
    semantic_key = _best_nonempty([canonical_title, title, _first_sentence(content)])
    quality_flags = _string_list(unit.get("quality_flags"))
    if not semantic_key or _is_source_unit_inventory_noise(
        unit_type="definition_unit",
        semantic_key=semantic_key,
        source_text=content,
        quality_flags=quality_flags,
    ):
        return None
    return SourceUnit(
        unit_id=str(unit["id"]),
        unit_type="definition_unit",
        page_no=int(unit.get("page") or 0),
        semantic_key=semantic_key,
        aliases=_unique_strings([canonical_title, title, semantic_key]),
        source_text=content,
        canonical_title=canonical_title,
        canonical_key=semantic_key,
        content_role=str(unit.get("content_role") or "definition"),
        quality_flags=quality_flags,
        importance="high",
        source_locator={
            "page_no": int(unit.get("page") or 0),
            "section": unit.get("section"),
            "title": title,
        },
        metadata={"knowledge_unit_type": "definition"},
    )


def _requirement_source_unit(unit: dict[str, object]) -> SourceUnit | None:
    unit = _unit_with_canonical_metadata(unit)
    title = _clean_label(unit.get("title"))
    canonical_title = _clean_label(unit.get("canonical_title")) or title
    subject = _clean_label(unit.get("subject"))
    topic = _clean_label(unit.get("topic"))
    content = _clean_text(unit.get("content"))
    semantic_key = _best_nonempty([topic, subject, canonical_title, title, _first_sentence(content)])
    quality_flags = _string_list(unit.get("quality_flags"))
    if not semantic_key or _is_source_unit_inventory_noise(
        unit_type="requirement_unit",
        semantic_key=semantic_key,
        source_text=content,
        quality_flags=quality_flags,
    ):
        return None
    scope_type = str(unit.get("scope_type") or "").strip()
    importance = _requirement_importance(scope_type, content, str(unit.get("threshold") or ""))
    return SourceUnit(
        unit_id=str(unit["id"]),
        unit_type="requirement_unit",
        page_no=int(unit.get("page") or 0),
        semantic_key=semantic_key,
        aliases=_unique_strings([topic, subject, canonical_title, title, str(unit.get("threshold") or "")]),
        source_text=content,
        canonical_title=canonical_title,
        canonical_key=semantic_key,
        content_role=str(unit.get("content_role") or scope_type or "requirement"),
        quality_flags=quality_flags,
        importance=importance,
        source_locator={
            "page_no": int(unit.get("page") or 0),
            "section": unit.get("section"),
            "title": title,
        },
        metadata={
            "knowledge_unit_type": "requirement",
            "scope_type": scope_type,
            "threshold": unit.get("threshold"),
            "condition": unit.get("condition"),
        },
    )


def _procedure_source_unit(unit: dict[str, object]) -> SourceUnit | None:
    unit = _unit_with_canonical_metadata(unit)
    canonical_title = _clean_label(unit.get("canonical_title")) or _clean_label(unit.get("title"))
    content = _clean_text(unit.get("content"))
    process_code = str(unit.get("canonical_process_code") or "").strip()
    semantic_key = _best_nonempty([process_code, canonical_title, _first_sentence(content)])
    if not semantic_key or not content:
        return None
    return SourceUnit(
        unit_id=str(unit["id"]),
        unit_type="process_unit",
        page_no=int(unit.get("page") or 0),
        semantic_key=semantic_key,
        aliases=_unique_strings([process_code, canonical_title, semantic_key]),
        source_text=content,
        canonical_title=canonical_title,
        canonical_key=semantic_key,
        content_role=str(unit.get("content_role") or "procedure"),
        quality_flags=_string_list(unit.get("quality_flags")),
        importance="high" if process_code else "medium",
        source_locator={
            "page_no": int(unit.get("page") or 0),
            "section": unit.get("section"),
            "title": unit.get("title"),
            "canonical_title": canonical_title,
            "process_code": process_code,
        },
        metadata={
            "knowledge_unit_type": "procedure",
            "process_code": process_code,
            "raw_title": unit.get("title"),
            "canonical_title": canonical_title,
            "content_role": unit.get("content_role"),
            "quality_flags": unit.get("quality_flags") or [],
        },
    )


def _parameter_row_source_units(unit: dict[str, object]) -> list[SourceUnit]:
    unit = _unit_with_canonical_metadata(unit)
    headers = [str(item or "").strip() for item in unit.get("headers") or []]
    rows = list(unit.get("rows") or [])
    normalized_headers = [_normalize_header_name(header) for header in headers]
    if not rows or "参数" not in normalized_headers and "符号" not in normalized_headers:
        return []

    source_units: list[SourceUnit] = []
    column_map = {name: index for index, name in enumerate(normalized_headers)}
    parameter_index = column_map.get("参数")
    symbol_index = column_map.get("符号")
    object_index = column_map.get("对象", 0)
    unit_index = column_map.get("单位")
    nominal_index = column_map.get("标称值")
    max_index = column_map.get("最大值")
    min_index = column_map.get("最小值")
    state_index = column_map.get("状态")
    if state_index is None:
        state_index = column_map.get("对应状态")

    table_title = _clean_label(unit.get("canonical_table_title") or unit.get("table_title") or unit.get("canonical_title") or unit.get("title"))
    canonical_title = _clean_label(unit.get("canonical_title")) or table_title
    quality_flags = _string_list(unit.get("quality_flags"))

    for row_index, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            continue
        object_name = _row_value(row, object_index)
        parameter = _row_value(row, parameter_index)
        symbol = _row_value(row, symbol_index)
        unit_name = _normalize_unit(_row_value(row, unit_index))
        nominal = _row_value(row, nominal_index)
        max_value = _row_value(row, max_index)
        min_value = _row_value(row, min_index)
        state = _row_value(row, state_index)

        if not parameter and not symbol:
            continue

        aliases = _parameter_row_aliases(
            table_title=table_title,
            object_name=object_name,
            parameter=parameter,
            symbol=symbol,
            unit_name=unit_name,
            state=state,
        )
        semantic_key = aliases[0] if aliases else _best_nonempty([parameter, symbol, object_name])
        if not semantic_key:
            continue

        source_text = " | ".join(
            value
            for value in [object_name, parameter, symbol, unit_name, nominal, max_value, min_value, state]
            if value
        )
        if _is_source_unit_inventory_noise(
            unit_type="parameter_row_unit",
            semantic_key=semantic_key,
            source_text=source_text,
            quality_flags=quality_flags,
        ):
            continue
        source_units.append(
            SourceUnit(
                unit_id=f"{unit['id']}:row:{row_index}",
                unit_type="parameter_row_unit",
                page_no=int(unit.get("page") or 0),
                semantic_key=semantic_key,
                aliases=aliases,
                source_text=source_text,
                canonical_title=canonical_title,
                canonical_key=semantic_key,
                content_role="parameter_row",
                quality_flags=quality_flags,
                importance="high",
                source_locator={
                    "page_no": int(unit.get("page") or 0),
                    "section": unit.get("section"),
                    "table_title": table_title,
                    "row_index": row_index,
                },
                metadata={
                    "knowledge_unit_type": "table_requirement",
                    "table_title": table_title,
                    "object": object_name,
                    "parameter": parameter,
                    "symbol": symbol,
                    "unit": unit_name,
                    "nominal_value": nominal,
                    "max_value": max_value,
                    "min_value": min_value,
                    "state": state,
                },
            )
        )
    return source_units


def _unit_with_canonical_metadata(unit: dict[str, object]) -> dict[str, object]:
    normalized = _normalize_unit_metadata(
        unit_type=str(unit.get("type") or ""),
        title=str(unit.get("title") or ""),
        content=str(unit.get("content") or ""),
        table_title=str(unit.get("table_title") or "") or None,
        section=str(unit.get("section") or "") or None,
        scope_type=str(unit.get("scope_type") or "") or None,
        headers=unit.get("headers") if isinstance(unit.get("headers"), list) else None,
    )
    merged = dict(unit)
    old_flags = _string_list(unit.get("quality_flags"))
    new_flags = _string_list(normalized.get("quality_flags"))
    for key, value in normalized.items():
        merged[key] = value
    merged["quality_flags"] = _unique_strings([*old_flags, *new_flags])
    return merged


def _row_to_fact(row) -> dict[str, object]:
    payload = _safe_json(row["object_value"])
    qualifiers = _safe_json(row["qualifiers_json"])
    return {
        "fact_id": row["fact_id"],
        "fact_type": row["fact_type"],
        "subject_entity_id": row["subject_entity_id"],
        "predicate": row["predicate"],
        "object_value": payload if isinstance(payload, dict) else {},
        "object_entity_id": row["object_entity_id"],
        "qualifiers_json": qualifiers if isinstance(qualifiers, dict) else {},
        "confidence": float(row["confidence"] or 0.0),
    }


def _row_to_wiki_page(row) -> dict[str, object]:
    source_fact_ids = _safe_json(row["source_fact_ids_json"])
    return {
        "page_id": row["page_id"],
        "page_type": row["page_type"],
        "title": row["title"],
        "entity_id": row["entity_id"],
        "source_fact_ids": source_fact_ids if isinstance(source_fact_ids, list) else [],
    }


def _load_fact_evidence_map(connection, doc_id: str) -> dict[str, list[str]]:
    rows = connection.execute(
        """
        SELECT fem.fact_id, fem.evidence_id
        FROM fact_evidence_map fem
        JOIN facts f ON f.fact_id = fem.fact_id
        WHERE f.source_doc_id = ?
        ORDER BY fem.fact_id, fem.evidence_id
        """,
        (doc_id,),
    ).fetchall()
    mapping: dict[str, list[str]] = {}
    for row in rows:
        mapping.setdefault(row["fact_id"], []).append(row["evidence_id"])
    return mapping


def _match_facts_for_unit(unit: SourceUnit, facts: list[dict[str, object]]) -> list[dict[str, object]]:
    matched: list[dict[str, object]] = []
    for fact in facts:
        page_no = int(fact.get("qualifiers_json", {}).get("page_no") or 0)
        if page_no and unit.page_no and abs(page_no - unit.page_no) > 1:
            continue
        if unit.unit_type == "definition_unit" and (
            _definition_matches_fact(unit, fact) or _source_unit_text_matches_fact(unit, fact)
        ):
            matched.append(fact)
        elif unit.unit_type == "requirement_unit" and (
            _requirement_matches_fact(unit, fact) or _source_unit_text_matches_fact(unit, fact)
        ):
            matched.append(fact)
        elif unit.unit_type == "parameter_row_unit" and (
            _parameter_row_matches_fact(unit, fact) or _source_unit_text_matches_fact(unit, fact)
        ):
            matched.append(fact)
        elif unit.unit_type == "process_unit" and (
            _process_unit_matches_fact(unit, fact) or _source_unit_text_matches_fact(unit, fact)
        ):
            matched.append(fact)
    return matched


def _source_unit_text_matches_fact(unit: SourceUnit, fact: dict[str, object]) -> bool:
    payload = fact["object_value"]
    anchors = [unit.semantic_key, *unit.aliases, unit.source_text]
    candidates = _fact_text_candidates(fact)
    return any(_soft_contains(anchor, candidate) for anchor in anchors for candidate in candidates if anchor and candidate)


def _fact_text_candidates(fact: dict[str, object]) -> list[str]:
    payload = fact["object_value"]
    candidates: list[str] = []
    for key in (
        "term",
        "definition",
        "title",
        "topic",
        "subject",
        "content",
        "value",
        "table_title",
        "table_no",
        "process_name",
        "step_text",
    ):
        value = payload.get(key)
        if value:
            candidates.append(str(value))
    headers = payload.get("headers")
    if isinstance(headers, list):
        candidates.append(" ".join(str(item or "") for item in headers))
    rows = payload.get("rows")
    if isinstance(rows, list):
        for row in rows[:20]:
            if isinstance(row, list):
                candidates.append(" ".join(str(item or "") for item in row))
            else:
                candidates.append(str(row))
    return _unique_strings(candidates)


def _definition_matches_fact(unit: SourceUnit, fact: dict[str, object]) -> bool:
    if fact["fact_type"] not in {"term_definition", "concept_definition"}:
        return False
    payload = fact["object_value"]
    term = _clean_label(payload.get("term"))
    definition = _clean_text(payload.get("definition"))
    return any(
        _soft_contains(candidate, term) or _soft_contains(candidate, definition)
        for candidate in [unit.semantic_key, *unit.aliases, unit.source_text]
        if candidate
    )


def _requirement_matches_fact(unit: SourceUnit, fact: dict[str, object]) -> bool:
    if fact["fact_type"] not in {"requirement", "threshold", "table_requirement"}:
        return False
    payload = fact["object_value"]
    candidates = [
        _clean_label(payload.get("title")),
        _clean_label(payload.get("topic")),
        _clean_label(payload.get("subject")),
        _clean_text(payload.get("content")),
        _clean_text(payload.get("value")),
    ]
    anchors = [unit.semantic_key, *unit.aliases, unit.source_text]
    return any(_soft_contains(anchor, candidate) for anchor in anchors for candidate in candidates if anchor and candidate)


def _parameter_row_matches_fact(unit: SourceUnit, fact: dict[str, object]) -> bool:
    if fact["fact_type"] != "parameter_value":
        return False
    payload = fact["object_value"]
    metadata = unit.metadata
    anchors = _unique_strings(
        [
            unit.semantic_key,
            *unit.aliases,
            str(metadata.get("parameter") or ""),
            str(metadata.get("symbol") or ""),
            str(metadata.get("table_title") or ""),
        ]
    )
    candidates = _unique_strings(
        [
            str(payload.get("parameter") or ""),
            str(payload.get("symbol") or ""),
            str(payload.get("object") or ""),
            str(payload.get("table_title") or ""),
            str(payload.get("state") or ""),
            *[str(item or "") for item in payload.get("focus_tags") or []],
            *[str(item or "") for item in payload.get("detection_points") or []],
        ]
    )
    if anchors and any(_soft_contains(anchor, candidate) for anchor in anchors for candidate in candidates if candidate):
        return True

    table_match = _soft_contains(str(metadata.get("table_title") or ""), str(payload.get("table_title") or ""))
    parameter_match = _soft_contains(str(metadata.get("parameter") or ""), str(payload.get("parameter") or ""))
    symbol_match = _soft_contains(str(metadata.get("symbol") or ""), str(payload.get("symbol") or ""))
    return table_match and (parameter_match or symbol_match)


def _process_unit_matches_fact(unit: SourceUnit, fact: dict[str, object]) -> bool:
    if fact["fact_type"] not in {"process_fact", "transition_fact"}:
        return False
    payload = fact["object_value"]
    metadata = unit.metadata
    anchors = _unique_strings(
        [
            unit.semantic_key,
            unit.canonical_title or "",
            *unit.aliases,
            str(metadata.get("process_code") or ""),
        ]
    )
    candidates = _unique_strings(
        [
            str(payload.get("title") or ""),
            str(payload.get("process_name") or ""),
            str(payload.get("table_title") or ""),
            str(payload.get("step_text") or ""),
            str(payload.get("action") or ""),
        ]
    )
    return any(_soft_contains(anchor, candidate) for anchor in anchors for candidate in candidates if anchor and candidate)


def _match_evidence_for_unit(unit: SourceUnit, evidence_rows) -> list[str]:
    matched: list[str] = []
    anchors = [unit.semantic_key, *unit.aliases, unit.source_text]
    for row in evidence_rows:
        page_no = int(row["page_no"] or 0)
        if unit.page_no and page_no and abs(page_no - unit.page_no) > 1:
            continue
        evidence_text = str(row["normalized_text"] or "")
        if any(_soft_contains(anchor, evidence_text) for anchor in anchors if anchor):
            matched.append(str(row["evidence_id"]))
    return matched


def _match_wiki_pages_for_unit(
    unit: SourceUnit,
    fact_ids: list[str],
    entity_ids: list[str],
    wiki_rows: list[dict[str, object]],
) -> list[str]:
    matched: list[str] = []
    fact_id_set = set(fact_ids)
    entity_id_set = set(entity_ids)
    anchors = [unit.semantic_key, *unit.aliases]
    for wiki in wiki_rows:
        title = str(wiki["title"] or "")
        if fact_id_set.intersection(wiki["source_fact_ids"]) or (wiki["entity_id"] and wiki["entity_id"] in entity_id_set):
            matched.append(str(wiki["page_id"]))
            continue
        if any(_soft_contains(anchor, title) for anchor in anchors if anchor):
            matched.append(str(wiki["page_id"]))
    return sorted(set(matched))


def _match_test_cases_for_unit(unit: SourceUnit, test_cases: list[dict[str, object]]) -> list[dict[str, object]]:
    matched: list[dict[str, object]] = []
    anchors = _unique_strings(
        [
            unit.semantic_key,
            *unit.aliases,
            str(unit.metadata.get("parameter") or ""),
            str(unit.metadata.get("symbol") or ""),
            str(unit.metadata.get("table_title") or ""),
        ]
    )
    for case in test_cases:
        blob = str(case.get("match_blob") or "")
        if any(_soft_contains(anchor, blob) for anchor in anchors if anchor):
            matched.append(case)
    return matched


def _load_test_cases(generated_dir: Path, doc_id: str) -> list[dict[str, object]]:
    if not generated_dir.exists():
        return []

    cases: list[dict[str, object]] = []
    golden_path = generated_dir / f"{doc_id}.golden.json"
    if golden_path.exists():
        golden_payload = json.loads(golden_path.read_text(encoding="utf-8"))
        for index, case in enumerate(golden_payload.get("cases", []), start=1):
            cases.append(
                {
                    "case_id": f"GOLD-{doc_id}-{index:03d}",
                    "suite": "golden",
                    "doc_id": doc_id,
                    "match_blob": _test_case_blob(case),
                }
            )

    for path in sorted(generated_dir.glob("*regression*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, list):
            continue
        stem = path.stem
        for index, case in enumerate(payload, start=1):
            if not isinstance(case, dict):
                continue
            case_doc_id = str(case.get("doc_id") or "").strip()
            if case_doc_id and case_doc_id != doc_id:
                continue
            cases.append(
                {
                    "case_id": f"REG-{stem}-{index:03d}",
                    "suite": "regression",
                    "doc_id": case_doc_id or doc_id,
                    "match_blob": _test_case_blob(case),
                }
            )
    return cases


def _test_case_blob(case: dict[str, object]) -> str:
    parts: list[str] = []
    for key, value in case.items():
        if key == "doc_id":
            continue
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif isinstance(value, dict):
            parts.append(json.dumps(value, ensure_ascii=False))
        else:
            parts.append(str(value))
    return "\n".join(part for part in parts if part)


def _coverage_status(
    evidence_ids: list[str],
    fact_ids: list[str],
    entity_ids: list[str],
    golden_case_ids: list[str],
    regression_case_ids: list[str],
    misaligned: bool,
) -> str:
    if misaligned:
        return "u4_misaligned"
    if not evidence_ids and not fact_ids and not entity_ids:
        return "u0_full_miss"
    if evidence_ids and not fact_ids:
        return "u1_text_only"
    if fact_ids and not entity_ids:
        return "u2_fact_no_object"
    if (fact_ids or entity_ids) and not (golden_case_ids or regression_case_ids):
        return "u3_not_tested"
    return "covered"


def _is_potentially_misaligned(
    unit: SourceUnit,
    matched_facts: list[dict[str, object]],
    entity_ids: list[str],
    wiki_page_ids: list[str],
    entity_rows: dict[str, dict[str, object]],
    wiki_rows: list[dict[str, object]],
) -> bool:
    anchors = [unit.semantic_key, *unit.aliases]
    if not anchors:
        return False
    candidates: list[str] = []
    for fact in matched_facts:
        candidates.extend(_fact_text_candidates(fact))
    for entity_id in entity_ids:
        entity = entity_rows.get(entity_id)
        if entity:
            candidates.append(str(entity.get("canonical_name") or ""))
    wiki_map = {row["page_id"]: row for row in wiki_rows}
    for wiki_page_id in wiki_page_ids:
        wiki = wiki_map.get(wiki_page_id)
        if wiki:
            candidates.append(str(wiki.get("title") or ""))

    candidates = [candidate for candidate in candidates if candidate]
    if not candidates:
        return False
    return not any(_soft_contains(anchor, candidate) for anchor in anchors for candidate in candidates)


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


def _build_test_gap_candidates(
    doc_id: str,
    generated_at: str,
    matrix_rows: list[dict[str, object]],
    *,
    limit: int | None = None,
    excluded_unit_ids: set[str] | None = None,
) -> dict[str, object]:
    excluded_unit_ids = excluded_unit_ids or set()
    raw_rows = [
        row
        for row in matrix_rows
        if row.get("coverage_status") == "u3_not_tested"
    ]
    rows = _dedupe_test_gap_rows([
        row
        for row in raw_rows
        if str(row.get("unit_id") or "") not in excluded_unit_ids and _is_actionable_test_gap_row(row)
    ])
    sorted_rows = _sort_test_gap_rows(rows)
    if limit is not None and limit >= 0:
        sorted_rows = sorted_rows[:limit]

    return {
        "doc_id": doc_id,
        "generated_at": generated_at,
        "version": SOURCE_UNIT_EXPORT_VERSION,
        "source_gap_count": len(raw_rows),
        "skipped_candidate_count": len(raw_rows) - len(rows),
        "excluded_candidate_count": sum(1 for row in raw_rows if str(row.get("unit_id") or "") in excluded_unit_ids),
        "candidate_count": len(sorted_rows),
        "items": [_test_gap_candidate_from_row(row) for row in sorted_rows],
    }


def _test_gap_candidate_from_row(row: dict[str, object]) -> dict[str, object]:
    unit_type = str(row.get("unit_type") or "")
    semantic_key = _clean_test_gap_label(str(row.get("semantic_key") or "").strip())
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    source_locator = row.get("source_locator") if isinstance(row.get("source_locator"), dict) else {}
    query_seed, assert_mode, must_include = _recommended_test_seed(unit_type, semantic_key, metadata, row)

    return {
        "unit_id": row.get("unit_id"),
        "coverage_status": row.get("coverage_status"),
        "unit_type": unit_type,
        "importance": row.get("importance"),
        "page_no": row.get("page_no"),
        "semantic_key": semantic_key,
        "source_locator": source_locator,
        "recommended_query_seed": query_seed,
        "recommended_assert_mode": assert_mode,
        "recommended_must_include": must_include,
        "recommended_suite": "golden" if row.get("importance") == "high" else "regression",
        "covered_by": row.get("covered_by") or {},
        "source_excerpt": _first_sentence(str(row.get("source_text") or "")),
    }


def _recommended_test_seed(
    unit_type: str,
    semantic_key: str,
    metadata: dict[str, object],
    row: dict[str, object],
) -> tuple[str, str, list[str]]:
    key = semantic_key or str(row.get("unit_id") or "")
    if unit_type == "definition_unit":
        return f"什么是{key}？", "rich_answer", [key]

    if unit_type == "parameter_row_unit":
        value = _best_nonempty(
            [
                str(metadata.get("nominal_value") or ""),
                str(metadata.get("max_value") or ""),
                str(metadata.get("min_value") or ""),
            ]
        )
        unit_name = str(metadata.get("unit") or "")
        query = f"{key}是多少？"
        must_include = [item for item in [key, value, unit_name] if item]
        return query, "parameter_value", must_include or [key]

    if unit_type == "process_unit":
        process_code = str(metadata.get("process_code") or key).strip()
        return f"{process_code}有哪些活动？", "rich_answer", [process_code]

    return f"{key}有哪些要求？", "rich_answer", [key]


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


def _sort_test_gap_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    unit_priority = {
        "definition_unit": 0,
        "parameter_row_unit": 1,
        "requirement_unit": 2,
    }
    return sorted(
        rows,
        key=lambda row: (
            {"high": 0, "medium": 1, "low": 2}.get(str(row.get("importance")), 9),
            unit_priority.get(str(row.get("unit_type")), 9),
            int(row.get("page_no") or 0),
            str(row.get("semantic_key") or ""),
            str(row.get("unit_id") or ""),
        ),
    )


def _dedupe_test_gap_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for row in _sort_test_gap_rows(rows):
        key = (
            str(row.get("unit_type") or ""),
            _compare_key(_clean_test_gap_label(str(row.get("semantic_key") or ""))),
        )
        if not key[1] or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _is_actionable_test_gap_row(row: dict[str, object]) -> bool:
    semantic_key = _clean_test_gap_label(str(row.get("semantic_key") or ""))
    if not semantic_key:
        return False
    if _looks_like_test_gap_noise(semantic_key):
        return False
    if _looks_like_toc_entry_noise(semantic_key, str(row.get("source_excerpt") or row.get("source_text") or "")):
        return False
    unit_type = str(row.get("unit_type") or "")
    if unit_type == "parameter_row_unit" and _looks_like_low_value_parameter_gap(semantic_key):
        return False
    if any(marker in semantic_key for marker in ["☆", "★", "□", "■"]):
        return False
    if unit_type == "definition_unit":
        tokens = [token for token in re.split(r"\s+", semantic_key) if token]
        ascii_tokens = [token for token in tokens if re.search(r"[A-Za-z]", token)]
        # Diagram captions and term clusters often arrive as long Chinese token lists;
        # they are useful diagnostics but poor seeds for executable QA tests.
        if len(tokens) > 4 and not ascii_tokens:
            return False
        if len(tokens) > 8:
            return False
    return True


def _is_source_unit_inventory_noise(
    *,
    unit_type: str,
    semantic_key: str,
    source_text: str,
    quality_flags: list[str],
) -> bool:
    """Filter non-knowledge inventory before it becomes a coverage obligation."""
    raw_key = re.sub(r"\s+", "", str(semantic_key or "")).strip()
    if raw_key and re.fullmatch(r"\d+", raw_key):
        return True
    cleaned_key = _clean_test_gap_label(semantic_key)
    cleaned_text = _clean_test_gap_label(source_text)
    if "layout_title_noise" in quality_flags:
        return True
    if _looks_like_test_gap_noise(cleaned_key):
        return True
    if _looks_like_toc_entry_noise(cleaned_key, cleaned_text):
        return True
    if _looks_like_structural_inventory_noise(cleaned_key, cleaned_text):
        return True
    if unit_type == "parameter_row_unit" and _looks_like_low_value_parameter_gap(cleaned_key):
        return True
    if unit_type in {"definition_unit", "requirement_unit"} and _looks_like_boilerplate_definition_pair(cleaned_key, cleaned_text):
        return True
    if unit_type == "definition_unit" and _looks_like_figure_legend_definition(cleaned_key, cleaned_text):
        return True
    if unit_type in {"definition_unit", "requirement_unit"} and _looks_like_table_syntax_source(cleaned_text):
        return True
    if unit_type in {"definition_unit", "requirement_unit"} and _looks_like_clause_reference_noise(cleaned_key, cleaned_text):
        return True
    return False


def _looks_like_structural_inventory_noise(semantic_key: str, source_text: str) -> bool:
    key = re.sub(r"\s+", " ", semantic_key).strip()
    text = re.sub(r"\s+", " ", source_text).strip()
    compact_key = re.sub(r"\s+", "", key)
    structural_titles = {
        "概述",
        "概述。",
        "术语",
        "引言",
        "结语",
        "分类",
        "目次",
        "目录",
        "材料",
        "结构",
        "foreword",
        "introduction",
        "contents",
        "bibliography",
    }
    lower_key = key.lower()
    if compact_key in {"目次", "目录", "引言", "结语"}:
        return True
    if lower_key in {"foreword", "introduction", "contents", "bibliography"}:
        return True
    if compact_key in structural_titles and len(text) <= 80:
        return True
    if compact_key in {"概述", "材料", "结构", "分类"} and re.fullmatch(r"(?:应)?符合.+(?:规定|要求)", text):
        return True
    if compact_key == "3":
        return True
    if key.startswith("Abstract ") and len(key) > 80:
        return True
    if key.startswith("Process reference model and performance indicators") and len(key) > 80:
        return True
    if "文章引用" in text and len(key) > 40:
        return True
    return False


def _looks_like_toc_entry_noise(semantic_key: str, source_text: str) -> bool:
    key = re.sub(r"\s+", " ", str(semantic_key or "")).strip()
    text = re.sub(r"\s+", " ", str(source_text or "")).strip()
    if not key:
        return False
    dot_leader = bool(re.search(r"\.{6,}", key))
    page_ref = bool(re.search(r"(?:^|\s)\d{1,3}(?:\s+\d{1,3})?(?:\s|$)", key))
    multiple_clause_labels = len(re.findall(r"(?:^|\s)\d+(?:\.\d+)*\s+[A-Z\u4e00-\u9fff]", key)) >= 2
    if dot_leader and (page_ref or multiple_clause_labels) and len(text) < 80:
        return True
    return False


def _looks_like_figure_legend_definition(semantic_key: str, source_text: str) -> bool:
    key_tokens = [token for token in re.split(r"\s+", semantic_key) if token]
    if len(key_tokens) >= 5 and ("标引序号说明" in source_text or "☆" in source_text):
        return True
    return False


def _looks_like_table_syntax_source(source_text: str) -> bool:
    if source_text.count("|") >= 6 and re.search(r"\|\s*:?-{2,}:?\s*\|", source_text):
        return True
    if source_text.count("|") >= 10:
        return True
    return False


def _looks_like_clause_reference_noise(semantic_key: str, source_text: str) -> bool:
    key = re.sub(r"\s+", " ", semantic_key).strip()
    text = re.sub(r"\s+", " ", source_text).strip()
    if re.match(r"^条款\s*\d+(?:\.\d+)*", key) and (
        "过程评估模型" in text or "过程参考模型" in text or "ISO/IEC" in text
    ):
        return True
    return False


def _looks_like_boilerplate_definition_pair(semantic_key: str, source_text: str) -> bool:
    key = re.sub(r"\s+", " ", semantic_key).strip()
    text = re.sub(r"\s+", " ", source_text).strip()
    upper_key = key.upper()
    upper_blob = f"{key} {text}".upper()
    boilerplate_markers = (
        "VDA QMC",
        "AUTOMOTIVE SPICE",
        "PUBLIC",
        "COPYRIGHT",
        "ALL RIGHTS RESERVED",
        "LICENSE",
        "PERMISSION",
        "ISO/IEC",
        "© ISO",
    )
    if not any(marker in upper_blob for marker in boilerplate_markers):
        return False
    if upper_key in {"PUBLIC", "VDA", "VDA QMC"}:
        return True
    if "VDA QMC" in upper_key and "AUTOMOTIVE SPICE" in upper_key:
        return True
    if "ALL RIGHTS RESERVED" in upper_blob or "© ISO" in upper_blob:
        return True
    if not re.search(r"(?:\b[A-Z]{2,5}\.\d+\b|[\u4e00-\u9fff]{2,})", text):
        return True
    return False


def _looks_like_test_gap_noise(label: str) -> bool:
    compact = label.strip()
    upper = compact.upper()
    if "[SPACE]" in upper:
        return True
    if upper in {"PUBLIC", "SAC", "VDA", "VDA QMC"}:
        return True
    if any(token in compact for token in ("页码", "目录", "目次", "版权", "©", "www.", "http")):
        return True
    if re.match(r"^(?:SAC|VDA QMC|PUBLIC)\b", compact, re.I):
        return True
    if re.fullmatch(r"\d+", compact):
        return True
    return False


def _looks_like_low_value_parameter_gap(label: str) -> bool:
    compact = label.strip()
    upper = compact.upper()
    if not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", compact):
        return True
    generic_labels = {
        "A",
        "V",
        "W",
        "VA",
        "HZ",
        "%",
        "Ω",
        "时刻",
        "项目",
        "要求",
        "参数",
        "符号",
        "单位",
        "备注",
        "数据交互",
        "输出电压",
        "输出电流",
        "DP3",
        "S0",
        "SAC",
        "SV",
        "SV'",
        "S+/S-",
        "S+/S",
        "C1,C2",
        "C5,C6",
        "U1B",
        "U1C",
        "U2B",
        "信号设置时间^{B,C}",
        "VDC",
        "ADC",
        "—",
        "-",
    }
    if upper in generic_labels or compact in generic_labels:
        return True
    if re.fullmatch(r"(?:DP|S|C)\d+(?:[,/](?:DP|S|C)?\d+)*", upper):
        return True
    if re.fullmatch(r"U\d+[A-Zᵃ-ᶻ]*", compact, re.I):
        return True
    if "^{" in compact or "}^{ " in compact:
        return True
    if re.fullmatch(r"S[Vv]'?|S[+-]/S-?", compact):
        return True
    if re.fullmatch(r"[AV]dc(?:\s*\([^)]{1,12}\))?", compact, re.I):
        return True
    if re.fullmatch(r"开关\s*0\s*[（(]?可选[）)]?", compact):
        return True
    if re.fullmatch(r"0", compact):
        return True
    if len(compact) <= 2 and re.fullmatch(r"[A-Za-z%Ω]+", compact):
        return True
    return False


def _clean_test_gap_label(value: str) -> str:
    value = _clean_label(value)
    value = value.replace("**", "")
    value = re.sub(r"^[^\w\u4e00-\u9fff]+", "", value).strip()
    value = re.sub(r"[^\w\u4e00-\u9fff）)\]]+$", "", value).strip()
    value = re.sub(r"\s+", " ", value)
    return value


def _sort_uncovered_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    priority = {
        "u4_misaligned": 0,
        "u0_full_miss": 1,
        "u1_text_only": 2,
        "u2_fact_no_object": 3,
        "u3_not_tested": 4,
    }
    return sorted(
        rows,
        key=lambda row: (
            priority.get(str(row.get("coverage_status")), 9),
            {"high": 0, "medium": 1, "low": 2}.get(str(row.get("importance")), 9),
            int(row.get("page_no") or 0),
            str(row.get("unit_id") or ""),
        ),
    )


def _parameter_row_aliases(
    *,
    table_title: str,
    object_name: str,
    parameter: str,
    symbol: str,
    unit_name: str,
    state: str,
) -> list[str]:
    aliases = _unique_strings([parameter, symbol, object_name, table_title, state])
    table_blob = f"{table_title} {object_name} {parameter} {symbol} {state}".upper()

    if unit_name == "V":
        for token in ("检测点1", "检测点2", "检测点3"):
            if token in table_blob and f"{token}电压" not in aliases:
                aliases.insert(0, f"{token}电压")

    if "占空比" in parameter or symbol.upper().startswith("D"):
        if any(token in table_blob for token in ("CP", "控制导引")):
            aliases.insert(0, "CP占空比")

    if unit_name == "Ω" or "阻值" in parameter or "电阻" in parameter or symbol.upper().startswith("R"):
        aliases.extend(_unique_strings([f"{symbol}阻值" if symbol else "", "阻值"]))
        if any(token in table_blob for token in ("CC", "CC1", "CC2", "连接确认", "检测点")):
            aliases.insert(0, "CC阻值")

    return _unique_strings(aliases)


def _requirement_importance(scope_type: str, content: str, threshold: str) -> str:
    if scope_type in {"index", "preface"}:
        return "low"
    if threshold or any(token in content for token in ("应", "不应", "不得", "不超过", "不小于", "应符合", "应满足")):
        return "high"
    if scope_type == "overview":
        return "medium"
    return "medium"


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
