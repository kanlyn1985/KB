"""Fact augmentation, ranking, filtering, and answer-fact selection for answer generation."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import AppPaths
from .logging_config import get_logger

_logger = get_logger(__name__)
from .db import connect
from .evidence_shapes import is_test_method_query, looks_like_test_method_blob
from .answer_utils import _row_to_fact, _safe_json, _INTENT_FACT_TYPES
from .answer_query_parsing import (
    _normalize_query_phrase,
    _normalize_standard_code,
    _extract_standard_from_query,
    _extract_table_no_from_query,
    _is_timing_query,
    _extract_constraint_keywords,
)
from .answer_subgraph import _prioritize_subgraph_facts


def _augment_facts(
    workspace_root: Path,
    documents: list[dict[str, object]],
    facts: list[dict[str, object]],
    rewritten_payload: dict[str, object],
    query: str,
    intent: str,
) -> list[dict[str, object]]:
    """Augment *facts* with intent-specific DB queries and re-rank.

    Dispatches to one of seven intent-specific helpers
    (``_augment_standard_facts``, ``_augment_definition_facts``, etc.),
    then deduplicates by ``fact_id`` and re-ranks via ``_rank_facts``.

    See each per-intent helper for SQL details.
    """
    _logger.info(
        "augment_facts:start intent=%s facts=%d docs=%d query=%r",
        intent, len(facts), len(documents), query[:80],
    )
    if not documents:
        return _rank_facts(facts, intent, query=query)

    doc_id = documents[0]["doc_id"]
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)

    try:
        extra = _augment_intent_dispatch(
            connection=connection,
            doc_id=doc_id,
            documents=documents,
            rewritten_payload=rewritten_payload,
            query=query,
            intent=intent,
        )
        seen = {item["fact_id"] for item in facts}
        for item in extra:
            if item["fact_id"] not in seen:
                facts.append(item)
                seen.add(item["fact_id"])
        ranked = _rank_facts(facts, intent, query=query)
        _logger.info("augment_facts:done ranked=%d", len(ranked))
        return ranked
    finally:
        connection.close()


def _augment_intent_dispatch(
    *,
    connection,
    doc_id: str,
    documents: list[dict[str, object]],
    rewritten_payload: dict[str, object],
    query: str,
    intent: str,
) -> list[dict[str, object]]:
    """Dispatch augmentation by *intent* to the matching per-intent helper."""
    if intent == "standard":
        return _augment_standard_facts(connection, doc_id)
    if intent == "definition":
        return _augment_definition_facts(
            connection, doc_id, documents, query, rewritten_payload,
        )
    if intent == "parameter":
        return _augment_parameter_facts(
            connection, doc_id, query, rewritten_payload,
        )
    if intent == "process":
        return _augment_process_facts(
            connection, doc_id, query, rewritten_payload,
        )
    if intent == "comparison":
        return _augment_comparison_facts(
            connection, doc_id, query, rewritten_payload,
        )
    if intent == "constraint":
        return _augment_constraint_facts(
            connection, doc_id, query, rewritten_payload,
        )
    return _augment_default_facts(
        connection, doc_id, query, rewritten_payload,
    )


def _augment_standard_facts(connection, doc_id: str) -> list[dict[str, object]]:
    """For ``intent == "standard"``: pull document/versioning/lifecycle facts."""
    rows = connection.execute(
        """
        SELECT fact_id, fact_type, predicate, object_value, confidence,
               source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
        FROM facts
        WHERE source_doc_id = ?
          AND fact_type IN ('document_standard', 'document_versioning', 'document_lifecycle')
        ORDER BY fact_id
        """,
        (doc_id,),
    ).fetchall()
    return [_row_to_fact(row) for row in rows]


def _augment_definition_facts(
    connection, doc_id: str, documents: list[dict[str, object]],
    query: str, rewritten_payload: dict[str, object],
) -> list[dict[str, object]]:
    """For ``intent == "definition"``: search for term/concept definitions
    matching the query's target terms across the preferred document(s)."""
    from .answer_api import _definition_target_terms
    normalized_query = _normalize_query_phrase(query)
    target_terms = _definition_target_terms(query, rewritten_payload)
    preferred_doc_ids = [item.get("doc_id") for item in documents if item.get("doc_id")]
    search_doc_ids = preferred_doc_ids or [doc_id]
    placeholders = ",".join("?" for _ in search_doc_ids)
    like_clauses = " OR ".join("object_value LIKE ?" for _ in target_terms[:6])
    if not like_clauses:
        like_clauses = "object_value LIKE ?"
        target_terms = [normalized_query]
    rows = connection.execute(
        f"""
        SELECT fact_id, fact_type, predicate, object_value, confidence,
               source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
        FROM facts
        WHERE source_doc_id IN ({placeholders})
          AND fact_type IN ('term_definition', 'concept_definition', 'document_abstract')
          AND ({like_clauses})
        ORDER BY confidence DESC, fact_id ASC
        LIMIT 12
        """,
        [*search_doc_ids, *[f"%{term}%" for term in target_terms[:6]]],
    ).fetchall()
    return [_row_to_fact(row) for row in rows]


def _augment_parameter_facts(
    connection, doc_id: str, query: str,
    rewritten_payload: dict[str, object],
) -> list[dict[str, object]]:
    """For ``intent == "parameter"``: pull parameter/table/threshold/requirement
    facts and apply focus-term and page-focus bonuses. Adds PWM/voltage
    targeted rows for signal-state queries."""
    from .answer_parameter import _parameter_focus_terms, _is_signal_state_query, _requested_voltage_value
    normalized_query = _normalize_query_phrase(query)
    focus_terms = _parameter_focus_terms(query, rewritten_payload)
    relevant_pages = _find_relevant_pages_for_query(
        connection,
        doc_id,
        focus_terms,
    )
    rows = connection.execute(
        """
        SELECT fact_id, fact_type, predicate, object_value, confidence,
               source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
        FROM facts
        WHERE source_doc_id = ?
          AND fact_type IN ('parameter_value', 'table_requirement', 'threshold', 'requirement')
        ORDER BY
            CASE fact_type
                WHEN 'parameter_value' THEN 0
                WHEN 'table_requirement' THEN 1
                WHEN 'threshold' THEN 2
                ELSE 3
            END,
            confidence DESC,
            fact_id ASC
        LIMIT 240
        """,
        (doc_id,),
    ).fetchall()
    if _is_signal_state_query(query):
        requested_voltage = _requested_voltage_value(query)
        targeted_rows = connection.execute(
            """
            SELECT fact_id, fact_type, predicate, object_value, confidence,
                   source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
            FROM facts
            WHERE source_doc_id = ?
              AND fact_type = 'table_requirement'
              AND object_value LIKE '%PWM%'
              AND object_value LIKE '%状态%'
              AND object_value LIKE ?
            ORDER BY confidence DESC, fact_id ASC
            LIMIT 20
            """,
            (doc_id, f"%{requested_voltage}%" if requested_voltage else "%"),
        ).fetchall()
        rows = [*targeted_rows, *rows]
    extra: list[dict[str, object]] = []
    for row in rows:
        fact = _row_to_fact(row)
        qualifiers = fact.get("qualifiers_json")
        page_no = None
        if isinstance(qualifiers, dict):
            page_no = int(qualifiers.get("page_no") or 0)
        payload = fact.get("object_value")
        blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
        focus_bonus = _focus_term_bonus(blob, focus_terms)
        if focus_bonus:
            fact["_focus_term_bonus"] = focus_bonus
        if page_no and page_no in relevant_pages:
            fact["_page_focus_bonus"] = 2.0
        if any(term and term in blob for term in [normalized_query, *focus_terms]):
            extra.append(fact)
            continue
        if page_no and page_no in relevant_pages:
            extra.append(fact)
    return extra


def _augment_process_facts(
    connection, doc_id: str, query: str,
    rewritten_payload: dict[str, object],
) -> list[dict[str, object]]:
    """For ``intent == "process"``: pull process/transition/table/requirement
    facts, with focus-term and timing-token filtering. Test-method queries
    use a stricter ``looks_like_test_method_blob`` filter."""
    normalized_query = _normalize_query_phrase(query)
    test_method_query = is_test_method_query(query)
    rows = connection.execute(
        """
        SELECT fact_id, fact_type, predicate, object_value, confidence,
               source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
        FROM facts
        WHERE source_doc_id = ?
          AND fact_type IN ('process_fact', 'transition_fact', 'table_requirement', 'requirement')
        ORDER BY
            CASE fact_type
                WHEN 'transition_fact' THEN 0
                WHEN 'process_fact' THEN 1
                WHEN 'table_requirement' THEN 2
                ELSE 3
            END,
            confidence DESC,
            fact_id ASC
        LIMIT 160
        """,
        (doc_id,),
    ).fetchall()
    extra: list[dict[str, object]] = []
    focus_terms = [
        normalized_query,
        *[str(item) for item in rewritten_payload.get("must_terms", [])],
        *[str(item) for item in rewritten_payload.get("aliases", [])],
        *[str(item) for item in rewritten_payload.get("should_terms", [])],
    ]
    for row in rows:
        fact = _row_to_fact(row)
        payload = fact.get("object_value")
        blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
        if test_method_query:
            if looks_like_test_method_blob(query, blob):
                extra.append(fact)
            continue
        if any(term and term in blob for term in focus_terms):
            extra.append(fact)
            continue
        if any(token in blob for token in ("时序", "状态", "流程", "握手", "预充", "停机")):
            extra.append(fact)
    return extra


def _augment_comparison_facts(
    connection, doc_id: str, query: str,
    rewritten_payload: dict[str, object],
) -> list[dict[str, object]]:
    """For ``intent == "comparison"``: pull comparison/term/concept facts
    and apply focus-term and V2X-family-token filtering."""
    normalized_query = _normalize_query_phrase(query)
    rows = connection.execute(
        """
        SELECT fact_id, fact_type, predicate, object_value, confidence,
               source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
        FROM facts
        WHERE source_doc_id = ?
          AND fact_type IN ('comparison_relation', 'term_definition', 'concept_definition')
        ORDER BY
            CASE fact_type
                WHEN 'comparison_relation' THEN 0
                ELSE 1
            END,
            confidence DESC,
            fact_id ASC
        LIMIT 80
        """,
        (doc_id,),
    ).fetchall()
    extra: list[dict[str, object]] = []
    comparison_terms = [
        normalized_query,
        *[str(item) for item in rewritten_payload.get("must_terms", [])],
        *[str(item) for item in rewritten_payload.get("aliases", [])],
        *[str(item) for item in rewritten_payload.get("should_terms", [])],
    ]
    for row in rows:
        fact = _row_to_fact(row)
        payload = fact.get("object_value")
        blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
        if any(term and term in blob for term in comparison_terms):
            extra.append(fact)
            continue
        if fact.get("fact_type") == "comparison_relation" and any(token in blob.upper() for token in ("V2X", "V2G", "V2V", "V2B", "V2H")):
            extra.append(fact)
    return extra


def _augment_constraint_facts(
    connection, doc_id: str, query: str,
    rewritten_payload: dict[str, object],
) -> list[dict[str, object]]:
    """For ``intent == "constraint"``: pull threshold/requirement/table facts
    and apply topic-match / heading-page bonuses. Excludes preface and index
    sections."""
    normalized_query = _normalize_query_phrase(query)
    constraint_keywords = _extract_constraint_keywords(query)
    rows = connection.execute(
        """
        SELECT fact_id, fact_type, predicate, object_value, confidence,
               source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
        FROM facts
        WHERE source_doc_id = ?
          AND fact_type IN ('threshold', 'requirement', 'table_requirement', 'section_heading')
        ORDER BY
            CASE fact_type
                WHEN 'threshold' THEN 0
                WHEN 'requirement' THEN 1
                ELSE 2
            END,
            confidence DESC,
            fact_id ASC
        LIMIT 120
        """,
        (doc_id,),
    ).fetchall()
    heading_pages = _constraint_heading_pages(connection, doc_id, constraint_keywords)
    extra: list[dict[str, object]] = []
    constraint_terms = [
        normalized_query,
        *[str(item) for item in rewritten_payload.get("must_terms", [])],
        *[str(item) for item in rewritten_payload.get("aliases", [])],
        *[str(item) for item in rewritten_payload.get("should_terms", [])],
    ]
    for row in rows:
        fact = _row_to_fact(row)
        payload = fact.get("object_value")
        blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
        if isinstance(payload, dict) and str(payload.get("scope_type") or "") in {"index", "preface"}:
            continue
        if any(token in blob for token in ("前言", "前    言", "目 次", "目次")):
            continue
        topic = str(payload.get("topic") or payload.get("subject") or payload.get("title") or "") if isinstance(payload, dict) else ""
        topic_match = any(kw in topic for kw in constraint_keywords)
        qualifiers = fact.get("qualifiers_json")
        fact_page = 0
        if isinstance(qualifiers, dict):
            fact_page = int(qualifiers.get("page_no") or 0)
        heading_page_match = fact_page in heading_pages if heading_pages else False
        if topic_match:
            fact["_topic_match_bonus"] = 4.0
        elif heading_page_match:
            fact["_topic_match_bonus"] = 2.0
        if any(term and term in blob for term in constraint_terms):
            extra.append(fact)
            continue
        if topic_match or heading_page_match:
            extra.append(fact)
            continue
        if any(token in blob for token in ("要求", "应", "不应", "必须", "切断", "急停", "锁止")):
            extra.append(fact)
    return extra


def _constraint_heading_pages(
    connection, doc_id: str, constraint_keywords: list[str],
) -> set[int]:
    """Return the set of page numbers whose section heading matches any of
    *constraint_keywords* (used to boost facts on those pages)."""
    heading_pages: set[int] = set()
    heading_rows = connection.execute(
        """
        SELECT object_value, qualifiers_json FROM facts
        WHERE source_doc_id = ? AND fact_type = 'section_heading'
        """,
        (doc_id,),
    ).fetchall()
    for hrow in heading_rows:
        object_value_str = str(hrow[0] or "")
        try:
            q = json.loads(hrow[1] or "{}")
            page_no = int(q.get("page_no") or 0)
        except (json.JSONDecodeError, ValueError):
            continue
        if page_no and any(kw in object_value_str for kw in constraint_keywords):
            heading_pages.add(page_no)
    return heading_pages


def _augment_default_facts(
    connection, doc_id: str, query: str,
    rewritten_payload: dict[str, object],
) -> list[dict[str, object]]:
    """For unrecognised intents: pull requirement/table/threshold/parameter
    facts, with three sub-paths based on regex matches (CC/resistor,
    ``表\\d+`` reference, or plain keyword)."""
    normalized_query = _normalize_query_phrase(query)
    if re.search(r"(CC|阻值|电阻|参数值)", query, re.I):
        parameter_rows = connection.execute(
            """
            SELECT fact_id, fact_type, predicate, object_value, confidence,
                   source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
            FROM facts
            WHERE source_doc_id = ?
              AND fact_type = 'parameter_value'
            ORDER BY confidence DESC, fact_id ASC
            LIMIT 20
            """,
            (doc_id,),
        ).fetchall()
        supplemental_rows = connection.execute(
            """
            SELECT fact_id, fact_type, predicate, object_value, confidence,
                   source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
            FROM facts
            WHERE source_doc_id = ?
              AND fact_type IN ('table_requirement', 'requirement', 'threshold')
            ORDER BY confidence DESC, fact_id ASC
            LIMIT 30
            """,
            (doc_id,),
        ).fetchall()
        rows = [*parameter_rows, *supplemental_rows]
    elif re.search(r"表\s*\d+", query):
        table_rows = connection.execute(
            """
            SELECT fact_id, fact_type, predicate, object_value, confidence,
                   source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
            FROM facts
            WHERE source_doc_id = ?
              AND fact_type = 'table_requirement'
            ORDER BY confidence DESC, fact_id ASC
            LIMIT 8
            """,
            (doc_id,),
        ).fetchall()
        other_rows = connection.execute(
            """
            SELECT fact_id, fact_type, predicate, object_value, confidence,
                   source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
            FROM facts
            WHERE source_doc_id = ?
              AND fact_type IN ('requirement', 'threshold', 'parameter_value')
            ORDER BY confidence DESC, fact_id ASC
            LIMIT 12
            """,
            (doc_id,),
        ).fetchall()
        rows = [*table_rows, *other_rows]
    else:
        rows = connection.execute(
            """
            SELECT fact_id, fact_type, predicate, object_value, confidence,
                   source_doc_id, subject_entity_id, object_entity_id, qualifiers_json
            FROM facts
            WHERE source_doc_id = ?
              AND fact_type IN ('requirement', 'table_requirement', 'threshold', 'parameter_value')
              AND object_value LIKE ?
            ORDER BY confidence DESC, fact_id ASC
            LIMIT 12
            """,
            (doc_id, f"%{normalized_query}%"),
        ).fetchall()
    return [_row_to_fact(row) for row in rows]



def _filter_facts_by_intent(facts: list[dict[str, object]], intent: str) -> list[dict[str, object]]:
    allowed = _INTENT_FACT_TYPES.get(intent)
    if not allowed:
        return facts
    primary = [f for f in facts if f.get("fact_type") in allowed]
    supplementary = [f for f in facts if f.get("fact_type") not in allowed]
    # Return all ranked facts — do NOT truncate here; downstream answer_policy
    # will pick what it needs from the full ordered list.
    return primary + supplementary



def _rank_facts(facts: list[dict[str, object]], intent: str, query: str = "") -> list[dict[str, object]]:
    target_standard = _normalize_standard_code(_extract_standard_from_query(query)) if intent == "standard" else None
    requested_table_no = _extract_table_no_from_query(query)

    # Pre-compute doc_title match boost per doc_id (avoid duplicate DB hits).
    doc_title_boost: dict[str, float] = {}
    if query:
        from .db import connect as _connect_for_title
        from .config import AppPaths as _AP
        try:
            with _connect_for_title(_AP.from_workspace_root().db_file) as _conn:
                rows = _conn.execute(
                    "SELECT doc_id, source_filename FROM documents"
                ).fetchall()
                from .reranker import _norm as _norm_filename
                q_norm = _norm_filename(query)
                for r in rows:
                    fn = str(r["source_filename"] or "")
                    fn_norm = _norm_filename(fn)
                    if not q_norm or not fn_norm:
                        continue
                    # Count overlap of CJK keywords (3+ chars) with the filename
                    q_cjk = set(re.findall(r"[一-鿿]{3,}", query))
                    if not q_cjk:
                        continue
                    hits = sum(1 for kw in q_cjk if kw in fn_norm)
                    if hits:
                        doc_title_boost[r["doc_id"]] = min(0.3 * hits, 1.0)
        except Exception:
            pass

    def score(item: dict[str, object]) -> tuple[float, float]:
        fact_type = item.get("fact_type")
        confidence = float(item.get("confidence") or 0)
        bonus = 0.0
        # Doc-title match boost (precomputed above): +0.3 to +1.0
        # depending on how many query keywords appear in the document's
        # filename.  Helps the system pick facts from the document the
        # query is actually about, when the same keyword appears in many
        # docs (e.g. "逆变器" appears in DOC-000001 and DOC-000002).
        if doc_title_boost:
            item_doc = str(item.get("source_doc_id") or "")
            if item_doc in doc_title_boost:
                bonus += doc_title_boost[item_doc]
        if intent == "definition":
            if fact_type in {"term_definition", "concept_definition"}:
                bonus = 4.0
            elif fact_type == "document_abstract":
                bonus = 3.0
            elif fact_type == "section_heading":
                bonus = 1.5
        elif intent == "standard":
            if fact_type in {"document_standard", "document_versioning", "document_lifecycle"}:
                bonus = 3.0
            elif fact_type in {"term_definition", "concept_definition"}:
                bonus = 0.5
            if fact_type == "document_standard" and isinstance(item.get("object_value"), dict):
                value = _normalize_standard_code(str(item["object_value"].get("value", "")))
                if value and target_standard and value == target_standard:
                    bonus += 2.0
        elif intent == "parameter":
            if fact_type == "parameter_value":
                bonus = 4.0
            elif fact_type == "table_requirement":
                bonus = 2.8
            elif fact_type == "threshold":
                bonus = 1.6
            elif fact_type == "requirement":
                bonus = 1.2
            payload = item.get("object_value")
            blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
            if "目 次" in blob or "前    言" in blob or "前言" in blob:
                bonus -= 5.0
            # Penalize appendix/index-like table_requirement
            if fact_type == "table_requirement" and isinstance(payload, dict):
                title = str(payload.get("title") or "") + str(payload.get("table_title") or "")
                headers = payload.get("headers") or []
                header_blob = " ".join(str(h) for h in headers) if isinstance(headers, list) else str(headers)
                if any(token in title for token in ("序号", "标准编号", "标准名称", "起始实施日期", "附件")):
                    bonus -= 8.0
                elif "序号" in header_blob and "标准编号" in header_blob:
                    bonus -= 8.0
            if re.search(r"(阻值|电阻|欧姆|Ω)", query) and re.search(r"(Ω|电阻|阻值|R\d+)", blob, re.I):
                bonus += 3.0
            if re.search(r"\bCC\b|CC1|CC2", query, re.I) and re.search(r"\bCC\b|CC1|CC2", blob, re.I):
                bonus += 2.5
            if re.search(r"(检测点\s*\d)", query) and re.search(r"(检测点\s*\d)", blob):
                bonus += 2.0
            if re.search(r"(控制导引|导引电路)", blob):
                bonus += 1.0
            # Efficiency / power keyword boost for parameter queries
            if re.search(r"(效率|功率)", query) and re.search(r"(效率|功率|85)", blob):
                bonus += 3.5
            # Insulation resistance requirement boost for parameter queries
            if re.search(r"(绝缘电阻|绝缘强度)", query) and re.search(r"(绝缘电阻|绝缘强度|绝缘|MΩ)", blob):
                bonus += 4.0
            # Title-matching boost: prefer facts whose topic/title contains query keywords
            if isinstance(payload, dict):
                title = str(payload.get("title") or payload.get("topic") or payload.get("subject") or "").lower()
                query_lower = query.lower()
                title_match = False
                for kw in re.findall(r"[一-鿿]{2,}|[a-z0-9]+", query_lower):
                    if len(kw) >= 2 and kw in title:
                        title_match = True
                        break
                if title_match:
                    bonus += 4.0
                elif fact_type == "requirement" and len(title) > 4:
                    bonus -= 2.0
            bonus += float(item.get("_focus_term_bonus") or 0.0)
            bonus += float(item.get("_page_focus_bonus") or 0.0)
            bonus += float(item.get("_subgraph_bonus") or 0.0)
        elif intent == "process":
            if fact_type == "transition_fact":
                bonus = 4.2
            elif fact_type == "process_fact":
                bonus = 4.0
            elif fact_type == "table_requirement":
                bonus = 2.0
            elif fact_type == "requirement":
                bonus = 1.0
            payload = item.get("object_value")
            blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
            if isinstance(payload, dict) and str(payload.get("scope_type") or "") in {"index", "preface"}:
                bonus -= 10.0
            if any(token in blob for token in ("前言", "前    言", "目 次", "目次")):
                bonus -= 10.0
            if _is_timing_query(query) and ("表 A.7" in blob or "控制时序" in blob or "状态转换" in blob):
                bonus += 5.0
            if any(token in blob for token in ("时序", "状态", "握手", "预充", "停机", "控制时序说明")):
                bonus += 2.0
            if "控制导引" in blob or "检测点" in blob or "CP" in blob:
                bonus += 1.2
            # Specificity boost: prefer process_facts whose title directly contains query keywords
            if isinstance(payload, dict):
                title = str(payload.get("title") or payload.get("process_name") or "").lower()
                query_lower = query.lower()
                for kw in re.findall(r"[一-鿿]{2,}", query_lower):
                    if kw in title and len(kw) >= 2:
                        bonus += 3.0
                        break
            bonus += float(item.get("_subgraph_bonus") or 0.0)
        elif intent == "constraint":
            # List-type queries ("有哪些保护") should prefer requirement over threshold
            is_list_query = any(token in query for token in ("有哪些", "包括哪些", "包含哪些", "分为哪些"))
            if fact_type == "threshold":
                bonus = 3.0 if is_list_query else 4.4
            elif fact_type == "requirement":
                bonus = 4.5 if is_list_query else 4.0
            elif fact_type == "table_requirement":
                bonus = 2.4
            elif fact_type == "parameter_value":
                bonus = 1.4
            elif fact_type == "section_heading":
                bonus = 1.0
            payload = item.get("object_value")
            blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
            if any(token in blob for token in ("要求", "应", "不应", "应满足", "不得")):
                bonus += 1.4
            if any(token in blob for token in ("最大", "最小", "不超过", "不小于", "阈值")):
                bonus += 1.0
            # Penalize appendix/index-like table_requirement (standard directory tables)
            if fact_type == "table_requirement" and isinstance(payload, dict):
                title = str(payload.get("title") or "") + str(payload.get("table_title") or "")
                headers = payload.get("headers") or []
                header_blob = " ".join(str(h) for h in headers) if isinstance(headers, list) else str(headers)
                if any(token in title for token in ("序号", "标准编号", "标准名称", "起始实施日期", "附件")):
                    bonus -= 8.0
                elif "序号" in header_blob and "标准编号" in header_blob:
                    bonus -= 8.0
            # Boost facts whose topic/subject matches the query keywords
            query_lower = query.lower()
            for kw in ("保护", "过压", "欠压", "过载", "短路", "过流", "过热", "反接", "安全"):
                if kw in query_lower:
                    # Strong boost when topic/subject/title directly contains the keyword
                    topic = str(payload.get("topic") or payload.get("subject") or payload.get("title") or "").lower()
                    if kw in topic:
                        bonus += 5.0
                        break
                    # Moderate boost when the keyword appears in the content but not the topic
                    if kw in blob:
                        bonus += 1.5
                        break
            # Penalize preface/index/index-like scope
            if isinstance(payload, dict) and str(payload.get("scope_type") or "") in {"index", "preface", "overview"}:
                bonus -= 5.0
            bonus += float(item.get("_subgraph_bonus") or 0.0)
            bonus += float(item.get("_topic_match_bonus") or 0.0)
            if fact_type == "comparison_relation":
                bonus = 4.6
            elif fact_type in {"term_definition", "concept_definition"}:
                bonus = 2.0
            else:
                bonus = 0.6
            payload = item.get("object_value")
            blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
            if any(token in blob.upper() for token in ("V2X", "V2G", "V2V", "V2B", "V2H")):
                bonus += 1.2
            bonus += float(item.get("_subgraph_bonus") or 0.0)
        else:
            # Penalize appendix/attachment index tables across all intents
            if fact_type == "table_requirement" and isinstance(item.get("object_value"), dict):
                table_title = str(item["object_value"].get("table_title") or "").strip()
                if table_title in {"附件:", "附件", "附 录"} or "标准编号" in str(item["object_value"].get("headers", [])):
                    bonus -= 8.0
            if fact_type in {"term_definition", "concept_definition"}:
                bonus = 1.0
            elif fact_type == "requirement":
                bonus = 2.0
            elif fact_type == "threshold":
                bonus = 1.8
            payload = item.get("object_value")
            blob = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
            if isinstance(payload, dict) and str(payload.get("scope_type") or "") in {"index", "preface", "overview"}:
                bonus -= 5.0
            # Generic specificity boost: prefer facts whose title/topic directly contains query keywords
            if isinstance(payload, dict):
                title = str(payload.get("title") or payload.get("topic") or payload.get("subject") or "").lower()
                query_lower = query.lower()
                for kw in re.findall(r"[一-鿿]{2,}", query_lower):
                    if kw in title and len(kw) >= 2:
                        bonus += 2.5
                        break
            elif fact_type == "table_requirement":
                bonus = 1.6
            elif fact_type == "parameter_value":
                bonus = 2.4
            if re.search(r"表\s*\d+", query) and fact_type == "table_requirement":
                bonus += 3.0
                payload = item.get("object_value")
                if isinstance(payload, dict):
                    table_no = str(payload.get("table_no") or "").strip()
                    if requested_table_no and table_no == requested_table_no:
                        bonus += 4.0
                    elif requested_table_no and table_no and table_no != requested_table_no:
                        bonus -= 2.0
            if re.search(r"(字段|表头|参数)", query) and fact_type == "table_requirement":
                bonus += 2.0
            if re.search(r"(阻值|参数|电阻|CC)", query) and fact_type == "parameter_value":
                bonus += 3.0
            # Generic specificity boost: prefer facts whose title/topic directly contains query keywords
            if isinstance(payload, dict):
                title = str(payload.get("title") or payload.get("topic") or payload.get("subject") or "").lower()
                query_lower = query.lower()
                for kw in re.findall(r"[一-鿿]{2,}", query_lower):
                    if kw in title and len(kw) >= 2:
                        bonus += 2.5
                        break
            bonus += float(item.get("_subgraph_bonus") or 0.0)
        return (bonus + confidence, confidence)

    return sorted(facts, key=score, reverse=True)



def _prioritize_judged_facts(context: dict[str, object], facts: list[dict[str, object]]) -> list[dict[str, object]]:
    judgement = context.get("evidence_judgement")
    if not isinstance(judgement, dict) or not judgement.get("sufficient"):
        return facts
    best_fact_ids = [str(item).strip() for item in judgement.get("best_fact_ids") or [] if str(item).strip()]
    if not best_fact_ids:
        return facts
    rank = {fact_id: index for index, fact_id in enumerate(best_fact_ids)}
    return sorted(
        facts,
        key=lambda item: (
            0 if str(item.get("fact_id") or "") in rank else 1,
            rank.get(str(item.get("fact_id") or ""), len(rank)),
        ),
    )



def _find_relevant_pages_for_query(connection, doc_id: str, terms: list[str]) -> set[int]:
    relevant: set[int] = set()
    cleaned_terms = []
    for term in terms:
        normalized = str(term or "").strip()
        if normalized and normalized not in cleaned_terms:
            cleaned_terms.append(normalized)
    for term in cleaned_terms[:12]:
        rows = connection.execute(
            """
            SELECT page_no
            FROM evidence
            WHERE doc_id = ?
              AND normalized_text LIKE ?
            LIMIT 20
            """,
            (doc_id, f"%{term}%"),
        ).fetchall()
        for row in rows:
            page_no = int(row["page_no"])
            for candidate in range(max(1, page_no - 2), page_no + 3):
                relevant.add(candidate)
    return relevant



def _select_answer_facts(
    facts: list[dict[str, object]],
    intent: str,
    query: str,
    knowledge_subgraph: dict[str, object] | None = None,
    rewritten_payload: dict[str, object] | None = None,
    answer_mode: str = "",
) -> list[dict[str, object]]:
    from .answer_parameter import _parameter_focus_terms, _select_parameter_meaning_answer_facts
    from .answer_process import _select_process_answer_facts
    from .answer_standard import _select_standard_answer_facts
    from .answer_definition import _select_definition_answer_facts
    from .answer_constraint import _select_constraint_answer_facts
    from .answer_comparison import _select_comparison_answer_facts
    if intent == "standard":
        return _select_standard_answer_facts(facts, knowledge_subgraph, query)
    if intent not in {"parameter", "process", "definition", "constraint", "comparison"}:
        return _prioritize_subgraph_facts(facts, knowledge_subgraph)

    if intent == "process":
        return _select_process_answer_facts(facts, knowledge_subgraph, query)
    if intent == "definition":
        return _select_definition_answer_facts(facts, knowledge_subgraph, query, rewritten_payload or {})
    if intent == "constraint":
        return _select_constraint_answer_facts(facts, knowledge_subgraph, query, rewritten_payload or {})
    if intent == "comparison":
        return _select_comparison_answer_facts(facts, knowledge_subgraph)
    if answer_mode == "parameter_meaning":
        return _select_parameter_meaning_answer_facts(facts, knowledge_subgraph, query, rewritten_payload or {})

    focus_terms = _parameter_focus_terms(query, {"must_terms": [], "aliases": [], "should_terms": []})

    def score(item: dict[str, object]) -> tuple[float, float]:
        fact_type = str(item.get("fact_type") or "")
        confidence = float(item.get("confidence") or 0.0)
        payload = item.get("object_value")
        if not isinstance(payload, dict):
            payload = {}
        focus_tags = [str(tag).upper() for tag in payload.get("focus_tags") or []]
        page_bonus = float(item.get("_page_focus_bonus") or 0.0)
        raw_focus_bonus = float(item.get("_focus_term_bonus") or 0.0)
        wiki_bonus = 2.2 if item.get("_source_from_wiki") else 0.0
        subgraph_bonus = float(item.get("_subgraph_bonus") or 0.0)
        bonus = confidence + page_bonus + raw_focus_bonus + wiki_bonus + subgraph_bonus

        if fact_type == "parameter_value":
            bonus += 6.0
        elif fact_type == "table_requirement":
            bonus += 3.0
        elif fact_type == "threshold":
            bonus += 1.0
        elif fact_type in {"term_definition", "concept_definition"}:
            # Term definitions are the most direct answer for definition queries
            bonus += 2.5
        else:
            bonus += 0.2

        if any(term.upper() in focus_tags for term in focus_terms if term):
            bonus += 5.0
        if "CC" in query.upper():
            if "CC1" in focus_tags or "CC2" in focus_tags:
                bonus += 4.0
            elif fact_type == "parameter_value":
                bonus -= 2.5
        if re.search(r"(检测点\s*\d)", query):
            if any("检测点" in tag for tag in focus_tags):
                bonus += 3.0
        # Definition-like queries: "什么是X", "X是什么" — boost term/concept definitions
        if re.search(r"(什么是|是什么|指什么|定义|含义|的意思)", query):
            if fact_type in {"term_definition", "concept_definition"}:
                bonus += 3.0
        return (bonus, confidence)

    ranked = sorted(_prioritize_subgraph_facts(facts, knowledge_subgraph), key=score, reverse=True)
    parameter_first = [item for item in ranked if item.get("fact_type") == "parameter_value"]
    if parameter_first:
        supporting_tables = [item for item in ranked if item.get("fact_type") == "table_requirement"]
        return parameter_first + supporting_tables + [item for item in ranked if item.get("fact_type") not in {"parameter_value", "table_requirement"}]
    return ranked



def _focus_term_bonus(blob: str, focus_terms: list[str]) -> float:
    if not blob:
        return 0.0
    bonus = 0.0
    for term in focus_terms:
        if not term:
            continue
        if term in blob:
            if re.fullmatch(r"[A-Z]{1,4}\d*", term):
                bonus += 1.8
            elif "检测点" in term:
                bonus += 1.6
            else:
                bonus += 0.8
    return bonus



