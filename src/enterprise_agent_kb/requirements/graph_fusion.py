"""Phase 5: Requirement Resolver <-> KB1 Graph fusion.

Projects requirement-domain relationships into the KB1 graph_edges table,
forming an engineering knowledge network. Five relation types:

  supported_by : effective_requirement -> evidence (proof backing)
  verified_by  : effective_requirement -> test_result (verification status)
  impacts      : effective_requirement -> component (blast radius)
  changed_by   : effective_requirement -> eco_order (change history)
  approved_by  : effective_requirement -> approval/user (governance trail)

Design constraints (KB1 evidence-constrained invariants):
- Graph edges are candidate enhancement only, never fact adjudication.
- Requirements must already have evidence bindings or effective records;
  the projector never fabricates entities or evidence.
- All edges carry confidence and edge_status for traceability.
- Idempotent: re-running the projector updates existing edges rather than
  duplicating them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .repository import RequirementRepository, utc_now

RELATION_SUPPORTED_BY = "supported_by"
RELATION_VERIFIED_BY = "verified_by"
RELATION_IMPACTS = "impacts"
RELATION_CHANGED_BY = "changed_by"
RELATION_APPROVED_BY = "approved_by"

ALL_FUSION_RELATIONS = (
    RELATION_SUPPORTED_BY,
    RELATION_VERIFIED_BY,
    RELATION_IMPACTS,
    RELATION_CHANGED_BY,
    RELATION_APPROVED_BY,
)


@dataclass(frozen=True)
class FusionEdge:
    src_entity_id: str
    relation: str
    dst_entity_id: str
    confidence: float
    edge_status: str
    source_table: str
    source_id: str

    def edge_id(self) -> str:
        return f"REQEDGE-{self.source_table}-{self.src_entity_id}-{self.relation}-{self.dst_entity_id}"


class RequirementGraphFusion:
    """Project requirement-domain relationships into KB1 graph_edges."""

    def __init__(self, repo: RequirementRepository):
        self.repo = repo
        self.repo.initialize_schema()

    @classmethod
    def from_root(cls, root: Path) -> "RequirementGraphFusion":
        return cls(RequirementRepository(root))

    def project_all(self) -> dict[str, Any]:
        results = {
            RELATION_SUPPORTED_BY: self._project_supported_by(),
            RELATION_VERIFIED_BY: self._project_verified_by(),
            RELATION_IMPACTS: self._project_impacts(),
            RELATION_CHANGED_BY: self._project_changed_by(),
            RELATION_APPROVED_BY: self._project_approved_by(),
        }
        total = sum(r["edges_upserted"] for r in results.values())
        return {"fusion_relations": results, "total_edges_upserted": total}


    def _upsert_edge(self, connection, edge: FusionEdge) -> bool:
        """Insert or update a fusion edge. Returns True if upserted, False if
        graph_edges table does not exist (standalone requirement workspace
        without KB1 schema)."""
        # Check graph_edges exists (KB1 table, may be absent in standalone
        # requirement workspaces).
        check = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='graph_edges'"
        ).fetchone()
        if not check:
            return False
        now = utc_now()
        connection.execute(
            """
            INSERT INTO graph_edges (
                edge_id, src_entity_id, relation, dst_entity_id,
                version_scope, condition_scope, confidence, edge_status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
            ON CONFLICT(edge_id) DO UPDATE SET
                confidence=excluded.confidence,
                edge_status=excluded.edge_status,
                updated_at=excluded.updated_at
            """,
            (
                edge.edge_id(),
                edge.src_entity_id,
                edge.relation,
                edge.dst_entity_id,
                json.dumps({"source_table": edge.source_table, "source_id": edge.source_id}, ensure_ascii=False),
                edge.confidence,
                edge.edge_status,
                now,
                now,
            ),
        )
        return True


    def _project_supported_by(self) -> dict[str, Any]:
        edges: list[FusionEdge] = []
        with self.repo._conn_ctx() as conn:
            rows = conn.execute(
                """
                SELECT binding_id, effective_id, variant_id, atom_id,
                       evidence_id, fact_id, document_id, confidence, binding_type
                FROM requirement_evidence_bindings
                WHERE evidence_id IS NOT NULL
                """
            ).fetchall()
            for row in rows:
                src = f"REQEFF-{row['effective_id']}" if row["effective_id"] else f"REQATOM-{row['atom_id']}"
                edges.append(FusionEdge(
                    src_entity_id=src,
                    relation=RELATION_SUPPORTED_BY,
                    dst_entity_id=row["evidence_id"],
                    confidence=row["confidence"] or 0.8,
                    edge_status="active",
                    source_table="requirement_evidence_bindings",
                    source_id=row["binding_id"],
                ))
            for edge in edges:
                self._upsert_edge(conn, edge)
            if edges:
                conn.commit()
        return {"edges_upserted": len(edges), "source": "requirement_evidence_bindings"}

    def _project_verified_by(self) -> dict[str, Any]:
        edges: list[FusionEdge] = []
        with self.repo._conn_ctx() as conn:
            rows = conn.execute(
                """
                SELECT result_id, test_case_id, status, evidence_id
                FROM requirement_test_results
                WHERE test_case_id IS NOT NULL
                """
            ).fetchall()
            for row in rows:
                src = f"REQTC-{row['test_case_id']}"
                status = row["status"] or "unknown"
                confidence = 0.95 if status == "pass" else 0.5 if status == "fail" else 0.7
                edges.append(FusionEdge(
                    src_entity_id=src,
                    relation=RELATION_VERIFIED_BY,
                    dst_entity_id=f"TESTRESULT-{row['result_id']}",
                    confidence=confidence,
                    edge_status="active" if status != "fail" else "flagged",
                    source_table="requirement_test_results",
                    source_id=row["result_id"],
                ))
            for edge in edges:
                self._upsert_edge(conn, edge)
            if edges:
                conn.commit()
        return {"edges_upserted": len(edges), "source": "requirement_test_results"}


    def _project_impacts(self) -> dict[str, Any]:
        """Project effective_requirements -> impacts edges (project blast radius).

        Maps effective_requirement -> project as a component proxy. When a
        richer component model exists, this can be extended.
        """
        edges: list[FusionEdge] = []
        with self.repo._conn_ctx() as conn:
            rows = conn.execute(
                """
                SELECT effective_id, atom_id, project_id
                FROM effective_requirements
                WHERE atom_id IS NOT NULL AND project_id IS NOT NULL
                """
            ).fetchall()
            for row in rows:
                edges.append(FusionEdge(
                    src_entity_id=f"REQEFF-{row['effective_id']}",
                    relation=RELATION_IMPACTS,
                    dst_entity_id=f"PROJECT-{row['project_id']}",
                    confidence=0.7,
                    edge_status="active",
                    source_table="effective_requirements",
                    source_id=row["effective_id"],
                ))
            for edge in edges:
                self._upsert_edge(conn, edge)
            if edges:
                conn.commit()
        return {"edges_upserted": len(edges), "source": "effective_requirements"}

    def _project_changed_by(self) -> dict[str, Any]:
        edges: list[FusionEdge] = []
        with self.repo._conn_ctx() as conn:
            rows = conn.execute(
                """
                SELECT eco_id, target_variant_id, status
                FROM requirement_eco_orders
                WHERE target_variant_id IS NOT NULL
                """
            ).fetchall()
            for row in rows:
                edges.append(FusionEdge(
                    src_entity_id=f"REQVAR-{row['target_variant_id']}",
                    relation=RELATION_CHANGED_BY,
                    dst_entity_id=f"ECO-{row['eco_id']}",
                    confidence=0.9,
                    edge_status="active" if row["status"] == "closed" else "pending",
                    source_table="requirement_eco_orders",
                    source_id=row["eco_id"],
                ))
            for edge in edges:
                self._upsert_edge(conn, edge)
            if edges:
                conn.commit()
        return {"edges_upserted": len(edges), "source": "requirement_eco_orders"}


    def _project_approved_by(self) -> dict[str, Any]:
        edges: list[FusionEdge] = []
        with self.repo._conn_ctx() as conn:
            rows = conn.execute(
                """
                SELECT approval_id, target_id, approver, approval_status
                FROM requirement_approvals
                WHERE target_id IS NOT NULL AND approver IS NOT NULL
                """
            ).fetchall()
            for row in rows:
                edges.append(FusionEdge(
                    src_entity_id=f"REQTARGET-{row['target_id']}",
                    relation=RELATION_APPROVED_BY,
                    dst_entity_id=f"USER-{row['approver']}",
                    confidence=0.95 if row["approval_status"] == "approved" else 0.5,
                    edge_status="active" if row["approval_status"] == "approved" else "pending",
                    source_table="requirement_approvals",
                    source_id=row["approval_id"],
                ))
            for edge in edges:
                self._upsert_edge(conn, edge)
            if edges:
                conn.commit()
        return {"edges_upserted": len(edges), "source": "requirement_approvals"}

    def list_fusion_edges(self, *, relation: str | None = None, limit: int = 100) -> dict[str, Any]:
        """List fusion edges currently in graph_edges. Returns empty if
        graph_edges table does not exist."""
        with self.repo._conn_ctx() as conn:
            check = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='graph_edges'"
            ).fetchone()
            if not check:
                return {"fusion_edge_count": 0, "edges": []}
            where = "WHERE edge_id LIKE 'REQEDGE-%'"
            params: list[Any] = []
            if relation:
                where += " AND relation = ?"
                params.append(relation)
            rows = conn.execute(
                f"""
                SELECT edge_id, src_entity_id, relation, dst_entity_id,
                       confidence, edge_status, updated_at
                FROM graph_edges
                {where}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()
        edges = [dict(row) for row in rows]
        return {"fusion_edge_count": len(edges), "edges": edges}
