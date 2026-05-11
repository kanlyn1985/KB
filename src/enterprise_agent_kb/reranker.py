from __future__ import annotations

import json
import re
from pathlib import Path

from .config import AppPaths
from .db import connect
from .query_rewrite import RewrittenQuery


def rerank_candidates(
    workspace_root: Path,
    rewritten: RewrittenQuery,
    candidates: list[dict[str, object]],
    limit: int = 20,
    connection=None,
) -> list[dict[str, object]]:
    own_connection = connection is None
    paths = AppPaths.from_root(workspace_root)
    if own_connection:
        connection = connect(paths.db_file)

    try:
        reranked: list[dict[str, object]] = []
        for candidate in candidates:
            rescored = dict(candidate)
            rescored["rerank"] = _score_candidate(connection, rewritten, candidate)
            rescored["score"] = rescored["rerank"]["final_score"]
            reranked.append(rescored)
        reranked.sort(key=lambda item: float(item["score"] or 0), reverse=True)
        return reranked[:limit]
    finally:
        if own_connection:
            connection.close()


def _score_candidate(connection, rewritten: RewrittenQuery, candidate: dict[str, object]) -> dict[str, object]:
    base_score = float(candidate.get("score") or 0.0)
    snippet = str(candidate.get("snippet", ""))
    result_type = str(candidate.get("result_type", ""))
    doc_id = str(candidate.get("doc_id", "") or "")

    lexical_score = _lexical_score(rewritten, snippet)
    exact_match_bonus = _exact_match_bonus(rewritten, snippet)
    standard_match_bonus = _standard_match_bonus(rewritten, snippet)
    term_match_bonus = _term_match_bonus(rewritten, snippet)
    object_anchor_bonus, object_anchor_penalty = _object_anchor_adjustment(connection, rewritten, candidate, snippet)
    type_bonus = _type_bonus(rewritten.query_type, result_type)
    subtype_bonus = _subtype_bonus(connection, rewritten, candidate)
    title_bonus = _document_title_bonus(connection, doc_id, rewritten)
    quality_bonus, risk_penalty = _quality_adjustment(connection, doc_id)
    routing_bonus = float(candidate.get("routing_priority") or 0.0) * 0.08

    final_score = round(
        base_score
        + lexical_score
        + exact_match_bonus
        + standard_match_bonus
        + term_match_bonus
        + object_anchor_bonus
        + type_bonus
        + subtype_bonus
        + title_bonus
        + routing_bonus
        + quality_bonus
        - risk_penalty
        - object_anchor_penalty,
        6,
    )
    return {
        "base_score": round(base_score, 6),
        "lexical_score": round(lexical_score, 6),
        "exact_match_bonus": round(exact_match_bonus, 6),
        "standard_match_bonus": round(standard_match_bonus, 6),
        "term_match_bonus": round(term_match_bonus, 6),
        "object_anchor_bonus": round(object_anchor_bonus, 6),
        "object_anchor_penalty": round(object_anchor_penalty, 6),
        "query_type_alignment_bonus": round(type_bonus, 6),
        "subtype_bonus": round(subtype_bonus, 6),
        "document_title_bonus": round(title_bonus, 6),
        "routing_bonus": round(routing_bonus, 6),
        "quality_bonus": round(quality_bonus, 6),
        "risk_penalty": round(risk_penalty, 6),
        "final_score": final_score,
    }


def _lexical_score(rewritten: RewrittenQuery, snippet: str) -> float:
    haystack = _norm(snippet)
    score = 0.0
    for term in [*rewritten.must_terms, *rewritten.should_terms]:
        normalized = _norm(term)
        if normalized and normalized in haystack:
            score += 0.08 if term in rewritten.must_terms else 0.04
    return score


def _exact_match_bonus(rewritten: RewrittenQuery, snippet: str) -> float:
    haystack = _norm(snippet)
    if rewritten.normalized_query and _norm(rewritten.normalized_query) in haystack:
        return 0.18
    return 0.0


def _standard_match_bonus(rewritten: RewrittenQuery, snippet: str) -> float:
    if rewritten.query_type not in {"standard_lookup", "lifecycle_lookup"}:
        return 0.0
    haystack = _norm(snippet)
    if any(_norm(term) in haystack for term in rewritten.must_terms):
        return 0.22
    return 0.0


def _term_match_bonus(rewritten: RewrittenQuery, snippet: str) -> float:
    if rewritten.query_type != "definition":
        return 0.0
    haystack = _norm(snippet)
    if rewritten.normalized_query and _norm(rewritten.normalized_query) in haystack:
        return 0.2
    return 0.0


def _type_bonus(query_type: str, result_type: str) -> float:
    matrix = {
        "definition": {"fact": 0.24, "wiki": 0.16, "evidence": 0.08, "document": 0.03},
        "standard_lookup": {"document": 0.24, "fact": 0.2, "wiki": 0.16, "evidence": 0.06},
        "lifecycle_lookup": {"document": 0.24, "fact": 0.2, "wiki": 0.14, "evidence": 0.06},
        "timing_lookup": {"fact": 0.26, "evidence": 0.2, "document": 0.06, "wiki": 0.04},
        "test_method_lookup": {"fact": 0.34, "evidence": 0.22, "wiki": 0.05, "document": -0.08},
        "parameter_lookup": {"fact": 0.28, "evidence": 0.18, "wiki": 0.06, "document": -0.08},
        "section_lookup": {"fact": 0.22, "evidence": 0.16, "document": 0.14, "wiki": 0.04},
        "scope": {"evidence": 0.18, "fact": 0.12, "document": 0.1, "wiki": 0.05},
        "constraint": {"fact": 0.16, "evidence": 0.14, "document": 0.08, "wiki": 0.04},
        "general_search": {"evidence": 0.14, "fact": 0.1, "wiki": 0.08, "document": 0.05},
    }
    return matrix.get(query_type, {}).get(result_type, 0.0)


def _subtype_bonus(connection, rewritten: RewrittenQuery, candidate: dict[str, object]) -> float:
    if rewritten.query_type not in {"definition", "lifecycle_lookup", "timing_lookup", "test_method_lookup", "parameter_lookup"}:
        return 0.0

    result_type = str(candidate.get("result_type", "") or "")
    result_id = str(candidate.get("result_id", "") or "")
    target = _norm(str(rewritten.target_topic or rewritten.normalized_query or ""))

    if result_type == "fact" and result_id:
        row = connection.execute(
            """
            SELECT fact_type, object_value
            FROM facts
            WHERE fact_id = ?
            """,
            (result_id,),
        ).fetchone()
        if row is None:
            return 0.0
        fact_type = str(row["fact_type"] or "")
        payload = str(row["object_value"] or "")
        payload_blob = _norm(payload)
        if rewritten.query_type == "parameter_lookup":
            return _parameter_subtype_bonus(rewritten, fact_type, payload)
        if rewritten.query_type in {"lifecycle_lookup", "timing_lookup"}:
            if fact_type == "process_fact":
                if rewritten.query_type == "lifecycle_lookup" and not re.search(
                    r"\b(?:SYS|SWE|SUP|MAN|HWE|VAL|REU|PIM)\.\d+\.BP\d+\b",
                    str(row["object_value"] or ""),
                    re.I,
                ):
                    return -0.18
                return 0.55
            if fact_type == "table_requirement":
                return 0.3 if _process_target_matches(target, payload_blob) else 0.05
            if fact_type == "section_heading":
                return 0.22 if _process_target_matches(target, payload_blob) else -0.12
            if fact_type == "transition_fact":
                return 0.35 if rewritten.query_type == "timing_lookup" else -0.12
        if rewritten.query_type == "test_method_lookup":
            if fact_type == "process_fact":
                bonus = 0.35
                if _looks_like_test_method_blob(str(row["object_value"] or "")):
                    bonus += 0.65
                if _test_target_matches(rewritten, str(row["object_value"] or "")):
                    bonus += 0.45
                return bonus
            if fact_type in {"requirement", "threshold", "table_requirement"}:
                return -0.08
            if fact_type == "section_heading":
                return 0.08
        if fact_type in {"term_definition", "concept_definition"}:
            return 0.45
        if fact_type == "document_abstract":
            return 0.18
        if fact_type == "section_heading":
            title_exact = bool(target) and (
                f'"title":"{target}"' in payload_blob
                or f'"title":"{target}"' in payload_blob
            )
            return 0.12 if title_exact else -0.24
        if fact_type in {"requirement", "threshold", "table_requirement", "parameter_value", "process_fact", "transition_fact"}:
            return -0.28
        return 0.0

    if result_type == "wiki" and result_id:
        row = connection.execute(
            """
            SELECT page_type, title
            FROM wiki_pages
            WHERE page_id = ?
            """,
            (result_id,),
        ).fetchone()
        if row is None:
            return 0.0
        page_type = str(row["page_type"] or "")
        title_blob = _norm(str(row["title"] or ""))
        if page_type in {"term", "concept"}:
            return 0.28
        if page_type == "document":
            return 0.08
        if page_type in {"parameter_group", "process", "constraint", "comparison"}:
            return -0.08 if target and target in title_blob else -0.24
    return 0.0


def _parameter_subtype_bonus(rewritten: RewrittenQuery, fact_type: str, payload: str) -> float:
    normalized_payload = _norm(payload)
    if not normalized_payload:
        return 0.0
    requested_tables = _requested_table_numbers(rewritten)
    payload_tables = _table_numbers(payload)
    table_match = bool(requested_tables and payload_tables and requested_tables & payload_tables)
    table_mismatch = bool(requested_tables and payload_tables and not requested_tables & payload_tables)
    parameter_terms = _parameter_anchor_terms(rewritten)
    matched_terms = [term for term in parameter_terms if _norm(term) in normalized_payload]
    field_matches = _parameter_field_matches(rewritten, payload)

    bonus = 0.0
    if fact_type == "parameter_value":
        bonus += 0.38
        if table_match:
            bonus += 0.95
        if table_mismatch:
            bonus -= 1.05
        if field_matches["parameter"]:
            bonus += 1.15
        if field_matches["symbol"]:
            bonus += 1.05
        if field_matches["row_focus"]:
            bonus += 0.45
        if field_matches["object"]:
            bonus += 0.45
        if field_matches["table_focus"]:
            bonus += 0.12
        if matched_terms and not any(field_matches[key] for key in ("parameter", "symbol", "row_focus")):
            bonus += min(0.35, 0.12 * len(matched_terms))
        if requested_tables and (field_matches["object"] or field_matches["table_focus"]) and not any(
            field_matches[key] for key in ("parameter", "symbol", "row_focus")
        ):
            bonus -= 0.18
        return bonus
    if fact_type == "table_requirement":
        if table_match:
            bonus += 0.55
        if matched_terms:
            bonus += min(0.5, 0.18 * len(matched_terms))
        if table_mismatch:
            bonus -= 0.85
        return bonus
    if fact_type in {"term_definition", "concept_definition"}:
        return 0.08 if matched_terms else -0.12
    if fact_type in {"process_fact", "transition_fact", "section_heading"}:
        return -0.18
    return 0.0


def _parameter_anchor_terms(rewritten: RewrittenQuery) -> list[str]:
    values = [
        rewritten.original_query,
        rewritten.normalized_query,
        rewritten.target_topic,
        *rewritten.must_terms,
        *rewritten.protected_anchor_terms,
    ]
    text = " ".join(str(item or "") for item in values)
    terms: list[str] = []
    for match in re.finditer(r"表\s*[A-Z]\s*[.．]\s*\d+", text, re.I):
        _append_parameter_anchor_term(terms, match.group(0))
    for term in re.findall(r"[A-Za-z][A-Za-z0-9+'/-]{1,10}", text):
        _append_parameter_anchor_term(terms, term)
    cleaned_text = re.sub(r"(?:GB|GBT|GB/T|ISO|IEC|QC|QC/T)[/—\-\s]*\d+(?:\.\d+)?(?:—\d{4})?", " ", text, flags=re.I)
    cleaned_text = re.sub(r"表\s*[A-Z]\s*[.．]\s*\d+|表\s*\d+", " ", cleaned_text, flags=re.I)
    cleaned_text = re.sub(
        r"(有哪些定义|定义有哪些|参数有哪些|参数是什么|哪些参数|参数值|是什么意思|是什么|代表什么|表示什么|指什么|含义|如何理解|怎么理解|[？?])",
        " ",
        cleaned_text,
    )
    cleaned_text = cleaned_text.replace("的参数", " ").replace("参数", " ")
    for chunk in re.split(r"[\s,，;；:：/|]+", cleaned_text):
        chunk = chunk.strip()
        if not chunk or not re.search(r"[\u4e00-\u9fff]", chunk):
            continue
        for part in re.split(r"的|和|与", chunk):
            part = part.strip()
            if not part:
                continue
            _append_parameter_anchor_term(terms, part)
            if len(part) > 2:
                for size in range(2, min(6, len(part)) + 1):
                    _append_parameter_anchor_term(terms, part[-size:])
    return terms[:12]


def _append_parameter_anchor_term(terms: list[str], term: str) -> None:
    cleaned = str(term or "").strip()
    if not cleaned or cleaned in terms:
        return
    if _is_generic_parameter_anchor(cleaned):
        return
    terms.append(cleaned)


def _is_generic_parameter_anchor(term: str) -> bool:
    normalized = _norm(term)
    return normalized in {
        "参数",
        "定义",
        "是什么",
        "什么意思",
        "控制导引",
        "控制导引电路",
        "电路",
        "表",
        "table",
    }


def _parameter_field_matches(rewritten: RewrittenQuery, payload: str) -> dict[str, bool]:
    data = _safe_json_object(payload)
    query_text = " ".join(
        str(item or "")
        for item in [
            rewritten.original_query,
            rewritten.normalized_query,
            rewritten.target_topic,
            *rewritten.must_terms,
            *rewritten.protected_anchor_terms,
        ]
    )
    query_norm = _norm(query_text)
    query_upper = query_text.upper()
    if not isinstance(data, dict):
        return {"parameter": False, "symbol": False, "object": False, "row_focus": False, "table_focus": False}
    parameter = _clean_parameter_field(data.get("parameter"))
    symbol = _clean_parameter_field(data.get("symbol"))
    object_name = _clean_parameter_field(data.get("object"))
    return {
        "parameter": _query_contains_field(query_norm, parameter),
        "symbol": _query_contains_symbol(query_text, symbol),
        "object": _query_contains_field(query_norm, object_name),
        "row_focus": _query_contains_any_tag(query_norm, query_upper, data.get("row_focus_tags") or data.get("focus_tags") or []),
        "table_focus": _query_contains_any_tag(query_norm, query_upper, data.get("table_focus_tags") or []),
    }


def _safe_json_object(value: str) -> dict[str, object] | None:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _clean_parameter_field(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\^[A-Za-z0-9]+", "", text)
    text = re.sub(r"[（(][^)）]*[)）]", "", text)
    text = text.strip(" *:：;；,，")
    return text


def _query_contains_field(query_norm: str, value: str) -> bool:
    if not value or _is_generic_parameter_anchor(value):
        return False
    normalized = _norm(value)
    if not normalized:
        return False
    if re.fullmatch(r"[a-z0-9+\-/'_.]{1,2}", normalized, re.I):
        return False
    return normalized in query_norm


def _query_contains_symbol(query_text: str, symbol: str) -> bool:
    if not symbol:
        return False
    if len(symbol) < 2:
        return False
    return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(symbol)}(?![A-Za-z0-9])", query_text, re.I))


def _query_contains_any_tag(query_norm: str, query_upper: str, tags: list[object]) -> bool:
    for tag in tags:
        text = _clean_parameter_field(tag)
        if not text or _is_generic_parameter_anchor(text):
            continue
        upper = text.upper()
        if upper in {"CP", "CC", "PE", "PWM"} and re.search(rf"(?<![A-Z0-9]){re.escape(upper)}(?![A-Z0-9])", query_upper):
            return True
        if re.fullmatch(r"CC\d", upper) and re.search(r"(?<![A-Z0-9])CC(?![A-Z0-9])", query_upper):
            return True
        normalized = _norm(text)
        if len(normalized) > 1 and normalized in query_norm:
            return True
    return False


def _requested_table_numbers(rewritten: RewrittenQuery) -> set[str]:
    values = [
        rewritten.original_query,
        rewritten.normalized_query,
        rewritten.target_topic,
        *rewritten.must_terms,
        *rewritten.should_terms,
        *rewritten.aliases,
    ]
    return _table_numbers(" ".join(str(item or "") for item in values))


def _table_numbers(value: str) -> set[str]:
    return {
        f"{match.group(1).upper()}.{match.group(2)}"
        for match in re.finditer(r"表\s*([A-Z])\s*[.．]\s*(\d+)", str(value or ""), re.I)
    }


def _object_anchor_adjustment(connection, rewritten: RewrittenQuery, candidate: dict[str, object], snippet: str) -> tuple[float, float]:
    positives, negatives = _object_anchor_terms(rewritten)
    if not positives and not negatives:
        return (0.0, 0.0)
    doc_id = str(candidate.get("doc_id") or "")
    filename = ""
    if doc_id:
        row = connection.execute("SELECT source_filename FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
        if row is not None:
            filename = str(row["source_filename"] or "")
    haystack = _norm(f"{snippet} {filename}")
    bonus = 0.0
    penalty = 0.0
    if positives and any(_norm(term) in haystack for term in positives):
        bonus += 1.0
    if negatives and any(_norm(term) in haystack for term in negatives) and not any(_norm(term) in haystack for term in positives):
        penalty += 1.35
    return (bonus, penalty)


def _object_anchor_terms(rewritten: RewrittenQuery) -> tuple[list[str], list[str]]:
    text = " ".join(
        str(item or "")
        for item in [
            rewritten.original_query,
            rewritten.normalized_query,
            rewritten.target_topic,
            *rewritten.must_terms,
            *rewritten.protected_anchor_terms,
        ]
    )
    if re.search(r"\bOBC\b|车载充电机|on-?board charger", text, re.I):
        return (
            ["OBC", "车载充电机", "电动汽车用传导式车载充电机", "on-board charger", "onboard charger"],
            [] if "逆变器" in text else ["汽车电源逆变器", "逆变器"],
        )
    return ([], [])


def _looks_like_test_method_blob(blob: str) -> bool:
    normalized = _norm(blob)
    return (
        ("试验" in normalized or "测试" in normalized or "测量" in normalized or "检测" in normalized)
        and any(token in normalized for token in ("试验方法及步骤", "按照图", "接好试验电路", "调节", "测量", "观察"))
    )


def _test_target_matches(rewritten: RewrittenQuery, blob: str) -> bool:
    normalized = _norm(blob)
    terms = [rewritten.normalized_query, rewritten.target_topic, *rewritten.must_terms, *rewritten.should_terms, *rewritten.aliases]
    variants: list[str] = []
    for term in terms:
        text = str(term or "").strip()
        if not text:
            continue
        variants.append(text)
        if "输入过压" in text:
            variants.extend(["输入过、欠压", "交流输入过、欠压", "过压保护试验"])
    return any(_norm(term) in normalized for term in variants)


def _process_target_matches(target: str, payload_blob: str) -> bool:
    if not target:
        return False
    variants = {
        target,
        target.replace("测试", "验证"),
        target.replace("验证", "测试"),
        target.replace("过程域", ""),
        target.replace("过程", ""),
    }
    variants |= {
        item.replace("集成测试", "集成").replace("集成验证", "集成")
        for item in list(variants)
    }
    return any(item and item in payload_blob for item in variants)


def _document_title_bonus(connection, doc_id: str, rewritten: RewrittenQuery) -> float:
    if not doc_id:
        return 0.0
    row = connection.execute(
        """
        SELECT source_filename
        FROM documents
        WHERE doc_id = ?
        """,
        (doc_id,),
    ).fetchone()
    if row is None:
        return 0.0
    filename = _norm(str(row["source_filename"]))
    if rewritten.normalized_query and _norm(rewritten.normalized_query) in filename:
        return 0.12
    if any(_norm(term) in filename for term in rewritten.must_terms):
        return 0.08
    return 0.0


def _quality_adjustment(connection, doc_id: str) -> tuple[float, float]:
    if not doc_id:
        return (0.0, 0.0)
    row = connection.execute(
        """
        SELECT overall_score, high_risk_page_count, blocked_count
        FROM quality_reports
        WHERE doc_id = ?
        """,
        (doc_id,),
    ).fetchone()
    if row is None:
        return (0.0, 0.0)
    quality_bonus = min(float(row["overall_score"] or 0.0) * 0.05, 0.05)
    risk_penalty = min(float(row["high_risk_page_count"] or 0.0) * 0.01 + float(row["blocked_count"] or 0.0) * 0.05, 0.2)
    return (quality_bonus, risk_penalty)


def _norm(value: str) -> str:
    text = value.lower().replace("—", "-").replace("_", "").replace("/", "")
    text = re.sub(r"\s+", "", text)
    return text
