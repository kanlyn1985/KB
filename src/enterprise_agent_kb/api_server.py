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
    build_failure_analysis,
    compare_eval_runs,
    draft_golden_case_from_failure,
    get_eval_run_detail,
    get_retrieval_run_detail,
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
from .pipeline import run_document_pipeline, run_document_pipeline_and_tests
from .parse import parse_document
from .quality import assess_document_quality
from .evidence import build_evidence_for_document
from .facts import build_facts_for_document
from .entities import build_entities_for_document
from .wiki_compiler import build_wiki_for_document
from .graph import build_graph_for_document
from .ingest import register_document
from .query_api import build_query_context
from .retrieval import search_knowledge_base
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
            "/activate-golden-draft": self._handle_activate_golden_draft,
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
        self._record_audit("build_document", {"doc_id": doc_id, "result": result.__dict__})
        self._write_json(HTTPStatus.OK, result.__dict__)

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
        self._record_audit("build_document_and_test", {"doc_id": doc_id, "result": result.__dict__})
        self._write_json(HTTPStatus.OK, result.__dict__)

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

        self._write_json(
            HTTPStatus.OK,
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
        )

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
        self._update_job(job_id, progress=15, stage="parse")
        parse_result = parse_document(self.server.workspace_root, doc_id)
        self._update_job(job_id, progress=30, stage="quality")
        quality_result = assess_document_quality(self.server.workspace_root, doc_id)
        self._update_job(job_id, progress=45, stage="evidence")
        evidence_result = build_evidence_for_document(self.server.workspace_root, doc_id)
        self._update_job(job_id, progress=60, stage="facts")
        facts_result = build_facts_for_document(self.server.workspace_root, doc_id)
        self._update_job(job_id, progress=72, stage="entities")
        entities_result = build_entities_for_document(self.server.workspace_root, doc_id)
        self._update_job(job_id, progress=84, stage="wiki")
        wiki_result = build_wiki_for_document(self.server.workspace_root, doc_id)
        self._update_job(job_id, progress=94, stage="graph")
        graph_result = build_graph_for_document(self.server.workspace_root, doc_id)
        from .coverage import build_coverage_for_document
        self._update_job(job_id, progress=98, stage="coverage")
        coverage_result = build_coverage_for_document(self.server.workspace_root, doc_id)
        return {
            "doc_id": doc_id,
            "parser_engine": parse_result.parser_engine,
            "page_count": parse_result.page_count,
            "block_count": parse_result.block_count,
            "overall_score": quality_result.overall_score,
            "evidence_count": evidence_result.evidence_count,
            "fact_count": facts_result.fact_count,
            "entity_count": entities_result.entity_count,
            "wiki_page_count": wiki_result.page_count,
            "edge_count": graph_result.edge_count,
            "coverage_source_unit_count": coverage_result.source_unit_count,
            "coverage_text_rate": coverage_result.text_coverage_rate,
            "coverage_semantic_rate": coverage_result.semantic_coverage_rate,
            "coverage_object_rate": coverage_result.object_coverage_rate,
            "coverage_test_rate": coverage_result.test_coverage_rate,
            "coverage_uncovered_count": sum(coverage_result.uncovered_counts.values()),
            "coverage_summary_path": str(coverage_result.summary_path),
            "coverage_report_path": str(coverage_result.report_path),
        }

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
            latest_retrieval_eval = _latest_eval_with_quality(connection, "retrieval_quality")
            latest_answer_eval = _latest_eval_with_quality(connection, "answer_quality")
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
            coverage = _workspace_coverage_snapshot(connection)
            uncovered_priority = _latest_uncovered_priority_snapshot(paths)
            latest_failure_analysis: dict[str, Any] | None = None
            repair_tasks: list[Any] = []
            repair_task_count = 0
            if latest_eval:
                latest_failure_analysis = build_failure_analysis(connection, str(latest_eval[0].get("eval_run_id") or ""))
                if latest_failure_analysis:
                    connection.commit()
            repair_tasks = list_repair_tasks(connection, limit=5)
            repair_task_status_counts = _repair_task_status_counts(connection)
            repair_task_count = int(repair_task_status_counts.get("open", 0))
            ingestion_loop = {
                "document_count": _count_rows(connection, "documents"),
                "page_count": _count_rows(connection, "pages"),
                "block_count": _count_rows(connection, "blocks"),
                "evidence_count": _count_rows(connection, "evidence"),
                "fact_count": _count_rows(connection, "facts"),
                "source_unit_count": _count_rows(connection, "source_units"),
                "source_unit_coverage": coverage,
                "uncovered_priority": uncovered_priority,
                "parse_risk_pages": _sum_column(connection, "quality_reports", "high_risk_page_count"),
                "artifacts": {
                    "coverage_snapshot_available": bool(coverage.get("source_unit_count")),
                    "coverage_report": "source_units",
                    "uncovered_priority_report": uncovered_priority,
                    "diagnostics": "document-diagnostics",
                },
            }
            retrieval_loop = {
                "retrieval_run_count": _count_rows(connection, "retrieval_runs"),
                "latest_run": latest_retrieval[0] if latest_retrieval else None,
                "recall_at_5": retrieval_quality.get("recall_at_5"),
                "recall_at_10": retrieval_quality.get("recall_at_10"),
                "mrr": retrieval_quality.get("mrr"),
                "negative_hit_rate": retrieval_quality.get("negative_hit_rate"),
                "artifacts": {
                    "latest_retrieval_run_id": latest_retrieval[0].get("run_id") if latest_retrieval else None,
                    "retrieval_runs_available": bool(latest_retrieval),
                    "latest_eval_run_id": latest_retrieval_eval.get("eval_run_id") if latest_retrieval_eval else None,
                    "latest_eval_suite_id": latest_retrieval_eval.get("suite_id") if latest_retrieval_eval else None,
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
                    "failure_analysis_available": bool(latest_failure_analysis),
                    "failure_count": latest_failure_analysis.get("failure_count") if latest_failure_analysis else None,
                    "repair_task_count": repair_task_count,
                },
            }
            regression_loop = {
                "eval_run_count": _count_rows(connection, "eval_runs"),
                "latest_run": latest_eval[0] if latest_eval else None,
                "new_failures": None,
                "repair_task_count": repair_task_count,
                "repair_task_status_counts": repair_task_status_counts,
                "repair_task_coverage": latest_failure_analysis.get("repair_task_coverage") if latest_failure_analysis else None,
                "golden_case_count": _count_rows(connection, "golden_cases"),
                "active_golden_case_count": _count_rows(connection, "golden_cases", "status = 'active'"),
                "draft_golden_case_count": _count_rows(connection, "golden_cases", "status = 'draft'"),
                "artifacts": {
                    "latest_eval_run_id": latest_eval[0].get("eval_run_id") if latest_eval else None,
                    "failure_analysis_available": bool(latest_failure_analysis),
                    "failure_count": latest_failure_analysis.get("failure_count") if latest_failure_analysis else None,
                    "repair_task_coverage": latest_failure_analysis.get("repair_task_coverage") if latest_failure_analysis else None,
                    "repair_tasks": repair_tasks[:5],
                    "repair_task_status_counts": repair_task_status_counts,
                    "comparison": latest_failure_analysis.get("comparison") if latest_failure_analysis else None,
                },
            }
            _attach_ingestion_health(ingestion_loop)
            _attach_retrieval_health(retrieval_loop)
            _attach_answer_health(answer_loop)
            _attach_regression_health(regression_loop)
            return {
                "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "ingestion_loop": ingestion_loop,
                "retrieval_loop": retrieval_loop,
                "answer_loop": answer_loop,
                "regression_loop": regression_loop,
            }
        finally:
            connection.close()


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
    if uncovered_units:
        risks.append(_loop_risk("warn", "uncovered_source_units", "存在未覆盖 source units。", "uncovered_units", uncovered_units))
        if int(root_causes.get("extraction_gap") or 0):
            actions.append("优先处理 uncovered priority report 中的 extraction_gap，它表示文本有了但事实/对象抽取未闭合。")
        if int(root_causes.get("golden_gap") or 0):
            actions.append("对 golden_gap 只扩展已有 evidence/fact/wiki 覆盖的高优先级 source units。")
        if int(root_causes.get("source_unit_noise") or 0):
            actions.append("对 source_unit_noise 修 source unit inventory 过滤，不把低价值噪声当召回失败处理。")
        if not root_causes:
            actions.append("打开 Coverage / Test Gaps，按 source_unit 补 evidence、fact 或测试草案。")
    parse_risk_pages = int(loop.get("parse_risk_pages") or 0)
    if parse_risk_pages:
        risks.append(_loop_risk("warn", "parse_risk_pages", "解析质量报告中存在高风险页面。", "parse_risk_pages", parse_risk_pages))
        actions.append("查看 Document Diagnostics，优先修复表格、标题层级和 OCR/分页风险。")
    _attach_loop_health(loop, risks, actions, has_data=bool(loop.get("document_count")))


def _latest_eval_with_quality(connection, quality_key: str) -> dict[str, Any] | None:
    for run in list_eval_runs(connection, limit=100):
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


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
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


def _workspace_coverage_snapshot(connection) -> dict[str, Any]:
    source_units = _count_rows(connection, "source_units")
    if not source_units:
        return {
            "source_unit_count": 0,
            "evidence_coverage_rate": None,
            "fact_coverage_rate": None,
            "tested_rate": None,
            "uncovered_units": 0,
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
    return {
        "source_unit_count": source_units,
        "evidence_coverage_rate": round(covered / source_units, 6),
        "fact_coverage_rate": None,
        "tested_rate": round(tested / source_units, 6),
        "uncovered_units": max(source_units - covered, 0),
    }


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
