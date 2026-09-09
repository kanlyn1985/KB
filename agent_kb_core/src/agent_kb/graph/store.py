from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Iterable

from agent_kb.projection.models import ObjectRelation
from agent_kb.query.query_frame import QueryFrame
from agent_kb.retrieval.models import RetrievalCandidate
from agent_kb.storage.migrations import SchemaMigrator


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    domain: str
    relation_type: str
    source_object_id: str
    target_object_id: str
    properties: dict[str, Any] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "candidate"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GraphPath:
    start_object_id: str
    end_object_id: str
    object_ids: list[str]
    edge_ids: list[str]
    depth: int
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GraphTraversalResult:
    start_object_ids: list[str]
    paths: list[GraphPath]
    visited_object_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_object_ids": list(self.start_object_ids),
            "paths": [item.to_dict() for item in self.paths],
            "visited_object_ids": list(self.visited_object_ids),
        }


class SQLiteGraphStore:
    """Persistent ontology-lite graph with bounded breadth-first traversal."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        SchemaMigrator(connection).migrate()

    def upsert_relations(self, relations: Iterable[ObjectRelation | GraphEdge]) -> int:
        count = 0
        now = _utc_now_iso()
        with self.connection:
            for relation in relations:
                if isinstance(relation, ObjectRelation):
                    evidence_ids = [ref.evidence_id for ref in relation.evidence_refs]
                    edge = GraphEdge(
                        edge_id=relation.relation_id,
                        domain=relation.domain,
                        relation_type=relation.relation_type,
                        source_object_id=relation.source_object_id,
                        target_object_id=relation.target_object_id,
                        properties=dict(relation.properties),
                        evidence_ids=evidence_ids,
                        confidence=relation.confidence,
                        status=relation.status,
                    )
                else:
                    edge = relation
                self.connection.execute(
                    """
                    INSERT INTO graph_edges(
                        edge_id, domain, relation_type, source_object_id,
                        target_object_id, properties_json, evidence_ids_json,
                        confidence, status, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(edge_id) DO UPDATE SET
                        domain=excluded.domain,
                        relation_type=excluded.relation_type,
                        source_object_id=excluded.source_object_id,
                        target_object_id=excluded.target_object_id,
                        properties_json=excluded.properties_json,
                        evidence_ids_json=excluded.evidence_ids_json,
                        confidence=excluded.confidence,
                        status=excluded.status,
                        updated_at=excluded.updated_at
                    """,
                    (
                        edge.edge_id,
                        edge.domain,
                        edge.relation_type,
                        edge.source_object_id,
                        edge.target_object_id,
                        _json(edge.properties),
                        _json(edge.evidence_ids),
                        edge.confidence,
                        edge.status,
                        now,
                    ),
                )
                count += 1
        return count

    def materialize_from_cards(self, cards: Iterable[Any]) -> int:
        edges: list[GraphEdge] = []
        for card in cards:
            source = str(card.object_id or "").strip()
            if not source:
                continue
            for target in card.related_object_ids:
                target_id = str(target or "").strip()
                if not target_id or target_id == source:
                    continue
                edges.append(
                    GraphEdge(
                        edge_id=_edge_id(card.domain, "related_to", source, target_id),
                        domain=card.domain,
                        relation_type="related_to",
                        source_object_id=source,
                        target_object_id=target_id,
                        properties={"source": "retrieval_card", "card_id": card.card_id},
                        evidence_ids=list(card.evidence_ids),
                        confidence=max(0.45, min(float(card.confidence), 1.0)),
                        status="materialized",
                    )
                )
        return self.upsert_relations(edges)

    def traverse(
        self,
        start_object_ids: Iterable[str],
        *,
        max_depth: int = 2,
        max_paths: int = 64,
        relation_types: set[str] | None = None,
    ) -> GraphTraversalResult:
        starts = [str(item).strip() for item in start_object_ids if str(item).strip()]
        queue: deque[tuple[str, list[str], list[str], float]] = deque(
            (item, [item], [], 1.0) for item in starts
        )
        visited: set[str] = set(starts)
        paths: list[GraphPath] = []
        while queue and len(paths) < max(1, max_paths):
            current, object_path, edge_path, score = queue.popleft()
            depth = len(edge_path)
            if depth >= max(0, max_depth):
                continue
            rows = self.connection.execute(
                """
                SELECT * FROM graph_edges
                WHERE status != 'deleted' AND (source_object_id = ? OR target_object_id = ?)
                ORDER BY confidence DESC, edge_id
                """,
                (current, current),
            )
            for row in rows:
                if relation_types and row["relation_type"] not in relation_types:
                    continue
                neighbor = row["target_object_id"] if row["source_object_id"] == current else row["source_object_id"]
                if neighbor in object_path:
                    continue
                new_objects = [*object_path, neighbor]
                new_edges = [*edge_path, row["edge_id"]]
                new_score = score * max(0.05, float(row["confidence"]))
                paths.append(
                    GraphPath(
                        start_object_id=object_path[0],
                        end_object_id=neighbor,
                        object_ids=new_objects,
                        edge_ids=new_edges,
                        depth=len(new_edges),
                        score=new_score,
                    )
                )
                visited.add(neighbor)
                queue.append((neighbor, new_objects, new_edges, new_score))
                if len(paths) >= max(1, max_paths):
                    break
        paths.sort(key=lambda item: (item.score, -item.depth, item.end_object_id), reverse=True)
        return GraphTraversalResult(
            start_object_ids=starts,
            paths=paths,
            visited_object_ids=sorted(visited),
        )

    def search(self, query_frame: QueryFrame, *, limit: int = 32) -> list[RetrievalCandidate]:
        starts = [item.object_id for item in query_frame.target_objects]
        if not starts:
            return []
        result = self.traverse(starts, max_depth=2, max_paths=max(1, limit))
        candidates: list[RetrievalCandidate] = []
        for path in result.paths[: max(1, limit)]:
            candidates.append(
                RetrievalCandidate(
                    candidate_id=f"object:{path.end_object_id}",
                    source_type="object",
                    source_id=path.end_object_id,
                    channel="graph",
                    score=path.score,
                    matched_terms=[],
                    reasons=["graph_traversal"],
                    payload={
                        "object_id": path.end_object_id,
                        "graph_path": path.object_ids,
                        "edge_ids": path.edge_ids,
                        "depth": path.depth,
                    },
                )
            )
        return candidates

    def list_edges(self, *, object_id: str | None = None) -> list[GraphEdge]:
        if object_id:
            rows = self.connection.execute(
                "SELECT * FROM graph_edges WHERE source_object_id = ? OR target_object_id = ? ORDER BY edge_id",
                (object_id, object_id),
            )
        else:
            rows = self.connection.execute("SELECT * FROM graph_edges ORDER BY edge_id")
        return [_edge_from_row(row) for row in rows]


def _edge_id(domain: str, relation_type: str, source: str, target: str) -> str:
    digest = hashlib.sha256(f"{domain}:{relation_type}:{source}:{target}".encode("utf-8")).hexdigest()
    return f"edge_{digest[:20]}"


def _edge_from_row(row: sqlite3.Row) -> GraphEdge:
    return GraphEdge(
        edge_id=row["edge_id"],
        domain=row["domain"],
        relation_type=row["relation_type"],
        source_object_id=row["source_object_id"],
        target_object_id=row["target_object_id"],
        properties=json.loads(row["properties_json"] or "{}"),
        evidence_ids=json.loads(row["evidence_ids_json"] or "[]"),
        confidence=float(row["confidence"]),
        status=row["status"],
    )
