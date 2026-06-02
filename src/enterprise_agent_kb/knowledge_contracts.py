from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection

from .db import connect


@dataclass(frozen=True)
class KnowledgeTypeContract:
    knowledge_type: str
    evidence_shape: str
    source_unit_types: tuple[str, ...]
    content_roles: tuple[str, ...]
    fact_types: tuple[str, ...]
    required: bool = False
    activate_from_facts: bool = True


DOCUMENT_KNOWLEDGE_CONTRACTS: tuple[KnowledgeTypeContract, ...] = (
    KnowledgeTypeContract(
        knowledge_type="standard_metadata",
        evidence_shape="standard_metadata",
        source_unit_types=(),
        content_roles=(),
        fact_types=("document_standard", "document_title", "document_lifecycle", "document_versioning"),
        required=True,
    ),
    KnowledgeTypeContract(
        knowledge_type="definition",
        evidence_shape="term_definition",
        source_unit_types=("definition_unit",),
        content_roles=("definition",),
        fact_types=("term_definition", "concept_definition"),
    ),
    KnowledgeTypeContract(
        knowledge_type="parameter",
        evidence_shape="parameter_definition",
        source_unit_types=("parameter_row_unit",),
        content_roles=("parameter_row",),
        fact_types=("parameter_value", "parameter_definition"),
    ),
    KnowledgeTypeContract(
        knowledge_type="process_activity",
        evidence_shape="process_activity",
        source_unit_types=("process_unit",),
        content_roles=("process_activity", "process_practice", "procedure"),
        fact_types=("process_fact",),
    ),
    KnowledgeTypeContract(
        knowledge_type="requirement",
        evidence_shape="requirement",
        source_unit_types=("requirement_unit",),
        content_roles=("requirement",),
        fact_types=("requirement", "table_requirement"),
    ),
    KnowledgeTypeContract(
        knowledge_type="test_method",
        evidence_shape="test_method",
        source_unit_types=(),
        content_roles=("test_method", "procedure", "test_procedure"),
        fact_types=("process_fact", "table_requirement"),
        activate_from_facts=False,
    ),
)


def document_knowledge_contract_summary(db_file: Path, doc_id: str) -> dict[str, object]:
    connection = connect(db_file)
    try:
        return document_knowledge_contract_summary_from_connection(connection, doc_id)
    finally:
        connection.close()


def document_knowledge_contract_summary_from_connection(connection: Connection, doc_id: str) -> dict[str, object]:
    contract_results = [_evaluate_contract(connection, doc_id, contract) for contract in DOCUMENT_KNOWLEDGE_CONTRACTS]
    active_results = [item for item in contract_results if item["active"]]
    failed = [item for item in active_results if item["status"] == "failed"]
    warned = [item for item in active_results if item["status"] == "warn"]
    active_shapes = sorted({str(item["evidence_shape"]) for item in active_results if item.get("evidence_shape")})
    return {
        "doc_id": doc_id,
        "status": "failed" if failed else ("warn" if warned else "passed"),
        "contract_count": len(contract_results),
        "active_contract_count": len(active_results),
        "failed_count": len(failed),
        "warn_count": len(warned),
        "active_evidence_shapes": active_shapes,
        "contracts": contract_results,
    }


def _evaluate_contract(connection: Connection, doc_id: str, contract: KnowledgeTypeContract) -> dict[str, object]:
    source_unit_count = _source_unit_count(connection, doc_id, contract)
    fact_count = _fact_count(connection, doc_id, contract)
    linked_fact_unit_count = _linked_fact_unit_count(connection, doc_id, contract)
    linked_evidence_unit_count = _linked_evidence_unit_count(connection, doc_id, contract)
    golden_case_count = _golden_case_count(connection, doc_id, contract)
    active = contract.required or bool(source_unit_count or golden_case_count or (contract.activate_from_facts and fact_count))
    issues: list[str] = []
    status = "passed"

    if contract.required:
        if contract.knowledge_type == "standard_metadata":
            if not _has_any_fact_type(connection, doc_id, ("document_standard", "document_title")):
                issues.append("missing_standard_or_title_fact")
                status = "warn"
        elif not fact_count:
            issues.append("missing_required_fact")
            status = "failed"

    if source_unit_count and not fact_count:
        issues.append("source_units_without_contract_fact_shape")
        status = "failed"
    if source_unit_count and not linked_fact_unit_count:
        issues.append("source_units_without_fact_links")
        status = "failed"
    if source_unit_count and not linked_evidence_unit_count:
        issues.append("source_units_without_evidence_links")
        status = "failed"
    if fact_count and contract.source_unit_types and not source_unit_count:
        issues.append("facts_without_source_unit_inventory")
        if status == "passed":
            status = "warn"
    if fact_count and not golden_case_count:
        # Only warn about missing golden cases when there are source units
        # that should be verified.  Shapes with zero source units (e.g.
        # standard_metadata which is a document-level check) don't need
        # golden cases — there is nothing to test.
        if source_unit_count > 0:
            issues.append("no_active_golden_case_for_shape")
            if status == "passed":
                status = "warn"

    return {
        "knowledge_type": contract.knowledge_type,
        "evidence_shape": contract.evidence_shape,
        "status": status if active else "inactive",
        "active": active,
        "required": contract.required,
        "source_unit_count": source_unit_count,
        "fact_count": fact_count,
        "linked_fact_unit_count": linked_fact_unit_count,
        "linked_evidence_unit_count": linked_evidence_unit_count,
        "golden_case_count": golden_case_count,
        "issues": issues,
        "contract": {
            "source_unit_types": list(contract.source_unit_types),
            "content_roles": list(contract.content_roles),
            "fact_types": list(contract.fact_types),
        },
    }


def _source_unit_count(connection: Connection, doc_id: str, contract: KnowledgeTypeContract) -> int:
    clauses: list[str] = []
    params: list[object] = [doc_id]
    if contract.source_unit_types:
        clauses.append(f"unit_type IN ({_placeholders(contract.source_unit_types)})")
        params.extend(contract.source_unit_types)
    if contract.content_roles:
        clauses.append(f"content_role IN ({_placeholders(contract.content_roles)})")
        params.extend(contract.content_roles)
    if not clauses:
        return 0
    row = connection.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM source_units
        WHERE doc_id = ?
          AND status NOT IN ('rejected', 'noise', 'ignored')
          AND ({' OR '.join(clauses)})
        """,
        params,
    ).fetchone()
    return int(row["count"] if row else 0)


def _fact_count(connection: Connection, doc_id: str, contract: KnowledgeTypeContract) -> int:
    if not contract.fact_types:
        return 0
    row = connection.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM facts
        WHERE source_doc_id = ?
          AND fact_status IN ('active', 'ready')
          AND fact_type IN ({_placeholders(contract.fact_types)})
        """,
        (doc_id, *contract.fact_types),
    ).fetchone()
    return int(row["count"] if row else 0)


def _linked_fact_unit_count(connection: Connection, doc_id: str, contract: KnowledgeTypeContract) -> int:
    if not contract.fact_types:
        return 0
    row = connection.execute(
        f"""
        SELECT COUNT(DISTINCT m.unit_id) AS count
        FROM source_unit_fact_map m
        JOIN source_units su ON su.unit_id = m.unit_id
        JOIN facts f ON f.fact_id = m.fact_id
        WHERE m.doc_id = ?
          AND su.status NOT IN ('rejected', 'noise', 'ignored')
          AND f.fact_status IN ('active', 'ready')
          AND f.fact_type IN ({_placeholders(contract.fact_types)})
        """,
        (doc_id, *contract.fact_types),
    ).fetchone()
    return int(row["count"] if row else 0)


def _linked_evidence_unit_count(connection: Connection, doc_id: str, contract: KnowledgeTypeContract) -> int:
    clauses: list[str] = []
    params: list[object] = [doc_id]
    if contract.source_unit_types:
        clauses.append(f"su.unit_type IN ({_placeholders(contract.source_unit_types)})")
        params.extend(contract.source_unit_types)
    if contract.content_roles:
        clauses.append(f"su.content_role IN ({_placeholders(contract.content_roles)})")
        params.extend(contract.content_roles)
    if not clauses:
        return 0
    row = connection.execute(
        f"""
        SELECT COUNT(DISTINCT m.unit_id) AS count
        FROM source_unit_evidence_map m
        JOIN source_units su ON su.unit_id = m.unit_id
        JOIN evidence e ON e.evidence_id = m.evidence_id
        WHERE m.doc_id = ?
          AND su.status NOT IN ('rejected', 'noise', 'ignored')
          AND ({' OR '.join(clauses)})
        """,
        params,
    ).fetchone()
    return int(row["count"] if row else 0)


def _golden_case_count(connection: Connection, doc_id: str, contract: KnowledgeTypeContract) -> int:
    shapes = _golden_shapes_for_contract(contract)
    if not shapes:
        return 0
    row = connection.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM golden_cases
        WHERE (doc_id = ? OR json_extract(metadata_json, '$.expected_doc_id') = ?)
          AND status NOT IN ('deprecated', 'rejected', 'inactive')
          AND expected_evidence_shape IN ({_placeholders(shapes)})
        """,
        (doc_id, doc_id, *shapes),
    ).fetchone()
    return int(row["count"] if row else 0)


def _golden_shapes_for_contract(contract: KnowledgeTypeContract) -> tuple[str, ...]:
    if contract.evidence_shape == "standard_metadata":
        return ("standard_metadata", "term_definition")
    if contract.evidence_shape == "requirement":
        return ("requirement", "parameter_definition", "process_activity")
    # test_method shapes overlap with process_activity and requirement —
    # test methods verify requirements and process steps.
    if contract.evidence_shape == "test_method":
        return ("process_activity", "requirement", "parameter_definition")
    # definition includes term_definition and concept_definition golden cases
    if contract.evidence_shape == "term_definition":
        return ("term_definition", "concept_definition")
    return (contract.evidence_shape,)


def _has_any_fact_type(connection: Connection, doc_id: str, fact_types: tuple[str, ...]) -> bool:
    row = connection.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM facts
        WHERE source_doc_id = ?
          AND fact_status IN ('active', 'ready')
          AND fact_type IN ({_placeholders(fact_types)})
        """,
        (doc_id, *fact_types),
    ).fetchone()
    return bool(row and int(row["count"] or 0))


def _placeholders(values: tuple[object, ...]) -> str:
    return ", ".join("?" for _ in values)


def compact_contract_summary(summary: dict[str, object]) -> dict[str, object]:
    contracts = summary.get("contracts") if isinstance(summary.get("contracts"), list) else []
    return {
        "status": summary.get("status"),
        "active_contract_count": summary.get("active_contract_count"),
        "failed_count": summary.get("failed_count"),
        "warn_count": summary.get("warn_count"),
        "active_evidence_shapes": summary.get("active_evidence_shapes"),
        "issue_counts": _issue_counts(contracts),
    }


def _issue_counts(contracts: list[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in contracts:
        if not isinstance(item, dict):
            continue
        if not item.get("active"):
            continue
        for issue in item.get("issues") or []:
            key = str(issue)
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
