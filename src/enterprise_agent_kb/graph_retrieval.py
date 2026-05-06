from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from .query_rewrite import RewrittenQuery


STRONG_RELATIONS_BY_QUERY_TYPE: dict[str, tuple[str, ...]] = {
    "definition": ("defines_term", "has_parameter_topic"),
    "parameter_lookup": ("has_parameter_topic", "has_parameter_group", "defines_term"),
    "timing_lookup": ("has_process",),
    "constraint": ("has_constraint", "has_parameter_topic"),
    "comparison": ("has_comparison",),
    "standard_lookup": ("references_standard", "replaces_standard"),
    "lifecycle_lookup": ("has_process", "references_standard", "replaces_standard"),
}

WEAK_RELATIONS = ("relates_to_term",)

RELATION_SCORE = {
    "defines_term": 1.18,
    "has_parameter_topic": 1.14,
    "has_process": 1.12,
    "has_parameter_group": 1.02,
    "has_constraint": 1.0,
    "has_comparison": 1.0,
    "references_standard": 0.96,
    "replaces_standard": 0.96,
    "relates_to_term": 0.48,
}


@dataclass(frozen=True)
class GraphCandidate:
    result_type: str
    result_id: str
    doc_id: str
    page_no: int | None
    score: float
    snippet: str
    edge_id: str
    relation: str
    graph_path: list[dict[str, object]]
    evidence_ids: list[str]
    fact_id: str | None
    trust_tier: str

    def to_hit(self) -> dict[str, object]:
        payload = asdict(self)
        payload["channel"] = "graph"
        payload["channels"] = ["graph"]
        payload["graph_source"] = True
        return payload


def retrieve_graph_candidates(
    connection,
    rewritten: RewrittenQuery,
    entity_ids: list[str] | set[str] | tuple[str, ...],
    limit: int = 20,
) -> list[GraphCandidate]:
    seed_entity_ids = [str(item).strip() for item in entity_ids if str(item or "").strip()]
    if not seed_entity_ids:
        return []

    strong_relations = STRONG_RELATIONS_BY_QUERY_TYPE.get(
        rewritten.query_type,
        ("defines_term", "has_parameter_topic", "has_process", "has_constraint"),
    )
    allowed_relations = [*strong_relations, *WEAK_RELATIONS]
    placeholders = ",".join("?" for _ in seed_entity_ids)
    relation_placeholders = ",".join("?" for _ in allowed_relations)
    edge_rows = connection.execute(
        f"""
        SELECT g.edge_id, g.src_entity_id, g.relation, g.dst_entity_id, g.version_scope, g.confidence
        FROM graph_edges g
        JOIN entities src ON src.entity_id = g.src_entity_id
        JOIN entities dst ON dst.entity_id = g.dst_entity_id
        WHERE (g.src_entity_id IN ({placeholders}) OR g.dst_entity_id IN ({placeholders}))
          AND g.relation IN ({relation_placeholders})
          AND g.edge_status = 'ready'
          AND src.entity_status = 'ready'
          AND dst.entity_status = 'ready'
        ORDER BY
          CASE g.relation
            WHEN 'defines_term' THEN 0
            WHEN 'has_parameter_topic' THEN 1
            WHEN 'has_process' THEN 2
            WHEN 'has_parameter_group' THEN 3
            WHEN 'has_constraint' THEN 4
            WHEN 'has_comparison' THEN 5
            WHEN 'references_standard' THEN 6
            WHEN 'replaces_standard' THEN 7
            ELSE 8
          END,
          g.confidence DESC,
          g.edge_id ASC
        LIMIT ?
        """,
        [*seed_entity_ids, *seed_entity_ids, *allowed_relations, max(limit * 4, 24)],
    ).fetchall()
    if not edge_rows:
        return []

    entity_names = _load_entity_names(connection, {
        str(row["src_entity_id"]) for row in edge_rows
    } | {
        str(row["dst_entity_id"]) for row in edge_rows
    })

    candidates: dict[tuple[str, str], GraphCandidate] = {}
    for edge in edge_rows:
        relation = str(edge["relation"] or "")
        trust_tier = "strong" if relation in strong_relations else "weak"
        edge_evidence = _load_edge_evidence(connection, str(edge["edge_id"]))
        for evidence in edge_evidence:
            fact_rows = _load_facts_for_evidence(connection, str(evidence["evidence_id"]))
            if not fact_rows:
                candidate = _candidate_from_evidence(edge, evidence, entity_names, trust_tier)
                _keep_best(candidates, candidate)
                continue
            for fact in fact_rows:
                candidate = _candidate_from_fact(edge, evidence, fact, entity_names, trust_tier)
                _keep_best(candidates, candidate)

    ranked = sorted(
        candidates.values(),
        key=lambda item: (
            0 if item.trust_tier == "strong" else 1,
            -item.score,
            item.result_id,
        ),
    )
    return ranked[:limit]


def _keep_best(candidates: dict[tuple[str, str], GraphCandidate], candidate: GraphCandidate) -> None:
    key = (candidate.result_type, candidate.result_id)
    existing = candidates.get(key)
    if existing is None or candidate.score > existing.score:
        candidates[key] = candidate


def _load_entity_names(connection, entity_ids: set[str]) -> dict[str, str]:
    if not entity_ids:
        return {}
    placeholders = ",".join("?" for _ in entity_ids)
    rows = connection.execute(
        f"""
        SELECT entity_id, canonical_name
        FROM entities
        WHERE entity_id IN ({placeholders})
        """,
        list(entity_ids),
    ).fetchall()
    return {str(row["entity_id"]): str(row["canonical_name"] or "") for row in rows}


def _load_edge_evidence(connection, edge_id: str) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT e.evidence_id, e.doc_id, e.page_no, e.confidence, e.normalized_text
        FROM edge_evidence_map m
        JOIN evidence e ON e.evidence_id = m.evidence_id
        WHERE m.edge_id = ?
        ORDER BY e.confidence DESC, e.page_no ASC
        LIMIT 12
        """,
        (edge_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _load_facts_for_evidence(connection, evidence_id: str) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT f.fact_id, f.fact_type, f.source_doc_id, f.confidence,
               json_extract(f.qualifiers_json, '$.page_no') AS page_no,
               f.object_value
        FROM fact_evidence_map m
        JOIN facts f ON f.fact_id = m.fact_id
        WHERE m.evidence_id = ?
        ORDER BY f.confidence DESC, f.fact_id ASC
        LIMIT 12
        """,
        (evidence_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _candidate_from_fact(
    edge,
    evidence: dict[str, object],
    fact: dict[str, object],
    entity_names: dict[str, str],
    trust_tier: str,
) -> GraphCandidate:
    relation = str(edge["relation"] or "")
    confidence = max(float(edge["confidence"] or 0.0), float(fact.get("confidence") or 0.0))
    score = round(RELATION_SCORE.get(relation, 0.5) + confidence * 0.25, 6)
    return GraphCandidate(
        result_type="fact",
        result_id=str(fact["fact_id"]),
        doc_id=str(fact["source_doc_id"] or evidence.get("doc_id") or ""),
        page_no=_as_int(fact.get("page_no") or evidence.get("page_no")),
        score=score,
        snippet=_fact_snippet(fact),
        edge_id=str(edge["edge_id"]),
        relation=relation,
        graph_path=_graph_path(edge, entity_names, evidence_id=str(evidence["evidence_id"]), fact_id=str(fact["fact_id"])),
        evidence_ids=[str(evidence["evidence_id"])],
        fact_id=str(fact["fact_id"]),
        trust_tier=trust_tier,
    )


def _candidate_from_evidence(
    edge,
    evidence: dict[str, object],
    entity_names: dict[str, str],
    trust_tier: str,
) -> GraphCandidate:
    relation = str(edge["relation"] or "")
    score = round(RELATION_SCORE.get(relation, 0.5) + float(evidence.get("confidence") or 0.0) * 0.2, 6)
    evidence_id = str(evidence["evidence_id"])
    return GraphCandidate(
        result_type="evidence",
        result_id=evidence_id,
        doc_id=str(evidence.get("doc_id") or ""),
        page_no=_as_int(evidence.get("page_no")),
        score=score,
        snippet=f"graph_evidence {str(evidence.get('normalized_text') or '')[:500]}",
        edge_id=str(edge["edge_id"]),
        relation=relation,
        graph_path=_graph_path(edge, entity_names, evidence_id=evidence_id, fact_id=None),
        evidence_ids=[evidence_id],
        fact_id=None,
        trust_tier=trust_tier,
    )


def _graph_path(edge, entity_names: dict[str, str], evidence_id: str, fact_id: str | None) -> list[dict[str, object]]:
    src_id = str(edge["src_entity_id"])
    dst_id = str(edge["dst_entity_id"])
    path: list[dict[str, object]] = [
        {
            "edge_id": str(edge["edge_id"]),
            "src_entity_id": src_id,
            "src_name": entity_names.get(src_id, src_id),
            "relation": str(edge["relation"] or ""),
            "dst_entity_id": dst_id,
            "dst_name": entity_names.get(dst_id, dst_id),
            "version_scope": edge["version_scope"],
            "confidence": float(edge["confidence"] or 0.0),
        },
        {
            "edge_id": str(edge["edge_id"]),
            "relation": "supported_by",
            "evidence_id": evidence_id,
        },
    ]
    if fact_id:
        path.append({"evidence_id": evidence_id, "relation": "supports_fact", "fact_id": fact_id})
    return path


def _fact_snippet(fact: dict[str, object]) -> str:
    payload = fact.get("object_value")
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = payload
    else:
        parsed = payload
    return f"graph_fact {fact.get('fact_type')}: {json.dumps(parsed, ensure_ascii=False)[:600]}"


def _as_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
