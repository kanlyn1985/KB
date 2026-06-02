from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import AppPaths
from .db import connect
from .doc_diagnostics import build_document_diagnostics
from .knowledge_contracts import compact_contract_summary, document_knowledge_contract_summary


@dataclass(frozen=True)
class IngestionAcceptanceResult:
    doc_id: str
    status: str
    check_count: int
    passed_count: int
    failed_count: int
    warn_count: int
    checks: list[dict[str, object]]
    diagnostics: dict[str, object]
    knowledge_contracts: dict[str, object]
    json_path: Path
    report_path: Path

    def to_dict(self) -> dict[str, object]:
        return {
            "doc_id": self.doc_id,
            "status": self.status,
            "check_count": self.check_count,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "warn_count": self.warn_count,
            "checks": self.checks,
            "diagnostics": self.diagnostics,
            "knowledge_contracts": self.knowledge_contracts,
            "json_path": str(self.json_path),
            "report_path": str(self.report_path),
        }


def validate_document_ingestion(
    workspace_root: Path,
    doc_id: str,
    *,
    min_text_coverage: float = 0.9,
    min_semantic_coverage: float = 0.5,
    min_answerability: float = 0.5,
    min_test_coverage: float = 0.5,
    min_contract_pass_rate: float = 0.5,
    output_dir: Path | None = None,
) -> IngestionAcceptanceResult:
    paths = AppPaths.from_root(workspace_root)
    diagnostics = build_document_diagnostics(workspace_root, doc_id)
    knowledge_contracts = document_knowledge_contract_summary(paths.db_file, doc_id)
    db_counts = _load_db_counts(paths.db_file, doc_id)
    coverage = diagnostics.get("coverage") if isinstance(diagnostics.get("coverage"), dict) else {}
    counts = diagnostics.get("counts") if isinstance(diagnostics.get("counts"), dict) else {}
    artifacts = diagnostics.get("artifacts") if isinstance(diagnostics.get("artifacts"), dict) else {}
    checks = [
        _check("document_registered", bool(diagnostics.get("document")), "document row exists"),
        _check("pages_present", int(counts.get("page_count") or 0) > 0, "parsed page_count > 0", counts.get("page_count")),
        _check("blocks_present", db_counts["block_count"] > 0, "blocks count > 0", db_counts["block_count"]),
        _check("evidence_present", int(counts.get("evidence_count") or 0) > 0, "evidence count > 0", counts.get("evidence_count")),
        _check("facts_present", int(counts.get("fact_count") or 0) > 0, "facts count > 0", counts.get("fact_count")),
        _check("wiki_present", db_counts["wiki_page_count"] > 0, "wiki pages count > 0", db_counts["wiki_page_count"], severity="warn"),
        _check("source_units_present", int(coverage.get("source_unit_count") or 0) > 0, "source_units count > 0", coverage.get("source_unit_count")),
        _threshold_check("text_coverage_rate", coverage.get("text_coverage_rate"), min_text_coverage),
        _threshold_check("semantic_coverage_rate", coverage.get("semantic_coverage_rate"), min_semantic_coverage),
        _threshold_check("answerability_score", coverage.get("answerability_score"), min_answerability),
        _threshold_check("test_coverage_rate", coverage.get("test_coverage_rate"), min_test_coverage),
        _contract_pass_rate_check(knowledge_contracts, min_contract_pass_rate),
        _path_check("coverage_summary_exists", artifacts.get("coverage_summary_path")),
        _path_check("coverage_report_exists", artifacts.get("coverage_report_path")),
        _contract_check(knowledge_contracts),
    ]
    warnings = diagnostics.get("warnings") if isinstance(diagnostics.get("warnings"), list) else []
    checks.append(
        _check(
            "diagnostic_warnings",
            len(warnings) == 0,
            "document diagnostics has no warnings",
            warnings,
            severity="warn",
        )
    )
    failed_count = sum(1 for item in checks if item["status"] == "failed")
    warn_count = sum(1 for item in checks if item["status"] == "warn")
    passed_count = sum(1 for item in checks if item["status"] == "passed")
    status = "failed" if failed_count else ("warn" if warn_count else "passed")

    report_dir = output_dir or paths.root / "acceptance_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{doc_id}.ingestion_acceptance.json"
    report_path = report_dir / f"{doc_id}.ingestion_acceptance.md"
    payload = {
        "doc_id": doc_id,
        "status": status,
        "check_count": len(checks),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "warn_count": warn_count,
        "thresholds": {
            "min_text_coverage": min_text_coverage,
            "min_semantic_coverage": min_semantic_coverage,
            "min_answerability": min_answerability,
            "min_test_coverage": min_test_coverage,
            "min_contract_pass_rate": min_contract_pass_rate,
        },
        "checks": checks,
        "diagnostics": diagnostics,
        "knowledge_contracts": knowledge_contracts,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(_render_report(payload), encoding="utf-8")
    return IngestionAcceptanceResult(
        doc_id=doc_id,
        status=status,
        check_count=len(checks),
        passed_count=passed_count,
        failed_count=failed_count,
        warn_count=warn_count,
        checks=checks,
        diagnostics=diagnostics,
        knowledge_contracts=knowledge_contracts,
        json_path=json_path,
        report_path=report_path,
    )


def _load_db_counts(db_file: Path, doc_id: str) -> dict[str, int]:
    connection = connect(db_file)
    try:
        return {
            "block_count": int(connection.execute("SELECT COUNT(*) AS count FROM blocks WHERE doc_id = ?", (doc_id,)).fetchone()["count"]),
            "wiki_page_count": int(
                connection.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM wiki_pages
                    WHERE source_doc_ids_json LIKE ?
                    """,
                    (f"%{doc_id}%",),
                ).fetchone()["count"]
            ),
        }
    finally:
        connection.close()


def _check(name: str, passed: bool, expectation: str, actual: object | None = None, *, severity: str = "fail") -> dict[str, object]:
    if passed:
        status = "passed"
    elif severity == "warn":
        status = "warn"
    else:
        status = "failed"
    return {
        "name": name,
        "status": status,
        "expectation": expectation,
        "actual": actual,
    }


def _threshold_check(name: str, value: object, minimum: float, *, severity: str = "fail") -> dict[str, object]:
    try:
        actual = float(value or 0.0)
    except (TypeError, ValueError):
        actual = 0.0
    return _check(name, actual >= minimum, f">= {minimum}", actual, severity=severity)


def _path_check(name: str, value: object) -> dict[str, object]:
    path = Path(str(value or ""))
    return _check(name, path.exists(), "artifact path exists", str(path))


def _contract_pass_rate_check(summary: dict[str, object], min_pass_rate: float) -> dict[str, object]:
    """Check that the contract pass rate meets the minimum threshold."""
    active = int(summary.get("active_contract_count") or 0)
    failed = int(summary.get("failed_count") or 0)
    pass_rate = (1.0 - failed / active) if active > 0 else 0.0
    return _threshold_check("contract_pass_rate", round(pass_rate, 4), min_pass_rate)


def _contract_check(summary: dict[str, object]) -> dict[str, object]:
    status = str(summary.get("status") or "")
    compact = compact_contract_summary(summary)
    if status == "failed":
        return _check(
            "document_knowledge_contract",
            False,
            "active knowledge contracts have traceable source_units/evidence/facts",
            compact,
        )
    if status == "warn":
        return _check(
            "document_knowledge_contract",
            False,
            "active knowledge contracts have traceable source_units/evidence/facts",
            compact,
            severity="warn",
        )
    return _check(
        "document_knowledge_contract",
        status == "passed",
        "active knowledge contracts have traceable source_units/evidence/facts",
        compact,
    )


def _render_report(payload: dict[str, object]) -> str:
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    lines = [
        "# Document Ingestion Acceptance",
        "",
        f"- doc_id: {payload.get('doc_id')}",
        f"- status: {payload.get('status')}",
        f"- passed: {payload.get('passed_count')}",
        f"- warnings: {payload.get('warn_count')}",
        f"- failed: {payload.get('failed_count')}",
        "",
        "## Knowledge Contracts",
        "",
    ]
    contract_summary = payload.get("knowledge_contracts") if isinstance(payload.get("knowledge_contracts"), dict) else {}
    lines.extend(
        [
            f"- status: {contract_summary.get('status')}",
            f"- active_contract_count: {contract_summary.get('active_contract_count')}",
            f"- active_evidence_shapes: {', '.join(str(item) for item in contract_summary.get('active_evidence_shapes') or [])}",
            "",
        ]
    )
    for item in contract_summary.get("contracts") or []:
        if not isinstance(item, dict) or not item.get("active"):
            continue
        lines.append(
            "- {status}: {knowledge_type} | shape {shape} | source_units {source_units} | facts {facts} | golden {golden} | issues {issues}".format(
                status=item.get("status"),
                knowledge_type=item.get("knowledge_type"),
                shape=item.get("evidence_shape"),
                source_units=item.get("source_unit_count"),
                facts=item.get("fact_count"),
                golden=item.get("golden_case_count"),
                issues=", ".join(str(issue) for issue in item.get("issues") or []) or "-",
            )
        )
    lines.extend([
        "",
        "## Checks",
        "",
    ])
    for item in checks:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- {item.get('status')}: {item.get('name')} | expected {item.get('expectation')} | actual {item.get('actual')}"
        )
    lines.append("")
    return "\n".join(lines)
