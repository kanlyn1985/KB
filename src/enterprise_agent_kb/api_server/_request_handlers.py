"""HTTP request handler: route dispatch, body parsing, response formatting.

Extracted from `api_server._impl` to isolate the
`ApiRequestHandler` class (which is a tightly-coupled base class
specialization) and its call-time name resolver for tests that
patch the api_server module's parse_risk_actions symbols.
"""
from __future__ import annotations

import json
import sys as _sys
import tempfile
import base64
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from datetime import UTC, datetime

from ..agent_tools import run_agent_query
from ..answer_api import answer_query
from ..answer_feedback import submit_feedback, reflect_on_feedback, list_answer_feedback, get_feedback_detail
from ..exceptions import NetworkError, ValidationError
from ..logging_config import get_logger
from ..closed_loop_store import (
    activate_golden_case_draft,
    backfill_eval_run_scope_metadata,
    backfill_source_unit_mappings_from_metadata,
    build_failure_analysis,
    compare_eval_runs,
    draft_golden_case_from_failure,
    draft_golden_cases_from_eval_failures,
    get_eval_run_detail,
    get_retrieval_run_detail,
    ensure_source_unit_mapping_tables,
    list_golden_cases,
    list_eval_runs,
    list_repair_tasks,
    list_retrieval_runs,
    update_repair_task_status,
)
from ..config import AppPaths
from ._health_snapshots import _body_string_list
from ..coverage import build_test_gap_candidates_for_document
from ..doc_diagnostics import build_document_diagnostics
from ..generated_tests import (
    generate_coverage_test_drafts_for_document,
    generate_golden_tests_for_document,
    promote_coverage_test_drafts_for_document,
    run_coverage_promoted_tests_for_document,
    run_golden_tests_for_document,
    validate_coverage_test_drafts_for_document,
)
from ..golden_generation import generate_golden_candidates
from ..pipeline import PipelineEvent, run_document_pipeline, run_document_pipeline_and_tests, run_document_pipeline_with_progress
from ..parse import parse_document
from ..parse_risk_history import summarize_parse_risk_history
from ..parse_views import list_parse_view_pages
from ..quality import assess_document_quality
from ..evidence import build_evidence_for_document
from ..facts import build_facts_for_document
from ..entities import build_entities_for_document
from ..wiki_compiler import build_wiki_for_document
from ..graph import build_graph_for_document
from ..ingest import register_document
from ..ingestion_acceptance import validate_document_ingestion
from ..query_api import build_query_context
from ..retrieval import search_knowledge_base
from ..workspace_doctor import run_workspace_doctor
from ..db import connect
from .. import __version__

_PARENT_PACKAGE = "enterprise_agent_kb.api_server"


def _resolve(name: str):  # noqa: ANN202
    return getattr(_sys.modules[_PARENT_PACKAGE], name)

class ApiServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], workspace_root: Path):
        self.workspace_root = workspace_root
        self.project_root = Path(__file__).resolve().parents[2]
        self.started_at = datetime.now(UTC).isoformat(timespec="seconds")
        self.jobs: dict[str, dict[str, Any]] = {}
        self.jobs_lock = threading.Lock()
        self.audit_log_path = self.workspace_root / "logs" / "audit_log.jsonl"
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_lock = threading.Lock()
        super().__init__(server_address, ApiRequestHandler)


class ApiRequestHandler(BaseHTTPRequestHandler):
    server: ApiServer

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._write_common_headers("application/json; charset=utf-8", 0)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "server": {
                        "name": "enterprise-agent-kb",
                        "version": __version__,
                        "started_at": self.server.started_at,
                        "workspace_root": str(self.server.workspace_root),
                    },
                },
            )
            return
        if parsed.path == "/documents":
            self._write_json(HTTPStatus.OK, {"documents": self._list_documents()})
            return
        if parsed.path == "/jobs":
            self._write_json(HTTPStatus.OK, {"jobs": self._list_jobs()})
            return
        if parsed.path == "/audit-log":
            self._write_json(HTTPStatus.OK, {"events": self._read_audit_events()})
            return
        if parsed.path == "/closed-loop-dashboard":
            self._write_json(HTTPStatus.OK, self._closed_loop_dashboard())
            return
        if parsed.path == "/favicon.ico":
            favicon_svg = (
                "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
                "<rect width='32' height='32' rx='9' fill='#2563eb'/>"
                "<path d='M9 8h4v7l6-7h5l-7 8 7 8h-5l-6-7v7H9V8z' fill='white'/>"
                "</svg>"
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self._write_common_headers("image/svg+xml; charset=utf-8", len(favicon_svg))
            self.end_headers()
            self.wfile.write(favicon_svg)
            return
        if parsed.path in {"/", "/demo"}:
            self._write_file(self.server.project_root / "examples" / "demo.html", "text/html; charset=utf-8")
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        body = self._read_json_body()
        if body is None:
            return

        routes = {
            "/search": self._handle_search,
            "/query-context": self._handle_query_context,
            "/answer-query": self._handle_answer_query,
            "/agent-query": self._handle_agent_query,
            "/build-document": self._handle_build_document,
            "/build-document-and-test": self._handle_build_document_and_test,
            "/convert-document": self._handle_convert_document,
            "/upload-build": self._handle_upload_build,
            "/upload-build-and-test": self._handle_upload_build_and_test,
            "/upload-convert": self._handle_upload_convert,
            "/start-build-document": self._handle_start_build_document,
            "/start-build-document-and-test": self._handle_start_build_document_and_test,
            "/start-convert-document": self._handle_start_convert_document,
            "/start-upload-build": self._handle_start_upload_build,
            "/start-upload-build-and-test": self._handle_start_upload_build_and_test,
            "/start-upload-convert": self._handle_start_upload_convert,
            "/job-status": self._handle_job_status,
            "/document-detail": self._handle_document_detail,
            "/document-diagnostics": self._handle_document_diagnostics,
            "/parse-risk-actions": self._handle_parse_risk_actions,
            "/parse-risk-repair-review": self._handle_parse_risk_repair_review,
            "/parse-view-detail": self._handle_parse_view_detail,
            "/validate-document-ingestion": self._handle_validate_document_ingestion,
            "/coverage-test-gaps": self._handle_coverage_test_gaps,
            "/generate-coverage-test-drafts": self._handle_generate_coverage_test_drafts,
            "/validate-coverage-test-drafts": self._handle_validate_coverage_test_drafts,
            "/promote-coverage-test-drafts": self._handle_promote_coverage_test_drafts,
            "/run-coverage-promoted-tests": self._handle_run_coverage_promoted_tests,
            "/generate-golden-tests": self._handle_generate_golden_tests,
            "/run-golden-tests": self._handle_run_golden_tests,
            "/retrieval-runs": self._handle_retrieval_runs,
            "/retrieval-run-detail": self._handle_retrieval_run_detail,
            "/eval-runs": self._handle_eval_runs,
            "/eval-run-detail": self._handle_eval_run_detail,
            "/eval-run-comparison": self._handle_eval_run_comparison,
            "/failure-analysis": self._handle_failure_analysis,
            "/repair-tasks": self._handle_repair_tasks,
            "/update-repair-task": self._handle_update_repair_task,
            "/draft-golden-from-failure": self._handle_draft_golden_from_failure,
            "/draft-golden-from-failures": self._handle_draft_golden_from_failures,
            "/activate-golden-draft": self._handle_activate_golden_draft,
            "/golden-candidates": self._handle_golden_candidates,
            "/build-quality": self._handle_build_quality,
            "/check-quality": self._handle_check_quality,
            "/auto-close-coverage": self._handle_auto_close_coverage,
            "/revalidate-golden": self._handle_revalidate_golden,
            "/submit-answer-feedback": self._handle_submit_answer_feedback,
            "/reflect-answer-feedback": self._handle_reflect_answer_feedback,
            "/answer-feedback": self._handle_answer_feedback,
            "/list-golden-cases": self._handle_list_golden_cases,
            "/low-confidence-queries": self._handle_low_confidence_queries,
            "/schedule-quality-improvement": self._handle_schedule_quality_improvement,
        }
        handler = routes.get(parsed.path)
        if handler is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return

        try:
            handler(body)
        except (NetworkError, ValidationError, RuntimeError) as exc:  # pragma: no cover - last-resort API guard
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "internal_error", "message": str(exc)},
            )

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_search(self, body: dict[str, Any]) -> None:
        query = str(body.get("query", "")).strip()
        limit = int(body.get("limit", 10))
        result = search_knowledge_base(self.server.workspace_root, query, limit=limit)
        self._record_audit("search", {"query": query, "limit": limit, "result_count": len(result)})
        self._write_json(HTTPStatus.OK, {"results": result})

    def _handle_query_context(self, body: dict[str, Any]) -> None:
        query = str(body.get("query", "")).strip()
        limit = int(body.get("limit", 8))
        preferred_doc_id = str(body.get("preferred_doc_id", "")).strip() or None
        result = build_query_context(self.server.workspace_root, query, limit=limit, preferred_doc_id=preferred_doc_id)
        self._record_audit("query_context", {"query": query, "limit": limit, "hit_count": result.get("hit_count", 0)})
        self._write_json(HTTPStatus.OK, result)

    def _handle_answer_query(self, body: dict[str, Any]) -> None:
        query = str(body.get("query", "")).strip()
        limit = int(body.get("limit", 8))
        preferred_doc_id = str(body.get("preferred_doc_id", "")).strip() or None
        result = answer_query(self.server.workspace_root, query, limit=limit, preferred_doc_id=preferred_doc_id)
        self._record_audit(
            "answer_query",
            {"query": query, "limit": limit, "direct_answer": str(result.get("direct_answer", ""))[:200]},
        )

        # Record low-confidence queries to feedback queue for quality improvement
        confidence = float(result.get("confidence_score") or 0)
        if confidence < 0.5:
            try:
                from .feedback_loop import record_low_confidence_query
                record_low_confidence_query(
                    self.server.workspace_root,
                    query=query,
                    doc_id=preferred_doc_id,
                    confidence=confidence,
                    answer_mode=result.get("answer_mode"),
                    answer_preview=str(result.get("direct_answer") or "")[:200],
                )
            except (NetworkError, ValidationError, IOError):
                pass  # feedback recording must not break the answer path

        self._write_json(HTTPStatus.OK, result)

    def _handle_agent_query(self, body: dict[str, Any]) -> None:
        query = str(body.get("query", "")).strip()
        limit = int(body.get("limit", 8))
        result = run_agent_query(self.server.workspace_root, query, limit=limit)
        self._record_audit(
            "agent_query",
            {"query": query, "limit": limit, "plan_steps": len(result.plan)},
        )
        self._write_json(
            HTTPStatus.OK,
            {
                "query": result.query,
                "plan": result.plan,
                "tool_results": result.tool_results,
                "final_answer": result.final_answer,
            },
        )

    def _handle_build_document(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        result = run_document_pipeline(self.server.workspace_root, doc_id)
        payload = self._pipeline_result_payload(result.__dict__, doc_id)
        self._record_audit("build_document", {"doc_id": doc_id, "result": payload})
        self._write_json(HTTPStatus.OK, payload)

    def _handle_convert_document(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        result = parse_document(self.server.workspace_root, doc_id)
        payload = {
            "doc_id": result.doc_id,
            "page_count": result.page_count,
            "block_count": result.block_count,
            "normalized_path": str(result.normalized_path),
            "parser_engine": result.parser_engine,
            "mode": "convert_only",
        }
        self._record_audit("convert_document", {"doc_id": doc_id, "result": payload})
        self._write_json(HTTPStatus.OK, payload)

    def _handle_build_document_and_test(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        result = run_document_pipeline_and_tests(self.server.workspace_root, doc_id)
        payload = self._pipeline_result_payload(result.__dict__, doc_id)
        self._record_audit("build_document_and_test", {"doc_id": doc_id, "result": payload})
        self._write_json(HTTPStatus.OK, payload)

    def _handle_validate_document_ingestion(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        result = validate_document_ingestion(
            self.server.workspace_root,
            doc_id,
            min_text_coverage=float(body.get("min_text_coverage", 0.5)),
            min_semantic_coverage=float(body.get("min_semantic_coverage", 0.2)),
            min_answerability=float(body.get("min_answerability", 0.2)),
        )
        payload = result.to_dict()
        self._record_audit("validate_document_ingestion", {"doc_id": doc_id, "status": result.status})
        self._write_json(HTTPStatus.OK, payload)

    def _handle_upload_build(self, body: dict[str, Any]) -> None:
        filename = str(body.get("filename", "")).strip()
        content_base64 = str(body.get("content_base64", "")).strip()
        if not filename or not content_base64:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "filename_and_content_required"})
            return

        with tempfile.TemporaryDirectory(prefix="eakb_upload_", dir=str(self.server.project_root)) as temp_dir:
            temp_path = Path(temp_dir) / filename
            temp_path.write_bytes(base64.b64decode(content_base64))
            register_result = register_document(self.server.workspace_root, temp_path)
            pipeline_result = run_document_pipeline(self.server.workspace_root, register_result.doc_id)

        payload = self._pipeline_result_payload(
            {
                "doc_id": pipeline_result.doc_id,
                "registered": True,
                "deduplicated": register_result.deduplicated,
                "parser_engine": pipeline_result.parser_engine,
                "page_count": pipeline_result.page_count,
                "block_count": pipeline_result.block_count,
                "overall_score": pipeline_result.overall_score,
                "evidence_count": pipeline_result.evidence_count,
                "fact_count": pipeline_result.fact_count,
                "entity_count": pipeline_result.entity_count,
                "wiki_page_count": pipeline_result.wiki_page_count,
                "edge_count": pipeline_result.edge_count,
                "coverage_source_unit_count": pipeline_result.coverage_source_unit_count,
                "coverage_text_rate": pipeline_result.coverage_text_rate,
                "coverage_semantic_rate": pipeline_result.coverage_semantic_rate,
                "coverage_object_rate": pipeline_result.coverage_object_rate,
                "coverage_test_rate": pipeline_result.coverage_test_rate,
                "coverage_uncovered_count": pipeline_result.coverage_uncovered_count,
                "coverage_summary_path": pipeline_result.coverage_summary_path,
                "coverage_report_path": pipeline_result.coverage_report_path,
            },
            pipeline_result.doc_id,
        )
        self._write_json(HTTPStatus.OK, payload)

    def _handle_upload_convert(self, body: dict[str, Any]) -> None:
        filename = str(body.get("filename", "")).strip()
        content_base64 = str(body.get("content_base64", "")).strip()
        if not filename or not content_base64:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "filename_and_content_required"})
            return

        with tempfile.TemporaryDirectory(prefix="eakb_upload_", dir=str(self.server.project_root)) as temp_dir:
            temp_path = Path(temp_dir) / filename
            temp_path.write_bytes(base64.b64decode(content_base64))
            register_result = register_document(self.server.workspace_root, temp_path)
            parse_result = parse_document(self.server.workspace_root, register_result.doc_id)

        self._write_json(
            HTTPStatus.OK,
            {
                "doc_id": parse_result.doc_id,
                "registered": True,
                "deduplicated": register_result.deduplicated,
                "page_count": parse_result.page_count,
                "block_count": parse_result.block_count,
                "normalized_path": str(parse_result.normalized_path),
                "parser_engine": parse_result.parser_engine,
                "mode": "convert_only",
            },
        )

    def _handle_upload_build_and_test(self, body: dict[str, Any]) -> None:
        filename = str(body.get("filename", "")).strip()
        content_base64 = str(body.get("content_base64", "")).strip()
        if not filename or not content_base64:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "filename_and_content_required"})
            return

        with tempfile.TemporaryDirectory(prefix="eakb_upload_", dir=str(self.server.project_root)) as temp_dir:
            temp_path = Path(temp_dir) / filename
            temp_path.write_bytes(base64.b64decode(content_base64))
            register_result = register_document(self.server.workspace_root, temp_path)
            result = run_document_pipeline_and_tests(self.server.workspace_root, register_result.doc_id)

        payload = result.__dict__.copy()
        payload["registered"] = True
        payload["deduplicated"] = register_result.deduplicated
        self._write_json(HTTPStatus.OK, payload)

    def _handle_start_build_document(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        job_id = self._create_job("build_document", {"doc_id": doc_id})
        self._record_audit("start_build_document", {"doc_id": doc_id, "job_id": job_id})
        self._write_json(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued"})

    def _handle_start_convert_document(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        job_id = self._create_job("convert_document", {"doc_id": doc_id})
        self._record_audit("start_convert_document", {"doc_id": doc_id, "job_id": job_id})
        self._write_json(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued"})

    def _handle_start_build_document_and_test(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        job_id = self._create_job("build_document_and_test", {"doc_id": doc_id})
        self._record_audit("start_build_document_and_test", {"doc_id": doc_id, "job_id": job_id})
        self._write_json(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued"})

    def _handle_start_upload_build(self, body: dict[str, Any]) -> None:
        filename = str(body.get("filename", "")).strip()
        content_base64 = str(body.get("content_base64", "")).strip()
        if not filename or not content_base64:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "filename_and_content_required"})
            return
        job_id = self._create_job(
            "upload_build",
            {"filename": filename, "content_base64": content_base64},
        )
        self._record_audit("start_upload_build", {"filename": filename, "job_id": job_id})
        self._write_json(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued"})

    def _handle_start_upload_convert(self, body: dict[str, Any]) -> None:
        filename = str(body.get("filename", "")).strip()
        content_base64 = str(body.get("content_base64", "")).strip()
        if not filename or not content_base64:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "filename_and_content_required"})
            return
        job_id = self._create_job(
            "upload_convert",
            {"filename": filename, "content_base64": content_base64},
        )
        self._record_audit("start_upload_convert", {"filename": filename, "job_id": job_id})
        self._write_json(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued"})

    def _handle_start_upload_build_and_test(self, body: dict[str, Any]) -> None:
        filename = str(body.get("filename", "")).strip()
        content_base64 = str(body.get("content_base64", "")).strip()
        if not filename or not content_base64:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "filename_and_content_required"})
            return
        job_id = self._create_job(
            "upload_build_and_test",
            {"filename": filename, "content_base64": content_base64},
        )
        self._record_audit("start_upload_build_and_test", {"filename": filename, "job_id": job_id})
        self._write_json(HTTPStatus.ACCEPTED, {"job_id": job_id, "status": "queued"})

    def _handle_job_status(self, body: dict[str, Any]) -> None:
        job_id = str(body.get("job_id", "")).strip()
        if not job_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "job_id_required"})
            return
        with self.server.jobs_lock:
            payload = self.server.jobs.get(job_id)
        if payload is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "job_not_found", "job_id": job_id})
            return
        self._write_json(HTTPStatus.OK, payload)

    def _handle_document_detail(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        detail = self._document_detail(doc_id)
        self._record_audit("document_detail", {"doc_id": doc_id})
        self._write_json(HTTPStatus.OK, detail)

    def _handle_document_diagnostics(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        detail = build_document_diagnostics(self.server.workspace_root, doc_id)
        self._record_audit("document_diagnostics", {"doc_id": doc_id})
        self._write_json(HTTPStatus.OK, detail)

    def _handle_parse_risk_actions(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        output_dir_value = str(body.get("output_dir") or "").strip()
        output_dir = Path(output_dir_value) if output_dir_value else None
        detail = _resolve("generate_parse_risk_action_plan")(
            self.server.workspace_root,
            doc_id,
            output_dir=output_dir,
            persist_repair_tasks=bool(body.get("persist_repair_tasks", False)),
        )
        self._record_audit("parse_risk_actions", {"doc_id": doc_id})
        self._write_json(HTTPStatus.OK, detail.to_dict())

    def _handle_parse_risk_repair_review(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        output_dir_value = str(body.get("output_dir") or "").strip()
        output_dir = Path(output_dir_value) if output_dir_value else None
        detail = _resolve("review_parse_risk_repair_tasks")(self.server.workspace_root, doc_id, output_dir=output_dir)
        self._record_audit("parse_risk_repair_review", {"doc_id": doc_id})
        self._write_json(HTTPStatus.OK, detail.to_dict())

    def _handle_parse_view_detail(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        page_no_value = body.get("page_no")
        page_no = int(page_no_value) if page_no_value not in (None, "") else None
        text_limit = int(body.get("text_limit") or 1200)
        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            detail = list_parse_view_pages(connection, doc_id, page_no=page_no, text_limit=text_limit)
        finally:
            connection.close()
        self._record_audit("parse_view_detail", {"doc_id": doc_id, "page_no": page_no})
        self._write_json(HTTPStatus.OK, detail)

    def _handle_coverage_test_gaps(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        limit_value = body.get("limit")
        limit = int(limit_value) if limit_value is not None else None
        rebuild = bool(body.get("rebuild", False))
        result = build_test_gap_candidates_for_document(
            self.server.workspace_root,
            doc_id,
            limit=limit,
            rebuild=rebuild,
        )
        payload = {
            "doc_id": result.doc_id,
            "candidate_count": result.candidate_count,
            "candidates_path": str(result.candidates_path),
            "report_path": str(result.report_path),
        }
        self._record_audit("coverage_test_gaps", {"doc_id": doc_id, "candidate_count": result.candidate_count})
        self._write_json(HTTPStatus.OK, payload)

    def _handle_generate_coverage_test_drafts(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        limit_value = body.get("limit")
        limit = int(limit_value) if limit_value is not None else 50
        result = generate_coverage_test_drafts_for_document(
            self.server.workspace_root,
            doc_id,
            limit=limit,
            rebuild_coverage=bool(body.get("rebuild_coverage", False)),
            validate=bool(body.get("validate", False)),
        )
        payload = {
            "doc_id": result["doc_id"],
            "draft_case_count": result["draft_case_count"],
            "validated": result["validated"],
            "json_path": result["json_path"],
            "report_path": result["report_path"],
            "coverage_candidates_path": result["coverage_candidates_path"],
        }
        self._record_audit("generate_coverage_test_drafts", {"doc_id": doc_id, "draft_case_count": result["draft_case_count"]})
        self._write_json(HTTPStatus.OK, payload)

    def _handle_validate_coverage_test_drafts(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        result = validate_coverage_test_drafts_for_document(self.server.workspace_root, doc_id)
        payload = {
            "doc_id": result["doc_id"],
            "draft_case_count": result["draft_case_count"],
            "passed_count": result["passed_count"],
            "failed_count": result["failed_count"],
            "json_path": result["json_path"],
            "report_path": result["report_path"],
        }
        self._record_audit("validate_coverage_test_drafts", {"doc_id": doc_id, "passed_count": result["passed_count"]})
        self._write_json(HTTPStatus.OK, payload)

    def _handle_promote_coverage_test_drafts(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        result = promote_coverage_test_drafts_for_document(
            self.server.workspace_root,
            doc_id,
            require_validated=not bool(body.get("allow_unvalidated", False)),
        )
        self._record_audit("promote_coverage_test_drafts", {"doc_id": doc_id, "added_case_count": result["added_case_count"]})
        self._write_json(HTTPStatus.OK, result)

    def _handle_run_coverage_promoted_tests(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        mode = str(body.get("mode") or "trace").strip()
        result = run_coverage_promoted_tests_for_document(
            self.server.workspace_root,
            doc_id,
            validation_mode=mode,
        )
        self._record_audit("run_coverage_promoted_tests", {"doc_id": doc_id, "success": result["success"]})
        self._write_json(HTTPStatus.OK, result)

    def _handle_generate_golden_tests(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        result = generate_golden_tests_for_document(self.server.workspace_root, doc_id)
        self._record_audit("generate_golden_tests", {"doc_id": doc_id, "case_count": result["case_count"]})
        self._write_json(HTTPStatus.OK, result)

    def _handle_run_golden_tests(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id_required"})
            return
        result = run_golden_tests_for_document(self.server.workspace_root, doc_id)
        self._record_audit(
            "run_golden_tests",
            {"doc_id": doc_id, "success": result["success"], "passed": result["passed"], "failed": result["failed"]},
        )
        self._write_json(HTTPStatus.OK, result)

    def _handle_eval_runs(self, body: dict[str, Any]) -> None:
        suite_id = str(body.get("suite_id", "")).strip() or None
        limit = int(body.get("limit", 30) or 30)
        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            runs = list_eval_runs(connection, suite_id=suite_id, limit=limit)
        finally:
            connection.close()
        self._write_json(HTTPStatus.OK, {"runs": runs})

    def _handle_retrieval_runs(self, body: dict[str, Any]) -> None:
        query = str(body.get("query", "")).strip() or None
        query_type = str(body.get("query_type", "")).strip() or None
        limit = int(body.get("limit", 30) or 30)
        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            runs = list_retrieval_runs(connection, query=query, query_type=query_type, limit=limit)
        finally:
            connection.close()
        self._write_json(HTTPStatus.OK, {"runs": runs})

    def _handle_retrieval_run_detail(self, body: dict[str, Any]) -> None:
        run_id = str(body.get("run_id", "")).strip()
        if not run_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "run_id_required"})
            return
        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            detail = get_retrieval_run_detail(connection, run_id)
        finally:
            connection.close()
        if detail is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "retrieval_run_not_found"})
            return
        self._write_json(HTTPStatus.OK, detail)

    def _handle_eval_run_detail(self, body: dict[str, Any]) -> None:
        eval_run_id = str(body.get("eval_run_id", "")).strip()
        if not eval_run_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "eval_run_id_required"})
            return
        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            detail = get_eval_run_detail(connection, eval_run_id)
        finally:
            connection.close()
        if detail is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "eval_run_not_found"})
            return
        self._write_json(HTTPStatus.OK, detail)

    def _handle_failure_analysis(self, body: dict[str, Any]) -> None:
        eval_run_id = str(body.get("eval_run_id", "")).strip()
        case_id = str(body.get("case_id", "")).strip() or None
        if not eval_run_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "eval_run_id_required"})
            return
        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            analysis = build_failure_analysis(connection, eval_run_id, case_id=case_id)
            if analysis is not None:
                connection.commit()
        finally:
            connection.close()
        if analysis is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "eval_run_not_found"})
            return
        self._write_json(HTTPStatus.OK, analysis)

    def _handle_repair_tasks(self, body: dict[str, Any]) -> None:
        status = str(body.get("status", "")).strip() or None
        limit = int(body.get("limit", 50) or 50)
        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            tasks = list_repair_tasks(connection, status=status, limit=limit)
        finally:
            connection.close()
        self._write_json(HTTPStatus.OK, {"tasks": tasks})

    def _handle_update_repair_task(self, body: dict[str, Any]) -> None:
        task_id = str(body.get("task_id", "")).strip()
        status = str(body.get("status", "")).strip()
        note = str(body.get("note", "")).strip() or None
        if not task_id or not status:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "task_id_and_status_required"})
            return
        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            try:
                task = update_repair_task_status(connection, task_id, status, note=note)
            except ValueError as exc:
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if task is not None:
                connection.commit()
        finally:
            connection.close()
        if task is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "repair_task_not_found"})
            return
        self._write_json(HTTPStatus.OK, {"task": task})

    def _handle_draft_golden_from_failure(self, body: dict[str, Any]) -> None:
        eval_run_id = str(body.get("eval_run_id", "")).strip()
        case_id = str(body.get("case_id", "")).strip()
        if not eval_run_id or not case_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "eval_run_id_and_case_id_required"})
            return
        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            result = draft_golden_case_from_failure(connection, eval_run_id, case_id)
            if result is not None:
                connection.commit()
        finally:
            connection.close()
        if result is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "failure_case_not_found"})
            return
        self._write_json(HTTPStatus.OK, result)

    def _handle_draft_golden_from_failures(self, body: dict[str, Any]) -> None:
        eval_run_id = str(body.get("eval_run_id", "")).strip()
        if not eval_run_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "eval_run_id_required"})
            return
        case_ids = [str(item).strip() for item in body.get("case_ids", []) if str(item).strip()] if isinstance(body.get("case_ids"), list) else None
        failure_types = [str(item).strip() for item in body.get("failure_types", []) if str(item).strip()] if isinstance(body.get("failure_types"), list) else None
        limit_value = body.get("limit")
        limit = int(limit_value) if limit_value is not None else None
        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            result = draft_golden_cases_from_eval_failures(
                connection,
                eval_run_id,
                case_ids=case_ids,
                failure_types=failure_types,
                limit=limit,
            )
            if result is not None:
                connection.commit()
        finally:
            connection.close()
        if result is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "eval_run_not_found"})
            return
        self._write_json(HTTPStatus.OK, result)

    def _handle_activate_golden_draft(self, body: dict[str, Any]) -> None:
        case_id = str(body.get("case_id", "")).strip()
        if not case_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "case_id_required"})
            return
        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            result = activate_golden_case_draft(connection, case_id)
            if result is not None:
                connection.commit()
        finally:
            connection.close()
        if result is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "golden_draft_not_found"})
            return
        if result.get("activation_blocked"):
            self._write_json(HTTPStatus.CONFLICT, {"error": "golden_draft_not_ready", "draft": result})
            return
        self._write_json(HTTPStatus.OK, {"activated_case": result})

    def _handle_golden_candidates(self, body: dict[str, Any]) -> None:
        origins = _body_string_list(body.get("origins") or body.get("origin"))
        doc_ids = _body_string_list(body.get("doc_ids") or body.get("doc_id"))
        case_types = _body_string_list(body.get("case_types") or body.get("case_type"))
        eval_run_id = str(body.get("eval_run_id") or "").strip() or None
        limit_value = body.get("limit_per_type")
        limit_per_type = int(limit_value) if limit_value is not None else 20
        output_dir_value = str(body.get("output_dir") or "").strip()
        output_dir = Path(output_dir_value) if output_dir_value else None
        try:
            result = generate_golden_candidates(
                self.server.workspace_root,
                origins=origins or None,
                doc_ids=doc_ids or None,
                eval_run_id=eval_run_id,
                limit_per_type=limit_per_type,
                case_types=case_types or None,
                output_dir=output_dir,
            )
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._write_json(HTTPStatus.OK, result.to_dict())

    def _handle_build_quality(self, body: dict[str, Any]) -> None:
        from .pipeline import run_full_quality_pipeline
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id required"})
            return
        min_test_coverage = float(body.get("min_test_coverage", 0.3))
        result = run_full_quality_pipeline(
            self.server.workspace_root, doc_id, min_test_coverage=min_test_coverage,
        )
        self._write_json(HTTPStatus.OK, {
            "doc_id": result.doc_id,
            "acceptance_status": result.acceptance_status,
            "overall_score": result.overall_score,
            "parse_quality_score": result.parse_quality_score,
            "knowledge_completeness_score": result.knowledge_completeness_score,
            "test_coverage_score": result.test_coverage_score,
            "contract_compliance_score": result.contract_compliance_score,
            "gate_status": result.gate_status,
            "coverage_iterations": result.coverage_iterations,
            "golden_cases_activated": result.golden_cases_activated,
            "stale_cases_removed": result.stale_cases_removed,
        })

    def _handle_check_quality(self, body: dict[str, Any]) -> None:
        from .quality_gate import compute_quality_gate
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id required"})
            return
        result = compute_quality_gate(self.server.workspace_root, doc_id)
        self._write_json(HTTPStatus.OK, {
            "doc_id": result.doc_id,
            "overall_score": result.overall_score,
            "parse_quality_score": result.parse_quality_score,
            "knowledge_completeness_score": result.knowledge_completeness_score,
            "test_coverage_score": result.test_coverage_score,
            "contract_compliance_score": result.contract_compliance_score,
            "gate_status": result.gate_status,
            "report_path": str(result.report_path),
        })

    def _handle_auto_close_coverage(self, body: dict[str, Any]) -> None:
        from .generated_tests import auto_activate_golden_cases
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id required"})
            return
        max_candidates = int(body.get("max_candidates", 50))
        result = auto_activate_golden_cases(
            self.server.workspace_root, doc_id, max_candidates=max_candidates,
        )
        self._write_json(HTTPStatus.OK, result)

    def _handle_revalidate_golden(self, body: dict[str, Any]) -> None:
        from .generated_tests import revalidate_stale_golden_cases
        doc_id = str(body.get("doc_id", "")).strip()
        if not doc_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "doc_id required"})
            return
        result = revalidate_stale_golden_cases(self.server.workspace_root, doc_id)
        self._write_json(HTTPStatus.OK, result)

    def _handle_submit_answer_feedback(self, body: dict[str, Any]) -> None:
        query = str(body.get("query", "")).strip()
        direct_answer = str(body.get("direct_answer", "")).strip()
        if not query:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "query_required"})
            return
        result = submit_feedback(
            self.server.workspace_root,
            query=query,
            direct_answer=direct_answer,
            answer_mode=body.get("answer_mode"),
            preferred_doc_id=body.get("preferred_doc_id"),
            confidence_score=body.get("confidence_score"),
            satisfaction=str(body.get("satisfaction", "")).strip(),
            categories=body.get("categories") or [],
            user_comment=body.get("user_comment"),
        )
        self._record_audit(
            "submit_answer_feedback",
            {"query": query, "satisfaction": result["satisfaction"], "feedback_id": result["feedback_id"]},
        )
        self._write_json(HTTPStatus.OK, result)

    def _handle_reflect_answer_feedback(self, body: dict[str, Any]) -> None:
        feedback_id = str(body.get("feedback_id", "")).strip()
        if not feedback_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "feedback_id_required"})
            return
        reflection = reflect_on_feedback(self.server.workspace_root, feedback_id)
        self._write_json(HTTPStatus.OK, {"feedback_id": feedback_id, "reflection": reflection})

    def _handle_answer_feedback(self, body: dict[str, Any]) -> None:
        satisfaction = str(body.get("satisfaction", "")).strip() or None
        limit = int(body.get("limit", 50) or 50)
        feedback = list_answer_feedback(self.server.workspace_root, satisfaction=satisfaction, limit=limit)
        self._write_json(HTTPStatus.OK, {"feedback": feedback})

    def _handle_list_golden_cases(self, body: dict[str, Any]) -> None:
        doc_id = str(body.get("doc_id", "")).strip() or None
        status = str(body.get("status", "")).strip() or None
        limit = int(body.get("limit", 100) or 100)
        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            cases = list_golden_cases(connection, doc_id=doc_id, status=status, limit=limit)
        finally:
            connection.close()
        self._write_json(HTTPStatus.OK, {"cases": cases})

    def _handle_low_confidence_queries(self, body: dict[str, Any]) -> None:
        limit = int(body.get("limit", 100) or 100)
        from .feedback_loop import drain_low_confidence_queries
        queries = drain_low_confidence_queries(self.server.workspace_root, limit=limit)
        self._write_json(HTTPStatus.OK, {"queries": queries})

    def _handle_schedule_quality_improvement(self, body: dict[str, Any]) -> None:
        from .feedback_loop import schedule_quality_improvement, FeedbackAction
        actions = schedule_quality_improvement(self.server.workspace_root)
        result = []
        for a in actions:
            result.append({"action_type": a.action_type, "doc_id": a.doc_id, "details": a.details})
        self._write_json(HTTPStatus.OK, {"actions": result})

    def _handle_eval_run_comparison(self, body: dict[str, Any]) -> None:
        eval_run_id = str(body.get("eval_run_id", "")).strip()
        baseline_eval_run_id = str(body.get("baseline_eval_run_id", "")).strip() or None
        if not eval_run_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "eval_run_id_required"})
            return
        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            comparison = compare_eval_runs(connection, eval_run_id, baseline_eval_run_id)
        finally:
            connection.close()
        if comparison is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "eval_run_not_found"})
            return
        self._write_json(HTTPStatus.OK, comparison)

    def _read_json_body(self) -> dict[str, Any] | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return None

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._write_common_headers("application/json; charset=utf-8", len(encoded))
        self.end_headers()
        self.wfile.write(encoded)

    def _write_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        payload = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._write_common_headers(content_type, len(payload))
        self.end_headers()
        self.wfile.write(payload)

    def _write_common_headers(self, content_type: str, content_length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _create_job(self, job_type: str, payload: dict[str, Any]) -> str:
        job_id = f"api-job-{uuid.uuid4().hex}"
        job = {
            "job_id": job_id,
            "job_type": job_type,
            "status": "queued",
            "progress": 0,
            "stage": "queued",
            "history": [{"stage": "queued", "progress": 0}],
            "result": None,
            "error": None,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        with self.server.jobs_lock:
            self.server.jobs[job_id] = job

        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, job_type, payload),
            daemon=True,
        )
        thread.start()
        return job_id

    def _run_job(self, job_id: str, job_type: str, payload: dict[str, Any]) -> None:
        try:
            self._update_job(job_id, status="running", progress=5, stage="starting")
            if job_type == "build_document":
                result = self._run_document_pipeline_with_updates(job_id, str(payload["doc_id"]))
            elif job_type == "build_document_and_test":
                result = self._run_document_pipeline_and_test_with_updates(job_id, str(payload["doc_id"]))
            elif job_type == "convert_document":
                result = self._run_convert_document_with_updates(job_id, str(payload["doc_id"]))
            elif job_type == "upload_build":
                result = self._run_upload_pipeline_with_updates(job_id, payload)
            elif job_type == "upload_build_and_test":
                result = self._run_upload_pipeline_and_test_with_updates(job_id, payload)
            elif job_type == "upload_convert":
                result = self._run_upload_convert_with_updates(job_id, payload)
            else:
                raise ValueError(f"unsupported job type: {job_type}")
            self._update_job(job_id, status="completed", progress=100, stage="completed", result=result)
        except (NetworkError, ValidationError, ValueError, RuntimeError) as exc:
            self._update_job(job_id, status="failed", stage="failed", error=str(exc))

    def _run_document_pipeline_with_updates(self, job_id: str, doc_id: str) -> dict[str, Any]:
        def on_progress(event: PipelineEvent) -> None:
            self._update_job(
                job_id,
                status="running",
                progress=event.progress,
                stage=event.stage,
                result={
                    "stage_status": event.status,
                    "elapsed_seconds": event.elapsed_seconds,
                    "stage_detail": event.detail,
                },
            )

        result = run_document_pipeline_with_progress(
            self.server.workspace_root,
            doc_id,
            progress_callback=on_progress,
        )
        return self._pipeline_result_payload(result.__dict__, doc_id)

    def _pipeline_result_payload(self, payload: dict[str, Any], doc_id: str) -> dict[str, Any]:
        result = dict(payload)
        existing_acceptance = result.get("ingestion_acceptance")
        if isinstance(existing_acceptance, dict):
            return result
        acceptance = validate_document_ingestion(self.server.workspace_root, doc_id)
        result["ingestion_acceptance"] = {
            "status": acceptance.status,
            "check_count": acceptance.check_count,
            "passed_count": acceptance.passed_count,
            "failed_count": acceptance.failed_count,
            "warn_count": acceptance.warn_count,
            "json_path": str(acceptance.json_path),
            "report_path": str(acceptance.report_path),
            "failed_checks": [
                item
                for item in acceptance.checks
                if item.get("status") == "failed"
            ],
            "warning_checks": [
                item
                for item in acceptance.checks
                if item.get("status") == "warn"
            ],
        }
        return result

    def _run_upload_pipeline_with_updates(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="eakb_upload_", dir=str(self.server.project_root)) as temp_dir:
            temp_path = Path(temp_dir) / str(payload["filename"])
            temp_path.write_bytes(base64.b64decode(str(payload["content_base64"])))
            self._update_job(job_id, progress=10, stage="ingest")
            register_result = register_document(self.server.workspace_root, temp_path)
            result = self._run_document_pipeline_with_updates(job_id, register_result.doc_id)
            result["registered"] = True
            result["deduplicated"] = register_result.deduplicated
            return result

    def _run_convert_document_with_updates(self, job_id: str, doc_id: str) -> dict[str, Any]:
        self._update_job(job_id, progress=20, stage="parse")
        parse_result = parse_document(self.server.workspace_root, doc_id)
        return {
            "doc_id": doc_id,
            "parser_engine": parse_result.parser_engine,
            "page_count": parse_result.page_count,
            "block_count": parse_result.block_count,
            "normalized_path": str(parse_result.normalized_path),
            "mode": "convert_only",
        }

    def _run_upload_convert_with_updates(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="eakb_upload_", dir=str(self.server.project_root)) as temp_dir:
            temp_path = Path(temp_dir) / str(payload["filename"])
            temp_path.write_bytes(base64.b64decode(str(payload["content_base64"])))
            self._update_job(job_id, progress=10, stage="ingest")
            register_result = register_document(self.server.workspace_root, temp_path)
            result = self._run_convert_document_with_updates(job_id, register_result.doc_id)
            result["registered"] = True
            result["deduplicated"] = register_result.deduplicated
            return result

    def _run_document_pipeline_and_test_with_updates(self, job_id: str, doc_id: str) -> dict[str, Any]:
        result = self._run_document_pipeline_with_updates(job_id, doc_id)
        self._update_job(job_id, progress=96, stage="golden_generate")
        golden_result = generate_golden_tests_for_document(self.server.workspace_root, doc_id)
        self._update_job(job_id, progress=98, stage="golden_run")
        golden_run = run_golden_tests_for_document(self.server.workspace_root, doc_id)
        result.update(
            {
                "golden_case_count": int(golden_result.get("case_count", 0)),
                "golden_network_case_count": int(golden_result.get("network_case_count", 0)),
                "golden_local_case_count": int(golden_result.get("local_case_count", 0)),
                "golden_test_success": bool(golden_run.get("success", False)),
                "golden_test_passed": int(golden_run.get("passed", 0)),
                "golden_test_failed": int(golden_run.get("failed", 0)),
            }
        )
        return result

    def _run_upload_pipeline_and_test_with_updates(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="eakb_upload_", dir=str(self.server.project_root)) as temp_dir:
            temp_path = Path(temp_dir) / str(payload["filename"])
            temp_path.write_bytes(base64.b64decode(str(payload["content_base64"])))
            self._update_job(job_id, progress=10, stage="ingest")
            register_result = register_document(self.server.workspace_root, temp_path)
            result = self._run_document_pipeline_and_test_with_updates(job_id, register_result.doc_id)
            result["registered"] = True
            result["deduplicated"] = register_result.deduplicated
            return result

    def _update_job(self, job_id: str, **updates: Any) -> None:
        with self.server.jobs_lock:
            if job_id not in self.server.jobs:
                return
            stage = updates.get("stage")
            progress = updates.get("progress")
            if stage is not None:
                history = self.server.jobs[job_id].setdefault("history", [])
                if not history or history[-1].get("stage") != stage:
                    history.append(
                        {
                            "stage": stage,
                            "progress": progress if progress is not None else self.server.jobs[job_id].get("progress", 0),
                        }
                    )
            self.server.jobs[job_id].update(updates)

    def _list_jobs(self) -> list[dict[str, Any]]:
        with self.server.jobs_lock:
            jobs = list(self.server.jobs.values())
        jobs.sort(key=lambda item: item["created_at"], reverse=True)
        return jobs[:30]

    def _record_audit(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "payload": payload,
        }
        with self.server.audit_lock:
            with self.server.audit_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _read_audit_events(self) -> list[dict[str, Any]]:
        if not self.server.audit_log_path.exists():
            return []
        lines = self.server.audit_log_path.read_text(encoding="utf-8").splitlines()
        events = []
        for line in reversed(lines[-100:]):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def _list_documents(self) -> list[dict[str, Any]]:
        from .db import connect

        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            rows = connection.execute(
                """
                SELECT doc_id, source_filename, source_type, page_count, parse_status, quality_status
                FROM documents
                ORDER BY ingest_time DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def _document_detail(self, doc_id: str) -> dict[str, Any]:
        from .db import connect

        connection = connect(AppPaths.from_root(self.server.workspace_root).db_file)
        try:
            document = connection.execute(
                """
                SELECT doc_id, source_filename, source_type, page_count, parse_status, quality_status
                FROM documents
                WHERE doc_id = ?
                """,
                (doc_id,),
            ).fetchone()
            if document is None:
                return {"error": "document_not_found", "doc_id": doc_id}

            counts = {
                "pages": connection.execute("SELECT count(*) FROM pages WHERE doc_id = ?", (doc_id,)).fetchone()[0],
                "blocks": connection.execute("SELECT count(*) FROM blocks WHERE doc_id = ?", (doc_id,)).fetchone()[0],
                "evidence": connection.execute("SELECT count(*) FROM evidence WHERE doc_id = ?", (doc_id,)).fetchone()[0],
                "facts": connection.execute("SELECT count(*) FROM facts WHERE source_doc_id = ?", (doc_id,)).fetchone()[0],
                "wiki_pages": connection.execute(
                    "SELECT count(*) FROM wiki_pages WHERE json_extract(source_doc_ids_json, '$[0]') = ?",
                    (doc_id,),
                ).fetchone()[0],
                "graph_edges": connection.execute("SELECT count(*) FROM graph_edges WHERE version_scope = ?", (doc_id,)).fetchone()[0],
            }
            quality = connection.execute(
                """
                SELECT overall_score, high_risk_page_count, review_required_count, blocked_count
                FROM quality_reports
                WHERE doc_id = ?
                """,
                (doc_id,),
            ).fetchone()
            diagnostics = build_document_diagnostics(self.server.workspace_root, doc_id)
            return {
                "document": dict(document),
                "counts": counts,
                "quality": dict(quality) if quality else None,
                "coverage": diagnostics.get("coverage", {}),
                "artifacts": diagnostics.get("artifacts", {}),
                "parse_views": diagnostics.get("parse_views", {}),
                "parse_quality": diagnostics.get("parse_quality", {}),
            }
        finally:
            connection.close()

    def _closed_loop_dashboard(self) -> dict[str, Any]:
        paths = AppPaths.from_root(self.server.workspace_root)
        connection = connect(paths.db_file)
        try:
            backfill_result = backfill_eval_run_scope_metadata(connection, limit=200)
            if int(backfill_result.get("updated_count") or 0):
                connection.commit()
            latest_eval = list_eval_runs(connection, limit=1)
            current_code_version = _runtime_code_version()
            latest_retrieval_eval = _latest_eval_with_quality(
                connection,
                "retrieval_quality",
                code_version=current_code_version,
                suite_id_prefix="regression:user_query_retrieval",
            )
            if latest_retrieval_eval is None:
                latest_retrieval_eval = _latest_eval_with_quality(
                    connection,
                    "retrieval_quality",
                    code_version=current_code_version,
                )
            latest_answer_eval = _latest_eval_with_quality(
                connection,
                "answer_quality",
                code_version=current_code_version,
            )
            latest_historical_retrieval_eval = _latest_eval_with_quality(connection, "retrieval_quality")
            latest_historical_answer_eval = _latest_eval_with_quality(connection, "answer_quality")
            latest_retrieval = list_retrieval_runs(connection, limit=1)
            latest_retrieval_eval_summary = latest_retrieval_eval.get("result_summary", {}) if latest_retrieval_eval else {}
            latest_answer_eval_summary = latest_answer_eval.get("result_summary", {}) if latest_answer_eval else {}
            retrieval_quality = (
                latest_retrieval_eval_summary.get("retrieval_quality", {})
                if isinstance(latest_retrieval_eval_summary, dict)
                else {}
            )
            answer_quality = (
                latest_answer_eval_summary.get("answer_quality", {})
                if isinstance(latest_answer_eval_summary, dict)
                else {}
            )
            shape_contract_quality = (
                latest_answer_eval_summary.get("shape_contract_quality", {})
                if isinstance(latest_answer_eval_summary, dict)
                else {}
            )
            source_unit_mapping_backfill = backfill_source_unit_mappings_from_metadata(connection, only_missing=True)
            if (
                int(source_unit_mapping_backfill.get("fact_link_count") or 0)
                or int(source_unit_mapping_backfill.get("evidence_link_count") or 0)
            ):
                connection.commit()
            coverage = _workspace_coverage_snapshot(connection)
            coverage["mapping_backfill"] = source_unit_mapping_backfill
            graph_contribution = _graph_contribution_snapshot(connection)
            uncovered_priority = _latest_uncovered_priority_snapshot(paths)
            latest_failure_analysis: dict[str, Any] | None = None
            latest_answer_failure_analysis: dict[str, Any] | None = None
            current_repair_tasks: list[Any] = []
            current_answer_repair_tasks: list[Any] = []
            historical_repair_tasks: list[Any] = []
            repair_task_count = 0
            if latest_eval:
                latest_failure_analysis = build_failure_analysis(connection, str(latest_eval[0].get("eval_run_id") or ""))
                if latest_failure_analysis:
                    connection.commit()
                    raw_tasks = latest_failure_analysis.get("repair_tasks")
                    if isinstance(raw_tasks, list):
                        current_repair_tasks = raw_tasks
            if latest_answer_eval:
                latest_answer_failure_analysis = build_failure_analysis(
                    connection,
                    str(latest_answer_eval.get("eval_run_id") or ""),
                )
                if latest_answer_failure_analysis:
                    connection.commit()
                    raw_answer_tasks = latest_answer_failure_analysis.get("repair_tasks")
                    if isinstance(raw_answer_tasks, list):
                        current_answer_repair_tasks = raw_answer_tasks
            historical_repair_tasks = list_repair_tasks(connection, limit=5)
            historical_repair_task_status_counts = _repair_task_status_counts(connection)
            repair_task_status_counts = _repair_task_status_counts_from_tasks(current_repair_tasks)
            answer_repair_task_status_counts = _repair_task_status_counts_from_tasks(current_answer_repair_tasks)
            repair_task_count = int(repair_task_status_counts.get("open", 0))
            parse_risk_profile = _workspace_parse_risk_snapshot(connection)
            parse_risk_history = summarize_parse_risk_history(self.server.workspace_root)
            ingestion_loop = {
                "document_count": _count_rows(connection, "documents"),
                "page_count": _count_rows(connection, "pages"),
                "block_count": _count_rows(connection, "blocks"),
                "evidence_count": _count_rows(connection, "evidence"),
                "fact_count": _count_rows(connection, "facts"),
                "source_unit_count": _count_rows(connection, "source_units"),
                "source_unit_coverage": coverage,
                "uncovered_priority": uncovered_priority,
                "parse_risk_pages": parse_risk_profile["high_risk_page_count"],
                "actionable_parse_risk_pages": parse_risk_profile["actionable_parse_risk_pages"],
                "parse_risk_profile": parse_risk_profile,
                "artifacts": {
                    "coverage_snapshot_available": bool(coverage.get("source_unit_count")),
                    "coverage_report": "source_units",
                    "uncovered_priority_report": uncovered_priority,
                    "diagnostics": "document-diagnostics",
                },
            }
            parse_quality_loop = {
                "parse_risk_pages": parse_risk_profile["high_risk_page_count"],
                "actionable_parse_risk_pages": parse_risk_profile["actionable_parse_risk_pages"],
                "evidence_backed_high_risk_pages": parse_risk_profile.get("evidence_backed_high_risk_pages", 0),
                "source_unit_backed_high_risk_pages": parse_risk_profile.get("source_unit_backed_high_risk_pages", 0),
                "fact_backed_high_risk_pages": parse_risk_profile.get("fact_backed_high_risk_pages", 0),
                "fully_backed_high_risk_pages": parse_risk_profile.get("fully_backed_high_risk_pages", 0),
                "root_cause_counts": parse_risk_profile.get("root_cause_counts", {}),
                "parse_risk_history": parse_risk_history,
                "parse_risk_profile": parse_risk_profile,
                "artifacts": {
                    "document_diagnostics": "document-diagnostics",
                    "workspace_parse_risk_profile": "closed-loop-dashboard.parse_quality_loop.parse_risk_profile",
                    "parse_risk_history": parse_risk_history,
                },
            }
            retrieval_loop = {
                "retrieval_run_count": _count_rows(connection, "retrieval_runs"),
                "latest_run": latest_retrieval[0] if latest_retrieval else None,
                "recall_at_5": retrieval_quality.get("recall_at_5"),
                "recall_at_10": retrieval_quality.get("recall_at_10"),
                "mrr": retrieval_quality.get("mrr"),
                "negative_hit_rate": retrieval_quality.get("negative_hit_rate"),
                "graph_contribution": graph_contribution,
                "artifacts": {
                    "latest_retrieval_run_id": latest_retrieval[0].get("run_id") if latest_retrieval else None,
                    "retrieval_runs_available": bool(latest_retrieval),
                    "latest_eval_run_id": latest_retrieval_eval.get("eval_run_id") if latest_retrieval_eval else None,
                    "latest_eval_suite_id": latest_retrieval_eval.get("suite_id") if latest_retrieval_eval else None,
                    "current_code_version": current_code_version,
                    "latest_historical_eval_run_id": (
                        latest_historical_retrieval_eval.get("eval_run_id") if latest_historical_retrieval_eval else None
                    ),
                    "latest_historical_eval_code_version": (
                        latest_historical_retrieval_eval.get("code_version") if latest_historical_retrieval_eval else None
                    ),
                    "graph_contribution": graph_contribution,
                },
            }
            answer_loop = {
                "answer_pass_rate": answer_quality.get("answer_pass_rate"),
                "answer_mode_accuracy": answer_quality.get("answer_mode_accuracy"),
                "forbidden_hit_rate": answer_quality.get("forbidden_hit_rate"),
                "render_artifact_rate": answer_quality.get("render_artifact_rate"),
                "shape_contract_quality": shape_contract_quality,
                "artifacts": {
                    "latest_eval_run_id": latest_answer_eval.get("eval_run_id") if latest_answer_eval else None,
                    "latest_eval_suite_id": latest_answer_eval.get("suite_id") if latest_answer_eval else None,
                    "current_code_version": current_code_version,
                    "latest_historical_eval_run_id": (
                        latest_historical_answer_eval.get("eval_run_id") if latest_historical_answer_eval else None
                    ),
                    "latest_historical_eval_code_version": (
                        latest_historical_answer_eval.get("code_version") if latest_historical_answer_eval else None
                    ),
                    "failure_analysis_available": bool(latest_answer_failure_analysis),
                    "failure_count": latest_answer_failure_analysis.get("failure_count") if latest_answer_failure_analysis else None,
                    "repair_task_count": int(answer_repair_task_status_counts.get("open", 0)),
                    "historical_repair_task_count": int(historical_repair_task_status_counts.get("open", 0)),
                },
            }
            regression_loop = {
                "eval_run_count": _count_rows(connection, "eval_runs"),
                "latest_run": latest_eval[0] if latest_eval else None,
                "new_failures": None,
                "repair_task_count": repair_task_count,
                "repair_task_status_counts": repair_task_status_counts,
                "historical_repair_task_status_counts": historical_repair_task_status_counts,
                "repair_task_coverage": latest_failure_analysis.get("repair_task_coverage") if latest_failure_analysis else None,
                "golden_case_count": _count_rows(connection, "golden_cases"),
                "active_golden_case_count": _count_rows(connection, "golden_cases", "status = 'active'"),
                "draft_golden_case_count": _count_rows(connection, "golden_cases", "status = 'draft'"),
                "artifacts": {
                    "latest_eval_run_id": latest_eval[0].get("eval_run_id") if latest_eval else None,
                    "failure_analysis_available": bool(latest_failure_analysis),
                    "failure_count": latest_failure_analysis.get("failure_count") if latest_failure_analysis else None,
                    "repair_task_coverage": latest_failure_analysis.get("repair_task_coverage") if latest_failure_analysis else None,
                    "repair_tasks": current_repair_tasks[:5],
                    "historical_repair_tasks": historical_repair_tasks[:5],
                    "repair_task_status_counts": repair_task_status_counts,
                    "historical_repair_task_status_counts": historical_repair_task_status_counts,
                    "comparison": latest_failure_analysis.get("comparison") if latest_failure_analysis else None,
                },
            }
            hygiene_loop = _hygiene_loop_snapshot(self.server.workspace_root)
            _attach_ingestion_health(ingestion_loop)
            _attach_parse_quality_health(parse_quality_loop)
            _attach_retrieval_health(retrieval_loop)
            _attach_answer_health(answer_loop)
            _attach_regression_health(regression_loop)
            return {
                "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "ingestion_loop": ingestion_loop,
                "parse_quality_loop": parse_quality_loop,
                "retrieval_loop": retrieval_loop,
                "answer_loop": answer_loop,
                "regression_loop": regression_loop,
                "hygiene_loop": hygiene_loop,
            }
        finally:
            connection.close()


def serve_api(workspace_root: Path, host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ApiServer((host, port), workspace_root)
    try:
        server.serve_forever()
    finally:
        server.server_close()
