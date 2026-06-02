"""Test-case construction: build/select/dedupe/prioritize cases from corpus.

Extracted from `generated_tests._impl` to isolate the per-kind case
construction (page coverage, retrieval quality, last-resort, network,
answer quality, evidence-derived) and the case-selection/dedup/render
logic from the lifecycle (activate/detect/revalidate) and coverage
drafting concerns.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ._case_helpers import (
    _contains_locally,
    _normalize_compare,
    _safe_identifier,
    _safe_json,
    _strip_html,
    _unique_matches,
    _unique_values,
)
from ._lifecycle import EVAL_RETRIEVAL_LIMIT

MIN_CASE_COUNT = 20
MAX_CASE_COUNT = 220

def generate_golden_tests_for_document(
    workspace_root: Path,
    doc_id: str,
    *,
    validate_cases: bool = True,
    include_network: bool = True,
) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    tests_dir = paths.root.parent / "tests" / "generated"
    tests_dir.mkdir(parents=True, exist_ok=True)

    try:
        document = connection.execute(
            """
            SELECT doc_id, source_filename, page_count
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        if document is None:
            raise ValueError(f"document not found: {doc_id}")

        facts = connection.execute(
            """
            SELECT fact_type, predicate, object_value, qualifiers_json
            FROM facts
            WHERE source_doc_id = ?
            ORDER BY fact_id
            """,
            (doc_id,),
        ).fetchall()
        evidence_rows = connection.execute(
            """
            SELECT page_no, normalized_text, confidence
            FROM evidence
            WHERE doc_id = ?
            ORDER BY page_no, evidence_id
            """,
            (doc_id,),
        ).fetchall()
        wiki_rows = connection.execute(
            """
            SELECT page_type, title, slug
            FROM wiki_pages
            WHERE json_extract(source_doc_ids_json, '$[0]') = ?
            ORDER BY page_id
            """,
            (doc_id,),
        ).fetchall()

        target_case_count = _target_case_count(
            int(document["page_count"] or 0),
            len(facts),
            len(evidence_rows),
        )

        local_context = _build_local_context(document, facts, evidence_rows, wiki_rows)
        network_target = min(target_case_count, max(8, math.ceil(target_case_count * 0.6)))
        network_cases = _build_network_cases(local_context, network_target) if include_network else []
        network_candidate_count = len(network_cases)
        local_cases = _build_local_cases(local_context, target_case_count * 2)
        supplemental_cases = _build_local_cases(local_context, target_case_count * 3, extra_round=True)
        rq_target = max(5, math.ceil(target_case_count * 0.3))
        retrieval_quality_cases = _build_retrieval_quality_cases(local_context, rq_target)
        aq_target = max(3, math.ceil(target_case_count * 0.1))
        answer_quality_cases = _build_answer_quality_cases(local_context, aq_target)

        candidate_pool = _dedupe_cases([*retrieval_quality_cases, *answer_quality_cases, *network_cases, *local_cases, *supplemental_cases])
        cases = (
            _select_validated_cases(workspace_root, candidate_pool, target_case_count)
            if validate_cases
            else _select_cases_without_validation(candidate_pool, target_case_count)
        )
        if len(cases) < MIN_CASE_COUNT:
            extra_candidates = _dedupe_cases([*candidate_pool, *_build_last_resort_cases(local_context)])
            cases = (
                _select_validated_cases(workspace_root, extra_candidates, MIN_CASE_COUNT)
                if validate_cases
                else _select_cases_without_validation(extra_candidates, MIN_CASE_COUNT)
            )
        for case in cases:
            case["target_doc_id"] = doc_id
        if not validate_cases:
            cases = [case for case in cases if _validate_case_source_trace(workspace_root, case)]

        coverage = _page_coverage_summary(local_context, cases)

        json_path = tests_dir / f"{doc_id}.golden.json"
        json_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "source_filename": document["source_filename"],
                    "page_count": document["page_count"],
                    "target_case_count": target_case_count,
                    "validated_during_generation": validate_cases,
                    "network_enabled": include_network,
                    "network_candidate_count": network_candidate_count,
                    "network_case_count": sum(1 for item in cases if item.get("source") == "network"),
                    "local_case_count": sum(1 for item in cases if item.get("source") == "local"),
                    "page_coverage_count": coverage["page_coverage_count"],
                    "covered_pages": coverage["covered_pages"],
                    "uncovered_pages": coverage["uncovered_pages"],
                    "cases": cases,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        safe_doc_id = _safe_identifier(doc_id.lower())
        py_path = tests_dir / f"test_{safe_doc_id}_golden.py"
        py_path.write_text(_render_pytest_file(doc_id, cases), encoding="utf-8")
        sync_golden_cases(connection, doc_id, cases)
        connection.commit()

        return {
            "doc_id": doc_id,
            "source_filename": document["source_filename"],
            "page_count": document["page_count"],
            "target_case_count": target_case_count,
            "case_count": len(cases),
            "validated_during_generation": validate_cases,
            "network_enabled": include_network,
            "network_candidate_count": network_candidate_count,
            "network_case_count": sum(1 for item in cases if item.get("source") == "network"),
            "local_case_count": sum(1 for item in cases if item.get("source") == "local"),
            "page_coverage_count": coverage["page_coverage_count"],
            "covered_pages": coverage["covered_pages"],
            "uncovered_pages": coverage["uncovered_pages"],
            "json_path": str(json_path),
            "pytest_path": str(py_path),
            "cases": cases,
        }
    finally:
        connection.close()
def _load_or_create_golden_payload(paths: AppPaths, doc_id: str, golden_path: Path) -> dict[str, object]:
    if golden_path.exists():
        payload = json.loads(golden_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("doc_id", doc_id)
            payload.setdefault("cases", [])
            return payload

    connection = connect(paths.db_file)
    try:
        document = connection.execute(
            """
            SELECT source_filename, page_count
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
    finally:
        connection.close()

    if document is None:
        raise ValueError(f"document not found: {doc_id}")
    return {
        "doc_id": doc_id,
        "source_filename": document["source_filename"],
        "page_count": document["page_count"],
        "target_case_count": 0,
        "network_candidate_count": 0,
        "network_case_count": 0,
        "local_case_count": 0,
        "page_coverage_count": 0,
        "covered_pages": [],
        "uncovered_pages": [],
        "cases": [],
    }
def _build_network_cases(local_context: dict[str, object], target_count: int) -> list[dict[str, object]]:
    if target_count <= 0:
        return []

    search_queries = _build_search_queries(local_context)
    cases: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    page_fetch_budget = 6

    for query in search_queries:
        for hit in _search_duckduckgo(query):
            if page_fetch_budget <= 0:
                return _dedupe_cases(cases)[:target_count]
            if hit["url"] in seen_urls:
                continue
            seen_urls.add(hit["url"])
            page_fetch_budget -= 1

            source_text = "\n".join(
                part for part in [hit["title"], hit["snippet"], _fetch_page_text(hit["url"])] if part
            )
            if not source_text.strip():
                continue

            extracted = _extract_network_metadata(source_text)
            candidates = _network_cases_from_metadata(local_context, extracted, hit["url"])
            for case in candidates:
                cases.append(case)
                if len(_dedupe_cases(cases)) >= target_count:
                    break
    return _dedupe_cases(cases)[:target_count]
def _build_answer_quality_cases(
    local_context: dict[str, object],
    target_count: int,
) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    seen_queries: set[str] = set()

    def _add_aq(query: str, must_include: list[str], *, expected_answer_mode: str, forbidden_contains: list[str], expected_evidence_shape: str, query_type: str = "parameter_lookup") -> None:
        normalized_query = re.sub(r"\s+", " ", query).strip()
        if normalized_query in seen_queries:
            return
        if not must_include or not _is_usable_golden_anchor(must_include[0]):
            return
        seen_queries.add(normalized_query)
        case: dict[str, object] = {
            "kind": "answer_quality",
            "query": normalized_query,
            "must_include": must_include[0],
            "retrieval_must_hit": must_include,
            "assert_mode": "rich_answer",
            "expected_answer_mode": expected_answer_mode,
            "forbidden_contains": forbidden_contains,
            "expected_evidence_shape": expected_evidence_shape,
            "source": "local_aq",
            "query_type": query_type,
        }
        cases.append(case)

    parameter_facts = [
        f for f in local_context.get("facts", [])
        if f.get("fact_type") == "parameter_value"
        and isinstance(_safe_json(f.get("object_value")), dict)
    ]
    seen_param_keys: set[str] = set()
    for fact in parameter_facts:
        payload = _safe_json(fact.get("object_value"))
        if not isinstance(payload, dict):
            continue
        parameter = str(payload.get("parameter") or "").strip()
        symbol = str(payload.get("symbol") or "").strip()
        unit = str(payload.get("unit", "")).strip()
        key_parts = [p for p in [parameter, symbol] if p]
        key = "|".join(key_parts)
        if key in seen_param_keys or not key_parts:
            continue
        seen_param_keys.add(key)
        if not parameter or not symbol:
            continue
        if not _is_usable_parameter_label(parameter):
            continue
        _add_aq(
            query=f"{parameter}是多少",
            must_include=[parameter, unit] if unit else [parameter],
            expected_answer_mode="parameter_value",
            forbidden_contains=["没有找到足够的结构化结果。", "GB：代替"],
            expected_evidence_shape="parameter_value",
            query_type="parameter_lookup",
        )

    return _dedupe_cases(cases)[:target_count]

    return _dedupe_cases(cases)[:target_count]
def _build_search_queries(local_context: dict[str, object]) -> list[str]:
    filename_stem = Path(str(local_context["source_filename"])).stem
    standard_code = str(local_context.get("standard_code", "")).replace("—", "-")
    title = str(local_context.get("title", ""))
    queries = [
        f"{standard_code} {title}".strip(),
        f"{standard_code} {filename_stem}".strip(),
        filename_stem,
        standard_code,
        title,
    ]
    deduped: list[str] = []
    for item in queries:
        cleaned = re.sub(r"\s+", " ", item).strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped[:4]
def _build_local_cases(
    local_context: dict[str, object],
    target_count: int,
    extra_round: bool = False,
) -> list[dict[str, str]]:
    if target_count <= 0:
        return []

    cases: list[dict[str, str]] = []
    standard_code = str(local_context.get("standard_code", "")).strip()
    title = str(local_context.get("title", "")).strip()
    publication_date = str(local_context.get("publication_date", "")).strip()
    effective_date = str(local_context.get("effective_date", "")).strip()

    if standard_code and _is_valid_standard_code(standard_code):
        for query in [
            f"{standard_code} 的标准号和实施日期是什么？",
            f"{standard_code} 对应的标准编号是什么？",
            f"{standard_code} 的现行标准号是什么？",
        ]:
            cases.append(_case("standard", _scope_query(local_context, query), standard_code, source="local", assert_mode="context_contains"))

    if publication_date:
        for query in [
            f"{standard_code or title} 的发布日期是什么？",
            f"{standard_code or title} 是哪一天发布的？",
        ]:
            cases.append(_case("publication_date", _scope_query(local_context, query), publication_date, source="local", assert_mode="context_contains"))

    if effective_date:
        for query in [
            f"{standard_code or title} 的实施日期是什么？",
            f"{standard_code or title} 从哪一天开始实施？",
        ]:
            cases.append(_case("effective_date", _scope_query(local_context, query), effective_date, source="local", assert_mode="context_contains"))

    if title and _is_usable_golden_anchor(title):
        cases.append(_case("title", _scope_query(local_context, f"{standard_code or title} 这份文档的标题是什么？"), title, source="local", assert_mode="context_contains"))

    for item in list(local_context.get("term_definitions", []))[:8]:
        term = _strip_markdown_bold(str(item["term"]).strip())
        definition = _strip_markdown_bold(str(item["definition"]).strip())
        if not term or not definition or not _is_usable_golden_anchor(term) or not _is_usable_golden_anchor(definition):
            continue
        if _looks_like_person_name(term):
            continue
        definition_query_prefix = f"在{standard_code}中，" if standard_code else ""
        cases.append(
            _case(
                "definition",
                _scope_query(local_context, f"{definition_query_prefix}什么是{term}？"),
                term,
                source="local",
                assert_mode="context_contains",
            )
        )
        cases.append(
            _case(
                "definition_detail",
                _scope_query(local_context, f"{definition_query_prefix}{term} 的定义是什么？"),
                _definition_anchor(definition),
                source="local",
                assert_mode="context_contains",
            )
        )

    sampled_headings = _sample_headings(list(local_context.get("section_headings", [])), 4 if not extra_round else 6)
    for heading in sampled_headings:
        title_value = str(heading["title"]).strip()
        if not title_value or not _is_usable_golden_anchor(title_value):
            continue
        cases.append(
            _case(
                "section",
                _scope_query(local_context, f"在{standard_code or '该文档'}中，是否包含“{title_value}”这一章节？"),
                title_value,
                source="local",
                assert_mode="context_contains",
                page_no=int(heading.get("page_no") or 0),
            )
        )

    evidence_cases = _cases_from_evidence(local_context, list(local_context.get("evidence", [])), extra_round=extra_round)
    cases.extend(evidence_cases)

    return _dedupe_cases(cases)[:target_count]
def _cases_from_evidence(
    local_context: dict[str, object],
    evidence_items: list[dict[str, object]],
    extra_round: bool = False,
) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    sentence_budget = 10 if not extra_round else 18
    sentence_items: list[tuple[str, int]] = []
    seen_sentences: set[str] = set()

    for item in evidence_items:
        text = str(item.get("normalized_text", "")).strip()
        if not text or _is_low_value_evidence_text(text):
            continue
        for sentence in _extract_candidate_sentences(text):
            if sentence not in seen_sentences:
                sentence_items.append((sentence, int(item.get("page_no") or 0)))
                seen_sentences.add(sentence)
            if len(sentence_items) >= sentence_budget:
                break
        if len(sentence_items) >= sentence_budget:
            break

    for sentence, page_no in sentence_items:
        anchor = _definition_anchor(sentence)
        if not _is_usable_golden_anchor(anchor):
            continue
        if "适用于" in sentence:
            query = anchor
        elif "规定了" in sentence:
            query = anchor
        elif "发布" in sentence and re.search(r"\d{4}-\d{2}-\d{2}", sentence):
            query = anchor
        elif "实施" in sentence and re.search(r"\d{4}-\d{2}-\d{2}", sentence):
            query = anchor
        else:
            query = anchor
        cases.append(
            _case(
                "evidence",
                _scope_query(local_context, query),
                anchor,
                source="local",
                assert_mode="context_contains",
                page_no=page_no,
            )
        )

    return cases
def _build_page_coverage_cases(local_context: dict[str, object]) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    per_page_seen: set[int] = set()

    for evidence_item in list(local_context.get("evidence", [])):
        page_no = int(evidence_item.get("page_no") or 0)
        if page_no <= 0 or page_no in per_page_seen:
            continue
        text = str(evidence_item.get("normalized_text", "")).strip()
        if _is_low_value_evidence_text(text):
            continue
        sentence = _select_page_anchor_sentence(text) or _select_page_anchor_fragment(text)
        if not sentence:
            continue
        per_page_seen.add(page_no)
        anchor = _definition_anchor(sentence, max_chars=38)
        if not _is_usable_golden_anchor(anchor):
            continue
        query = f"第{page_no}页 {anchor}"
        cases.append(
            _case(
                "page_coverage",
                query,
                anchor,
                source="local",
                assert_mode="context_contains",
                page_no=page_no,
            )
        )

    return cases
def _build_retrieval_quality_cases(
    local_context: dict[str, object],
    target_count: int,
) -> list[dict[str, object]]:
    if target_count <= 0:
        return []

    standard_code = str(local_context.get("standard_code", "")).strip()
    title = str(local_context.get("title", "")).strip()
    scope_label = standard_code or title or str(local_context.get("doc_id", "")).strip()
    cases: list[dict[str, object]] = []
    seen_queries: set[str] = set()

    def _add_rq(query, must_hit, expected_pages=None, expected_sections=None, negative_expected=None, difficulty="medium", query_type="scenario"):
        normalized_query = re.sub(r"\s+", " ", query).strip()
        if normalized_query in seen_queries:
            return
        if not must_hit or not _is_usable_golden_anchor(must_hit[0] if must_hit else ""):
            return
        seen_queries.add(normalized_query)
        case: dict[str, object] = {
            "kind": "retrieval_quality",
            "query": normalized_query,
            "must_include": must_hit[0],
            "retrieval_must_hit": must_hit,
            "assert_mode": "rich_answer",
            "source": "local_rq",
            "expected_pages": expected_pages or [],
            "expected_sections": expected_sections or [],
            "negative_expected": negative_expected or [],
            "difficulty": difficulty,
            "query_type": query_type,
        }
        if "expected_pages" in case and not case["expected_pages"]:
            del case["expected_pages"]
        if "expected_sections" in case and not case["expected_sections"]:
            del case["expected_sections"]
        if "negative_expected" in case and not case["negative_expected"]:
            del case["negative_expected"]
        cases.append(case)

    def _add_aq(query: str, must_include: list[str], *, expected_answer_mode: str, forbidden_contains: list[str], expected_evidence_shape: str, query_type: str = "parameter_lookup") -> None:
        """Add an answer_quality case for testing answer correctness."""
        nonlocal cases, seen_queries
        normalized_query = re.sub(r"\s+", " ", query).strip()
        if normalized_query in seen_queries:
            return
        if not must_include or not _is_usable_golden_anchor(must_include[0]):
            return
        seen_queries.add(normalized_query)
        case: dict[str, object] = {
            "kind": "answer_quality",
            "query": normalized_query,
            "must_include": must_include[0],
            "retrieval_must_hit": must_include,
            "assert_mode": "rich_answer",
            "expected_answer_mode": expected_answer_mode,
            "forbidden_contains": forbidden_contains,
            "expected_evidence_shape": expected_evidence_shape,
            "source": "local_aq",
            "query_type": query_type,
        }
        if "forbidden_contains" in case and not case["forbidden_contains"]:
            del case["forbidden_contains"]
        cases.append(case)

    for item in list(local_context.get("term_definitions", [])):
        term = _strip_markdown_bold(str(item["term"]).strip())
        definition = _strip_markdown_bold(str(item["definition"]).strip())
        if not term or not definition or not _is_usable_golden_anchor(term) or not _is_usable_golden_anchor(definition):
            continue
        if _looks_like_person_name(term):
            continue
        _add_rq(
            query=f"什么是{term}？",
            must_hit=[term],
            expected_sections=[term],
            query_type="definition",
        )
        _add_rq(
            query=f"{scope_label}中{term}的定义是什么？",
            must_hit=[term],
            expected_sections=[term],
            query_type="definition",
        )

    parameter_facts = [
        f for f in local_context.get("facts", [])
        if f.get("fact_type") == "parameter_value"
        and isinstance(_safe_json(f.get("object_value")), dict)
    ]
    seen_param_keys: set[str] = set()
    for fact in parameter_facts:
        payload = _safe_json(fact.get("object_value"))
        if not isinstance(payload, dict):
            continue
        parameter = str(payload.get("parameter") or "").strip()
        symbol = str(payload.get("symbol") or "").strip()
        table_title = str(payload.get("table_title") or "").strip()
        object_name = str(payload.get("object") or "").strip()
        state = str(payload.get("state") or "").strip()
        qualifiers = _safe_json(fact.get("qualifiers_json"))
        page_no = int(qualifiers.get("page_no", 0)) if isinstance(qualifiers, dict) else 0
        key_parts = [p for p in [object_name, parameter, symbol] if p]
        key = "|".join(key_parts)
        if key in seen_param_keys or not key_parts:
            continue
        seen_param_keys.add(key)
        label = key_parts[0]
        if not _is_usable_parameter_label(label):
            continue
        _add_rq(
            query=f"{label}的参数要求是什么？",
            must_hit=[label],
            expected_pages=[page_no] if page_no else [],
            expected_sections=[table_title] if table_title else [],
            query_type="parameter_lookup",
        )
        if parameter and symbol:
            _add_rq(
            query=f"{symbol}代表什么参数？",
            must_hit=[parameter],
            expected_pages=[page_no] if page_no else [],
            expected_sections=[table_title] if table_title else [],
            query_type="parameter_lookup",
        )

    if local_context.get("term_definitions"):
        top_terms = [str(t.get("term", "")) for t in local_context["term_definitions"][:6] if str(t.get("term", "")).strip()]
        if len(top_terms) >= 2:
            pair = "和".join(top_terms[:2])
            _add_rq(
                query=f"{pair}有什么区别？",
                must_hit=top_terms[:2],
                query_type="comparison",
                difficulty="hard",
            )

    requirement_facts = [
        f for f in local_context.get("facts", [])
        if f.get("fact_type") == "requirement"
        and isinstance(_safe_json(f.get("object_value")), dict)
    ]
    seen_req_keys: set[str] = set()
    for fact in requirement_facts[:40]:
        payload = _safe_json(fact.get("object_value"))
        if not isinstance(payload, dict):
            continue
        subject = str(payload.get("subject") or payload.get("topic") or "").strip()
        content = str(payload.get("content") or "").strip()
        section_title = str(payload.get("title") or "").strip()
        qualifiers = _safe_json(fact.get("qualifiers_json"))
        page_no = int(qualifiers.get("page_no", 0)) if isinstance(qualifiers, dict) else 0
        if not subject or subject in seen_req_keys:
            continue
        if len(subject) < 3 or len(subject) > 30:
            continue
        seen_req_keys.add(subject)
        _add_rq(
            query=f"{subject}有什么要求？",
            must_hit=[subject],
            expected_pages=[page_no] if page_no else [],
            expected_sections=[section_title] if section_title else [],
            query_type="general_search",
        )

    process_facts = [
        f for f in local_context.get("facts", [])
        if f.get("fact_type") == "process_fact"
        and isinstance(_safe_json(f.get("object_value")), dict)
    ]
    seen_proc_keys: set[str] = set()
    for fact in process_facts[:30]:
        payload = _safe_json(fact.get("object_value"))
        if not isinstance(payload, dict):
            continue
        proc_name = str(payload.get("process_name") or payload.get("title") or "").strip()
        section = str(payload.get("section") or "").strip()
        qualifiers = _safe_json(fact.get("qualifiers_json"))
        page_no = int(qualifiers.get("page_no", 0)) if isinstance(qualifiers, dict) else 0
        clean_name = re.sub(r"^\d+[\.\s]+", "", proc_name).strip()
        if not clean_name or clean_name in seen_proc_keys or len(clean_name) < 3:
            continue
        seen_proc_keys.add(clean_name)
        _add_rq(
            query=f"{clean_name}的流程是什么？",
            must_hit=[clean_name],
            expected_pages=[page_no] if page_no else [],
            expected_sections=[section] if section else [],
            query_type="timing_lookup",
        )

    threshold_facts = [
        f for f in local_context.get("facts", [])
        if f.get("fact_type") == "threshold"
        and isinstance(_safe_json(f.get("object_value")), dict)
    ]
    seen_thr_keys: set[str] = set()
    for fact in threshold_facts[:20]:
        payload = _safe_json(fact.get("object_value"))
        if not isinstance(payload, dict):
            continue
        parameter = str(payload.get("parameter") or "").strip()
        condition = str(payload.get("condition") or "").strip()
        section_title = str(payload.get("title") or "").strip()
        qualifiers = _safe_json(fact.get("qualifiers_json"))
        page_no = int(qualifiers.get("page_no", 0)) if isinstance(qualifiers, dict) else 0
        label = parameter or condition
        if not label or label in seen_thr_keys or len(label) < 3:
            continue
        seen_thr_keys.add(label)
        _add_rq(
            query=f"{label}的限值是多少？",
            must_hit=[label],
            expected_pages=[page_no] if page_no else [],
            expected_sections=[section_title] if section_title else [],
            query_type="parameter_lookup",
        )

    return _dedupe_cases(cases)[:target_count]
def _build_last_resort_cases(local_context: dict[str, object]) -> list[dict[str, str]]:
    standard_code = str(local_context.get("standard_code", "")).strip()
    title = str(local_context.get("title", "")).strip()
    cases: list[dict[str, str]] = []
    for heading in list(local_context.get("section_headings", [])):
        title_value = str(heading.get("title", "")).strip()
        if not title_value or not _is_usable_golden_anchor(title_value):
            continue
        query = _scope_query(local_context, f"{standard_code or title} {title_value}")
        cases.append(
            _case(
                "keyword_section",
                query,
                title_value,
                source="local",
                assert_mode="context_contains",
                page_no=int(heading.get("page_no") or 0),
            )
        )
    for term_item in list(local_context.get("term_definitions", [])):
        term = str(term_item.get("term", "")).strip()
        if term and _is_usable_golden_anchor(term):
            query = _scope_query(local_context, f"{standard_code or title} {term}")
            cases.append(_case("keyword_term", query, term, source="local", assert_mode="context_contains"))
    for wiki_item in list(local_context.get("wiki", [])):
        wiki_title = str(wiki_item.get("title", "")).strip()
        if wiki_title and _is_usable_golden_anchor(wiki_title):
            query = _scope_query(local_context, wiki_title)
            cases.append(
                _case(
                    "keyword_wiki",
                    query,
                    wiki_title,
                    source="local",
                    assert_mode="context_contains",
                )
            )
    evidence_budget = 24
    for evidence_item in list(local_context.get("evidence", [])):
        text = str(evidence_item.get("normalized_text", "")).strip()
        if not text or _is_low_value_evidence_text(text):
            continue
        for sentence in _extract_candidate_sentences(text):
            anchor = _definition_anchor(sentence, max_chars=28)
            if len(anchor) < 10 or not _is_usable_golden_anchor(anchor):
                continue
            cases.append(
                _case(
                    "keyword_evidence",
                    _scope_query(local_context, anchor),
                    anchor,
                    source="local",
                    assert_mode="context_contains",
                    page_no=int(evidence_item.get("page_no") or 0),
                )
            )
            evidence_budget -= 1
            if evidence_budget <= 0:
                break
        if evidence_budget <= 0:
            break
    return cases
def _sample_headings(headings: list[dict[str, object]], budget: int) -> list[dict[str, object]]:
    if len(headings) <= budget:
        return headings
    step = max(1, len(headings) // budget)
    sampled = [headings[index] for index in range(0, len(headings), step)]
    return sampled[:budget]
def _case(
    kind: str,
    query: str,
    must_include: str,
    *,
    source: str,
    assert_mode: str,
    page_no: int | None = None,
    source_url: str | None = None,
    expected_evidence_shape: str | None = None,
) -> dict[str, str]:
    payload = {
        "kind": kind,
        "query": re.sub(r"\s+", " ", query).strip(),
        "must_include": re.sub(r"\s+", " ", must_include).strip(),
        "source": source,
        "assert_mode": assert_mode,
    }
    evidence_shape = expected_evidence_shape or _expected_evidence_shape_for_case_kind(kind)
    if evidence_shape:
        payload["expected_evidence_shape"] = evidence_shape
    if page_no:
        payload["page_no"] = int(page_no)
    if source_url:
        payload["source_url"] = source_url
    return payload
def _expected_evidence_shape_for_case_kind(kind: str) -> str:
    case_kind = str(kind or "").strip()
    if case_kind in {"standard", "title", "publication_date", "effective_date"}:
        return "standard_metadata"
    if case_kind in {"definition", "definition_detail", "coverage_definition"}:
        return "term_definition"
    if case_kind in {"coverage_parameter_value"}:
        return "parameter_definition"
    if case_kind in {"coverage_requirement"}:
        return "requirement"
    return ""
def _dedupe_cases(cases: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: dict[tuple[str, str, str], int] = {}
    for case in cases:
        key = (
            case.get("query", ""),
            _normalize_compare(case.get("must_include", "")),
            case.get("assert_mode", ""),
        )
        if not case.get("must_include"):
            continue
        if key in seen:
            _merge_case_constraints(deduped[seen[key]], case)
            continue
        seen[key] = len(deduped)
        deduped.append(case)
    return deduped
def _merge_case_constraints(target: dict[str, str], incoming: dict[str, str]) -> None:
    for key in (
        "expected_evidence_shape",
        "expected_answer_mode",
        "query_type",
        "target_doc_id",
        "page_no",
        "coverage_unit_id",
        "coverage_semantic_key",
    ):
        if not target.get(key) and incoming.get(key):
            target[key] = incoming[key]
def _extract_candidate_titles(text: str) -> list[str]:
    titles: list[str] = []
    for pattern in [
        r"(Automotive DC-AC power inverter)",
        r"(汽车电源逆变器)",
        r"(电动汽车用传导式车载充电机)",
        r"(电动汽车传导充电系统[^。；]{0,60})",
    ]:
        titles.extend(_unique_matches(pattern, text, flags=re.I))
    return titles[:6]
def _extract_scope_sentences(text: str) -> list[str]:
    scopes: list[str] = []
    for match in re.finditer(r"((?:本标准|本文件).{0,80}?(?:规定了|适用于).{0,120}[。；])", text):
        scopes.append(_definition_anchor(match.group(1)))
    for match in re.finditer(r"((?:This standard|This document).{0,140}?(?:specifies|applies to).{0,180}\.)", text, re.I):
        scopes.append(_definition_anchor(match.group(1)))
    return _unique_values(scopes)[:6]
def _extract_organizations(text: str) -> list[str]:
    organizations: list[str] = []
    for pattern in [
        r"(中华人民共和国工业和信息化部)",
        r"(全国汽车标准化技术委员会[^，。；]{0,40})",
        r"(上海汽车集团股份有限公司技术中心)",
        r"(长沙汽车电器研究所)",
    ]:
        organizations.extend(_unique_matches(pattern, text))
    return _unique_values(organizations)[:6]
def _extract_candidate_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[。；.!?])\s+", cleaned)
    sentences: list[str] = []
    for part in parts:
        segment = part.strip()
        if len(segment) < 16:
            continue
        if "<table" in segment.lower():
            continue
        if segment not in sentences:
            sentences.append(segment)
    return sentences[:6]
def _select_page_anchor_sentence(text: str) -> str:
    sentences = _extract_candidate_sentences(text)
    ranked = sorted(sentences, key=_page_sentence_score, reverse=True)
    return ranked[0] if ranked else ""
def _select_page_anchor_fragment(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", _strip_html(text)).strip()
    if not cleaned:
        return ""
    for pattern in [
        r"(QC/T\s*[\d.]+[—-]\d{4})",
        r"(GB/T\s*[\d.]+[—-]\d{4})",
        r"(第\s*\d+\s*部分[^，。；]{0,18})",
        r"([一二三四五六七八九十\d]+\s*[范围要求试验方法检验规则术语定义保护功能效率电压功率]{1,8}[^，。；]{0,18})",
    ]:
        match = re.search(pattern, cleaned, re.I)
        if match:
            return match.group(1).strip()
    if len(cleaned) <= 28:
        return cleaned
    return cleaned[:28].rstrip(" ，,;；。")
def _page_sentence_score(sentence: str) -> tuple[int, int]:
    penalty = 1 if any(token in sentence for token in ("目次", "目 次", "前言", "目录", "chapter", "contents")) else 0
    signal = sum(1 for token in ("适用于", "规定", "要求", "试验", "定义", "保护", "输出", "电压", "功率", "效率") if token in sentence)
    return (signal - penalty, len(sentence))
def _definition_anchor(text: str, max_chars: int = 42) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip(" ，,;；。")
def _query_anchor(text: str, max_chars: int = 18) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip(" ，,;；。") + "..."
def _render_pytest_file(doc_id: str, cases: list[dict[str, str]]) -> str:
    safe_doc_id = _safe_identifier(doc_id.lower())
    lines = [
        "from __future__ import annotations",
        "",
        "import json",
        "import os",
        "from pathlib import Path",
        "",
        "import pytest",
        "",
        "from enterprise_agent_kb.answer_api import answer_query",
        "from enterprise_agent_kb.query_api import build_query_context",
        "",
        'os.environ.setdefault("EAKB_ENABLE_LLM_EVIDENCE_JUDGE", "0")',
        "",
        'WORKSPACE = Path("knowledge_base")',
        "",
        "",
        "def _normalize(value: str) -> str:",
        '    text = value.lower().replace("—", "-").replace("／", "/")',
        '    return "".join(text.split())',
        "",
        "",
        "def _assert_case(case: dict[str, str]) -> None:",
        '    expected = _normalize(case["must_include"])',
        '    target_doc_id = str(case.get("target_doc_id") or "") or None',
        '    if case.get("assert_mode") == "context_contains":',
        f'        context = build_query_context(WORKSPACE, case["query"], limit={EVAL_RETRIEVAL_LIMIT}, preferred_doc_id=target_doc_id)',
        '        blob = json.dumps(context, ensure_ascii=False)',
        '    else:',
        f'        answer = answer_query(WORKSPACE, case["query"], limit={EVAL_RETRIEVAL_LIMIT}, preferred_doc_id=target_doc_id)',
        '        blob = "\\n".join(',
        '            [',
        '                str(answer.get("direct_answer", "")),',
        '                *[str(item) for item in answer.get("summary", [])],',
        '                *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_facts", [])],',
        '                *[json.dumps(item, ensure_ascii=False) for item in answer.get("supporting_evidence", [])],',
        '                *[json.dumps(item, ensure_ascii=False) for item in answer.get("related_wiki_pages", [])],',
        '            ]',
        '        )',
        '    if target_doc_id:',
        '        assert _normalize(target_doc_id) in _normalize(blob)',
        '    assert expected in _normalize(blob)',
        "",
    ]
    for index, case in enumerate(cases, start=1):
        marker_lines = _pytest_marker_lines_for_case(case)
        lines.extend(
            [
                "@pytest.mark.integration",
                "@pytest.mark.benchmark",
                *marker_lines,
                f"def test_{safe_doc_id}_golden_{index}() -> None:",
                f"    case = {json.dumps(case, ensure_ascii=False)!r}",
                "    _assert_case(json.loads(case))",
                "",
            ]
        )
    return "\n".join(lines)
def _pytest_marker_lines_for_case(case: dict[str, str]) -> list[str]:
    markers: list[str] = []
    source = str(case.get("source") or "").strip()
    kind = str(case.get("kind") or "").strip()
    if source == "coverage" or kind.startswith("coverage_"):
        markers.append("@pytest.mark.coverage")
    if kind == "page_coverage":
        markers.append("@pytest.mark.page_coverage")
    return markers
def _select_validated_cases(
    workspace_root: Path,
    candidate_pool: list[dict[str, str]],
    target_count: int,
) -> list[dict[str, str]]:
    prioritized = _prioritize_cases(candidate_pool)
    validated: list[dict[str, str]] = []
    selected_keys: set[tuple[str, str, str]] = set()

    network_candidates = [case for case in prioritized if case.get("source") == "network"]
    other_candidates = [
        case for case in prioritized
        if case.get("source") != "network"
    ]

    network_quota = 0
    if network_candidates:
        network_quota = max(1, min(6, math.ceil(target_count * 0.2)))

    validated.extend(_validate_into(workspace_root, network_candidates, network_quota, selected_keys))
    if len(validated) < target_count:
        validated.extend(_validate_into(workspace_root, other_candidates, target_count - len(validated), selected_keys))
    if len(validated) < target_count:
        validated.extend(_validate_into(workspace_root, network_candidates, target_count - len(validated), selected_keys))

    return validated[:target_count]
def _select_cases_without_validation(
    candidate_pool: list[dict[str, str]],
    target_count: int,
) -> list[dict[str, str]]:
    prioritized = _prioritize_cases(candidate_pool)
    selected: list[dict[str, str]] = []
    selected_keys: set[tuple[str, str, str]] = set()
    covered_pages: set[int] = set()

    rq_candidates = [c for c in prioritized if c.get("kind") == "retrieval_quality"]
    aq_candidates = [c for c in prioritized if c.get("kind") == "answer_quality"]
    other_candidates = [c for c in prioritized if c.get("kind") not in {"retrieval_quality", "answer_quality"}]

    rq_quota = max(5, math.ceil(target_count * 0.3)) if rq_candidates else 0
    aq_quota = max(3, math.ceil(target_count * 0.1)) if aq_candidates else 0

    for case in rq_candidates[:rq_quota]:
        key = (case.get("query", ""), _normalize_compare(case.get("must_include", "")), case.get("assert_mode", ""))
        if key in selected_keys:
            continue
        selected.append(case)
        selected_keys.add(key)

    for case in aq_candidates[:aq_quota]:
        if len(selected) >= target_count:
            break
        key = (case.get("query", ""), _normalize_compare(case.get("must_include", "")), case.get("assert_mode", ""))
        if key in selected_keys:
            continue
        selected.append(case)
        selected_keys.add(key)

    for case in other_candidates:
        if len(selected) >= target_count:
            break
        key = (case.get("query", ""), _normalize_compare(case.get("must_include", "")), case.get("assert_mode", ""))
        if key in selected_keys:
            continue
        selected.append(case)
        selected_keys.add(key)

    for case in rq_candidates[rq_quota:]:
        if len(selected) >= target_count:
            break
        key = (case.get("query", ""), _normalize_compare(case.get("must_include", "")), case.get("assert_mode", ""))
        if key in selected_keys:
            continue
        selected.append(case)
        selected_keys.add(key)

    return selected
def _prioritize_cases(candidate_pool: list[dict[str, str]]) -> list[dict[str, str]]:
    prioritized: list[dict[str, str]] = []
    used_pages: set[int] = set()
    remainder: list[dict[str, str]] = []

    for case in candidate_pool:
        page_no = int(case.get("page_no") or 0)
        if case.get("kind") == "page_coverage" and page_no > 0 and page_no not in used_pages:
            prioritized.append(case)
            used_pages.add(page_no)
        else:
            remainder.append(case)

    remainder.sort(key=_case_priority)
    for case in remainder:
        page_no = int(case.get("page_no") or 0)
        if page_no > 0 and page_no not in used_pages:
            prioritized.append(case)
            used_pages.add(page_no)
        else:
            prioritized.append(case)
    return prioritized
def _case_priority(case: dict[str, str]) -> tuple[int, int]:
    kind = str(case.get("kind", ""))
    page_no = int(case.get("page_no") or 0)
    if kind == "page_coverage":
        rank = 0
    elif kind == "retrieval_quality":
        rank = 1
    elif kind in {"evidence", "definition", "definition_detail", "network_scope"}:
        rank = 2
    elif kind in {"standard", "publication_date", "effective_date", "network_standard", "network_publication_date", "network_effective_date"}:
        rank = 3
    elif kind in {"section", "keyword_evidence", "keyword_term"}:
        rank = 4
    else:
        rank = 5
    return (rank, page_no or 10_000)
