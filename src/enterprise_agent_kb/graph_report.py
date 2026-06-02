from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from .db import connect_context

from .graph_retrieval import STRONG_RELATIONS_BY_QUERY_TYPE, RELATION_SCORE


@dataclass(frozen=True)
class GraphQueryTypeReport:
    query_type: str
    required_relations: list[str]
    strong_edges: int
    weak_edges: int
    missing_relation: list[str]
    linked_facts: int
    unlinked_facts: int
    avg_confidence: float
    status: str


@dataclass(frozen=True)
class GraphHealthReport:
    total_edges: int
    strong_edges: int
    weak_edges: int
    edges_no_classification: int
    linked_facts: int
    unlinked_facts: int
    total_facts: int
    query_type_reports: list[GraphQueryTypeReport]
    issues: list[str]


def _classify_relation(relation: str) -> str:
    all_strong = {r for vals in STRONG_RELATIONS_BY_QUERY_TYPE.values() for r in vals}
    if relation in all_strong:
        return "strong"
    if relation in ("relates_to_term",):
        return "weak"
    return "unclassified"


def build_graph_health_report(db_path: str | Path) -> GraphHealthReport:
    with connect_context(db_path) as connection:

        edge_rows = connection.execute(
            "SELECT edge_id, src_entity_id, relation, dst_entity_id, confidence FROM graph_edges"
        ).fetchall()

        total_edges = len(edge_rows)
        strong_total = 0
        weak_total = 0
        unclassified_total = 0

        for er in edge_rows:
            cls = _classify_relation(er["relation"])
            if cls == "strong":
                strong_total += 1
            elif cls == "weak":
                weak_total += 1
            else:
                unclassified_total += 1

        fact_rows = connection.execute(
            "SELECT fact_id, subject_entity_id, object_entity_id FROM facts"
        ).fetchall()

        # Build entity -> edge mapping
        entity_edges: dict[str, set[str]] = {}
        for er in edge_rows:
            entity_edges.setdefault(er["src_entity_id"], set()).add(er["edge_id"])
            entity_edges.setdefault(er["dst_entity_id"], set()).add(er["edge_id"])

        linked_facts = 0
        unlinked_facts = 0
        for fr in fact_rows:
            sid = fr["subject_entity_id"]
            oid = fr["object_entity_id"]
            if (sid and sid in entity_edges) or (oid and oid in entity_edges):
                linked_facts += 1
            else:
                unlinked_facts += 1

        qtype_reports: list[GraphQueryTypeReport] = []
        issues: list[str] = []

        for qtype, required in STRONG_RELATIONS_BY_QUERY_TYPE.items():
            rel_set = set(required)
            q_strong = 0
            q_weak = 0
            q_confidences: list[float] = []

            for er in edge_rows:
                if er["relation"] in rel_set:
                    cls = _classify_relation(er["relation"])
                    if cls == "strong":
                        q_strong += 1
                    elif cls == "weak":
                        q_weak += 1
                    conf = er["confidence"]
                    if conf is not None:
                        q_confidences.append(float(conf))

            existing_rels = {er["relation"] for er in edge_rows}
            missing = [r for r in required if r not in existing_rels]
            avg_conf = sum(q_confidences) / len(q_confidences) if q_confidences else 0.0

            # Count linked/unlinked facts for this query type via entity relation filter
            q_linked = 0
            q_unlinked = 0
            relevant_entity_ids: set[str] = set()
            for er in edge_rows:
                if er["relation"] in rel_set:
                    relevant_entity_ids.add(er["src_entity_id"])
                    relevant_entity_ids.add(er["dst_entity_id"])
            for fr in fact_rows:
                if fr["subject_entity_id"] in relevant_entity_ids or fr["object_entity_id"] in relevant_entity_ids:
                    q_linked += 1
                else:
                    q_unlinked += 1

            if missing:
                status = "degraded"
                issues.append(f"query_type={qtype}: missing strong relations {missing}")
            elif q_strong == 0:
                status = "empty"
                issues.append(f"query_type={qtype}: no strong edges for required relations")
            else:
                status = "healthy"

            qtype_reports.append(
                GraphQueryTypeReport(
                    query_type=qtype,
                    required_relations=list(required),
                    strong_edges=q_strong,
                    weak_edges=q_weak,
                    missing_relation=missing,
                    linked_facts=q_linked,
                    unlinked_facts=q_unlinked,
                    avg_confidence=round(avg_conf, 3),
                    status=status,
                )
            )

        return GraphHealthReport(
            total_edges=total_edges,
            strong_edges=strong_total,
            weak_edges=weak_total,
            edges_no_classification=unclassified_total,
            linked_facts=linked_facts,
            unlinked_facts=unlinked_facts,
            total_facts=len(fact_rows),
            query_type_reports=qtype_reports,
            issues=issues,
        )


def format_graph_health_report(report: GraphHealthReport) -> str:
    lines = [
        "=" * 72,
        "  Graph Health Report",
        "=" * 72,
        "",
        f"  Total edges:            {report.total_edges:>6}",
        f"  Strong edges:           {report.strong_edges:>6}",
        f"  Weak edges:             {report.weak_edges:>6}",
        f"  Unclassified edges:     {report.edges_no_classification:>6}",
        "",
        f"  Facts linked to graph:  {report.linked_facts:>6} / {report.total_facts}",
        f"  Facts not linked:       {report.unlinked_facts:>6} / {report.total_facts}",
        "",
        "-" * 72,
        f"  {'Query Type':<22} {'Status':<10} {'Strong':>7} {'Weak':>7} {'Missing':>8} {'L-Facts':>7} {'Conf':>6}",
        "-" * 72,
    ]
    for qr in report.query_type_reports:
        missing_str = str(len(qr.missing_relation)) if qr.missing_relation else "-"
        lines.append(
            f"  {qr.query_type:<22} {qr.status:<10} {qr.strong_edges:>7} {qr.weak_edges:>7} "
            f"{missing_str:>8} {qr.linked_facts:>7} {qr.avg_confidence:>6.2f}"
        )
    if report.issues:
        lines.append("")
        lines.append("-" * 72)
        lines.append("  Issues:")
        for issue in report.issues:
            lines.append(f"  - {issue}")
    lines.append("")
    lines.append("=" * 72)
    return "\n".join(lines)