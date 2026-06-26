from __future__ import annotations

from pathlib import Path

from .config import AppPaths
from .logging_config import get_logger

_logger = get_logger(__name__)
from .db import connect
from .answer_utils import _safe_json
from .answer_query_parsing import _normalize_standard_code, _extract_standard_from_query, _normalize_query_phrase


"""Document selection, context restriction, and hit routing for answer generation."""


def _choose_primary_doc_id(workspace_root: Path, query: str, context: dict[str, object], intent: str) -> str | None:
    documents = context.get("documents", [])
    if not documents:
        _logger.info("no documents in context for query=%r intent=%r; no primary doc will be chosen", query[:80], intent)
        return None

    if intent == "standard":
        normalized_query = _normalize_standard_code(_extract_standard_from_query(query))
        paths = AppPaths.from_root(workspace_root)
        connection = connect(paths.db_file)
        try:
            rows = connection.execute(
                """
                SELECT source_doc_id, object_value
                FROM facts
                WHERE fact_type = 'document_standard'
                """
            ).fetchall()
            for row in rows:
                payload = _safe_json(row["object_value"])
                if isinstance(payload, dict):
                    value = _normalize_standard_code(str(payload.get("value", "")))
                    if value and value == normalized_query:
                        return row["source_doc_id"]
            rows = connection.execute(
                """
                SELECT json_extract(source_doc_ids_json, '$[0]') AS doc_id, title
                FROM wiki_pages
                WHERE page_type = 'standard'
                """
            ).fetchall()
            for row in rows:
                if _normalize_standard_code(str(row["title"])) == normalized_query:
                    return row["doc_id"]
        finally:
            connection.close()

    judged_doc_id = _choose_doc_from_evidence_judgement(context)
    if judged_doc_id:
        return judged_doc_id

    routed_doc_id = _choose_doc_from_routed_hits(context)
    if routed_doc_id:
        return routed_doc_id

    normalized_phrase = _normalize_query_phrase(query)
    if normalized_phrase:
        best_doc_id = _choose_doc_by_phrase_match(workspace_root, normalized_phrase, intent)
        if best_doc_id:
            return best_doc_id

    return documents[0]["doc_id"]


def _choose_doc_from_evidence_judgement(context: dict[str, object]) -> str | None:
    judgement = context.get("evidence_judgement")
    if not isinstance(judgement, dict) or not judgement.get("sufficient"):
        return None

    best_fact_ids = [str(item).strip() for item in judgement.get("best_fact_ids") or [] if str(item).strip()]
    if not best_fact_ids:
        # Sprint 3: when the judge is sufficient but only returned best_evidence_ids
        # (no best_fact_ids), fall back to deriving the primary doc from the
        # evidence documents. Previously this returned None, causing doc selection
        # to fall through to a wrong doc and _restrict_context_to_doc to empty
        # all hits -> 'not found' despite sufficient=True with real evidence.
        # Only triggers on the currently-broken path; happy path (best_fact_ids
        # present) is unaffected. Evidence-driven, no LLM, no main-path rewrite.
        best_evidence_ids = [str(item).strip() for item in judgement.get("best_evidence_ids") or [] if str(item).strip()]
        if not best_evidence_ids:
            _logger.info("no best_fact_ids and no best_evidence_ids in judgement; primary doc will fall through")
            return None
        evidence_docs: dict[str, str] = {}
        for evidence in context.get("evidence", []):
            if not isinstance(evidence, dict):
                continue
            ev_id = str(evidence.get("evidence_id") or evidence.get("result_id") or "").strip()
            doc_id = str(evidence.get("doc_id") or evidence.get("source_doc_id") or "").strip()
            if ev_id and doc_id:
                evidence_docs[ev_id] = doc_id
        for hit in context.get("hits", []):
            if not isinstance(hit, dict) or hit.get("result_type") != "evidence":
                continue
            ev_id = str(hit.get("result_id") or "").strip()
            doc_id = str(hit.get("doc_id") or "").strip()
            if ev_id and doc_id:
                evidence_docs.setdefault(ev_id, doc_id)
        doc_votes: dict[str, int] = {}
        for ev_id in best_evidence_ids:
            doc_id = evidence_docs.get(ev_id)
            if doc_id:
                doc_votes[doc_id] = doc_votes.get(doc_id, 0) + 1
        if doc_votes:
            chosen = sorted(doc_votes.items(), key=lambda pair: (-pair[1], pair[0]))[0][0]
            _logger.info("primary doc derived from best_evidence_ids: %s (votes=%s)", chosen, doc_votes)
            return chosen
        _logger.info("best_evidence_ids present but no doc mapping found; primary doc will fall through")
        return None

    fact_docs: dict[str, str] = {}
    for fact in context.get("facts", []):
        if not isinstance(fact, dict):
            continue
        fact_id = str(fact.get("fact_id") or "").strip()
        doc_id = str(fact.get("source_doc_id") or "").strip()
        if fact_id and doc_id:
            fact_docs[fact_id] = doc_id
    for hit in context.get("hits", []):
        if not isinstance(hit, dict) or hit.get("result_type") != "fact":
            continue
        fact_id = str(hit.get("result_id") or "").strip()
        doc_id = str(hit.get("doc_id") or "").strip()
        if fact_id and doc_id:
            fact_docs.setdefault(fact_id, doc_id)

    for fact_id in best_fact_ids:
        doc_id = fact_docs.get(fact_id)
        if doc_id:
            return doc_id
    return None


def _choose_doc_from_routed_hits(context: dict[str, object]) -> str | None:
    routed_hits = _query_specific_doc_hits(context)
    if not routed_hits:
        routed_hits = [
            item for item in context.get("graph_candidates", [])
            if str(item.get("doc_id") or "").strip()
        ]
    if not routed_hits:
        return None

    doc_scores: dict[str, tuple[int, float]] = {}
    for index, item in enumerate(routed_hits[:10]):
        doc_id = str(item.get("doc_id") or "").strip()
        if not doc_id:
            continue
        count, score = doc_scores.get(doc_id, (0, 0.0))
        rank_bonus = max(0.0, 1.0 - index * 0.05)
        doc_scores[doc_id] = (count + 1, score + float(item.get("score") or 0.0) + rank_bonus)
    if not doc_scores:
        return None
    return sorted(doc_scores.items(), key=lambda pair: (-pair[1][0], -pair[1][1], pair[0]))[0][0]


def _query_specific_doc_hits(context: dict[str, object]) -> list[dict[str, object]]:
    hits = [
        item for item in context.get("hits", [])[:10]
        if isinstance(item, dict) and str(item.get("doc_id") or "").strip()
    ]
    direct_hits = [
        item for item in hits
        if item.get("channel") == "routing_summary"
        or "routing_summary" in {str(channel) for channel in item.get("channels", [])}
    ]
    if direct_hits:
        return direct_hits
    return [
        item for item in hits
        if item.get("channel") == "graph"
        or "graph" in {str(channel) for channel in item.get("channels", [])}
    ]


def _restrict_context_to_doc(workspace_root: Path, context: dict[str, object], doc_id: str) -> dict[str, object]:
    filtered = dict(context)
    documents = [item for item in context.get("documents", []) if item.get("doc_id") == doc_id]
    if not documents:
        filtered["documents"] = [_load_document_record(workspace_root, doc_id)]
    else:
        filtered["documents"] = documents
    filtered["hits"] = [item for item in context.get("hits", []) if item.get("doc_id") == doc_id]
    filtered["evidence"] = [item for item in context.get("evidence", []) if item.get("doc_id") == doc_id]
    filtered["facts"] = [item for item in context.get("facts", []) if item.get("source_doc_id") == doc_id]
    filtered["wiki_pages"] = [
        item for item in context.get("wiki_pages", [])
        if item.get("page_id") in {hit["result_id"] for hit in filtered["hits"] if hit.get("result_type") == "wiki"}
        or item.get("entity_id") in {
            fact.get("subject_entity_id") for fact in filtered["facts"] if fact.get("subject_entity_id")
        } | {
            fact.get("object_entity_id") for fact in filtered["facts"] if fact.get("object_entity_id")
        }
    ]
    filtered["entities"] = [
        item for item in context.get("entities", [])
        if item.get("entity_id") in {
            fact.get("subject_entity_id") for fact in filtered["facts"] if fact.get("subject_entity_id")
        } | {
            fact.get("object_entity_id") for fact in filtered["facts"] if fact.get("object_entity_id")
        }
    ]
    filtered["graph_edges"] = [
        item for item in context.get("graph_edges", [])
        if item.get("version_scope") == doc_id
    ]
    filtered["topic_objects"] = [
        item for item in context.get("topic_objects", [])
        if item.get("page_id") in {wiki.get("page_id") for wiki in filtered["wiki_pages"]}
        or str(item.get("page_id") or "").startswith(f"WCONTOP-{doc_id}-")
        or str(item.get("page_id") or "").startswith(f"WCON-{doc_id}-")
        or str(item.get("page_id") or "").startswith(f"WCMP-{doc_id}-")
        or str(item.get("page_id") or "").startswith(f"WPROC-{doc_id}-")
        or str(item.get("page_id") or "").startswith(f"WPAR-{doc_id}-")
    ]
    filtered["knowledge_subgraph"] = {
        **dict(context.get("knowledge_subgraph") or {}),
        "seed_wiki_page_ids": [item.get("page_id") for item in filtered["wiki_pages"][:8] if item.get("page_id")],
        "seed_entity_ids": sorted({
            *(item.get("entity_id") for item in filtered["entities"] if item.get("entity_id")),
        })[:20],
        "seed_fact_ids": [item.get("fact_id") for item in filtered["facts"][:80] if item.get("fact_id")],
        "seed_edge_ids": [item.get("edge_id") for item in filtered["graph_edges"][:80] if item.get("edge_id")],
        "wiki_page_types": sorted({
            str(item.get("page_type") or "").strip()
            for item in filtered["wiki_pages"]
            if str(item.get("page_type") or "").strip()
        }),
        "topic_object_ids": [item.get("page_id") for item in filtered["topic_objects"][:8] if item.get("page_id")],
        "fact_count": len(filtered["facts"]),
        "edge_count": len(filtered["graph_edges"]),
        "wiki_count": len(filtered["wiki_pages"]),
        "topic_count": len(filtered["topic_objects"]),
    }
    filtered["hit_count"] = len(filtered["hits"])
    return filtered


def _load_document_record(workspace_root: Path, doc_id: str) -> dict[str, object]:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        row = connection.execute(
            """
            SELECT doc_id, source_filename, source_type, page_count, parse_status, quality_status
            FROM documents
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
        return dict(row) if row else {"doc_id": doc_id}
    finally:
        connection.close()


def _choose_doc_by_phrase_match(workspace_root: Path, normalized_phrase: str, intent: str) -> str | None:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        scores: dict[str, float] = {}

        def bump(doc_id: str | None, score: float) -> None:
            if doc_id:
                scores[doc_id] = scores.get(doc_id, 0.0) + score

        fact_rows = connection.execute(
            """
            SELECT source_doc_id, fact_type, object_value
            FROM facts
            WHERE fact_type IN (
                'term_definition',
                'concept_definition',
                'document_title',
                'document_standard',
                'requirement',
                'table_requirement',
                'threshold'
            )
            """
        ).fetchall()
        for row in fact_rows:
            payload = _safe_json(row["object_value"])
            text_parts: list[str] = []
            if isinstance(payload, dict):
                text_parts.extend(str(value) for value in payload.values())
            elif payload:
                text_parts.append(str(payload))
            haystack = " ".join(text_parts)
            if normalized_phrase and normalized_phrase in haystack:
                weight = 4.0 if row["fact_type"] in {"term_definition", "concept_definition"} else 2.5
                if row["fact_type"] == "requirement":
                    weight = 4.2
                elif row["fact_type"] == "threshold":
                    weight = 4.0
                elif row["fact_type"] == "table_requirement":
                    weight = 4.1
                if intent == "definition" and row["fact_type"] in {"term_definition", "concept_definition"}:
                    weight += 2.0
                bump(row["source_doc_id"], weight)

        wiki_rows = connection.execute(
            """
            SELECT json_extract(source_doc_ids_json, '$[0]') AS doc_id, title, slug, page_type
            FROM wiki_pages
            """
        ).fetchall()
        for row in wiki_rows:
            haystack = f"{row['title']} {row['slug']}"
            if normalized_phrase and normalized_phrase in haystack:
                weight = 3.0 if row["page_type"] == "term" else 1.5
                bump(row["doc_id"], weight)

        evidence_rows = connection.execute(
            """
            SELECT doc_id, normalized_text
            FROM evidence
            WHERE normalized_text LIKE ?
            LIMIT 20
            """,
            (f"%{normalized_phrase}%",),
        ).fetchall()
        for row in evidence_rows:
            bump(row["doc_id"], 1.0)

        if not scores:
            return None
        return max(scores.items(), key=lambda item: item[1])[0]
    finally:
        connection.close()
