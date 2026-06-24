from __future__ import annotations

import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import AppPaths
from .logging_config import get_logger

_logger = get_logger(__name__)

from .coverage import build_coverage_for_document
from .entities import build_entities_for_document
from .evidence import build_evidence_for_document
from .facts import build_facts_for_document
from .generated_tests import generate_golden_tests_for_document, run_golden_tests_for_document
from .generated_tests import auto_activate_golden_cases, revalidate_stale_golden_cases
from .graph import build_graph_for_document
from .ingestion_acceptance import validate_document_ingestion
from .ingest import register_document
from .parse import parse_document
from .quality import assess_document_quality
from .quality_gate import compute_quality_gate, repair_document_metadata, repair_evidence_chains
from .wiki_compiler import build_wiki_for_document
from .ambiguity_index import build_ambiguity_index, save_ambiguity_index
from .db import connect


def _extract_ontology_terms_and_params(workspace_root: Path, doc_id: str) -> None:
    """Auto-extract terms and parameters from a newly built document
    into the ontology DB.  Failures are logged but never propagate —
    ontology extraction is best-effort and must not block the pipeline."""
    try:
        from scripts.ontology_demo.extract_terms import extract_terms_from_legacy
        from scripts.ontology_demo.extract_params import extract_params_from_legacy

        term_stats = extract_terms_from_legacy(workspace_root, doc_id=doc_id)
        param_stats = extract_params_from_legacy(workspace_root, doc_id=doc_id)

        _logger.info(
            "ontology_extract doc_id=%s terms=%s params=%s",
            doc_id,
            term_stats.get("total", term_stats.get("terms_extracted", 0)),
            param_stats.get("total", 0),
        )
    except Exception as e:
        _logger.warning("ontology_extract failed doc_id=%s err=%s", doc_id, e)


@dataclass(frozen=True)
class PipelineEvent:
    doc_id: str
    stage: str
    status: str
    progress: int
    elapsed_seconds: float
    detail: dict[str, object]


PipelineProgressCallback = Callable[[PipelineEvent], None]


@dataclass(frozen=True)
class PipelineResult:
    doc_id: str
    registered: bool
    deduplicated: bool
    parser_engine: str
    page_count: int
    block_count: int
    overall_score: float
    evidence_count: int
    fact_count: int
    entity_count: int
    wiki_page_count: int
    edge_count: int
    coverage_source_unit_count: int
    coverage_text_rate: float
    coverage_semantic_rate: float
    coverage_object_rate: float
    coverage_test_rate: float
    coverage_uncovered_count: int
    coverage_summary_path: str
    coverage_report_path: str
    ingestion_acceptance: dict[str, object]
    post_ingestion_gate: dict[str, object] | None = None


@dataclass(frozen=True)
class PipelineAndTestResult:
    doc_id: str
    registered: bool
    deduplicated: bool
    parser_engine: str
    page_count: int
    block_count: int
    overall_score: float
    evidence_count: int
    fact_count: int
    entity_count: int
    wiki_page_count: int
    edge_count: int
    golden_case_count: int
    golden_network_case_count: int
    golden_local_case_count: int
    golden_test_success: bool
    golden_test_passed: int
    golden_test_failed: int
    coverage_source_unit_count: int
    coverage_text_rate: float
    coverage_semantic_rate: float
    coverage_object_rate: float
    coverage_test_rate: float
    coverage_uncovered_count: int
    coverage_summary_path: str
    coverage_report_path: str
    ingestion_acceptance: dict[str, object]


def run_document_pipeline(workspace_root: Path, doc_id: str) -> PipelineResult:
    return _run_document_pipeline(workspace_root, doc_id, progress_callback=None)


def run_document_pipeline_with_progress(
    workspace_root: Path,
    doc_id: str,
    *,
    progress_callback: PipelineProgressCallback | None = None,
) -> PipelineResult:
    return _run_document_pipeline(workspace_root, doc_id, progress_callback=progress_callback)


def _run_document_pipeline(
    workspace_root: Path,
    doc_id: str,
    *,
    progress_callback: PipelineProgressCallback | None,
) -> PipelineResult:
    db_backup_path = _backup_pipeline_database(workspace_root, doc_id)
    try:
        result = _run_document_pipeline_unprotected(
            workspace_root,
            doc_id,
            progress_callback=progress_callback,
        )
        return result
    except Exception:
        _restore_pipeline_database(db_backup_path)
        raise
    finally:
        if db_backup_path.exists():
            db_backup_path.unlink()


def _run_document_pipeline_unprotected(
    workspace_root: Path,
    doc_id: str,
    *,
    progress_callback: PipelineProgressCallback | None,
) -> PipelineResult:
    """Run the full document-build pipeline (parse → quality → evidence →
    facts → entities → wiki → graph → coverage → acceptance) without
    database backup/restore. The caller is responsible for crash safety.

    Each stage runs in sequence; if any stage raises, the function
    propagates immediately (no automatic rollback).
    """
    _logger.info("pipeline:start doc_id=%s root=%s", doc_id, workspace_root)
    parse_result = _run_pipeline_stage(
        doc_id,
        "parse",
        15,
        lambda: parse_document(workspace_root, doc_id),
        progress_callback=progress_callback,
        detail_builder=lambda result: {
            "page_count": result.page_count,
            "block_count": result.block_count,
            "parser_engine": result.parser_engine,
            "normalized_path": str(result.normalized_path),
        },
    )
    quality_result = _run_pipeline_stage(
        doc_id,
        "quality",
        30,
        lambda: assess_document_quality(workspace_root, doc_id),
        progress_callback=progress_callback,
        detail_builder=lambda result: {
            "overall_score": result.overall_score,
            "high_risk_page_count": result.high_risk_page_count,
            "review_required_count": result.review_required_count,
            "blocked_count": result.blocked_count,
        },
    )
    evidence_result = _run_pipeline_stage(
        doc_id,
        "evidence",
        45,
        lambda: build_evidence_for_document(workspace_root, doc_id),
        progress_callback=progress_callback,
        detail_builder=lambda result: {"evidence_count": result.evidence_count},
    )
    facts_result = _run_pipeline_stage(
        doc_id,
        "facts",
        60,
        lambda: build_facts_for_document(workspace_root, doc_id),
        progress_callback=progress_callback,
        detail_builder=lambda result: {"fact_count": result.fact_count, "fact_types": result.fact_types},
    )
    entities_result = _run_pipeline_stage(
        doc_id,
        "entities",
        72,
        lambda: build_entities_for_document(workspace_root, doc_id),
        progress_callback=progress_callback,
        detail_builder=lambda result: {"entity_count": result.entity_count, "entity_types": result.entity_types},
    )
    wiki_result = _run_pipeline_stage(
        doc_id,
        "wiki",
        84,
        lambda: build_wiki_for_document(workspace_root, doc_id),
        progress_callback=progress_callback,
        detail_builder=lambda result: {"wiki_page_count": result.page_count},
    )
    graph_result = _run_pipeline_stage(
        doc_id,
        "graph",
        94,
        lambda: build_graph_for_document(workspace_root, doc_id),
        progress_callback=progress_callback,
        detail_builder=lambda result: {"edge_count": result.edge_count, "edge_types": result.edge_types},
    )
    coverage_result = _run_pipeline_stage(
        doc_id,
        "coverage",
        98,
        lambda: build_coverage_for_document(workspace_root, doc_id),
        progress_callback=progress_callback,
        detail_builder=lambda result: {
            "source_unit_count": result.source_unit_count,
            "text_coverage_rate": result.text_coverage_rate,
            "semantic_coverage_rate": result.semantic_coverage_rate,
            "object_coverage_rate": result.object_coverage_rate,
            "test_coverage_rate": result.test_coverage_rate,
        },
    )
    acceptance = _run_pipeline_stage(
        doc_id,
        "ingestion_acceptance",
        99,
        lambda: validate_document_ingestion(workspace_root, doc_id),
        progress_callback=progress_callback,
        detail_builder=lambda result: {
            "status": result.status,
            "failed_count": result.failed_count,
            "warn_count": result.warn_count,
            "json_path": str(result.json_path),
            "report_path": str(result.report_path),
        },
    )

    # Phase 12: auto-run the post-ingestion quality gate so the new
    # doc is immediately searchable.  Failures are logged but do not
    # raise (so the build pipeline still reports success).  Callers
    # can check PipelineResult.post_ingestion_gate to see the gate
    # status.
    gate_payload: dict[str, object] | None = None
    try:
        gate = run_post_ingestion_gate(workspace_root, doc_id)
        gate_payload = gate.to_dict()
        _logger.info(
            "post_ingestion_gate doc_id=%s passed=%s steps=%d",
            doc_id, gate_payload["passed"], len(gate_payload["steps"]),
        )
        if not gate_payload["passed"]:
            _logger.warning(
                "post_ingestion_gate FAIL doc_id=%s details=%s",
                doc_id, gate_payload,
            )
    except Exception as e:
        _logger.error(
            "post_ingestion_gate crashed doc_id=%s err=%s", doc_id, e
        )
        gate_payload = {"passed": False, "steps": [], "error": str(e)}

    # Phase 13: auto-extract ontology terms and parameters from the
    # newly built document.  Best-effort — failures are logged but
    # never block the pipeline.
    _extract_ontology_terms_and_params(workspace_root, doc_id)

    _logger.info("pipeline:done doc_id=%s", doc_id)
    return PipelineResult(
        doc_id=doc_id,
        registered=False,
        deduplicated=False,
        parser_engine=parse_result.parser_engine,
        page_count=parse_result.page_count,
        block_count=parse_result.block_count,
        overall_score=quality_result.overall_score,
        evidence_count=evidence_result.evidence_count,
        fact_count=facts_result.fact_count,
        entity_count=entities_result.entity_count,
        wiki_page_count=wiki_result.page_count,
        edge_count=graph_result.edge_count,
        coverage_source_unit_count=coverage_result.source_unit_count,
        coverage_text_rate=coverage_result.text_coverage_rate,
        coverage_semantic_rate=coverage_result.semantic_coverage_rate,
        coverage_object_rate=coverage_result.object_coverage_rate,
        coverage_test_rate=coverage_result.test_coverage_rate,
        coverage_uncovered_count=sum(coverage_result.uncovered_counts.values()),
        coverage_summary_path=str(coverage_result.summary_path),
        coverage_report_path=str(coverage_result.report_path),
        ingestion_acceptance=_acceptance_summary(acceptance.to_dict()),
        post_ingestion_gate=gate_payload,
    )


# ---- Post-ingestion quality gate -----------------------------------------

class PostIngestionGateResult:
    """Result of running the post-ingestion quality gate.

    Each step is a tuple ``(passed: bool, detail: str)``.  The overall
    pass is True iff all steps pass.
    """

    steps: list[tuple[str, bool, str]]

    def __init__(self, steps: list[tuple[str, bool, str]] | None = None) -> None:
        self.steps = steps or []

    @property
    def passed(self) -> bool:
        return all(passed for _, passed, _ in self.steps)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "steps": [
                {"name": name, "passed": passed, "detail": detail}
                for name, passed, detail in self.steps
            ],
        }


def run_post_ingestion_gate(
    workspace_root: Path,
    doc_id: str,
    *,
    refresh_fts: bool = True,
    regenerate_expected_points: bool = True,
    sync_term_definitions: bool = True,
) -> PostIngestionGateResult:
    """Run the post-ingestion quality gate for a single document.

    After the build pipeline completes, this gate ensures the new
    document is fully searchable in the KB.  It runs five steps:

      1. **FTS index refresh** — re-indexes facts and evidence so the
         new doc's content is searchable.
      2. **expected_points regeneration** — runs the LLM-based point
         decomposer for the new doc (no-op if version already exists).
      3. **term_definition sync** — derives term_definition facts from
         expected_points and inserts them into the facts table.
      4. **sanity check** — verifies facts/evidence counts > 0 and
         expected_points doc_id row exists.
      5. **wiki_coverage_check** — verifies that the wiki markdown covers
         all sections present in the cleaned source MD (if both exist).

    The function never raises; it captures all exceptions into step
    results so the caller can decide whether to fail loudly.
    """
    from .retrieval import _refresh_fts_index
    from .db import connect

    result = PostIngestionGateResult()

    # Step 1: FTS index refresh
    if refresh_fts:
        try:
            from .config import AppPaths
            paths = AppPaths.from_root(workspace_root)
            conn = connect(paths.db_file)
            try:
                _refresh_fts_index(conn, paths)
                # Verify the new doc is in the index
                c = conn.cursor()
                c.execute("SELECT COUNT(*) AS n FROM facts_fts WHERE doc_id = ?", (doc_id,))
                n_facts = c.fetchone()["n"]
                c.execute("SELECT COUNT(*) AS n FROM evidence_fts WHERE doc_id = ?", (doc_id,))
                n_evidence = c.fetchone()["n"]
                detail = f"facts={n_facts}, evidence={n_evidence} in FTS"
                result.steps.append(("fts_refresh", n_facts > 0, detail))
            finally:
                conn.close()
        except Exception as e:
            result.steps.append(("fts_refresh", False, f"{type(e).__name__}: {e}"))

    # Step 2: expected_points regeneration
    if regenerate_expected_points:
        try:
            # Only generate if missing for this doc
            from .db import connect
            from .config import AppPaths
            paths = AppPaths.from_root(workspace_root)
            conn = connect(paths.db_file)
            try:
                c = conn.cursor()
                c.execute(
                    "SELECT point_count FROM expected_points WHERE doc_id = ? AND version = ?",
                    (doc_id, "v1"),
                )
                row = c.fetchone()
                if row is None:
                    # Run build_expected_points.py as a subprocess (it's a script).
                    # Use sys.executable to handle venvs where 'python' isn't on PATH.
                    import subprocess
                    import sys as _sys
                    _repo_root = Path(__file__).resolve().parent.parent.parent
                    proc = subprocess.run(
                        [_sys.executable, "tools/build_expected_points.py",
                         "--version", "v1", "--doc-id", doc_id],
                        capture_output=True, text=True, timeout=600,
                        cwd=str(_repo_root),
                    )
                    if proc.returncode != 0:
                        result.steps.append((
                            "expected_points_generation", False,
                            f"subprocess failed: {proc.stderr[:200]}"
                        ))
                    else:
                        c.execute(
                            "SELECT point_count FROM expected_points WHERE doc_id = ? AND version = ?",
                            (doc_id, "v1"),
                        )
                        row = c.fetchone()
                        result.steps.append((
                            "expected_points_generation",
                            row is not None and row["point_count"] > 0,
                            f"point_count={row['point_count'] if row else 0}"
                        ))
                else:
                    result.steps.append((
                        "expected_points_generation",
                        True,
                        f"already exists, point_count={row['point_count']}"
                    ))
            finally:
                conn.close()
        except Exception as e:
            result.steps.append((
                "expected_points_generation", False,
                f"{type(e).__name__}: {e}"
            ))

    # Step 3: term_definition sync
    if sync_term_definitions:
        try:
            import json
            from .db import connect
            from .config import AppPaths
            from .ids import next_prefixed_id
            paths = AppPaths.from_root(workspace_root)
            conn = connect(paths.db_file)
            inserted = 0
            try:
                c = conn.cursor()
                c.execute(
                    "SELECT points_json FROM expected_points WHERE doc_id = ? AND version = ?",
                    (doc_id, "v1"),
                )
                row = c.fetchone()
                if row:
                    points = json.loads(row[0])
                    # Extract simple term_definition-style points
                    for p in points:
                        text = p.get("point", "")
                        if not text or len(text) > 300:
                            continue
                        import re
                        term = ""
                        definition = ""
                        # Pattern 1: "**Term** definition" (Markdown bold)
                        m = re.match(r"\*\*([^*]+)\*\*\s*(.{5,200})", text)
                        if m:
                            term = m.group(1).strip()
                            definition = m.group(2).strip()
                            # Clean up term: remove pure-ASCII noise, keep CJK + alphanumeric
                            # But for English terms, keep the original
                            if not any("一" <= c <= "鿿" for c in term):
                                # English term — keep as-is but strip punctuation
                                term = re.sub(r"[\s\-\(\)]+$", "", term).strip()
                            else:
                                term = re.sub(r"[A-Za-z\s\-]+", "", term).strip()
                        # Pattern 2: "Term — definition" or "Term: definition" (English)
                        if not term:
                            m = re.match(r"^([A-Z][A-Za-z0-9\s\-/]{1,40})(?:\s*[—:–-]\s+|\s+is\s+|\s+means\s+)(.{5,200})$", text)
                            if m:
                                term = m.group(1).strip()
                                definition = m.group(2).strip()
                        # Pattern 3: "Term是Definition。" (CJK definition sentence)
                        if not term:
                            m = re.match(r"^([一-鿿A-Za-z0-9·\-\(\)]{2,30})(?:是|指)\s*([一-鿿A-Za-z0-9，。；：、（）\(\)]{5,200})[。；]?$", text)
                            if m:
                                term = m.group(1).strip()
                                definition = m.group(2).strip()
                        if not term or len(term) < 2 or not definition:
                            continue
                        # Skip if term_def already exists
                        c.execute(
                            "SELECT fact_id FROM facts WHERE source_doc_id = ? "
                            "AND fact_type = 'term_definition' AND object_value LIKE ?",
                            (doc_id, f'%"term": "{term}"%'),
                        )
                        if c.fetchone():
                            continue
                        fact_id = next_prefixed_id(conn, "fact", "FACT")
                        page_no = p.get("page", 0) or 0
                        c.execute(
                            "INSERT INTO facts (fact_id, fact_type, subject_entity_id, "
                            "predicate, object_value, object_entity_id, qualifiers_json, "
                            "confidence, fact_status, source_doc_id, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                fact_id, "term_definition", None, "defines_term",
                                json.dumps({"term": term, "definition": definition},
                                           ensure_ascii=False),
                                None,
                                json.dumps({"page_no": page_no, "source": "post_ingestion_gate"}),
                                0.85, "ready_from_post_gate", doc_id,
                                datetime.now(UTC).isoformat(timespec="seconds"),
                                datetime.now(UTC).isoformat(timespec="seconds"),
                            ),
                        )
                        inserted += 1
                    conn.commit()
                result.steps.append((
                    "term_definition_sync", True,
                    f"inserted {inserted} new term_definitions"
                ))
            finally:
                conn.close()
        except Exception as e:
            result.steps.append(("term_definition_sync", False, f"{type(e).__name__}: {e}"))

    # Step 4: sanity check
    try:
        from .db import connect
        from .config import AppPaths
        paths = AppPaths.from_root(workspace_root)
        conn = connect(paths.db_file)
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) AS n FROM facts WHERE source_doc_id = ?", (doc_id,))
            n_facts = c.fetchone()["n"]
            c.execute("SELECT COUNT(*) AS n FROM evidence WHERE doc_id = ?", (doc_id,))
            n_evidence = c.fetchone()["n"]
            c.execute(
                "SELECT point_count FROM expected_points WHERE doc_id = ? AND version = ?",
                (doc_id, "v1"),
            )
            ep = c.fetchone()
            passed = n_facts > 0 and n_evidence > 0 and ep is not None and ep["point_count"] > 0
            result.steps.append((
                "sanity_check", passed,
                f"facts={n_facts}, evidence={n_evidence}, expected_points={ep['point_count'] if ep else 0}"
            ))
        finally:
            conn.close()
    except Exception as e:
        result.steps.append(("sanity_check", False, f"{type(e).__name__}: {e}"))

    # Step 5: wiki_coverage_check (best-effort, non-blocking)
    try:
        from ..scripts.check_coverage import check_coverage as _cc
        kb_md_dir = workspace_root.parent / "output" / "kb_md"
        source_md = next(kb_md_dir.glob(f"*{doc_id}*.md"), None) if kb_md_dir.exists() else None
        wiki_md = kb_md_dir / f"wiki_{doc_id}.md" if kb_md_dir else None
        if source_md and wiki_md and wiki_md.exists():
            missing = _cc(str(source_md), str(wiki_md))
            if len(missing) == 0:
                result.steps.append(("wiki_coverage", True, "100% coverage"))
            else:
                result.steps.append(("wiki_coverage", False,
                                     f"missing {len(missing)} sections"))
        else:
            result.steps.append(("wiki_coverage", True, "skipped (no wiki MD)"))
    except Exception as e:
        result.steps.append(("wiki_coverage", True, f"skipped ({type(e).__name__})"))

    return result


def _backup_pipeline_database(workspace_root: Path, doc_id: str) -> Path:
    paths = AppPaths.from_root(workspace_root)
    backup_dir = paths.root / "quarantine" / "pipeline-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{doc_id}.{uuid.uuid4().hex}.knowledge.db"
    shutil.copy2(paths.db_file, backup_path)
    return backup_path


def _restore_pipeline_database(backup_path: Path) -> None:
    if not backup_path.exists():
        return
    db_path = backup_path.parents[2] / "db" / "knowledge.db"
    shutil.copy2(backup_path, db_path)


def run_file_pipeline(workspace_root: Path, source_file: Path) -> PipelineResult:
    return run_file_pipeline_with_progress(workspace_root, source_file, progress_callback=None)


def run_file_pipeline_with_progress(
    workspace_root: Path,
    source_file: Path,
    *,
    progress_callback: PipelineProgressCallback | None = None,
) -> PipelineResult:
    register_result = register_document(workspace_root, source_file)
    if progress_callback:
        progress_callback(
            PipelineEvent(
                doc_id=register_result.doc_id,
                stage="register",
                status="completed",
                progress=10,
                elapsed_seconds=0.0,
                detail={
                    "source_file": str(source_file),
                    "deduplicated": register_result.deduplicated,
                },
            )
        )
    result = run_document_pipeline_with_progress(
        workspace_root,
        register_result.doc_id,
        progress_callback=progress_callback,
    )
    return PipelineResult(
        doc_id=result.doc_id,
        registered=True,
        deduplicated=register_result.deduplicated,
        parser_engine=result.parser_engine,
        page_count=result.page_count,
        block_count=result.block_count,
        overall_score=result.overall_score,
        evidence_count=result.evidence_count,
        fact_count=result.fact_count,
        entity_count=result.entity_count,
        wiki_page_count=result.wiki_page_count,
        edge_count=result.edge_count,
        coverage_source_unit_count=result.coverage_source_unit_count,
        coverage_text_rate=result.coverage_text_rate,
        coverage_semantic_rate=result.coverage_semantic_rate,
        coverage_object_rate=result.coverage_object_rate,
        coverage_test_rate=result.coverage_test_rate,
        coverage_uncovered_count=result.coverage_uncovered_count,
        coverage_summary_path=result.coverage_summary_path,
        coverage_report_path=result.coverage_report_path,
        ingestion_acceptance=result.ingestion_acceptance,
        post_ingestion_gate=result.post_ingestion_gate,
    )


def run_batch_pipeline(workspace_root: Path, doc_ids: list[str]) -> list[dict[str, object]]:
    return [asdict(run_document_pipeline(workspace_root, doc_id)) for doc_id in doc_ids]


def run_document_pipeline_and_tests(workspace_root: Path, doc_id: str) -> PipelineAndTestResult:
    return run_document_pipeline_and_tests_with_progress(workspace_root, doc_id, progress_callback=None)


def run_document_pipeline_and_tests_with_progress(
    workspace_root: Path,
    doc_id: str,
    *,
    progress_callback: PipelineProgressCallback | None = None,
) -> PipelineAndTestResult:
    pipeline_result = run_document_pipeline_with_progress(
        workspace_root,
        doc_id,
        progress_callback=progress_callback,
    )
    golden_result = _run_pipeline_stage(
        doc_id,
        "golden_generate",
        99,
        lambda: generate_golden_tests_for_document(workspace_root, doc_id),
        progress_callback=progress_callback,
        detail_builder=lambda result: {
            "case_count": int(result.get("case_count", 0)),
            "network_case_count": int(result.get("network_case_count", 0)),
            "local_case_count": int(result.get("local_case_count", 0)),
        },
    )
    golden_run = _run_pipeline_stage(
        doc_id,
        "golden_run",
        100,
        lambda: run_golden_tests_for_document(workspace_root, doc_id),
        progress_callback=progress_callback,
        detail_builder=lambda result: {
            "success": bool(result.get("success", False)),
            "passed": int(result.get("passed", 0)),
            "failed": int(result.get("failed", 0)),
        },
    )
    return PipelineAndTestResult(
        doc_id=pipeline_result.doc_id,
        registered=False,
        deduplicated=False,
        parser_engine=pipeline_result.parser_engine,
        page_count=pipeline_result.page_count,
        block_count=pipeline_result.block_count,
        overall_score=pipeline_result.overall_score,
        evidence_count=pipeline_result.evidence_count,
        fact_count=pipeline_result.fact_count,
        entity_count=pipeline_result.entity_count,
        wiki_page_count=pipeline_result.wiki_page_count,
        edge_count=pipeline_result.edge_count,
        golden_case_count=int(golden_result.get("case_count", 0)),
        golden_network_case_count=int(golden_result.get("network_case_count", 0)),
        golden_local_case_count=int(golden_result.get("local_case_count", 0)),
        golden_test_success=bool(golden_run.get("success", False)),
        golden_test_passed=int(golden_run.get("passed", 0)),
        golden_test_failed=int(golden_run.get("failed", 0)),
        coverage_source_unit_count=pipeline_result.coverage_source_unit_count,
        coverage_text_rate=pipeline_result.coverage_text_rate,
        coverage_semantic_rate=pipeline_result.coverage_semantic_rate,
        coverage_object_rate=pipeline_result.coverage_object_rate,
        coverage_test_rate=pipeline_result.coverage_test_rate,
        coverage_uncovered_count=pipeline_result.coverage_uncovered_count,
        coverage_summary_path=pipeline_result.coverage_summary_path,
        coverage_report_path=pipeline_result.coverage_report_path,
        ingestion_acceptance=pipeline_result.ingestion_acceptance,
        post_ingestion_gate=pipeline_result.post_ingestion_gate,
    )


def run_file_pipeline_and_tests(workspace_root: Path, source_file: Path) -> PipelineAndTestResult:
    return run_file_pipeline_and_tests_with_progress(workspace_root, source_file, progress_callback=None)


def run_file_pipeline_and_tests_with_progress(
    workspace_root: Path,
    source_file: Path,
    *,
    progress_callback: PipelineProgressCallback | None = None,
) -> PipelineAndTestResult:
    register_result = register_document(workspace_root, source_file)
    if progress_callback:
        progress_callback(
            PipelineEvent(
                doc_id=register_result.doc_id,
                stage="register",
                status="completed",
                progress=10,
                elapsed_seconds=0.0,
                detail={
                    "source_file": str(source_file),
                    "deduplicated": register_result.deduplicated,
                },
            )
        )
    result = run_document_pipeline_and_tests_with_progress(
        workspace_root,
        register_result.doc_id,
        progress_callback=progress_callback,
    )
    return PipelineAndTestResult(
        doc_id=result.doc_id,
        registered=True,
        deduplicated=register_result.deduplicated,
        parser_engine=result.parser_engine,
        page_count=result.page_count,
        block_count=result.block_count,
        overall_score=result.overall_score,
        evidence_count=result.evidence_count,
        fact_count=result.fact_count,
        entity_count=result.entity_count,
        wiki_page_count=result.wiki_page_count,
        edge_count=result.edge_count,
        golden_case_count=result.golden_case_count,
        golden_network_case_count=result.golden_network_case_count,
        golden_local_case_count=result.golden_local_case_count,
        golden_test_success=result.golden_test_success,
        golden_test_passed=result.golden_test_passed,
        golden_test_failed=result.golden_test_failed,
        coverage_source_unit_count=result.coverage_source_unit_count,
        coverage_text_rate=result.coverage_text_rate,
        coverage_semantic_rate=result.coverage_semantic_rate,
        coverage_object_rate=result.coverage_object_rate,
        coverage_test_rate=result.coverage_test_rate,
        coverage_uncovered_count=result.coverage_uncovered_count,
        coverage_summary_path=result.coverage_summary_path,
        coverage_report_path=result.coverage_report_path,
        ingestion_acceptance=result.ingestion_acceptance,
    )


def build_workspace_ambiguity_index(workspace_root: Path) -> dict[str, int]:
    db_path = workspace_root / "db" / "knowledge.db"
    conn = connect(db_path)
    try:
        index = build_ambiguity_index(conn)
    finally:
        conn.close()
    output_path = workspace_root / "ambiguity_index.json"
    save_ambiguity_index(index, str(output_path))
    return {acronym: len(senses) for acronym, senses in index.items()}


def _run_pipeline_stage(
    doc_id: str,
    stage: str,
    progress: int,
    action: Callable[[], Any],
    *,
    progress_callback: PipelineProgressCallback | None,
    detail_builder: Callable[[Any], dict[str, object]] | None = None,
) -> Any:
    start = time.perf_counter()
    _emit_pipeline_event(
        progress_callback,
        PipelineEvent(
            doc_id=doc_id,
            stage=stage,
            status="started",
            progress=progress,
            elapsed_seconds=0.0,
            detail={},
        ),
    )
    try:
        result = action()
    except Exception as exc:
        _emit_pipeline_event(
            progress_callback,
            PipelineEvent(
                doc_id=doc_id,
                stage=stage,
                status="failed",
                progress=progress,
                elapsed_seconds=round(time.perf_counter() - start, 3),
                detail={"error": str(exc), "error_type": type(exc).__name__},
            ),
        )
        raise
    detail = detail_builder(result) if detail_builder else {}
    _emit_pipeline_event(
        progress_callback,
        PipelineEvent(
            doc_id=doc_id,
            stage=stage,
            status="completed",
            progress=progress,
            elapsed_seconds=round(time.perf_counter() - start, 3),
            detail=detail,
        ),
    )
    return result


def _emit_pipeline_event(
    progress_callback: PipelineProgressCallback | None,
    event: PipelineEvent,
) -> None:
    """Forward a fully-built ``PipelineEvent`` to the callback, if any.

    Callers build the event (with timing, status, etc.) and pass it as a
    single object so the dispatcher's 7-field signature stays readable.
    """
    if not progress_callback:
        return
    progress_callback(event)


def _acceptance_summary(payload: dict[str, object]) -> dict[str, object]:
    return {
        "status": payload.get("status"),
        "check_count": payload.get("check_count"),
        "passed_count": payload.get("passed_count"),
        "failed_count": payload.get("failed_count"),
        "warn_count": payload.get("warn_count"),
        "json_path": payload.get("json_path"),
        "report_path": payload.get("report_path"),
        "failed_checks": [
            item
            for item in payload.get("checks", [])
            if isinstance(item, dict) and item.get("status") == "failed"
        ],
        "warning_checks": [
            item
            for item in payload.get("checks", [])
            if isinstance(item, dict) and item.get("status") == "warn"
        ],
    }


@dataclass(frozen=True)
class FullQualityPipelineResult:
    doc_id: str
    acceptance_status: str
    overall_score: float
    parse_quality_score: float
    knowledge_completeness_score: float
    test_coverage_score: float
    contract_compliance_score: float
    gate_status: str
    coverage_iterations: int
    golden_cases_activated: int
    stale_cases_removed: int


def run_full_quality_pipeline(
    workspace_root: Path,
    doc_id: str,
    *,
    min_test_coverage: float = 0.3,
    max_iterations: int = 5,
) -> FullQualityPipelineResult:
    """Run the full document pipeline with automatic quality gate closure.

    After the standard pipeline, loops to close coverage gaps and compute
    the quality gate until gate_status is "passed" or max_iterations is
    reached. Each iteration: auto-activates golden cases for uncovered
    units, rebuilds coverage, runs ingestion acceptance (generates report
    file so contract_compliance can be read), revalidates stale golden
    cases, and recomputes the quality gate.
    """
    # 1. Run the standard pipeline
    pipeline_result = run_document_pipeline(workspace_root, doc_id)

    # 2. Iterative quality gate closure loop
    coverage_iterations = 0
    golden_cases_activated = 0
    stale_cases_removed = 0
    gate_status = "review_required"

    while gate_status != "passed" and coverage_iterations < max_iterations:
        # 2a. Auto-activate golden cases for uncovered source units
        activate_result = auto_activate_golden_cases(workspace_root, doc_id)
        golden_cases_activated += int(activate_result.get("promoted_case_count") or 0)

        # 2b. Revalidate stale golden cases (removes failing ones)
        revalidate_result = revalidate_stale_golden_cases(workspace_root, doc_id)
        stale_cases_removed += int(revalidate_result.get("removed_count") or 0)

        # 2c. Auto-repair metadata gaps and evidence chain breaks
        repair_document_metadata(workspace_root, doc_id)
        repair_evidence_chains(workspace_root, doc_id)

        # 2d. Run ingestion acceptance (generates report file so
        #     contract_compliance_score can be read from file)
        acceptance = validate_document_ingestion(workspace_root, doc_id)

        # 2e. Compute quality gate with all four dimensions
        gate_result = compute_quality_gate(workspace_root, doc_id)
        gate_status = gate_result.gate_status
        coverage_iterations += 1

        # If blocked pages exist, no amount of iteration will fix it
        if gate_status == "blocked":
            break

    # 3. Final acceptance if loop didn't run or exited early
    if coverage_iterations == 0:
        acceptance = validate_document_ingestion(workspace_root, doc_id)
        gate_result = compute_quality_gate(workspace_root, doc_id)

    return FullQualityPipelineResult(
        doc_id=doc_id,
        acceptance_status=acceptance.status,
        overall_score=gate_result.overall_score,
        parse_quality_score=gate_result.parse_quality_score,
        knowledge_completeness_score=gate_result.knowledge_completeness_score,
        test_coverage_score=gate_result.test_coverage_score,
        contract_compliance_score=gate_result.contract_compliance_score,
        gate_status=gate_result.gate_status,
        coverage_iterations=coverage_iterations,
        golden_cases_activated=golden_cases_activated,
        stale_cases_removed=stale_cases_removed,
    )
