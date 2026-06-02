from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppPaths
from .doc_diagnostics import build_document_diagnostics
from .knowledge_contracts import document_knowledge_contract_summary
from .quality import assess_document_quality, read_contract_status, read_coverage_rates


@dataclass(frozen=True)
class QualityWeights:
    parse_quality: float = 0.30
    knowledge_completeness: float = 0.25
    test_coverage: float = 0.25
    contract_compliance: float = 0.20


@dataclass(frozen=True)
class QualityGateResult:
    doc_id: str
    parse_quality_score: float
    knowledge_completeness_score: float
    test_coverage_score: float
    contract_compliance_score: float
    overall_score: float
    gate_status: str  # "passed" | "review_required" | "blocked"
    high_risk_page_count: int
    review_required_count: int
    blocked_count: int
    report_path: Path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def compute_quality_gate(
    workspace_root: Path,
    doc_id: str,
    weights: QualityWeights | None = None,
) -> QualityGateResult:
    """Compute a multi-dimensional quality gate score for a document.

    Combines parse quality, knowledge completeness, test coverage, and
    contract compliance into a single overall score and gate status.
    """
    if weights is None:
        weights = QualityWeights()

    # 1. Parse quality — from existing assess_document_quality
    quality_result = assess_document_quality(workspace_root, doc_id)
    parse_quality_score = quality_result.overall_score
    high_risk_page_count = quality_result.high_risk_page_count
    review_required_count = quality_result.review_required_count
    blocked_count = quality_result.blocked_count

    # 2. Knowledge completeness — from doc_diagnostics answerability_score
    try:
        diagnostics = build_document_diagnostics(workspace_root, doc_id)
        knowledge_completeness_score = float(
            diagnostics.get("coverage", {}).get("answerability_score", 0.0)
        )
    except (ValueError, OSError):
        knowledge_completeness_score = 0.0

    # 3. Test coverage — from coverage summary JSON
    coverage = read_coverage_rates(workspace_root, doc_id)
    test_coverage_score = coverage["test_coverage_rate"]

    # 4. Contract compliance — reflects whether each knowledge type is verified
    #    passed = fully verified, warn = partially (e.g. no golden case), failed = broken chain
    #    Score: passed contracts contribute 1.0, warned contribute 0.4, failed contribute 0.0
    contract = read_contract_status(workspace_root, doc_id)
    contract_active = int(contract.get("active_count") or 0)
    contract_failed = int(contract.get("failed_count") or 0)
    contract_warned = int(contract.get("warn_count") or 0)
    if contract_active > 0:
        contract_compliance_score = round(
            (contract_active - contract_failed - contract_warned) / contract_active
            + 0.4 * (contract_warned / contract_active),
            4,
        )
    else:
        contract_compliance_score = 0.0

    # Weighted overall score
    overall_score = (
        weights.parse_quality * parse_quality_score
        + weights.knowledge_completeness * knowledge_completeness_score
        + weights.test_coverage * test_coverage_score
        + weights.contract_compliance * contract_compliance_score
    )
    overall_score = round(max(0.0, min(1.0, overall_score)), 4)

    # Gate status determination
    # If any pages are blocked, the document is blocked.
    # If all component scores meet their minimum thresholds, the document passes
    # (no human review needed — the system is usable).
    # Otherwise, specific component gaps need attention (review_required).
    if blocked_count > 0:
        gate_status = "blocked"
    elif (
        parse_quality_score >= 0.9
        and knowledge_completeness_score >= 0.8
        and test_coverage_score >= 0.5
        and contract_compliance_score >= 0.8
    ):
        gate_status = "passed"
    else:
        gate_status = "review_required"

    # Persist the gate report
    paths = AppPaths.from_root(workspace_root)
    report = {
        "doc_id": doc_id,
        "generated_at": _utc_now(),
        "weights": {
            "parse_quality": weights.parse_quality,
            "knowledge_completeness": weights.knowledge_completeness,
            "test_coverage": weights.test_coverage,
            "contract_compliance": weights.contract_compliance,
        },
        "parse_quality_score": parse_quality_score,
        "knowledge_completeness_score": knowledge_completeness_score,
        "test_coverage_score": test_coverage_score,
        "contract_compliance_score": contract_compliance_score,
        "contract_pass_rate": float(contract["pass_rate"]),
        "contract_active_count": contract_active,
        "contract_warn_count": contract_warned,
        "overall_score": overall_score,
        "gate_status": gate_status,
        "high_risk_page_count": high_risk_page_count,
        "review_required_count": review_required_count,
        "blocked_count": blocked_count,
    }

    report_path = paths.quality_reports / f"{doc_id}.quality_gate.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return QualityGateResult(
        doc_id=doc_id,
        parse_quality_score=parse_quality_score,
        knowledge_completeness_score=knowledge_completeness_score,
        test_coverage_score=test_coverage_score,
        contract_compliance_score=contract_compliance_score,
        overall_score=overall_score,
        gate_status=gate_status,
        high_risk_page_count=high_risk_page_count,
        review_required_count=review_required_count,
        blocked_count=blocked_count,
        report_path=report_path,
    )


def repair_document_metadata(workspace_root: Path, doc_id: str) -> int:
    """Detect and backfill missing metadata facts for a document. Returns count of inserted facts."""
    from .db import connect
    from .facts import _extract_cover_metadata, _insert_metadata_facts

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        # Check which metadata fact types already exist
        existing: set[str] = set()
        for row in connection.execute(
            "SELECT DISTINCT fact_type FROM facts WHERE source_doc_id = ? AND fact_type LIKE 'document_%'",
            (doc_id,),
        ):
            existing.add(row["fact_type"])

        required = {"document_title", "document_standard", "document_lifecycle", "document_abstract"}
        missing = required - existing
        if not missing:
            return 0

        # Get first-page evidence text and source filename
        doc = connection.execute(
            "SELECT source_filename FROM documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        if doc is None:
            return 0

        first_page_rows = connection.execute(
            "SELECT normalized_text FROM evidence WHERE doc_id = ? AND page_no = 1 ORDER BY evidence_id LIMIT 5",
            (doc_id,),
        ).fetchall()
        first_page_text = "\n".join(r["normalized_text"] or "" for r in first_page_rows)

        # Run enhanced metadata extraction
        extracted = _extract_cover_metadata(first_page_text, doc["source_filename"])

        # Convert extracted results to a metadata dict
        metadata: dict[str, str] = {}
        for fact_type, predicate, obj in extracted:
            val = obj.get("value", "")
            if isinstance(val, str) and val:
                if fact_type == "document_title":
                    metadata["title"] = val
                elif fact_type == "document_standard":
                    metadata["standard_id"] = val
                elif fact_type == "document_lifecycle" and predicate == "publication_date":
                    metadata["publication_date"] = val
                elif fact_type == "document_abstract":
                    metadata["abstract"] = val

        if not metadata:
            return 0

        # Insert only the missing types
        inserted = _insert_metadata_facts(connection, doc_id, metadata, missing)
        if inserted > 0:
            connection.commit()
        return inserted
    finally:
        connection.close()


def repair_evidence_chains(workspace_root: Path, doc_id: str) -> int:
    """Backfill missing source_unit_fact_map entries. Returns count of fixed facts."""
    from .db import connect
    from .facts import _ensure_evidence_chains

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        fixed = _ensure_evidence_chains(connection, doc_id)
        if fixed > 0:
            connection.commit()
        return fixed
    finally:
        connection.close()
