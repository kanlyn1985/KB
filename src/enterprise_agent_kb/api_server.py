from __future__ import annotations

import json
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

from .agent_tools import run_agent_query
from .answer_api import answer_query
from .closed_loop_store import (
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
    _runtime_code_version,
    list_eval_runs,
    list_repair_tasks,
    list_retrieval_runs,
    update_repair_task_status,
)
from .config import AppPaths
from .coverage import build_test_gap_candidates_for_document
from .doc_diagnostics import build_document_diagnostics
from .generated_tests import (
    generate_coverage_test_drafts_for_document,
    generate_golden_tests_for_document,
    promote_coverage_test_drafts_for_document,
    run_coverage_promoted_tests_for_document,
    run_golden_tests_for_document,
    validate_coverage_test_drafts_for_document,
)
from .golden_generation import generate_golden_candidates
from .pipeline import PipelineEvent, run_document_pipeline, run_document_pipeline_and_tests, run_document_pipeline_with_progress
from .parse import parse_document
from .parse_risk_history import summarize_parse_risk_history
from .parse_risk_actions import generate_parse_risk_action_plan, review_parse_risk_repair_tasks
from .parse_views import list_parse_view_pages
from .quality import assess_document_quality
from .evidence import build_evidence_for_document
from .facts import build_facts_for_document
from .entities import build_entities_for_document
from .wiki_compiler import build_wiki_for_document
from .graph import build_graph_for_document
from .ingest import register_document
from .ingestion_acceptance import validate_document_ingestion
from .query_api import build_query_context
from .retrieval import search_knowledge_base
from .run_governance import prune_stale_runs
from .workspace_doctor import run_workspace_doctor
from .db import connect
from . import __version__


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
        }
        handler = routes.get(parsed.path)
        if handler is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return

        try:
            handler(body)
        except Exception as exc:  # pragma: no cover - last-resort API guard
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
        detail = generate_parse_risk_action_plan(
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
        detail = review_parse_risk_repair_tasks(self.server.workspace_root, doc_id, output_dir=output_dir)
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
        except Exception as exc:
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


def _hygiene_loop_snapshot(workspace_root: Path) -> dict[str, Any]:
    try:
        doctor = run_workspace_doctor(workspace_root, scope="all")
        prune_report = prune_stale_runs(workspace_root, dry_run=True, keep_current_code_version=True)
    except Exception as exc:
        loop: dict[str, Any] = {
            "doctor_status": "fail",
            "issue_count": 1,
            "issue_summary": {"ok": 0, "warn": 0, "fail": 1},
            "derived_state_checks": [],
            "issues": [
                {
                    "issue_id": "hygiene_snapshot_failed",
                    "scope": "dashboard",
                    "severity": "fail",
                    "message": str(exc),
                    "details": {},
                    "recommended_actions": ["workspace-doctor --scope all --json"],
                }
            ],
            "stale_run_summary": {},
            "prune_plan": {"dry_run": True, "summary": {}, "items": []},
            "artifacts": {
                "workspace_doctor": "workspace-doctor --scope all --json",
                "prune_stale_runs": "prune-stale-runs --keep-current-code-version --dry-run",
            },
        }
        _attach_hygiene_health(loop)
        return loop

    loop = {
        "doctor_status": doctor.status,
        "issue_count": len(doctor.issues),
        "issue_summary": doctor.summary,
        "derived_state_checks": [check.to_dict() for check in doctor.derived_state_checks],
        "issues": [issue.to_dict() for issue in doctor.issues[:20]],
        "issues_truncated": len(doctor.issues) > 20,
        "stale_run_summary": prune_report.summary,
        "prune_plan": _compact_prune_plan(prune_report.to_dict()),
        "artifacts": {
            "workspace_doctor": "workspace-doctor --scope all --json",
            "prune_stale_runs": "prune-stale-runs --keep-current-code-version --dry-run",
            "current_code_version": doctor.current_code_version,
            "database_path": doctor.database_path,
        },
    }
    _attach_hygiene_health(loop)
    return loop


def _compact_prune_plan(report: dict[str, Any]) -> dict[str, Any]:
    compact_items: list[dict[str, Any]] = []
    for item in report.get("items") if isinstance(report.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        candidate_ids = item.get("candidate_ids") if isinstance(item.get("candidate_ids"), list) else []
        compact_items.append(
            {
                "table": item.get("table"),
                "status": item.get("status"),
                "dry_run": item.get("dry_run"),
                "candidate_count": item.get("candidate_count"),
                "deleted_count": item.get("deleted_count"),
                "candidate_ids": candidate_ids[:10],
                "candidate_ids_truncated": bool(item.get("candidate_ids_truncated") or len(candidate_ids) > 10),
                "message": item.get("message"),
            }
        )
    return {
        "dry_run": bool(report.get("dry_run", True)),
        "current_code_version": report.get("current_code_version"),
        "suite_id": report.get("suite_id"),
        "older_than_days": report.get("older_than_days"),
        "keep_current_code_version": report.get("keep_current_code_version"),
        "status": report.get("status"),
        "summary": report.get("summary") if isinstance(report.get("summary"), dict) else {},
        "items": compact_items,
    }


def _attach_ingestion_health(loop: dict[str, Any]) -> None:
    coverage = loop.get("source_unit_coverage") if isinstance(loop.get("source_unit_coverage"), dict) else {}
    priority = loop.get("uncovered_priority") if isinstance(loop.get("uncovered_priority"), dict) else {}
    root_causes = priority.get("root_cause_counts") if isinstance(priority.get("root_cause_counts"), dict) else {}
    risks: list[dict[str, Any]] = []
    actions: list[str] = []
    if not int(loop.get("document_count") or 0):
        risks.append(_loop_risk("fail", "no_documents", "没有已注册文档，入库闭环无法证明。", "document_count", 0))
        actions.append("先上传或注册文档，然后运行 build-document-and-test。")
    if int(loop.get("document_count") or 0) and not int(loop.get("source_unit_count") or 0):
        risks.append(_loop_risk("warn", "no_source_units", "文档已存在但没有 source_units，覆盖闭环缺少可追踪单元。", "source_unit_count", 0))
        actions.append("重新运行入库流水线，确认 source_units 表和 coverage 报告生成。")
    uncovered_units = int(coverage.get("uncovered_units") or 0)
    rejected_test_gap_units = int(root_causes.get("test_gap_rejected") or 0)
    actionable_uncovered_units = max(uncovered_units - rejected_test_gap_units, 0)
    loop["actionable_uncovered_units"] = actionable_uncovered_units
    if actionable_uncovered_units:
        risks.append(
            _loop_risk(
                "warn",
                "uncovered_source_units",
                "存在需要处理的未覆盖 source units。",
                "actionable_uncovered_units",
                actionable_uncovered_units,
            )
        )
        if int(root_causes.get("extraction_gap") or 0):
            actions.append("优先处理 uncovered priority report 中的 extraction_gap，它表示文本有了但事实/对象抽取未闭合。")
        if int(root_causes.get("golden_gap") or 0):
            actions.append("对 golden_gap 只扩展已有 evidence/fact/wiki 覆盖的高优先级 source units。")
        if int(root_causes.get("source_unit_noise") or 0):
            actions.append("对 source_unit_noise 修 source unit inventory 过滤，不把低价值噪声当召回失败处理。")
        if not root_causes:
            actions.append("打开 Coverage / Test Gaps，按 source_unit 补 evidence、fact 或测试草案。")
    if coverage.get("evidence_coverage_rate") is None and int(loop.get("evidence_count") or 0):
        risks.append(_loop_risk("warn", "evidence_coverage_unlinked", "Dashboard 尚未具备 source_unit 到 evidence 的覆盖映射，不能证明 evidence 级覆盖率。", "evidence_coverage_rate", None))
        actions.append("补 source_unit 与 evidence 的可追踪映射，再启用 evidence_coverage_rate。")
    if coverage.get("fact_coverage_rate") is None and int(loop.get("fact_count") or 0):
        risks.append(_loop_risk("warn", "fact_coverage_unlinked", "Dashboard 尚未具备 source_unit 到 fact 的覆盖映射，不能证明 fact 级覆盖率。", "fact_coverage_rate", None))
        actions.append("补 source_unit 与 facts 的可追踪映射，再启用 fact_coverage_rate。")
    _attach_loop_health(loop, risks, actions, has_data=bool(loop.get("document_count")))


def _attach_parse_quality_health(loop: dict[str, Any]) -> None:
    profile = loop.get("parse_risk_profile") if isinstance(loop.get("parse_risk_profile"), dict) else {}
    root_causes = profile.get("root_cause_counts") if isinstance(profile.get("root_cause_counts"), dict) else {}
    risks: list[dict[str, Any]] = []
    actions: list[str] = []
    high_risk_pages = int(loop.get("parse_risk_pages") or 0)
    actionable_pages = int(loop.get("actionable_parse_risk_pages") or 0)
    chain_gap_pages = int(root_causes.get("source_unit_without_fact") or 0)
    if actionable_pages:
        risks.append(
            _loop_risk(
                "warn",
                "actionable_parse_risk_pages",
                "存在没有 evidence 支撑的高风险页面，解析质量闭环无法证明页面已被解析。",
                "actionable_parse_risk_pages",
                actionable_pages,
            )
        )
        actions.append("查看 parse_risk_profile.samples.no_evidence，先确认页面是否空白；若不是空白页，再修解析/OCR。")
    if chain_gap_pages:
        risks.append(
            _loop_risk(
                "warn",
                "parse_chain_gap_pages",
                "存在 evidence 已生成但 source unit 或 fact 映射未闭合的高风险页面。",
                "parse_chain_gap_pages",
                chain_gap_pages,
            )
        )
        actions.append("按 evidence_without_source_unit/source_unit_without_fact 样例重建 coverage 或 facts 映射。")
    _attach_loop_health(loop, risks, actions, has_data=bool(high_risk_pages or profile))


def _latest_eval_with_quality(
    connection,
    quality_key: str,
    *,
    code_version: str | None = None,
    suite_id_prefix: str | None = None,
) -> dict[str, Any] | None:
    for run in list_eval_runs(connection, limit=100):
        if code_version is not None and str(run.get("code_version") or "") != code_version:
            continue
        if suite_id_prefix is not None and not str(run.get("suite_id") or "").startswith(suite_id_prefix):
            continue
        summary = run.get("result_summary") if isinstance(run.get("result_summary"), dict) else {}
        quality = summary.get(quality_key) if isinstance(summary.get(quality_key), dict) else {}
        if int(quality.get("total") or 0) > 0:
            return run
    return None


def _attach_retrieval_health(loop: dict[str, Any]) -> None:
    risks: list[dict[str, Any]] = []
    actions: list[str] = []
    run_count = int(loop.get("retrieval_run_count") or 0)
    if not run_count:
        risks.append(_loop_risk("warn", "no_retrieval_runs", "没有 retrieval_runs，召回闭环缺少可审计记录。", "retrieval_run_count", 0))
        actions.append("运行 Golden / Regression 或 Query Lab，让每次查询写入 retrieval_runs。")
    recall_at_5 = _as_float(loop.get("recall_at_5"))
    if recall_at_5 is not None and recall_at_5 < 0.8:
        risks.append(_loop_risk("warn", "low_recall_at_5", "Recall@5 低于闭环阈值。", "recall_at_5", recall_at_5))
        actions.append("在 Failure Analysis 查看 retrieval_miss / rerank_wrong，并从 source_unit 或 graph 路由修复。")
    mrr = _as_float(loop.get("mrr"))
    if mrr is not None and mrr < 0.6:
        risks.append(_loop_risk("warn", "low_mrr", "MRR 偏低，正确证据排序靠后。", "mrr", mrr))
        actions.append("检查 rerank 特征、graph candidate 和 evidence shape 是否让正确内容进入前排。")
    negative_hit_rate = _as_float(loop.get("negative_hit_rate"))
    if negative_hit_rate is not None and negative_hit_rate > 0:
        risks.append(_loop_risk("warn", "negative_hits", "召回结果包含负例命中。", "negative_hit_rate", negative_hit_rate))
        actions.append("补充 negative_expected 并检查检索通道的主题约束。")
    graph = loop.get("graph_contribution") if isinstance(loop.get("graph_contribution"), dict) else {}
    current_graph = graph.get("current_version_graph") if isinstance(graph.get("current_version_graph"), dict) else {}
    current_code_runs = int(graph.get("current_code_version_runs") or 0)
    stale_or_unknown_runs = int(graph.get("stale_or_unknown_runs") or 0)
    graph_scope = current_graph if current_code_runs else graph
    graph_candidate_runs = int(graph_scope.get("graph_candidate_runs") or 0)
    graph_top_runs = int(graph_scope.get("graph_top_runs") or 0)
    graph_lost_runs = int(graph_scope.get("graph_lost_after_rerank_runs") or 0)
    retention_rate = _as_float(graph_scope.get("graph_retention_rate"))
    if stale_or_unknown_runs and current_code_runs <= 0:
        risks.append(_loop_risk("warn", "retrieval_runs_mixed_code_versions", "召回统计混有旧代码版本或未知版本运行，修复效果需要优先看 current_code_version_runs。", "stale_or_unknown_runs", stale_or_unknown_runs))
        actions.append("重新跑关键 query/golden suite，让 retrieval_runs 形成当前代码版本样本后再判断 graph retention。")
    elif stale_or_unknown_runs:
        actions.append("Dashboard 已按 current_version_graph 判断 graph 健康；旧版本 retrieval_runs 仅作为历史背景。")
    if graph_candidate_runs and graph_top_runs == 0:
        risks.append(_loop_risk("warn", "graph_candidates_never_retained", "Graph 有候选但没有进入 top rerank，贡献未被最终召回使用。", "graph_top_runs", 0))
        actions.append("检查 rerank 对 graph_source、graph_relation、trust_tier 的权重，避免 graph 候选全被后续排序挤掉。")
    elif graph_candidate_runs and retention_rate is not None and retention_rate < 0.25:
        risks.append(_loop_risk("warn", "low_graph_retention", "Graph 候选进入 top rerank 的比例偏低。", "graph_retention_rate", retention_rate))
        actions.append("抽样查看 graph_candidates_lost_after_rerank 的 query_type，按定义/生命周期/约束类分别调 rerank 特征。")
    if graph_lost_runs > graph_top_runs and graph_candidate_runs:
        risks.append(_loop_risk("warn", "graph_lost_after_rerank_dominates", "Graph 候选更多时候在 rerank 后丢失。", "graph_lost_after_rerank_runs", graph_lost_runs))
    _attach_loop_health(loop, risks, actions, has_data=bool(run_count))


def _attach_answer_health(loop: dict[str, Any]) -> None:
    risks: list[dict[str, Any]] = []
    actions: list[str] = []
    pass_rate = _as_float(loop.get("answer_pass_rate"))
    if pass_rate is None:
        risks.append(_loop_risk("warn", "no_answer_quality", "最新 eval run 没有 answer_quality 汇总。", "answer_pass_rate", None))
        actions.append("运行 Golden / Regression，生成 answer_quality 和 evidence shape 指标。")
    elif pass_rate < 0.8:
        risks.append(_loop_risk("fail", "low_answer_pass_rate", "答案通过率低于闭环阈值。", "answer_pass_rate", pass_rate))
        actions.append("从 Failure Analysis 按 answer_policy_wrong、llm_generation_wrong、contract_mismatch 分组修复。")
    forbidden_hit_rate = _as_float(loop.get("forbidden_hit_rate"))
    if forbidden_hit_rate is not None and forbidden_hit_rate > 0:
        risks.append(_loop_risk("fail", "forbidden_answer_output", "答案包含禁止内容或错误模式。", "forbidden_hit_rate", forbidden_hit_rate))
        actions.append("修复 answer policy 和输出清洗，不允许非法符号或噪声进入最终答案。")
    render_artifact_rate = _as_float(loop.get("render_artifact_rate"))
    if render_artifact_rate is not None and render_artifact_rate > 0:
        risks.append(_loop_risk("warn", "render_artifacts", "答案中仍有 HTML/渲染残留。", "render_artifact_rate", render_artifact_rate))
        actions.append("检查答案标准化层，确保 evidence 文本进入答案前统一清洗。")
    contract = loop.get("shape_contract_quality") if isinstance(loop.get("shape_contract_quality"), dict) else {}
    mismatch_count = int(contract.get("contract_mismatch_count") or 0)
    missing_count = int(contract.get("contract_missing_count") or 0)
    if mismatch_count:
        risks.append(_loop_risk("fail", "shape_contract_mismatch", "证据形状契约存在不匹配。", "contract_mismatch_count", mismatch_count))
        actions.append("按 shape_contract_reason_counts 定位是解析缺口、证据分类、召回还是答案策略问题。")
    if missing_count:
        risks.append(_loop_risk("warn", "shape_contract_missing", "部分问题缺少证据形状契约。", "contract_missing_count", missing_count))
        actions.append("补齐 query_type 到 evidence shape contract 的映射，避免答案层无约束。")
    _attach_loop_health(loop, risks, actions, has_data=pass_rate is not None or bool(contract))


def _attach_regression_health(loop: dict[str, Any]) -> None:
    risks: list[dict[str, Any]] = []
    actions: list[str] = []
    eval_run_count = int(loop.get("eval_run_count") or 0)
    if not eval_run_count:
        risks.append(_loop_risk("warn", "no_eval_runs", "没有 eval_runs，回归闭环无法比较版本变化。", "eval_run_count", 0))
        actions.append("运行 Golden / Regression，记录 eval_runs 和 eval_results。")
    latest_run = loop.get("latest_run") if isinstance(loop.get("latest_run"), dict) else {}
    if latest_run and str(latest_run.get("status") or "").lower() not in {"passed", "success", "completed"}:
        risks.append(_loop_risk("fail", "latest_eval_failed", "最新回归运行未通过。", "latest_run_status", latest_run.get("status")))
        actions.append("打开 Failure Analysis，按 failure_type 和 repair_tasks 修复根因。")
    result_summary = latest_run.get("result_summary") if isinstance(latest_run.get("result_summary"), dict) else {}
    pytest_counts = result_summary.get("pytest_counts") if isinstance(result_summary.get("pytest_counts"), dict) else {}
    eval_scope = result_summary.get("eval_scope") if isinstance(result_summary.get("eval_scope"), dict) else {}
    if latest_run and "eval_scope" not in result_summary:
        risks.append(_loop_risk("warn", "missing_eval_scope", "最新 eval run 缺少 eval_scope，无法证明声明用例是否都被评估。", "eval_scope", None))
        actions.append("重新运行 Golden / Regression，让 eval_runs 记录 declared、evaluated 和 unevaluated 用例数量。")
    if latest_run and "pytest_counts" not in result_summary:
        risks.append(_loop_risk("warn", "missing_pytest_counts", "最新 eval run 缺少 pytest_counts，无法证明测试选择范围。", "pytest_counts", None))
        actions.append("重新运行 Golden / Regression，让 eval_runs 记录 selected、deselected 和 collected 测试数量。")
    elif str(pytest_counts.get("source") or "") == "legacy_unavailable":
        risks.append(_loop_risk("warn", "pytest_counts_unavailable", "历史 eval run 已回填基础计数，但原始 pytest 选择范围不可恢复。", "pytest_counts_source", "legacy_unavailable"))
        actions.append("重新运行 Golden / Regression，生成真实 pytest_counts，替代历史回填值。")
    unevaluated_case_count = int(eval_scope.get("unevaluated_case_count") or 0)
    if unevaluated_case_count:
        risks.append(_loop_risk("fail", "eval_cases_not_evaluated", "本次 eval 存在声明但未实际评估的用例。", "unevaluated_case_count", unevaluated_case_count))
        actions.append("检查 eval runner 的 case_id 映射和结构化结果写入，避免未评估用例被粗略通过/失败覆盖。")
    deselected_count = int(pytest_counts.get("deselected") or 0)
    if deselected_count:
        risks.append(_loop_risk("warn", "tests_deselected", "本次回归有测试被 pytest marker 或选择条件排除。", "deselected", deselected_count))
        actions.append("复核 pytest_counts 和 pytest.ini marker 过滤，确认被 deselect 的测试是否应进入主回归。")
    draft_count = int(loop.get("draft_golden_case_count") or 0)
    if draft_count:
        risks.append(_loop_risk("warn", "draft_golden_cases", "存在待确认 golden 草案。", "draft_golden_case_count", draft_count))
        actions.append("审核 golden 草案 readiness，合格后激活进入回归集。")
    repair_task_count = int(loop.get("repair_task_count") or 0)
    repair_task_counts = loop.get("repair_task_status_counts") if isinstance(loop.get("repair_task_status_counts"), dict) else {}
    repair_task_coverage = loop.get("repair_task_coverage") if isinstance(loop.get("repair_task_coverage"), dict) else {}
    artifacts = loop.get("artifacts") if isinstance(loop.get("artifacts"), dict) else {}
    comparison = artifacts.get("comparison") if isinstance(artifacts.get("comparison"), dict) else {}
    blocked_count = int(repair_task_counts.get("blocked") or 0)
    reopened_count = int(repair_task_counts.get("reopened") or 0)
    in_progress_count = int(repair_task_counts.get("in_progress") or 0)
    proposed_count = int(repair_task_counts.get("proposed") or 0)
    uncovered_failure_count = int(repair_task_coverage.get("uncovered_failure_case_count") or 0)
    removed_case_count = int(comparison.get("removed_case_count") or 0)
    added_case_count = int(comparison.get("added_case_count") or 0)
    if removed_case_count:
        risks.append(_loop_risk("warn", "golden_case_removed_since_baseline", "当前回归集相对基线减少了用例，可能掩盖失败。", "removed_case_count", removed_case_count))
        actions.append("复核 removed_cases，确认是有意废弃；否则恢复 golden case 或标记 deprecated 原因。")
    if added_case_count:
        actions.append("复核 added_cases，确认新增用例具备 must_hit、negative_expected 和 evidence shape 约束。")
    if uncovered_failure_count:
        risks.append(_loop_risk("fail", "failure_without_repair_task", "存在未任务化的失败案例，回归闭环无法推动修复。", "uncovered_failure_case_count", uncovered_failure_count))
        actions.append("先补 Failure Analysis 到 repair task 的归因映射，再继续具体模块修复。")
    if reopened_count:
        risks.append(_loop_risk("fail", "reopened_repair_tasks", "已完成修复任务在后续回归中再次出现。", "reopened_repair_tasks", reopened_count))
        actions.append("优先复查 reopened repair task，确认修复是否未覆盖根因或出现回归。")
    if blocked_count:
        risks.append(_loop_risk("fail", "blocked_repair_tasks", "存在被阻塞的修复任务。", "blocked_repair_tasks", blocked_count))
        actions.append("先解除 blocked repair task 的依赖，再继续新增局部修复。")
    if repair_task_count:
        risks.append(_loop_risk("warn", "open_repair_tasks", "存在未关闭的修复任务。", "repair_task_count", repair_task_count))
        actions.append("在 Failure Analysis 按 repair task 聚合处理，不按单个问题硬修。")
    if proposed_count and not in_progress_count:
        actions.append("优先把高优先级 proposed repair task 转为 in_progress 或 dismissed，明确处理决策。")
    _attach_loop_health(loop, risks, actions, has_data=bool(eval_run_count))


def _attach_hygiene_health(loop: dict[str, Any]) -> None:
    risks: list[dict[str, Any]] = []
    actions: list[str] = []
    issues = loop.get("issues") if isinstance(loop.get("issues"), list) else []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("severity") or "warn")
        code = str(issue.get("issue_id") or "hygiene_issue")
        message = str(issue.get("message") or code)
        risks.append(_loop_risk(severity, code, message, "scope", issue.get("scope")))
        raw_actions = issue.get("recommended_actions")
        if isinstance(raw_actions, list):
            actions.extend(str(action) for action in raw_actions)
    if bool(loop.get("issues_truncated")):
        risks.append(
            _loop_risk(
                "warn",
                "hygiene_issues_truncated",
                "Dashboard 只展示前 20 个 hygiene issues，完整列表需要运行 workspace doctor。",
                "issue_count",
                loop.get("issue_count"),
            )
        )
        actions.append("workspace-doctor --scope all --json")

    stale_summary = loop.get("stale_run_summary") if isinstance(loop.get("stale_run_summary"), dict) else {}
    stale_retrieval = int(stale_summary.get("retrieval_runs") or 0)
    stale_eval = int(stale_summary.get("eval_runs") or 0)
    stale_eval_results = int(stale_summary.get("eval_results") or 0)
    if stale_retrieval or stale_eval or stale_eval_results:
        if not any(risk.get("code") in {"retrieval_runs_unknown_code_version", "retrieval_runs_stale_code_version", "eval_runs_unknown_code_version", "eval_runs_stale_code_version"} for risk in risks):
            risks.append(
                _loop_risk(
                    "warn",
                    "stale_or_unknown_runs",
                    "存在旧或未知 code_version 的 retrieval/eval runs。",
                    "candidate_runs",
                    stale_retrieval + stale_eval,
                )
            )
        actions.append("prune-stale-runs --keep-current-code-version --dry-run")

    doctor_status = str(loop.get("doctor_status") or "")
    if doctor_status == "fail" and not risks:
        risks.append(_loop_risk("fail", "workspace_doctor_failed", "workspace doctor failed.", "doctor_status", doctor_status))
        actions.append("workspace-doctor --scope all --json")

    _attach_loop_health(loop, risks, actions, has_data=bool(loop.get("issue_summary") or loop.get("derived_state_checks") or stale_summary))


def _attach_loop_health(loop: dict[str, Any], risks: list[dict[str, Any]], actions: list[str], *, has_data: bool) -> None:
    loop["risks"] = risks
    loop["next_actions"] = _unique_strings(actions)
    if not has_data and risks:
        loop["status"] = "unknown"
    elif any(risk.get("severity") == "fail" for risk in risks):
        loop["status"] = "fail"
    elif risks:
        loop["status"] = "warn"
    else:
        loop["status"] = "ok"


def _loop_risk(
    severity: str,
    code: str,
    message: str,
    metric: str | None = None,
    value: object | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if metric:
        payload["metric"] = metric
        payload["value"] = value
    return payload


def _body_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _count_rows(connection, table: str, where: str = "") -> int:
    if not _table_exists(connection, table):
        return 0
    where_clause = f" WHERE {where}" if where else ""
    return int(connection.execute(f"SELECT count(*) FROM {table}{where_clause}").fetchone()[0] or 0)


def _repair_task_status_counts(connection) -> dict[str, int]:
    if not _table_exists(connection, "repair_tasks"):
        return {
            "total": 0,
            "open": 0,
            "proposed": 0,
            "in_progress": 0,
            "reopened": 0,
            "blocked": 0,
            "done": 0,
            "dismissed": 0,
        }
    counts = {
        "total": 0,
        "open": 0,
        "proposed": 0,
        "in_progress": 0,
        "reopened": 0,
        "blocked": 0,
        "done": 0,
        "dismissed": 0,
    }
    rows = connection.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM repair_tasks
        GROUP BY status
        """
    ).fetchall()
    for row in rows:
        status = str(row["status"] or "unknown")
        count = int(row["count"] or 0)
        counts[status] = count
        counts["total"] += count
        if status not in {"done", "dismissed"}:
            counts["open"] += count
    return counts


def _repair_task_status_counts_from_tasks(tasks: list[Any]) -> dict[str, int]:
    counts = {
        "total": 0,
        "open": 0,
        "proposed": 0,
        "in_progress": 0,
        "reopened": 0,
        "blocked": 0,
        "done": 0,
        "dismissed": 0,
    }
    for task in tasks:
        if not isinstance(task, dict):
            continue
        status = str(task.get("status") or "unknown")
        counts[status] = int(counts.get(status, 0)) + 1
        counts["total"] += 1
        if status not in {"done", "dismissed"}:
            counts["open"] += 1
    return counts


def _sum_column(connection, table: str, column: str) -> int:
    if not _table_exists(connection, table):
        return 0
    columns = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        return 0
    return int(connection.execute(f"SELECT COALESCE(sum({column}), 0) FROM {table}").fetchone()[0] or 0)


def _table_exists(connection, table: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _safe_json(value: object, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return default


def _workspace_parse_risk_snapshot(connection, *, sample_limit: int = 10) -> dict[str, Any]:
    empty = {
        "high_risk_page_count": 0,
        "actionable_parse_risk_pages": 0,
        "evidence_backed_high_risk_pages": 0,
        "source_unit_backed_high_risk_pages": 0,
        "fact_backed_high_risk_pages": 0,
        "fully_backed_high_risk_pages": 0,
        "root_cause_counts": {},
        "top_documents": [],
        "samples": {
            "no_evidence": [],
            "evidence_without_source_unit": [],
            "source_unit_without_fact": [],
            "fully_backed": [],
        },
        "metric_contract": {
            "high_risk_page_count": "pages.risk_level = high",
            "actionable_parse_risk_pages": "high-risk pages with no evidence rows",
            "fully_backed_high_risk_pages": "high-risk pages with evidence + source_units + linked facts",
        },
    }
    if not _table_exists(connection, "pages"):
        return empty

    high_pages = connection.execute(
        """
        SELECT doc_id, page_no, page_status
        FROM pages
        WHERE risk_level = 'high'
        ORDER BY doc_id, page_no
        """
    ).fetchall()
    if not high_pages:
        return empty

    evidence_counts = _doc_page_counts(connection, "evidence")
    source_unit_counts = _doc_page_counts(connection, "source_units")
    fact_counts = _doc_page_fact_counts(connection)
    quality_flags = _quality_page_flags(connection)

    root_causes = {
        "no_evidence": 0,
        "evidence_without_source_unit": 0,
        "source_unit_without_fact": 0,
        "fully_backed": 0,
    }
    doc_counts: dict[str, dict[str, int]] = {}
    samples: dict[str, list[dict[str, Any]]] = {
        "no_evidence": [],
        "evidence_without_source_unit": [],
        "source_unit_without_fact": [],
        "fully_backed": [],
    }
    evidence_backed = 0
    source_unit_backed = 0
    fact_backed = 0

    for row in high_pages:
        doc_id = str(row["doc_id"] or "")
        page_no = int(row["page_no"] or 0)
        key = (doc_id, page_no)
        evidence_count = evidence_counts.get(key, 0)
        source_unit_count = source_unit_counts.get(key, 0)
        fact_count = fact_counts.get(key, 0)
        if evidence_count:
            evidence_backed += 1
        if source_unit_count:
            source_unit_backed += 1
        if fact_count:
            fact_backed += 1

        if evidence_count == 0:
            category = "no_evidence"
        elif source_unit_count == 0:
            category = "evidence_without_source_unit"
        elif fact_count == 0:
            category = "source_unit_without_fact"
        else:
            category = "fully_backed"
        root_causes[category] += 1

        doc_entry = doc_counts.setdefault(
            doc_id,
            {
                "high_risk_page_count": 0,
                "actionable_parse_risk_pages": 0,
                "fully_backed_high_risk_pages": 0,
                "evidence_without_source_unit": 0,
                "source_unit_without_fact": 0,
            },
        )
        doc_entry["high_risk_page_count"] += 1
        if category == "no_evidence":
            doc_entry["actionable_parse_risk_pages"] += 1
        elif category == "fully_backed":
            doc_entry["fully_backed_high_risk_pages"] += 1
        elif category in {"evidence_without_source_unit", "source_unit_without_fact"}:
            doc_entry[category] += 1

        if len(samples[category]) < sample_limit:
            samples[category].append(
                {
                    "doc_id": doc_id,
                    "page_no": page_no,
                    "page_status": row["page_status"],
                    "risk_flags": quality_flags.get(key, []),
                    "evidence_count": evidence_count,
                    "source_unit_count": source_unit_count,
                    "linked_fact_count": fact_count,
                }
            )

    top_documents = [
        {"doc_id": doc_id, **counts}
        for doc_id, counts in sorted(
            doc_counts.items(),
            key=lambda item: (
                item[1]["actionable_parse_risk_pages"],
                item[1]["high_risk_page_count"],
            ),
            reverse=True,
        )
    ][:5]
    high_risk_count = len(high_pages)
    fully_backed = root_causes["fully_backed"]
    return {
        "high_risk_page_count": high_risk_count,
        "actionable_parse_risk_pages": root_causes["no_evidence"],
        "evidence_backed_high_risk_pages": evidence_backed,
        "source_unit_backed_high_risk_pages": source_unit_backed,
        "fact_backed_high_risk_pages": fact_backed,
        "fully_backed_high_risk_pages": fully_backed,
        "evidence_backed_rate": round(evidence_backed / high_risk_count, 6),
        "source_unit_backed_rate": round(source_unit_backed / high_risk_count, 6),
        "fully_backed_rate": round(fully_backed / high_risk_count, 6),
        "root_cause_counts": root_causes,
        "top_documents": top_documents,
        "samples": samples,
        "metric_contract": empty["metric_contract"],
    }


def _doc_page_counts(connection, table: str) -> dict[tuple[str, int], int]:
    if not _table_exists(connection, table):
        return {}
    columns = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    if not {"doc_id", "page_no"}.issubset(columns):
        return {}
    rows = connection.execute(
        f"""
        SELECT doc_id, page_no, count(*) AS count
        FROM {table}
        WHERE page_no IS NOT NULL
        GROUP BY doc_id, page_no
        """
    ).fetchall()
    return {
        (str(row["doc_id"] or ""), int(row["page_no"] or 0)): int(row["count"] or 0)
        for row in rows
    }


def _doc_page_fact_counts(connection) -> dict[tuple[str, int], int]:
    if not _table_exists(connection, "fact_evidence_map") or not _table_exists(connection, "evidence"):
        return {}
    rows = connection.execute(
        """
        SELECT e.doc_id, e.page_no, count(DISTINCT fem.fact_id) AS count
        FROM evidence e
        JOIN fact_evidence_map fem ON fem.evidence_id = e.evidence_id
        WHERE e.page_no IS NOT NULL
        GROUP BY e.doc_id, e.page_no
        """
    ).fetchall()
    return {
        (str(row["doc_id"] or ""), int(row["page_no"] or 0)): int(row["count"] or 0)
        for row in rows
    }


def _quality_page_flags(connection) -> dict[tuple[str, int], list[str]]:
    if not _table_exists(connection, "quality_reports"):
        return {}
    rows = connection.execute("SELECT doc_id, report_json FROM quality_reports").fetchall()
    flags_by_page: dict[tuple[str, int], list[str]] = {}
    for row in rows:
        doc_id = str(row["doc_id"] or "")
        payload = _safe_json(row["report_json"], {})
        pages = payload.get("pages") if isinstance(payload, dict) else None
        if not isinstance(pages, list):
            continue
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_no = _as_int(page.get("page_no"))
            if page_no is None:
                continue
            raw_flags = page.get("risk_flags")
            flags = raw_flags if isinstance(raw_flags, list) else []
            flags_by_page[(doc_id, page_no)] = [str(flag) for flag in flags if str(flag).strip()]
    return flags_by_page


def _workspace_coverage_snapshot(connection) -> dict[str, Any]:
    ensure_source_unit_mapping_tables(connection)
    source_units = _count_rows(connection, "source_units")
    if not source_units:
        return {
            "source_unit_count": 0,
            "source_unit_coverage_rate": None,
            "evidence_coverage_rate": None,
            "fact_coverage_rate": None,
            "tested_rate": None,
            "uncovered_units": 0,
            "metric_contract": {
                "source_unit_coverage_rate": "source_units.status in covered/tested/partial",
                "evidence_coverage_rate": "source_unit_evidence_map distinct unit_id / source_units",
                "fact_coverage_rate": "source_unit_fact_map distinct unit_id / source_units",
            },
        }
    rows = connection.execute(
        """
        SELECT
            sum(CASE WHEN status IN ('covered', 'tested', 'partial') THEN 1 ELSE 0 END) AS covered,
            sum(CASE WHEN status = 'tested' THEN 1 ELSE 0 END) AS tested
        FROM source_units
        """
    ).fetchone()
    covered = int(rows["covered"] or 0)
    tested = int(rows["tested"] or 0)
    source_unit_coverage_rate = round(covered / source_units, 6)
    evidence_covered = _count_distinct_source_unit_links(connection, "source_unit_evidence_map")
    fact_covered = _count_distinct_source_unit_links(connection, "source_unit_fact_map")
    return {
        "source_unit_count": source_units,
        "source_unit_coverage_rate": source_unit_coverage_rate,
        "evidence_coverage_rate": round(evidence_covered / source_units, 6),
        "fact_coverage_rate": round(fact_covered / source_units, 6),
        "tested_rate": round(tested / source_units, 6),
        "uncovered_units": max(source_units - covered, 0),
        "legacy_evidence_coverage_rate": source_unit_coverage_rate,
        "metric_contract": {
            "source_unit_coverage_rate": "source_units.status in covered/tested/partial",
            "evidence_coverage_rate": "source_unit_evidence_map distinct unit_id / source_units",
            "fact_coverage_rate": "source_unit_fact_map distinct unit_id / source_units",
            "legacy_evidence_coverage_rate": "deprecated_alias_for_source_unit_coverage_rate",
        },
    }


def _count_distinct_source_unit_links(connection, table: str) -> int:
    if not _table_exists(connection, table):
        return 0
    row = connection.execute(
        f"""
        SELECT count(DISTINCT map.unit_id)
        FROM {table} map
        JOIN source_units su ON su.unit_id = map.unit_id
        """
    ).fetchone()
    return int(row[0] or 0)


def _graph_contribution_snapshot(connection, *, limit: int = 500) -> dict[str, Any]:
    _ensure_retrieval_runs_code_version_column(connection)
    rows = connection.execute(
        """
        SELECT run_id, query, query_type, reranked_ids_json, metadata_json, code_version, created_at
        FROM retrieval_runs
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    total_runs = len(rows)
    graph_requested_runs = 0
    graph_candidate_runs = 0
    graph_top_runs = 0
    graph_lost_after_rerank_runs = 0
    graph_top_hit_count = 0
    graph_candidate_count_total = 0
    by_query_type: dict[str, dict[str, int]] = {}
    lost_samples: list[dict[str, Any]] = []
    current_code_version = _runtime_code_version()
    current_code_version_runs = 0
    stale_or_unknown_runs = 0
    code_version_counts: dict[str, int] = {}
    current_graph_requested_runs = 0
    current_graph_candidate_runs = 0
    current_graph_top_runs = 0
    current_graph_lost_after_rerank_runs = 0

    for row in rows:
        code_version = str(row["code_version"] or "unknown")
        is_current_code_version = code_version == current_code_version
        code_version_counts[code_version] = code_version_counts.get(code_version, 0) + 1
        if is_current_code_version:
            current_code_version_runs += 1
        else:
            stale_or_unknown_runs += 1
        metadata = _safe_json(row["metadata_json"], {})
        if not isinstance(metadata, dict):
            metadata = {}
        retrieval_plan = metadata.get("retrieval_plan") if isinstance(metadata.get("retrieval_plan"), dict) else {}
        channels = [str(item) for item in retrieval_plan.get("channels") or []]
        graph_requested = "graph" in channels
        graph_candidate_count = _as_int(metadata.get("graph_hit_count"))
        if graph_candidate_count is None:
            graph_candidate_count = _as_int(retrieval_plan.get("graph_candidate_count")) or 0
        rerank_explanations = metadata.get("rerank_explanations") if isinstance(metadata.get("rerank_explanations"), list) else []
        top_graph_source_count = sum(
            1
            for item in rerank_explanations
            if isinstance(item, dict) and item.get("graph_source")
        )
        query_type = str(row["query_type"] or "unknown")
        bucket = by_query_type.setdefault(
            query_type,
            {
                "total_runs": 0,
                "graph_requested_runs": 0,
                "graph_candidate_runs": 0,
                "graph_top_runs": 0,
                "graph_lost_after_rerank_runs": 0,
            },
        )
        bucket["total_runs"] += 1
        if graph_requested:
            graph_requested_runs += 1
            bucket["graph_requested_runs"] += 1
            if is_current_code_version:
                current_graph_requested_runs += 1
        if graph_candidate_count > 0:
            graph_candidate_runs += 1
            graph_candidate_count_total += graph_candidate_count
            bucket["graph_candidate_runs"] += 1
            if is_current_code_version:
                current_graph_candidate_runs += 1
        if top_graph_source_count > 0:
            graph_top_runs += 1
            graph_top_hit_count += top_graph_source_count
            bucket["graph_top_runs"] += 1
            if is_current_code_version:
                current_graph_top_runs += 1
        if graph_requested and graph_candidate_count > 0 and top_graph_source_count <= 0:
            graph_lost_after_rerank_runs += 1
            bucket["graph_lost_after_rerank_runs"] += 1
            if is_current_code_version:
                current_graph_lost_after_rerank_runs += 1
            if len(lost_samples) < 5:
                reranked_ids = _safe_json(row["reranked_ids_json"], [])
                if not isinstance(reranked_ids, list):
                    reranked_ids = []
                lost_samples.append(
                    {
                        "run_id": row["run_id"],
                        "query": row["query"],
                        "query_type": query_type,
                        "graph_candidate_count": graph_candidate_count,
                        "reranked_ids": reranked_ids[:5],
                    }
                )

    graph_retention_rate = round(graph_top_runs / graph_candidate_runs, 6) if graph_candidate_runs else None
    graph_request_rate = round(graph_requested_runs / total_runs, 6) if total_runs else None
    graph_candidate_rate = round(graph_candidate_runs / graph_requested_runs, 6) if graph_requested_runs else None
    current_graph_retention_rate = (
        round(current_graph_top_runs / current_graph_candidate_runs, 6)
        if current_graph_candidate_runs
        else None
    )
    return {
        "sample_size": total_runs,
        "graph_requested_runs": graph_requested_runs,
        "graph_candidate_runs": graph_candidate_runs,
        "graph_top_runs": graph_top_runs,
        "graph_lost_after_rerank_runs": graph_lost_after_rerank_runs,
        "graph_top_hit_count": graph_top_hit_count,
        "graph_candidate_count_total": graph_candidate_count_total,
        "graph_request_rate": graph_request_rate,
        "graph_candidate_rate": graph_candidate_rate,
        "graph_retention_rate": graph_retention_rate,
        "current_code_version": current_code_version,
        "current_code_version_runs": current_code_version_runs,
        "stale_or_unknown_runs": stale_or_unknown_runs,
        "code_version_counts": dict(sorted(code_version_counts.items())),
        "current_version_graph": {
            "sample_size": current_code_version_runs,
            "graph_requested_runs": current_graph_requested_runs,
            "graph_candidate_runs": current_graph_candidate_runs,
            "graph_top_runs": current_graph_top_runs,
            "graph_lost_after_rerank_runs": current_graph_lost_after_rerank_runs,
            "graph_retention_rate": current_graph_retention_rate,
        },
        "by_query_type": dict(sorted(by_query_type.items())),
        "lost_after_rerank_samples": lost_samples,
    }


def _ensure_retrieval_runs_code_version_column(connection) -> None:
    rows = connection.execute("PRAGMA table_info(retrieval_runs)").fetchall()
    columns = {str(row["name"]) for row in rows}
    if "code_version" not in columns:
        connection.execute("ALTER TABLE retrieval_runs ADD COLUMN code_version TEXT")


def _latest_uncovered_priority_snapshot(paths: AppPaths) -> dict[str, Any]:
    reports = sorted(
        paths.coverage_reports.glob("all_docs_uncovered_priority_report_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        return {
            "available": False,
            "json_path": None,
            "report_path": None,
            "issue_count": None,
            "root_cause_counts": {},
            "status_counts": {},
            "top_documents": [],
            "top_issues": [],
        }
    path = reports[0]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "available": False,
            "json_path": str(path),
            "report_path": None,
            "issue_count": None,
            "root_cause_counts": {},
            "status_counts": {},
            "top_documents": [],
            "top_issues": [],
            "error": "uncovered_priority_report_unreadable",
        }
    documents = [doc for doc in list(payload.get("documents") or []) if isinstance(doc, dict)]
    documents.sort(key=lambda item: -int(item.get("priority_score") or 0))
    report_path = path.with_suffix(".md")
    return {
        "available": True,
        "generated_at": payload.get("generated_at"),
        "json_path": str(path),
        "report_path": str(report_path) if report_path.exists() else None,
        "issue_count": payload.get("issue_count"),
        "root_cause_counts": dict(payload.get("root_cause_counts") or {}),
        "status_counts": dict(payload.get("status_counts") or {}),
        "top_documents": [
            {
                "doc_id": doc.get("doc_id"),
                "source_filename": doc.get("source_filename"),
                "quality_status": doc.get("quality_status"),
                "priority_score": doc.get("priority_score"),
                "root_cause_counts": doc.get("root_cause_counts") or {},
                "status_counts": doc.get("status_counts") or {},
            }
            for doc in documents[:5]
        ],
        "top_issues": [
            {
                "doc_id": issue.get("doc_id"),
                "unit_id": issue.get("unit_id"),
                "coverage_status": issue.get("coverage_status"),
                "root_cause": issue.get("root_cause"),
                "priority_score": issue.get("priority_score"),
                "unit_type": issue.get("unit_type"),
                "importance": issue.get("importance"),
                "page_no": issue.get("page_no"),
                "semantic_key": issue.get("semantic_key"),
            }
            for issue in list(payload.get("top_issues") or [])[:10]
            if isinstance(issue, dict)
        ],
    }


def serve_api(workspace_root: Path, host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ApiServer((host, port), workspace_root)
    try:
        server.serve_forever()
    finally:
        server.server_close()
