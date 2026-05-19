from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

import pytest

from enterprise_agent_kb.api_server import ApiServer
from enterprise_agent_kb.api_server import _attach_ingestion_health
from enterprise_agent_kb.api_server import _attach_regression_health
from enterprise_agent_kb.api_server import _attach_retrieval_health
from enterprise_agent_kb.api_server import _attach_hygiene_health
from enterprise_agent_kb.api_server import _graph_contribution_snapshot
from enterprise_agent_kb.api_server import _hygiene_loop_snapshot
from enterprise_agent_kb.api_server import _latest_eval_with_quality
from enterprise_agent_kb.api_server import _latest_uncovered_priority_snapshot
from enterprise_agent_kb.api_server import _repair_task_status_counts_from_tasks
from enterprise_agent_kb.api_server import _workspace_coverage_snapshot
from enterprise_agent_kb.api_server import _workspace_parse_risk_snapshot
from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.closed_loop_store import (
    _runtime_code_version,
    record_eval_run,
    record_retrieval_run,
    sync_golden_cases,
    sync_source_units_from_matrix,
)
from enterprise_agent_kb.config import AppPaths
from enterprise_agent_kb.db import connect
from test_helpers import resolve_doc_id_by_filename


WORKSPACE = Path("knowledge_base")


class _FakeParseRiskPlan:
    def __init__(self, doc_id: str, persisted: bool) -> None:
        self.doc_id = doc_id
        self.persisted = persisted

    def to_dict(self) -> dict[str, object]:
        return {
            "doc_id": self.doc_id,
            "status": "action_required",
            "repair_tasks": [],
            "golden_candidate_requests": [],
            "persist_repair_tasks": self.persisted,
            "persisted_repair_tasks": [{"task_id": "REPAIR-PARSE-TEST"}] if self.persisted else [],
        }


class _FakeParseRiskRepairReview:
    def __init__(self, doc_id: str) -> None:
        self.doc_id = doc_id

    def to_dict(self) -> dict[str, object]:
        return {
            "doc_id": self.doc_id,
            "review_count": 1,
            "status_counts": {"done": 1},
            "reviews": [{"task_id": "REPAIR-PARSE-TEST", "suggested_status": "done"}],
        }


@pytest.mark.unit
def test_dashboard_quality_eval_selection_does_not_cross_loop_pollute(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", Path("src/enterprise_agent_kb/schema.sql"))
    connection = connect(paths.db_file)
    try:
        retrieval_case = {"case_id": "CASE-RET", "query": "Q1", "must_include": "A", "assert_mode": "context_contains"}
        answer_case = {"case_id": "CASE-ANS", "query": "Q2", "must_include": "B", "assert_mode": "rich_answer"}
        record_eval_run(
            connection,
            suite_id="regression:query_repair_smoke",
            cases=[answer_case],
            summary={"suite": "query_repair_smoke"},
            command="answer",
            success=True,
            output="",
            case_results=[
                {
                    "case_id": "CASE-ANS",
                    "passed": True,
                    "metrics": {
                        "retrieval_quality": {"recall_at_5": 1.0, "recall_at_10": 1.0, "mrr": 1.0, "negative_hit_rate": 0.0, "failure_attribution": "ok"},
                        "answer_quality": {"answer_pass": True, "failure_attribution": "ok", "forbidden_hit_count": 0},
                    },
                }
            ],
        )
        record_eval_run(
            connection,
            suite_id="regression:user_query_retrieval",
            cases=[retrieval_case],
            summary={"suite": "user_query_retrieval"},
            command="retrieval",
            success=True,
            output="",
            case_results=[
                {
                    "case_id": "CASE-RET",
                    "passed": True,
                    "metrics": {
                        "retrieval_quality": {"recall_at_5": 0.5, "recall_at_10": 1.0, "mrr": 0.5, "negative_hit_rate": 0.0, "failure_attribution": "ok"}
                    },
                }
            ],
        )
        connection.commit()

        retrieval_eval = _latest_eval_with_quality(connection, "retrieval_quality")
        answer_eval = _latest_eval_with_quality(connection, "answer_quality")

        assert retrieval_eval is not None
        assert retrieval_eval["suite_id"] == "regression:user_query_retrieval"
        assert answer_eval is not None
        assert answer_eval["suite_id"] == "regression:query_repair_smoke"
    finally:
        connection.close()


@pytest.mark.unit
def test_dashboard_quality_eval_selection_can_require_current_code_version(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", Path("src/enterprise_agent_kb/schema.sql"))
    connection = connect(paths.db_file)
    try:
        current_code_version = _runtime_code_version()
        stale_answer_case = {"case_id": "CASE-ANS-OLD", "query": "Q1", "assert_mode": "rich_answer"}
        current_retrieval_case = {"case_id": "CASE-RET", "query": "Q2", "assert_mode": "context_contains"}
        record_eval_run(
            connection,
            suite_id="golden:DOC-OLD",
            cases=[stale_answer_case],
            summary={"suite": "old_answer"},
            command="answer",
            success=True,
            output="",
            code_version="legacy-unknown",
            case_results=[
                {
                    "case_id": "CASE-ANS-OLD",
                    "passed": False,
                    "failure_reason": "answer_render_artifact",
                    "metrics": {
                        "answer_quality": {
                            "answer_pass": False,
                            "failure_attribution": "answer_render_artifact",
                            "forbidden_hit_count": 0,
                            "render_artifact_count": 1,
                        }
                    },
                }
            ],
        )
        record_eval_run(
            connection,
            suite_id="regression:user_query_retrieval:current-code",
            cases=[current_retrieval_case],
            summary={"suite": "current_retrieval"},
            command="retrieval",
            success=True,
            output="",
            code_version=current_code_version,
            case_results=[
                {
                    "case_id": "CASE-RET",
                    "passed": True,
                    "metrics": {
                        "retrieval_quality": {
                            "recall_at_5": 1.0,
                            "recall_at_10": 1.0,
                            "mrr": 1.0,
                            "negative_hit_rate": 0.0,
                            "failure_attribution": "ok",
                        }
                    },
                }
            ],
        )
        connection.commit()

        historical_answer_eval = _latest_eval_with_quality(connection, "answer_quality")
        current_answer_eval = _latest_eval_with_quality(
            connection,
            "answer_quality",
            code_version=current_code_version,
        )
        current_retrieval_eval = _latest_eval_with_quality(
            connection,
            "retrieval_quality",
            code_version=current_code_version,
        )

        assert historical_answer_eval is not None
        assert historical_answer_eval["suite_id"] == "golden:DOC-OLD"
        assert current_answer_eval is None
        assert current_retrieval_eval is not None
        assert current_retrieval_eval["suite_id"] == "regression:user_query_retrieval:current-code"
    finally:
        connection.close()


@pytest.mark.unit
def test_dashboard_retrieval_eval_selection_prefers_user_query_suite(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", Path("src/enterprise_agent_kb/schema.sql"))
    connection = connect(paths.db_file)
    try:
        current_code_version = _runtime_code_version()
        user_case = {"case_id": "CASE-UQ", "query": "Q1", "assert_mode": "context_contains"}
        smoke_case = {"case_id": "CASE-SMOKE", "query": "Q2", "assert_mode": "rich_answer"}
        record_eval_run(
            connection,
            suite_id="regression:user_query_retrieval:current-code",
            cases=[user_case],
            summary={"suite": "user_query_retrieval"},
            command="retrieval",
            success=True,
            output="",
            code_version=current_code_version,
            case_results=[
                {
                    "case_id": "CASE-UQ",
                    "passed": True,
                    "metrics": {"retrieval_quality": {"recall_at_5": 0.8, "failure_attribution": "ok"}},
                }
            ],
        )
        record_eval_run(
            connection,
            suite_id="regression:query_repair_smoke",
            cases=[smoke_case],
            summary={"suite": "query_repair_smoke"},
            command="smoke",
            success=True,
            output="",
            code_version=current_code_version,
            case_results=[
                {
                    "case_id": "CASE-SMOKE",
                    "passed": True,
                    "metrics": {"retrieval_quality": {"recall_at_5": 1.0, "failure_attribution": "ok"}},
                }
            ],
        )
        connection.commit()

        retrieval_eval = _latest_eval_with_quality(
            connection,
            "retrieval_quality",
            code_version=current_code_version,
            suite_id_prefix="regression:user_query_retrieval",
        )

        assert retrieval_eval is not None
        assert retrieval_eval["suite_id"] == "regression:user_query_retrieval:current-code"
    finally:
        connection.close()


@pytest.mark.integration
def test_api_health_and_answer_query() -> None:
    doc_id = resolve_doc_id_by_filename("40432", ".pdf")
    server = ApiServer(("127.0.0.1", 0), WORKSPACE)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)

    host, port = server.server_address
    conn = HTTPConnection(host, port, timeout=120)

    try:
        conn.request("GET", "/health")
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["status"] == "ok"
        assert payload["server"]["name"] == "enterprise-agent-kb"
        assert "started_at" in payload["server"]

        conn.request("GET", "/demo")
        response = conn.getresponse()
        assert response.status == 200
        html = response.read().decode("utf-8")
        assert "企业级知识库工作台" in html
        assert "执行查询" in html
        assert "检查接口" in html
        assert "Parse Views" in html
        assert "只看风险页" in html
        assert "structure_quality_score" in html or "struct " in html
        assert "Repair Task Coverage" in html
        assert "renderRepairTaskCoverageTags" in html

        conn.request("GET", "/documents")
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert "documents" in payload
        assert isinstance(payload["documents"], list)

        conn.request("GET", "/closed-loop-dashboard")
        response = conn.getresponse()
        assert response.status == 200
        dashboard = json.loads(response.read().decode("utf-8"))
        assert "ingestion_loop" in dashboard
        assert "retrieval_loop" in dashboard
        assert "answer_loop" in dashboard
        assert "regression_loop" in dashboard
        assert "parse_quality_loop" in dashboard
        assert "hygiene_loop" in dashboard
        for loop_name in ["ingestion_loop", "parse_quality_loop", "retrieval_loop", "answer_loop", "regression_loop", "hygiene_loop"]:
            loop = dashboard[loop_name]
            assert loop["status"] in {"ok", "warn", "fail", "unknown"}
            assert isinstance(loop["risks"], list)
            assert isinstance(loop["next_actions"], list)
            assert isinstance(loop["artifacts"], dict)
        assert "latest_retrieval_run_id" in dashboard["retrieval_loop"]["artifacts"]
        assert "latest_eval_run_id" in dashboard["regression_loop"]["artifacts"]
        assert "repair_task_status_counts" in dashboard["regression_loop"]
        assert "open" in dashboard["regression_loop"]["repair_task_status_counts"]
        assert "reopened" in dashboard["regression_loop"]["repair_task_status_counts"]
        assert "repair_task_coverage" in dashboard["regression_loop"]
        assert "uncovered_priority_report" in dashboard["ingestion_loop"]["artifacts"]
        assert "parse_risk_profile" in dashboard["parse_quality_loop"]
        assert "workspace_doctor" in dashboard["hygiene_loop"]["artifacts"]
        assert "prune_plan" in dashboard["hygiene_loop"]

        body = json.dumps({"doc_id": doc_id})
        conn.request(
            "POST",
            "/parse-view-detail",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["doc_id"] == doc_id
        assert "pages" in payload
        assert "summary" in payload

        body = json.dumps({"limit": 5})
        conn.request(
            "POST",
            "/repair-tasks",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert isinstance(payload["tasks"], list)

        body = json.dumps({"doc_id": doc_id})
        conn.request(
            "POST",
            "/build-document",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["doc_id"] == doc_id
        assert payload["coverage_source_unit_count"] >= 1
        assert payload["coverage_summary_path"].endswith(".summary.json")
        assert payload["coverage_report_path"].endswith(".coverage_report.md")
        assert payload["ingestion_acceptance"]["status"] in {"passed", "warn"}
        assert payload["ingestion_acceptance"]["failed_count"] == 0
        assert payload["ingestion_acceptance"]["json_path"].endswith(".ingestion_acceptance.json")

        body = json.dumps({"doc_id": doc_id})
        conn.request(
            "POST",
            "/validate-document-ingestion",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["doc_id"] == doc_id
        assert payload["failed_count"] == 0
        assert payload["json_path"].endswith(".ingestion_acceptance.json")

        body = json.dumps({"doc_id": doc_id, "limit": 3})
        conn.request(
            "POST",
            "/coverage-test-gaps",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["doc_id"] == doc_id
        assert payload["candidate_count"] <= 3
        assert payload["candidates_path"].endswith(".test_gap_candidates.json")
        assert payload["report_path"].endswith(".test_gap_candidates.md")

        body = json.dumps({"doc_id": doc_id, "limit": 2})
        conn.request(
            "POST",
            "/generate-coverage-test-drafts",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["doc_id"] == doc_id
        assert payload["draft_case_count"] <= 2
        assert payload["json_path"].endswith(".coverage_test_drafts.json")
        assert payload["report_path"].endswith(".coverage_test_drafts.md")

        body = json.dumps({"doc_id": doc_id})
        conn.request(
            "POST",
            "/validate-coverage-test-drafts",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["doc_id"] == doc_id
        assert "passed_count" in payload
        assert "failed_count" in payload

        body = json.dumps({"doc_id": doc_id, "mode": "trace"})
        conn.request(
            "POST",
            "/run-coverage-promoted-tests",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["doc_id"] == doc_id
        assert payload["validation_mode"] == "trace"
        assert "success" in payload

        body = json.dumps({"query": "什么是控制导引电路？", "limit": 4})
        conn.request(
            "POST",
            "/answer-query",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert "direct_answer" in payload
        assert "控制导引电路" in payload["direct_answer"]

        body = json.dumps({"doc_id": doc_id})
        conn.request(
            "POST",
            "/start-build-document",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 202
        payload = json.loads(response.read().decode("utf-8"))
        job_id = payload["job_id"]

        body = json.dumps({"job_id": job_id})
        conn.request(
            "POST",
            "/job-status",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["job_id"] == job_id
        assert payload["status"] in {"queued", "running", "completed"}
        assert "history" in payload
        if payload["status"] == "completed":
            assert "ingestion_acceptance" in payload["result"]

        conn.request("GET", "/jobs")
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert "jobs" in payload

        conn.request("GET", "/audit-log")
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert "events" in payload
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.unit
def test_api_parse_risk_actions_is_dry_run_unless_persist_requested(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "knowledge_base", Path("src/enterprise_agent_kb/schema.sql"))
    calls: list[dict[str, object]] = []

    def fake_generate(root: Path, doc_id: str, *, output_dir: Path | None = None, persist_repair_tasks: bool = False):
        calls.append(
            {
                "root": root,
                "doc_id": doc_id,
                "output_dir": output_dir,
                "persist_repair_tasks": persist_repair_tasks,
            }
        )
        return _FakeParseRiskPlan(doc_id, persist_repair_tasks)

    server = ApiServer(("127.0.0.1", 0), paths.root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)

    host, port = server.server_address
    conn = HTTPConnection(host, port, timeout=30)
    try:
        with patch("enterprise_agent_kb.api_server.generate_parse_risk_action_plan", side_effect=fake_generate):
            conn.request(
                "POST",
                "/parse-risk-actions",
                body=json.dumps({"doc_id": "DOC-API"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            response = conn.getresponse()
            assert response.status == 200
            payload = json.loads(response.read().decode("utf-8"))
            assert payload["persist_repair_tasks"] is False
            assert payload["persisted_repair_tasks"] == []

            conn.request(
                "POST",
                "/parse-risk-actions",
                body=json.dumps({"doc_id": "DOC-API", "persist_repair_tasks": True}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            response = conn.getresponse()
            assert response.status == 200
            payload = json.loads(response.read().decode("utf-8"))
            assert payload["persist_repair_tasks"] is True
            assert payload["persisted_repair_tasks"][0]["task_id"] == "REPAIR-PARSE-TEST"

        assert calls[0]["persist_repair_tasks"] is False
        assert calls[1]["persist_repair_tasks"] is True
        assert calls[1]["doc_id"] == "DOC-API"
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.unit
def test_api_parse_risk_repair_review_returns_status_suggestions(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "knowledge_base", Path("src/enterprise_agent_kb/schema.sql"))
    calls: list[dict[str, object]] = []

    def fake_review(root: Path, doc_id: str, *, output_dir: Path | None = None):
        calls.append({"root": root, "doc_id": doc_id, "output_dir": output_dir})
        return _FakeParseRiskRepairReview(doc_id)

    server = ApiServer(("127.0.0.1", 0), paths.root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)

    host, port = server.server_address
    conn = HTTPConnection(host, port, timeout=30)
    try:
        with patch("enterprise_agent_kb.api_server.review_parse_risk_repair_tasks", side_effect=fake_review):
            conn.request(
                "POST",
                "/parse-risk-repair-review",
                body=json.dumps({"doc_id": "DOC-API"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            response = conn.getresponse()
            assert response.status == 200
            payload = json.loads(response.read().decode("utf-8"))
            assert payload["review_count"] == 1
            assert payload["status_counts"] == {"done": 1}
            assert payload["reviews"][0]["suggested_status"] == "done"

        assert calls[0]["doc_id"] == "DOC-API"
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.unit
def test_latest_uncovered_priority_snapshot_summarizes_root_causes(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "knowledge_base", Path("src/enterprise_agent_kb/schema.sql"))
    paths.coverage_reports.mkdir(parents=True, exist_ok=True)
    report_path = paths.coverage_reports / "all_docs_uncovered_priority_report_2026-05-01.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-05-01T00:00:00+00:00",
                "issue_count": 3,
                "root_cause_counts": {"golden_gap": 2, "extraction_gap": 1},
                "status_counts": {"u3_not_tested": 2, "u1_text_only": 1},
                "documents": [
                    {
                        "doc_id": "DOC-LOW",
                        "source_filename": "low.pdf",
                        "quality_status": "passed",
                        "priority_score": 10,
                        "root_cause_counts": {"golden_gap": 1},
                        "status_counts": {"u3_not_tested": 1},
                    },
                    {
                        "doc_id": "DOC-HIGH",
                        "source_filename": "high.pdf",
                        "quality_status": "review_required",
                        "priority_score": 90,
                        "root_cause_counts": {"extraction_gap": 1},
                        "status_counts": {"u1_text_only": 1},
                    },
                ],
                "top_issues": [
                    {
                        "doc_id": "DOC-HIGH",
                        "unit_id": "UNIT-1",
                        "coverage_status": "u1_text_only",
                        "root_cause": "extraction_gap",
                        "priority_score": 80,
                        "unit_type": "definition_unit",
                        "importance": "high",
                        "page_no": 3,
                        "semantic_key": "过程属性范围",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (paths.coverage_reports / "all_docs_uncovered_priority_report_2026-05-01.md").write_text(
        "# report\n",
        encoding="utf-8",
    )

    snapshot = _latest_uncovered_priority_snapshot(AppPaths.from_root(paths.root))

    assert snapshot["available"] is True
    assert snapshot["issue_count"] == 3
    assert snapshot["root_cause_counts"] == {"golden_gap": 2, "extraction_gap": 1}
    assert snapshot["top_documents"][0]["doc_id"] == "DOC-HIGH"
    assert snapshot["top_issues"][0]["root_cause"] == "extraction_gap"
    assert str(snapshot["report_path"]).endswith(".md")


@pytest.mark.unit
def test_api_lists_eval_runs_and_details(tmp_path: Path) -> None:
    schema_path = Path("src/enterprise_agent_kb/schema.sql")
    paths = initialize_workspace(tmp_path / "knowledge_base", schema_path)
    cases = [
        {
            "query": "什么是控制导引功能？",
            "must_include": "控制导引功能",
            "assert_mode": "rich_answer",
            "source": "manual",
        }
    ]
    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, "DOC-TEST", cases)
        case_id = connection.execute("SELECT case_id FROM golden_cases LIMIT 1").fetchone()["case_id"]
        eval_run_id = record_eval_run(
            connection,
            suite_id="golden:DOC-TEST",
            cases=cases,
            summary={"total": 1, "passed": 0, "failed": 1},
            command="pytest generated",
            success=False,
            output="failed output",
            case_results=[
                {
                    "case_id": case_id,
                    "passed": False,
                    "failure_reason": "retrieval_miss",
                    "retrieved_items": [],
                    "answer": "",
                    "metrics": {"expected_present": False},
                }
            ],
        )
        connection.commit()
    finally:
        connection.close()

    server = ApiServer(("127.0.0.1", 0), paths.root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)

    host, port = server.server_address
    conn = HTTPConnection(host, port, timeout=30)
    try:
        body = json.dumps({"suite_id": "golden:DOC-TEST", "limit": 5})
        conn.request(
            "POST",
            "/eval-runs",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["runs"][0]["eval_run_id"] == eval_run_id
        assert payload["runs"][0]["status"] == "failed"

        body = json.dumps({"eval_run_id": eval_run_id})
        conn.request(
            "POST",
            "/eval-run-detail",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        detail = json.loads(response.read().decode("utf-8"))
        assert detail["eval_run_id"] == eval_run_id
        assert detail["results"][0]["passed"] is False
        assert detail["results"][0]["case"]["query"] == "什么是控制导引功能？"

        body = json.dumps({"eval_run_id": eval_run_id})
        conn.request(
            "POST",
            "/failure-analysis",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        analysis = json.loads(response.read().decode("utf-8"))
        assert analysis["eval_run"]["eval_run_id"] == eval_run_id
        assert analysis["failure_count"] == 1
        failure = analysis["failures"][0]
        assert failure["query"] == "什么是控制导引功能？"
        assert failure["expected"]["must_hit"] == ["控制导引功能"]
        assert failure["failure_type"] == "retrieval_miss"
        assert failure["suggested_actions"]

        body = json.dumps({"eval_run_id": eval_run_id, "case_id": case_id})
        conn.request(
            "POST",
            "/failure-analysis",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        filtered = json.loads(response.read().decode("utf-8"))
        assert filtered["case_filter"] == case_id
        assert filtered["failure_count"] == 1
        assert filtered["failures"][0]["case_id"] == case_id

        body = json.dumps({"eval_run_id": eval_run_id})
        conn.request(
            "POST",
            "/draft-golden-from-failures",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        batch_payload = json.loads(response.read().decode("utf-8"))
        assert batch_payload["drafted_count"] == 1
        assert batch_payload["total_failure_draft_count"] == 1

        body = json.dumps({"eval_run_id": eval_run_id, "case_id": case_id})
        conn.request(
            "POST",
            "/draft-golden-from-failure",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        draft_payload = json.loads(response.read().decode("utf-8"))
        draft_case = draft_payload["draft_case"]
        assert draft_case["status"] == "draft"
        assert draft_case["source"] == "failure_analysis"

        body = json.dumps({"case_id": draft_case["case_id"]})
        conn.request(
            "POST",
            "/activate-golden-draft",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        activated = json.loads(response.read().decode("utf-8"))
        assert activated["activated_case"]["case_id"] == draft_case["case_id"]
        assert activated["activated_case"]["status"] == "active"
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.unit
def test_api_lists_retrieval_runs_and_details(tmp_path: Path) -> None:
    schema_path = Path("src/enterprise_agent_kb/schema.sql")
    paths = initialize_workspace(tmp_path / "knowledge_base", schema_path)
    connection = connect(paths.db_file)
    try:
        run_id = record_retrieval_run(
            connection,
            query="CC电阻有哪些定义",
            query_type="parameter_lookup",
            doc_scope="global",
            retrieved_evidence_ids=["EV-1"],
            reranked_ids=["fact:FACT-1", "evidence:EV-1"],
            scores={"fact:FACT-1": 0.91, "evidence:EV-1": 0.72},
            metadata={
                "retrieval_plan": {"channels": ["graph", "facts"]},
                "graph_hit_count": 2,
            },
        )
        connection.commit()
    finally:
        connection.close()

    server = ApiServer(("127.0.0.1", 0), paths.root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)

    host, port = server.server_address
    conn = HTTPConnection(host, port, timeout=30)
    try:
        body = json.dumps({"query_type": "parameter_lookup", "limit": 5})
        conn.request(
            "POST",
            "/retrieval-runs",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["runs"][0]["run_id"] == run_id
        assert payload["runs"][0]["channels"] == ["graph", "facts"]
        assert payload["runs"][0]["hit_count"] == 2
        assert payload["runs"][0]["evidence_hit_count"] == 1
        assert payload["runs"][0]["direct_evidence_hit_count"] == 1
        assert payload["runs"][0]["linked_evidence_hit_count"] == 0

        body = json.dumps({"run_id": run_id})
        conn.request(
            "POST",
            "/retrieval-run-detail",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        detail = json.loads(response.read().decode("utf-8"))
        assert detail["run_id"] == run_id
        assert detail["retrieved_evidence_ids"] == ["EV-1"]
        assert detail["evidence_hit_count"] == 1
        assert detail["direct_evidence_hit_count"] == 1
        assert detail["linked_evidence_hit_count"] == 0
        assert detail["reranked_ids"] == ["fact:FACT-1", "evidence:EV-1"]
        assert detail["scores"]["fact:FACT-1"] == 0.91
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.unit
def test_api_generates_golden_candidate_review_payload(tmp_path: Path) -> None:
    schema_path = Path("src/enterprise_agent_kb/schema.sql")
    paths = initialize_workspace(tmp_path / "knowledge_base", schema_path)
    connection = connect(paths.db_file)
    try:
        connection.execute(
            """
            INSERT INTO documents(
                doc_id, source_filename, source_type, mime_type, sha256, file_size,
                page_count, language, version_label, source_path, ingest_time,
                update_time, parse_status, quality_status, is_active
            )
            VALUES ('DOC-API', 'doc.pdf', 'pdf', 'application/pdf', 'sha', 100, 1, 'zh', NULL, 'doc.pdf', 'now', 'now', 'parsed', 'ok', 1)
            """
        )
        sync_source_units_from_matrix(
            connection,
            "DOC-API",
            [
                {
                    "unit_id": "SU-API-1",
                    "unit_type": "definition_unit",
                    "page_no": 1,
                    "canonical_title": "连接确认功能 connection confirm",
                    "canonical_key": "连接确认功能 connection confirm",
                    "content_role": "definition",
                    "source_text": "连接确认功能 connection confirm: 通过电子或者机械方式反映连接状态的功能。",
                    "covered_by": {"fact_ids": ["FACT-API"], "evidence_ids": ["EVID-API"]},
                    "coverage_status": "covered",
                }
            ],
        )
        connection.commit()
    finally:
        connection.close()

    server = ApiServer(("127.0.0.1", 0), paths.root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    host, port = server.server_address
    conn = HTTPConnection(host, port, timeout=30)
    try:
        body = json.dumps({"origins": ["source_unit"], "doc_ids": ["DOC-API"], "limit_per_type": 2})
        conn.request(
            "POST",
            "/golden-candidates",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["summary"]["dry_run"] is True
        assert payload["summary"]["auto_activation"] is False
        assert payload["candidate_count"] == 1
        candidate = payload["candidates"][0]
        assert candidate["origin"] == "source_unit"
        assert candidate["confidence_tier"] == "corpus_eval"
        assert candidate["readiness"]["readiness_status"] == "review_required"
        assert candidate["assertion_contract"]["expected_doc_id"] == "DOC-API"
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.unit
def test_api_blocks_unready_golden_draft_activation(tmp_path: Path) -> None:
    schema_path = Path("src/enterprise_agent_kb/schema.sql")
    paths = initialize_workspace(tmp_path / "knowledge_base", schema_path)
    connection = connect(paths.db_file)
    try:
        connection.execute(
            """
            INSERT INTO golden_cases (
                case_id, doc_id, assert_mode, query, must_hit_json,
                negative_expected_json, expected_pages_json, expected_sections_json,
                expected_evidence_shape, status, source, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "CASE-DRAFT-BLOCKED",
                "DOC-TEST",
                "rich_answer",
                "没有明确锚点的问题",
                "[]",
                "[]",
                "[]",
                "[]",
                None,
                "draft",
                "failure_analysis",
                '{"source_eval_run_id":"EVAL-X","source_case_id":"CASE-X","failure_type":"retrieval_miss"}',
                "2026-04-30T00:00:00+00:00",
                "2026-04-30T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    server = ApiServer(("127.0.0.1", 0), paths.root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)

    host, port = server.server_address
    conn = HTTPConnection(host, port, timeout=30)
    try:
        body = json.dumps({"case_id": "CASE-DRAFT-BLOCKED"})
        conn.request(
            "POST",
            "/activate-golden-draft",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 409
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["error"] == "golden_draft_not_ready"
        readiness = payload["draft"]["readiness"]
        assert readiness["status"] == "blocked"
        assert "missing_assertion_signal" in readiness["blockers"]
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.unit
def test_api_updates_repair_task_status(tmp_path: Path) -> None:
    schema_path = Path("src/enterprise_agent_kb/schema.sql")
    paths = initialize_workspace(tmp_path / "knowledge_base", schema_path)
    now = "2026-05-01T00:00:00+00:00"
    connection = connect(paths.db_file)
    try:
        connection.execute(
            """
            INSERT INTO repair_tasks (
                task_id, reason, module, action, priority, status,
                case_ids_json, query_types_json, impact_count,
                source_eval_run_id, metadata_json, first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "REPAIR-API-1",
                "contract_wrong_shape",
                "retrieval_router.py",
                "检查 retrieval_router.py 的 channel 选择和 query_type 路由",
                70,
                "proposed",
                '["CASE-1"]',
                '["lifecycle_lookup"]',
                1,
                "EVAL-1",
                "{}",
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    server = ApiServer(("127.0.0.1", 0), paths.root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)

    host, port = server.server_address
    conn = HTTPConnection(host, port, timeout=30)
    try:
        body = json.dumps({"task_id": "REPAIR-API-1", "status": "in_progress", "note": "started"})
        conn.request(
            "POST",
            "/update-repair-task",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["task"]["status"] == "in_progress"
        assert payload["task"]["metadata"]["last_status_note"] == "started"

        body = json.dumps({"task_id": "REPAIR-API-1", "status": "invalid"})
        conn.request(
            "POST",
            "/update-repair-task",
            body=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 400
        payload = json.loads(response.read().decode("utf-8"))
        assert payload["error"].startswith("invalid_repair_task_status")
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.unit
def test_regression_health_flags_missing_pytest_counts() -> None:
    loop = {
        "eval_run_count": 1,
        "latest_run": {
            "status": "passed",
            "result_summary": {"total": 1, "passed": 1, "failed": 0},
        },
        "draft_golden_case_count": 0,
        "repair_task_count": 0,
        "repair_task_status_counts": {},
        "repair_task_coverage": {},
        "artifacts": {},
    }

    _attach_regression_health(loop)

    assert loop["status"] == "warn"
    assert any(risk["code"] == "missing_pytest_counts" for risk in loop["risks"])
    assert any(risk["code"] == "missing_eval_scope" for risk in loop["risks"])


@pytest.mark.unit
def test_workspace_coverage_snapshot_keeps_source_unit_and_evidence_metrics_separate(tmp_path: Path) -> None:
    schema_path = Path("src/enterprise_agent_kb/schema.sql")
    paths = initialize_workspace(tmp_path / "knowledge_base", schema_path)
    now = "2026-05-10T00:00:00+00:00"
    connection = connect(paths.db_file)
    try:
        connection.execute(
            """
            INSERT INTO source_units (
                unit_id, doc_id, page_no, block_id, unit_type, text,
                normalized_text, importance, expected_knowledge_type,
                status, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("SU-1", "DOC-TEST", 1, "BLK-1", "definition", "a", "a", "high", "term", "covered", "{}", now, now),
        )
        connection.execute(
            """
            INSERT INTO source_units (
                unit_id, doc_id, page_no, block_id, unit_type, text,
                normalized_text, importance, expected_knowledge_type,
                status, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("SU-2", "DOC-TEST", 2, "BLK-2", "definition", "b", "b", "high", "term", "u3_not_tested", "{}", now, now),
        )
        connection.execute(
            """
            INSERT INTO source_unit_fact_map (
                unit_id, fact_id, doc_id, support_type, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("SU-1", "FACT-1", "DOC-TEST", "unit_test", now),
        )
        connection.execute(
            """
            INSERT INTO source_unit_evidence_map (
                unit_id, evidence_id, doc_id, support_type, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("SU-1", "EV-1", "DOC-TEST", "unit_test", now),
        )
        connection.commit()

        snapshot = _workspace_coverage_snapshot(connection)
    finally:
        connection.close()

    assert snapshot["source_unit_count"] == 2
    assert snapshot["source_unit_coverage_rate"] == 0.5
    assert snapshot["legacy_evidence_coverage_rate"] == 0.5
    assert snapshot["evidence_coverage_rate"] == 0.5
    assert snapshot["fact_coverage_rate"] == 0.5
    assert snapshot["metric_contract"]["legacy_evidence_coverage_rate"] == "deprecated_alias_for_source_unit_coverage_rate"
    assert snapshot["metric_contract"]["evidence_coverage_rate"] == "source_unit_evidence_map distinct unit_id / source_units"
    assert snapshot["metric_contract"]["fact_coverage_rate"] == "source_unit_fact_map distinct unit_id / source_units"


@pytest.mark.unit
def test_workspace_parse_risk_snapshot_separates_raw_quality_from_actionable_parse_gaps(tmp_path: Path) -> None:
    schema_path = Path("src/enterprise_agent_kb/schema.sql")
    paths = initialize_workspace(tmp_path / "parse_risk_runtime", schema_path)
    now = "2026-05-10T00:00:00+00:00"
    connection = connect(paths.db_file)
    try:
        for page_no in [1, 2, 3]:
            connection.execute(
                """
                INSERT INTO pages (
                    page_id, doc_id, page_no, width, height, parser_confidence,
                    ocr_confidence, risk_level, page_status, screenshot_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"PAGE-{page_no}",
                    "DOC-TEST",
                    page_no,
                    None,
                    None,
                    None,
                    None,
                    "high",
                    "review_required",
                    None,
                    now,
                    now,
                ),
            )
        for evidence_id, page_no in [("EV-2", 2), ("EV-3", 3)]:
            connection.execute(
                """
                INSERT INTO evidence (
                    evidence_id, doc_id, page_id, block_id, block_type, raw_text, normalized_text,
                    image_ref, table_ref, page_no, confidence, risk_level, evidence_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    "DOC-TEST",
                    f"PAGE-{page_no}",
                    f"BLK-{page_no}",
                    "text",
                    "raw",
                    "normalized",
                    None,
                    None,
                    page_no,
                    0.8,
                    "high",
                    "ready",
                    now,
                    now,
                ),
            )
        connection.execute(
            """
            INSERT INTO source_units (
                unit_id, doc_id, page_no, block_id, unit_type, text, normalized_text,
                importance, expected_knowledge_type, status, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("SU-3", "DOC-TEST", 3, "BLK-3", "requirement", "text", "normalized", "high", "requirement", "covered", "{}", now, now),
        )
        connection.execute(
            """
            INSERT INTO facts (
                fact_id, fact_type, predicate, object_value, confidence, fact_status,
                source_doc_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("FACT-3", "requirement", "states", "normalized", 0.9, "active", "DOC-TEST", now, now),
        )
        connection.execute(
            "INSERT INTO fact_evidence_map (fact_id, evidence_id, support_type) VALUES (?, ?, ?)",
            ("FACT-3", "EV-3", "unit_test"),
        )
        report = {
            "pages": [
                {"page_no": 1, "risk_flags": ["no_text"]},
                {"page_no": 2, "risk_flags": ["symbol_noise"]},
                {"page_no": 3, "risk_flags": ["low_readability"]},
            ]
        }
        connection.execute(
            """
            INSERT INTO quality_reports (
                doc_id, overall_score, ocr_avg_confidence, structure_score, table_score,
                fact_alignment_score, conflict_count, high_risk_page_count, review_required_count,
                blocked_count, report_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("DOC-TEST", 0.5, 0.8, 0.5, None, None, 0, 3, 3, 0, json.dumps(report), now, now),
        )
        connection.commit()

        snapshot = _workspace_parse_risk_snapshot(connection)
    finally:
        connection.close()

    assert snapshot["high_risk_page_count"] == 3
    assert snapshot["actionable_parse_risk_pages"] == 1
    assert snapshot["evidence_backed_high_risk_pages"] == 2
    assert snapshot["source_unit_backed_high_risk_pages"] == 1
    assert snapshot["fact_backed_high_risk_pages"] == 1
    assert snapshot["fully_backed_high_risk_pages"] == 1
    assert snapshot["root_cause_counts"] == {
        "no_evidence": 1,
        "evidence_without_source_unit": 1,
        "source_unit_without_fact": 0,
        "fully_backed": 1,
    }
    assert snapshot["samples"]["no_evidence"][0]["risk_flags"] == ["no_text"]


@pytest.mark.unit
def test_ingestion_health_flags_unavailable_evidence_and_fact_coverage() -> None:
    loop = {
        "document_count": 1,
        "source_unit_count": 2,
        "evidence_count": 3,
        "fact_count": 4,
        "parse_risk_pages": 0,
        "source_unit_coverage": {
            "source_unit_count": 2,
            "source_unit_coverage_rate": 0.5,
            "evidence_coverage_rate": None,
            "fact_coverage_rate": None,
            "uncovered_units": 1,
        },
        "uncovered_priority": {"root_cause_counts": {}},
    }

    _attach_ingestion_health(loop)

    risk_codes = {risk["code"] for risk in loop["risks"]}
    assert "evidence_coverage_unlinked" in risk_codes
    assert "fact_coverage_unlinked" in risk_codes


@pytest.mark.unit
def test_ingestion_health_uses_actionable_ingestion_risks() -> None:
    loop = {
        "document_count": 1,
        "source_unit_count": 2,
        "evidence_count": 2,
        "fact_count": 2,
        "parse_risk_pages": 5,
        "actionable_parse_risk_pages": 0,
        "parse_risk_profile": {
            "high_risk_page_count": 5,
            "actionable_parse_risk_pages": 0,
            "root_cause_counts": {"fully_backed": 5},
        },
        "source_unit_coverage": {
            "source_unit_count": 2,
            "source_unit_coverage_rate": 0.5,
            "evidence_coverage_rate": 1.0,
            "fact_coverage_rate": 1.0,
            "uncovered_units": 1,
        },
        "uncovered_priority": {"root_cause_counts": {"test_gap_rejected": 1}},
    }

    _attach_ingestion_health(loop)

    assert loop["status"] == "ok"
    assert loop["actionable_uncovered_units"] == 0
    assert {risk["code"] for risk in loop["risks"]} == set()


@pytest.mark.unit
def test_graph_contribution_snapshot_tracks_retained_and_lost_candidates(tmp_path: Path) -> None:
    schema_path = Path("src/enterprise_agent_kb/schema.sql")
    paths = initialize_workspace(tmp_path / "knowledge_base", schema_path)
    connection = connect(paths.db_file)
    try:
        retained_id = record_retrieval_run(
            connection,
            query="CP是什么意思",
            query_type="definition",
            doc_scope="global",
            retrieved_evidence_ids=[],
            reranked_ids=["fact:FACT-1", "wiki:WPAGE-1"],
            scores={"fact:FACT-1": 1.0},
            metadata={
                "retrieval_plan": {"channels": ["graph", "facts"], "graph_candidate_count": 2},
                "graph_hit_count": 2,
                "rerank_explanations": [
                    {"id": "fact:FACT-1", "graph_source": True},
                    {"id": "wiki:WPAGE-1", "graph_source": False},
                ],
            },
        )
        lost_id = record_retrieval_run(
            connection,
            query="软件架构分析有哪些活动",
            query_type="lifecycle_lookup",
            doc_scope="global",
            retrieved_evidence_ids=[],
            reranked_ids=["fact:FACT-2"],
            scores={"fact:FACT-2": 0.9},
            metadata={
                "retrieval_plan": {"channels": ["graph", "facts"], "graph_candidate_count": 3},
                "graph_hit_count": 3,
                "rerank_explanations": [{"id": "fact:FACT-2", "graph_source": False}],
            },
        )
        record_retrieval_run(
            connection,
            query="OBC输入过压怎么测",
            query_type="test_method_lookup",
            doc_scope="global",
            retrieved_evidence_ids=["EV-1"],
            reranked_ids=["evidence:EV-1"],
            scores={"evidence:EV-1": 1.0},
            metadata={
                "retrieval_plan": {"channels": ["facts", "evidence"]},
                "rerank_explanations": [{"id": "evidence:EV-1", "graph_source": False}],
            },
        )
        connection.commit()

        snapshot = _graph_contribution_snapshot(connection)
    finally:
        connection.close()

    assert retained_id is not None
    assert lost_id is not None
    assert snapshot["sample_size"] == 3
    assert snapshot["graph_requested_runs"] == 2
    assert snapshot["graph_candidate_runs"] == 2
    assert snapshot["graph_top_runs"] == 1
    assert snapshot["graph_lost_after_rerank_runs"] == 1
    assert snapshot["graph_top_hit_count"] == 1
    assert snapshot["graph_candidate_count_total"] == 5
    assert snapshot["graph_request_rate"] == 0.666667
    assert snapshot["graph_candidate_rate"] == 1.0
    assert snapshot["graph_retention_rate"] == 0.5
    assert snapshot["current_code_version_runs"] == 3
    assert snapshot["stale_or_unknown_runs"] == 0
    assert snapshot["current_code_version"] in snapshot["code_version_counts"]
    assert snapshot["current_version_graph"]["sample_size"] == 3
    assert snapshot["current_version_graph"]["graph_candidate_runs"] == 2
    assert snapshot["current_version_graph"]["graph_top_runs"] == 1
    assert snapshot["current_version_graph"]["graph_lost_after_rerank_runs"] == 1
    assert snapshot["current_version_graph"]["graph_retention_rate"] == 0.5
    assert snapshot["by_query_type"]["definition"]["graph_top_runs"] == 1
    assert snapshot["by_query_type"]["lifecycle_lookup"]["graph_lost_after_rerank_runs"] == 1
    assert snapshot["lost_after_rerank_samples"][0]["run_id"] == lost_id
    assert snapshot["lost_after_rerank_samples"][0]["reranked_ids"] == ["fact:FACT-2"]


@pytest.mark.unit
def test_retrieval_health_flags_graph_lost_after_rerank() -> None:
    loop = {
        "retrieval_run_count": 4,
        "recall_at_5": 1.0,
        "recall_at_10": 1.0,
        "mrr": 1.0,
        "negative_hit_rate": 0.0,
        "graph_contribution": {
            "graph_candidate_runs": 4,
            "graph_top_runs": 1,
            "graph_lost_after_rerank_runs": 3,
            "graph_retention_rate": 0.25,
        },
    }

    _attach_retrieval_health(loop)

    risk_codes = {risk["code"] for risk in loop["risks"]}
    assert "graph_lost_after_rerank_dominates" in risk_codes


@pytest.mark.unit
def test_retrieval_health_flags_mixed_retrieval_run_code_versions() -> None:
    loop = {
        "retrieval_run_count": 10,
        "recall_at_5": 1.0,
        "recall_at_10": 1.0,
        "mrr": 1.0,
        "negative_hit_rate": 0.0,
        "graph_contribution": {
            "graph_candidate_runs": 3,
            "graph_top_runs": 2,
            "graph_lost_after_rerank_runs": 1,
            "graph_retention_rate": 0.666667,
            "current_code_version_runs": 0,
            "stale_or_unknown_runs": 8,
        },
    }

    _attach_retrieval_health(loop)

    risk_codes = {risk["code"] for risk in loop["risks"]}
    assert "retrieval_runs_mixed_code_versions" in risk_codes


@pytest.mark.unit
def test_retrieval_health_uses_current_version_graph_when_available() -> None:
    loop = {
        "retrieval_run_count": 10,
        "recall_at_5": 1.0,
        "recall_at_10": 1.0,
        "mrr": 1.0,
        "negative_hit_rate": 0.0,
        "graph_contribution": {
            "graph_candidate_runs": 10,
            "graph_top_runs": 1,
            "graph_lost_after_rerank_runs": 9,
            "graph_retention_rate": 0.1,
            "current_code_version_runs": 6,
            "stale_or_unknown_runs": 400,
            "current_version_graph": {
                "graph_candidate_runs": 6,
                "graph_top_runs": 6,
                "graph_lost_after_rerank_runs": 0,
                "graph_retention_rate": 1.0,
            },
        },
    }

    _attach_retrieval_health(loop)

    risk_codes = {risk["code"] for risk in loop["risks"]}
    assert "retrieval_runs_mixed_code_versions" not in risk_codes
    assert "graph_lost_after_rerank_dominates" not in risk_codes


@pytest.mark.unit
def test_regression_health_uses_current_eval_repair_tasks_not_historical_backlog() -> None:
    current_counts = _repair_task_status_counts_from_tasks([])
    loop = {
        "eval_run_count": 4,
        "latest_run": {
            "status": "passed",
            "result_summary": {
                "total": 8,
                "passed": 8,
                "failed": 0,
                "pytest_counts": {"deselected": 0},
                "eval_scope": {
                    "declared_case_count": 8,
                    "evaluated_case_count": 8,
                    "unevaluated_case_count": 0,
                },
            },
        },
        "draft_golden_case_count": 0,
        "repair_task_count": int(current_counts["open"]),
        "repair_task_status_counts": current_counts,
        "historical_repair_task_status_counts": {"open": 21, "reopened": 2, "proposed": 19},
        "repair_task_coverage": {
            "failure_case_count": 0,
            "covered_failure_case_count": 0,
            "uncovered_failure_case_count": 0,
            "coverage_rate": None,
            "uncovered_case_ids": [],
        },
        "artifacts": {"comparison": {}},
    }

    _attach_regression_health(loop)

    risk_codes = {risk["code"] for risk in loop["risks"]}
    assert "reopened_repair_tasks" not in risk_codes
    assert "open_repair_tasks" not in risk_codes
    assert loop["status"] == "ok"


@pytest.mark.unit
def test_hygiene_loop_snapshot_reuses_doctor_and_dry_run_prune(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", Path("src/enterprise_agent_kb/schema.sql"))
    connection = connect(paths.db_file)
    try:
        retrieval_run_id = record_retrieval_run(
            connection,
            query="old query",
            query_type="definition",
            doc_scope="global",
            retrieved_evidence_ids=[],
            reranked_ids=[],
            scores={},
            metadata={},
        )
        assert retrieval_run_id is not None
        connection.execute("UPDATE retrieval_runs SET code_version = 'old-code' WHERE run_id = ?", (retrieval_run_id,))
        record_eval_run(
            connection,
            suite_id="regression:old",
            cases=[{"case_id": "CASE-OLD", "query": "q", "assert_mode": "context_contains"}],
            summary={"suite": "old"},
            command="eval",
            success=True,
            output="",
            code_version="old-code",
        )
        connection.commit()
    finally:
        connection.close()

    loop = _hygiene_loop_snapshot(paths.root)

    assert loop["prune_plan"]["dry_run"] is True
    assert loop["stale_run_summary"]["retrieval_runs"] == 1
    assert loop["stale_run_summary"]["eval_runs"] == 1
    assert loop["stale_run_summary"]["eval_results"] == 1
    assert loop["stale_run_summary"]["deleted_retrieval_runs"] == 0
    assert loop["stale_run_summary"]["deleted_eval_runs"] == 0
    assert "prune-stale-runs --keep-current-code-version --dry-run" in loop["next_actions"]

    connection = connect(paths.db_file)
    try:
        assert connection.execute("SELECT count(*) FROM retrieval_runs").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM eval_runs").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM eval_results").fetchone()[0] == 1
    finally:
        connection.close()


@pytest.mark.unit
def test_hygiene_health_flags_doctor_issue_actions() -> None:
    loop = {
        "doctor_status": "warn",
        "issue_count": 1,
        "issue_summary": {"ok": 0, "warn": 1, "fail": 0},
        "issues": [
            {
                "issue_id": "retrieval_runs_stale_code_version",
                "scope": "runs",
                "severity": "warn",
                "message": "retrieval_runs contains runs from older code versions",
                "recommended_actions": ["prune-stale-runs --keep-current-code-version --dry-run"],
            }
        ],
        "stale_run_summary": {"retrieval_runs": 2, "eval_runs": 0, "eval_results": 0},
        "derived_state_checks": [],
        "artifacts": {},
    }

    _attach_hygiene_health(loop)

    assert loop["status"] == "warn"
    assert any(risk["code"] == "retrieval_runs_stale_code_version" for risk in loop["risks"])
    assert "prune-stale-runs --keep-current-code-version --dry-run" in loop["next_actions"]


@pytest.mark.unit
def test_regression_health_flags_unevaluated_cases() -> None:
    loop = {
        "eval_run_count": 1,
        "latest_run": {
            "status": "passed",
            "result_summary": {
                "total": 2,
                "passed": 1,
                "failed": 0,
                "pytest_counts": {"deselected": 0},
                "eval_scope": {
                    "declared_case_count": 2,
                    "evaluated_case_count": 1,
                    "unevaluated_case_count": 1,
                },
            },
        },
        "draft_golden_case_count": 0,
        "repair_task_count": 0,
        "repair_task_status_counts": {},
        "repair_task_coverage": {},
        "artifacts": {},
    }

    _attach_regression_health(loop)

    assert loop["status"] == "fail"
    assert any(risk["code"] == "eval_cases_not_evaluated" for risk in loop["risks"])
