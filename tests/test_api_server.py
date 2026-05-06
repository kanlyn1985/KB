from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

from enterprise_agent_kb.api_server import ApiServer
from enterprise_agent_kb.api_server import _attach_regression_health
from enterprise_agent_kb.api_server import _latest_eval_with_quality
from enterprise_agent_kb.api_server import _latest_uncovered_priority_snapshot
from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.closed_loop_store import record_eval_run, record_retrieval_run, sync_golden_cases
from enterprise_agent_kb.config import AppPaths
from enterprise_agent_kb.db import connect
from test_helpers import resolve_doc_id_by_filename


WORKSPACE = Path("knowledge_base")


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
        for loop_name in ["ingestion_loop", "retrieval_loop", "answer_loop", "regression_loop"]:
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
        assert detail["reranked_ids"] == ["fact:FACT-1", "evidence:EV-1"]
        assert detail["scores"]["fact:FACT-1"] == 0.91
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
