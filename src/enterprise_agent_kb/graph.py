from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .db import connect
from .ids import next_prefixed_id


@dataclass(frozen=True)
class GraphBuildResult:
    doc_id: str
    edge_count: int
    edge_types: dict[str, int]
    export_path: Path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _find_doc_entity_id(connection, doc_id: str) -> str | None:
    row = connection.execute(
        """
        SELECT entity_id
        FROM entities
        WHERE entity_type = 'document' AND canonical_name LIKE ?
        LIMIT 1
        """,
        (f"{doc_id}:%",),
    ).fetchone()
    return row["entity_id"] if row else None


def _entity_type(connection, entity_id: str) -> str:
    row = connection.execute(
        "SELECT entity_type FROM entities WHERE entity_id = ?",
        (entity_id,),
    ).fetchone()
    return str(row["entity_type"] or "") if row else ""


def _ensure_edge(
    connection,
    src_entity_id: str,
    relation: str,
    dst_entity_id: str,
    version_scope: str | None,
    condition_scope: str | None,
    confidence: float,
    now: str,
) -> str:
    row = connection.execute(
        """
        SELECT edge_id, confidence
        FROM graph_edges
        WHERE src_entity_id = ?
          AND relation = ?
          AND dst_entity_id = ?
          AND COALESCE(version_scope, '') = COALESCE(?, '')
          AND COALESCE(condition_scope, '') = COALESCE(?, '')
        LIMIT 1
        """,
        (src_entity_id, relation, dst_entity_id, version_scope, condition_scope),
    ).fetchone()
    if row:
        if confidence > float(row["confidence"] or 0):
            connection.execute(
                "UPDATE graph_edges SET confidence = ?, updated_at = ? WHERE edge_id = ?",
                (confidence, now, row["edge_id"]),
            )
        return row["edge_id"]

    edge_id = next_prefixed_id(connection, "edge", "EDGE")
    connection.execute(
        """
        INSERT INTO graph_edges (
            edge_id, src_entity_id, relation, dst_entity_id,
            version_scope, condition_scope, confidence, edge_status,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            edge_id,
            src_entity_id,
            relation,
            dst_entity_id,
            version_scope,
            condition_scope,
            confidence,
            "ready",
            now,
            now,
        ),
    )
    return edge_id


def build_graph_for_document(workspace_root: Path, doc_id: str) -> GraphBuildResult:
    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    now = _utc_now()

    try:
        doc_entity_id = _find_doc_entity_id(connection, doc_id)
        if not doc_entity_id:
            raise ValueError(f"document entity missing for {doc_id}")

        rows = connection.execute(
            """
            SELECT
                f.fact_id,
                f.fact_type,
                f.predicate,
                f.subject_entity_id,
                f.object_entity_id,
                f.confidence,
                GROUP_CONCAT(m.evidence_id) AS evidence_ids
            FROM facts f
            LEFT JOIN fact_evidence_map m ON m.fact_id = f.fact_id
            WHERE f.source_doc_id = ?
            GROUP BY f.fact_id
            ORDER BY f.fact_id
            """,
            (doc_id,),
        ).fetchall()

        term_rows = connection.execute(
            """
            SELECT entity_id, canonical_name
            FROM entities
            WHERE entity_type = 'term'
            ORDER BY canonical_name
            """
        ).fetchall()

        edge_types: dict[str, int] = {}
        exported: list[dict[str, object]] = []
        seen_edges: set[str] = set()

        for row in rows:
            relation = None
            src_entity_id = doc_entity_id
            dst_entity_id = None

            if row["fact_type"] == "document_standard" and row["object_entity_id"]:
                relation = "references_standard"
                dst_entity_id = row["object_entity_id"]
            elif row["fact_type"] == "document_versioning" and row["object_entity_id"]:
                relation = "replaces_standard"
                dst_entity_id = row["object_entity_id"]
            elif row["fact_type"] in {"term_definition", "concept_definition"} and row["subject_entity_id"]:
                relation = "defines_term"
                dst_entity_id = row["subject_entity_id"]
            elif row["fact_type"] in {"process_fact", "transition_fact"} and row["object_entity_id"]:
                relation = "has_process"
                dst_entity_id = row["object_entity_id"]
            elif row["fact_type"] == "table_requirement" and row["object_entity_id"]:
                dst_entity_id = row["object_entity_id"]
                dst_entity_type = _entity_type(connection, dst_entity_id)
                relation = "has_process" if dst_entity_type == "process" else "has_parameter_group"
            elif row["fact_type"] == "parameter_value" and row["object_entity_id"]:
                relation = "has_parameter_topic"
                if row["subject_entity_id"]:
                    src_entity_id = row["subject_entity_id"]
                dst_entity_id = row["object_entity_id"]
            elif row["fact_type"] in {"requirement", "threshold"} and row["subject_entity_id"]:
                relation = "has_constraint"
                dst_entity_id = row["subject_entity_id"]
            elif row["fact_type"] == "comparison_relation" and row["subject_entity_id"]:
                relation = "has_comparison"
                dst_entity_id = row["subject_entity_id"]

            if not relation or not dst_entity_id:
                continue

            dedupe_key = f"{src_entity_id}|{relation}|{dst_entity_id}|{doc_id}"
            if dedupe_key in seen_edges:
                continue
            seen_edges.add(dedupe_key)

            edge_id = _ensure_edge(
                connection,
                src_entity_id=src_entity_id,
                relation=relation,
                dst_entity_id=dst_entity_id,
                version_scope=doc_id,
                condition_scope=None,
                confidence=float(row["confidence"] or 0.8),
                now=now,
            )

            evidence_ids = [item for item in (row["evidence_ids"] or "").split(",") if item]
            for evidence_id in evidence_ids:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO edge_evidence_map (edge_id, evidence_id)
                    VALUES (?, ?)
                    """,
                    (edge_id, evidence_id),
                )

            edge_types[relation] = edge_types.get(relation, 0) + 1
            exported.append(
                {
                    "edge_id": edge_id,
                    "src_entity_id": src_entity_id,
                    "relation": relation,
                    "dst_entity_id": dst_entity_id,
                    "version_scope": doc_id,
                    "confidence": float(row["confidence"] or 0.8),
                    "fact_id": row["fact_id"],
                    "evidence_ids": evidence_ids,
                }
            )

            payload = _load_fact_payload(connection, row["fact_id"])
            for term in term_rows:
                if _payload_relates_to_term(payload, str(term["canonical_name"])):
                    related_edge_id = _ensure_edge(
                        connection,
                        src_entity_id=dst_entity_id,
                        relation="relates_to_term",
                        dst_entity_id=term["entity_id"],
                        version_scope=doc_id,
                        condition_scope=None,
                        confidence=float(row["confidence"] or 0.8),
                        now=now,
                    )
                    for evidence_id in evidence_ids:
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO edge_evidence_map (edge_id, evidence_id)
                            VALUES (?, ?)
                            """,
                            (related_edge_id, evidence_id),
                        )
                    edge_types["relates_to_term"] = edge_types.get("relates_to_term", 0) + 1
                    exported.append(
                        {
                            "edge_id": related_edge_id,
                            "src_entity_id": dst_entity_id,
                            "relation": "relates_to_term",
                            "dst_entity_id": term["entity_id"],
                            "version_scope": doc_id,
                            "confidence": float(row["confidence"] or 0.8),
                            "fact_id": row["fact_id"],
                            "evidence_ids": evidence_ids,
                        }
                    )

        export_path = paths.facts / f"{doc_id}.graph.json"
        export_path.write_text(
            json.dumps(
                {
                    "doc_id": doc_id,
                    "generated_at": now,
                    "edge_count": len(exported),
                    "edge_types": edge_types,
                    "items": exported,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        connection.commit()
        return GraphBuildResult(
            doc_id=doc_id,
            edge_count=len(exported),
            edge_types=edge_types,
            export_path=export_path,
        )
    finally:
        connection.close()


def _load_fact_payload(connection, fact_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT object_value FROM facts WHERE fact_id = ?",
        (fact_id,),
    ).fetchone()
    if row is None:
        return {}
    try:
        return json.loads(row["object_value"] or "{}")
    except json.JSONDecodeError:
        return {}


def _payload_relates_to_term(payload: dict[str, object], canonical_name: str) -> bool:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    name = canonical_name.lower()
    if name and name in blob:
        return True
    if "control pilot" in name and "控制导引" in blob:
        return True
    if "connection confirm" in name and "cc" in blob:
        return True
    if "vehicle to grid" in name and "v2g" in blob:
        return True
    return False
