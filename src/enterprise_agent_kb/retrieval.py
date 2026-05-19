from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Iterable

from .config import AppPaths
from .db import connect
from .derived_state import check_derived_state, write_fts_freshness_stamp
from .synonyms import expand_with_synonyms


FTS_TABLES = {
    "evidence": "evidence_fts",
    "facts": "facts_fts",
    "wiki": "wiki_fts",
}


def ensure_fts_schema(connection) -> None:
    connection.executescript(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
            result_id UNINDEXED,
            doc_id UNINDEXED,
            page_no UNINDEXED,
            searchable_text,
            tokenize = 'unicode61'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
            result_id UNINDEXED,
            doc_id UNINDEXED,
            page_no UNINDEXED,
            searchable_text,
            tokenize = 'unicode61'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts USING fts5(
            result_id UNINDEXED,
            doc_id UNINDEXED,
            page_no UNINDEXED,
            searchable_text,
            tokenize = 'unicode61'
        );
        """
    )
    connection.commit()


def refresh_fts_index(workspace_root: Path) -> dict[str, int]:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        return _refresh_fts_index(connection, paths)
    finally:
        connection.close()


def _refresh_fts_index(connection, paths: AppPaths) -> dict[str, int]:
    ensure_fts_schema(connection)
    connection.execute("DELETE FROM evidence_fts")
    connection.execute("DELETE FROM facts_fts")
    connection.execute("DELETE FROM wiki_fts")

    evidence_rows = connection.execute(
        """
        SELECT evidence_id, doc_id, page_no, normalized_text
        FROM evidence
        """
    ).fetchall()
    for row in evidence_rows:
        searchable = _build_searchable_text(str(row["normalized_text"] or ""))
        connection.execute(
            """
            INSERT INTO evidence_fts(result_id, doc_id, page_no, searchable_text)
            VALUES (?, ?, ?, ?)
            """,
            (row["evidence_id"], row["doc_id"], row["page_no"], searchable),
        )

    fact_rows = connection.execute(
        """
        SELECT fact_id, source_doc_id, json_extract(qualifiers_json, '$.page_no') AS page_no,
               predicate, object_value
        FROM facts
        """
    ).fetchall()
    for row in fact_rows:
        searchable = _build_searchable_text(f"{row['predicate']} {row['object_value'] or ''}")
        connection.execute(
            """
            INSERT INTO facts_fts(result_id, doc_id, page_no, searchable_text)
            VALUES (?, ?, ?, ?)
            """,
            (row["fact_id"], row["source_doc_id"], row["page_no"], searchable),
        )

    wiki_rows = connection.execute(
        """
        SELECT w.page_id, json_extract(w.source_doc_ids_json, '$[0]') AS doc_id, w.title, w.slug
        FROM wiki_pages w
        LEFT JOIN entities e ON e.entity_id = w.entity_id
        WHERE COALESCE(w.trust_status, '') != 'stale'
          AND (w.entity_id IS NULL OR e.entity_status = 'ready')
        """
    ).fetchall()
    for row in wiki_rows:
        searchable = _build_searchable_text(f"{row['title']} {row['slug']}")
        connection.execute(
            """
            INSERT INTO wiki_fts(result_id, doc_id, page_no, searchable_text)
            VALUES (?, ?, ?, ?)
            """,
            (row["page_id"], row["doc_id"], None, searchable),
        )

    connection.commit()
    write_fts_freshness_stamp(paths, connection)
    return {
        "evidence": len(evidence_rows),
        "facts": len(fact_rows),
        "wiki": len(wiki_rows),
    }


def search_knowledge_base(
    workspace_root: Path,
    query: str,
    limit: int = 10,
) -> list[dict[str, object]]:
    query = query.strip()
    if not query:
        return []

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        return search_knowledge_base_expanded(workspace_root, query, limit=limit, connection=connection)
    finally:
        connection.close()


def search_knowledge_base_expanded(
    workspace_root: Path,
    query: str,
    limit: int = 10,
    connection=None,
    result_types: set[str] | None = None,
) -> list[dict[str, object]]:
    query = query.strip()
    if not query:
        return []

    own_connection = connection is None
    paths = AppPaths.from_root(workspace_root)
    if own_connection:
        connection = connect(paths.db_file)

    try:
        _ensure_fts_ready(paths.root, connection=connection)
        ensure_fts_schema(connection)
        expanded_queries = _expanded_queries(query)
        fts_hits = _search_fts(connection, expanded_queries, limit=max(limit * 4, 20), result_types=result_types)
        semantic_hits = _search_semantic(connection, expanded_queries, limit=max(limit * 4, 20), result_types=result_types)

        merged: dict[tuple[str, str], dict[str, object]] = {}
        for hit in [*fts_hits, *semantic_hits]:
            key = (hit["result_type"], hit["result_id"])
            existing = merged.get(key)
            if existing is None or float(hit["score"]) > float(existing["score"]):
                merged[key] = hit

        results = list(merged.values())
        results.sort(key=lambda item: (float(item["score"]), -int(item["page_no"] or 0)), reverse=True)
        return results[:limit]
    finally:
        if own_connection:
            connection.close()


def _ensure_fts_ready(workspace_root: Path, connection=None) -> None:
    paths = AppPaths.from_root(workspace_root)
    own_connection = connection is None
    if own_connection:
        connection = connect(paths.db_file)
    try:
        checks = check_derived_state(paths.root, connection=connection)
        if any(check.status != "fresh" and check.state_id in FTS_TABLES.values() for check in checks):
            _refresh_fts_index(connection, paths)
    finally:
        if own_connection:
            connection.close()


def _build_searchable_text(text: str) -> str:
    normalized = _normalize_text(text)
    tokens = _tokenize(normalized)
    cjk_ngrams = [*_cjk_ngrams(normalized, n=2), *_cjk_ngrams(normalized, n=3)]
    return " ".join([normalized, *tokens, *cjk_ngrams]).strip()


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9./-]+|[\u4e00-\u9fff]{1,}", text)


def _cjk_ngrams(text: str, n: int = 2) -> list[str]:
    chars = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
    return ["".join(chars[i : i + n]) for i in range(len(chars) - n + 1)]


def _expanded_queries(query: str) -> list[str]:
    variants = [query]
    normalized = _normalize_text(query)
    if normalized and normalized not in variants:
        variants.append(normalized)
    for synonym in expand_with_synonyms(query):
        if synonym not in variants:
            variants.append(synonym)
    return variants[:8]


def _fts_match_expr(query: str) -> str:
    tokens = _tokenize(_normalize_text(query))
    cjk_terms: list[str] = []
    for token in tokens:
        if re.fullmatch(r"[\u4e00-\u9fff]{2,}", token):
            cjk_terms.extend(_cjk_ngrams(token, n=2))
            if len(token) >= 3:
                cjk_terms.extend(_cjk_ngrams(token, n=3))
    tokens = [*tokens, *cjk_terms]
    if not tokens:
        return f'"{query}"'
    return " OR ".join(f'"{token}"' for token in tokens[:8])


def _search_fts(
    connection,
    queries: list[str],
    limit: int,
    result_types: set[str] | None = None,
) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    sources = [
        source
        for source in ("evidence", "facts", "wiki")
        if result_types is None or _source_result_type(source) in result_types
    ]
    for query in queries:
        expr = _fts_match_expr(query)
        for source in sources:
            hits.extend(_search_fts_table(connection, source, expr, limit, seen))
    return hits


def _source_result_type(source: str) -> str:
    return "wiki" if source == "wiki" else source.rstrip("s")


def _search_fts_table(connection, source: str, expr: str, limit: int, seen: set[tuple[str, str]]) -> list[dict[str, object]]:
    table = FTS_TABLES[source]
    rows = connection.execute(
        f"""
        SELECT result_id, doc_id, page_no, bm25({table}) AS rank, searchable_text
        FROM {table}
        WHERE {table} MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (expr, limit),
    ).fetchall()

    hits: list[dict[str, object]] = []
    for row in rows:
        key = (source, row["result_id"])
        if key in seen:
            continue
        seen.add(key)
        score = 1.0 / (1.0 + max(float(row["rank"] or 0), 0.0))
        hits.append(
            {
                "result_type": _source_result_type(source),
                "result_id": row["result_id"],
                "doc_id": row["doc_id"],
                "page_no": row["page_no"],
                "score": round(score, 6),
                "snippet": row["searchable_text"][:1200],
            }
        )
    return hits


def _search_semantic(
    connection,
    queries: list[str],
    limit: int,
    result_types: set[str] | None = None,
) -> list[dict[str, object]]:
    query_vec = _semantic_vector(" ".join(queries))
    candidates = _semantic_candidates(connection, limit=max(limit * 2, 40), result_types=result_types)
    hits: list[dict[str, object]] = []
    for item in candidates:
        score = _cosine_similarity(query_vec, _semantic_vector(item["snippet"]))
        if score <= 0:
            continue
        hits.append(
            {
                "result_type": item["result_type"],
                "result_id": item["result_id"],
                "doc_id": item["doc_id"],
                "page_no": item["page_no"],
                "score": round(score * 0.6, 6),
                "snippet": item["snippet"][:1200],
            }
        )
    hits.sort(key=lambda item: float(item["score"]), reverse=True)
    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for hit in hits:
        key = (hit["result_type"], hit["result_id"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)
        if len(deduped) >= limit:
            break
    return deduped


def _semantic_candidates(connection, limit: int, result_types: set[str] | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if result_types is None or "evidence" in result_types:
        rows.extend(
            dict(row)
            for row in connection.execute(
                """
                SELECT 'evidence' AS result_type, evidence_id AS result_id, doc_id, page_no, normalized_text AS snippet
                FROM evidence
                ORDER BY confidence DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        )
    if result_types is None or "fact" in result_types:
        rows.extend(
            dict(row)
            for row in connection.execute(
                """
                SELECT 'fact' AS result_type, fact_id AS result_id, source_doc_id AS doc_id,
                       json_extract(qualifiers_json, '$.page_no') AS page_no,
                       predicate || ' ' || object_value AS snippet
                FROM facts
                ORDER BY confidence DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        )
    if result_types is None or "wiki" in result_types:
        rows.extend(
            dict(row)
            for row in connection.execute(
                """
                SELECT 'wiki' AS result_type, w.page_id AS result_id,
                       json_extract(w.source_doc_ids_json, '$[0]') AS doc_id,
                       NULL AS page_no,
                       w.title || ' ' || w.slug AS snippet
                FROM wiki_pages w
                LEFT JOIN entities e ON e.entity_id = w.entity_id
                WHERE COALESCE(w.trust_status, '') != 'stale'
                  AND (w.entity_id IS NULL OR e.entity_status = 'ready')
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        )
    return rows


def _semantic_vector(text: str) -> dict[str, float]:
    normalized = _normalize_text(text)
    tokens = _tokenize(normalized)
    grams = [*_cjk_ngrams(normalized, n=2), *_cjk_ngrams(normalized, n=3)]
    features = [*tokens, *grams]
    if not features:
        return {}
    counts: dict[str, float] = {}
    for feature in features:
        counts[feature] = counts.get(feature, 0.0) + 1.0
    norm = math.sqrt(sum(value * value for value in counts.values()))
    if norm == 0:
        return counts
    return {key: value / norm for key, value in counts.items()}


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(key, 0.0) for key, value in left.items())
