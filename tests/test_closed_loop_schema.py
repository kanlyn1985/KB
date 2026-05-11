from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.closed_loop_store import (
    activate_golden_case_draft,
    backfill_eval_run_scope_metadata,
    backfill_source_unit_mappings_from_metadata,
    build_failure_analysis,
    compare_eval_runs,
    draft_golden_case_from_failure,
    draft_golden_cases_from_eval_failures,
    get_retrieval_run_detail,
    list_repair_tasks,
    list_retrieval_runs,
    record_eval_run,
    record_retrieval_run,
    sync_golden_cases,
    sync_source_units_from_matrix,
    update_repair_task_status,
)
from enterprise_agent_kb.db import connect, list_tables
from enterprise_agent_kb.workspace_admin import reset_workspace_data


SCHEMA_PATH = Path("src/enterprise_agent_kb/schema.sql")


def test_closed_loop_tables_are_initialized(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        tables = set(list_tables(connection))
        assert {
            "source_units",
            "source_unit_fact_map",
            "source_unit_evidence_map",
            "retrieval_runs",
            "golden_cases",
            "eval_runs",
            "eval_results",
            "repair_tasks",
            "audit_log",
        } <= tables

        assert _columns(connection, "source_units") >= {
            "unit_id",
            "doc_id",
            "page_no",
            "block_id",
            "unit_type",
            "text",
            "normalized_text",
            "canonical_title",
            "canonical_key",
            "content_role",
            "quality_flags_json",
            "importance",
            "expected_knowledge_type",
            "status",
        }
        assert _columns(connection, "source_unit_fact_map") >= {
            "unit_id",
            "fact_id",
            "doc_id",
            "support_type",
            "created_at",
        }
        assert _columns(connection, "source_unit_evidence_map") >= {
            "unit_id",
            "evidence_id",
            "doc_id",
            "support_type",
            "created_at",
        }
        assert _columns(connection, "retrieval_runs") >= {
            "run_id",
            "query",
            "query_type",
            "doc_scope",
            "retrieved_evidence_ids_json",
            "reranked_ids_json",
            "scores_json",
            "created_at",
        }
        assert _columns(connection, "golden_cases") >= {
            "case_id",
            "doc_id",
            "assert_mode",
            "query",
            "must_hit_json",
            "negative_expected_json",
            "expected_pages_json",
            "expected_sections_json",
            "expected_evidence_shape",
            "status",
            "source",
        }
        assert _columns(connection, "eval_runs") >= {
            "eval_run_id",
            "suite_id",
            "started_at",
            "config_hash",
            "code_version",
            "result_summary_json",
            "status",
        }
        assert _columns(connection, "eval_results") >= {
            "eval_run_id",
            "case_id",
            "passed",
            "failure_reason",
            "retrieved_items_json",
            "answer_text",
            "metrics_json",
        }
        assert _columns(connection, "repair_tasks") >= {
            "task_id",
            "reason",
            "module",
            "action",
            "priority",
            "status",
            "case_ids_json",
            "query_types_json",
            "impact_count",
            "source_eval_run_id",
            "metadata_json",
            "first_seen_at",
            "last_seen_at",
        }
    finally:
        connection.close()


def test_sync_source_units_persists_canonical_metadata(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        count = sync_source_units_from_matrix(
            connection,
            "DOC-TEST",
            [
                {
                    "unit_id": "UNIT-PROC-1",
                    "unit_type": "process_unit",
                    "page_no": 53,
                    "semantic_key": "SWE.2",
                    "canonical_title": "SWE.2 基本实践",
                    "canonical_key": "SWE.2",
                    "content_role": "process_activity",
                    "quality_flags": ["layout_title_noise", "process_code_extracted"],
                    "importance": "high",
                    "source_text": "SWE.2.BP1: 开发软件架构设计。",
                    "source_locator": {"block_id": "BLK-PROC-1"},
                    "metadata": {"knowledge_unit_type": "procedure", "process_code": "SWE.2"},
                    "covered_by": {
                        "fact_ids": ["FACT-PROC-1"],
                        "evidence_ids": ["EV-PROC-1"],
                    },
                    "coverage_status": "u3_not_tested",
                }
            ],
            generated_at="2026-04-29T00:00:00+00:00",
        )
        connection.commit()

        row = connection.execute(
            """
            SELECT canonical_title, canonical_key, content_role, quality_flags_json
            FROM source_units
            WHERE unit_id = ?
            """,
            ("UNIT-PROC-1",),
        ).fetchone()

        assert count == 1
        assert row is not None
        assert row["canonical_title"] == "SWE.2 基本实践"
        assert row["canonical_key"] == "SWE.2"
        assert row["content_role"] == "process_activity"
        assert "layout_title_noise" in row["quality_flags_json"]
        fact_link = connection.execute(
            """
            SELECT support_type
            FROM source_unit_fact_map
            WHERE unit_id = ? AND fact_id = ?
            """,
            ("UNIT-PROC-1", "FACT-PROC-1"),
        ).fetchone()
        evidence_link = connection.execute(
            """
            SELECT support_type
            FROM source_unit_evidence_map
            WHERE unit_id = ? AND evidence_id = ?
            """,
            ("UNIT-PROC-1", "EV-PROC-1"),
        ).fetchone()
        assert fact_link is not None
        assert fact_link["support_type"] == "coverage_matrix"
        assert evidence_link is not None
        assert evidence_link["support_type"] == "coverage_matrix"
    finally:
        connection.close()


def test_backfill_source_unit_mappings_from_metadata(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    now = "2026-04-29T00:00:00+00:00"
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
            (
                "UNIT-BACKFILL-1",
                "DOC-TEST",
                1,
                "BLK-1",
                "requirement_unit",
                "source",
                "source",
                "high",
                "requirement",
                "covered",
                '{"covered_by":{"fact_ids":["FACT-BACKFILL-1"],"evidence_ids":["EV-BACKFILL-1"]}}',
                now,
                now,
            ),
        )
        result = backfill_source_unit_mappings_from_metadata(connection, generated_at=now)
        connection.commit()

        assert result["source_unit_count"] == 1
        assert result["fact_link_count"] == 1
        assert result["evidence_link_count"] == 1
        assert connection.execute("SELECT COUNT(*) FROM source_unit_fact_map").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM source_unit_evidence_map").fetchone()[0] == 1
    finally:
        connection.close()


def test_reset_workspace_data_clears_closed_loop_tables(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    now = "2026-04-28T00:00:00+00:00"
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
            (
                "UNIT-TEST",
                "DOC-TEST",
                1,
                "BLOCK-TEST",
                "definition_unit",
                "raw text",
                "raw text",
                0.9,
                "term_definition",
                "ready",
                "{}",
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO retrieval_runs (
                run_id, query, query_type, doc_scope,
                retrieved_evidence_ids_json, reranked_ids_json, scores_json,
                metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("RUN-TEST", "CP是什么意思", "definition", "all", "[]", "[]", "{}", "{}", now),
        )
        connection.execute(
            """
            INSERT INTO source_unit_fact_map (
                unit_id, fact_id, doc_id, support_type, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("UNIT-TEST", "FACT-TEST", "DOC-TEST", "unit_test", now),
        )
        connection.execute(
            """
            INSERT INTO source_unit_evidence_map (
                unit_id, evidence_id, doc_id, support_type, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("UNIT-TEST", "EV-TEST", "DOC-TEST", "unit_test", now),
        )
        connection.execute(
            """
            INSERT INTO golden_cases (
                case_id, doc_id, assert_mode, query, must_hit_json,
                negative_expected_json, expected_pages_json, expected_sections_json,
                status, source, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "CASE-TEST",
                "DOC-TEST",
                "rich_answer",
                "CP是什么意思",
                "[]",
                "[]",
                "[]",
                "[]",
                "active",
                "manual",
                "{}",
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO eval_runs (
                eval_run_id, suite_id, started_at, finished_at, config_hash,
                code_version, result_summary_json, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("EVAL-TEST", "suite", now, None, "cfg", "code", "{}", "running"),
        )
        connection.execute(
            """
            INSERT INTO eval_results (
                eval_run_id, case_id, passed, failure_reason,
                retrieved_items_json, answer_text, metrics_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("EVAL-TEST", "CASE-TEST", 0, "retrieval_miss", "[]", "answer", "{}", now),
        )
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
                "REPAIR-TEST",
                "contract_wrong_shape",
                "retrieval_router.py",
                "fix router",
                70,
                "proposed",
                '["CASE-TEST"]',
                '["definition"]',
                1,
                "EVAL-TEST",
                "{}",
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO audit_log (event_id, event_type, timestamp, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            ("AUDIT-TEST", "test", now, "{}"),
        )
        connection.commit()
    finally:
        connection.close()

    result = reset_workspace_data(paths.root, keep_raw=True)

    assert result.deleted_rows["source_units"] == 1
    assert result.deleted_rows["source_unit_fact_map"] == 1
    assert result.deleted_rows["source_unit_evidence_map"] == 1
    assert result.deleted_rows["retrieval_runs"] == 1
    assert result.deleted_rows["golden_cases"] == 1
    assert result.deleted_rows["eval_runs"] == 1
    assert result.deleted_rows["eval_results"] == 1
    assert result.deleted_rows["repair_tasks"] == 1
    assert result.deleted_rows["audit_log"] == 1


def test_closed_loop_store_records_golden_and_eval_results(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    cases = [
        {
            "query": "什么是控制导引功能？",
            "must_include": "控制导引功能",
            "assert_mode": "rich_answer",
            "expected_evidence_shape": "term_definition",
            "source": "manual",
        },
        {
            "query": "第 1 页包含什么？",
            "must_include": "控制导引",
            "assert_mode": "context_contains",
            "source": "coverage",
            "page_no": 1,
        },
    ]
    connection = connect(paths.db_file)
    try:
        synced = sync_golden_cases(connection, "DOC-TEST", cases, source="unit_test")
        retrieval_run_id = record_retrieval_run(
            connection,
            query="CP的时序是什么样的",
            query_type="timing_lookup",
            doc_scope="DOC-TEST",
            retrieved_evidence_ids=["EV-1"],
            reranked_ids=["fact:FACT-1", "evidence:EV-1"],
            scores={"fact:FACT-1": 0.98, "evidence:EV-1": 0.88},
            metadata={"channels": ["graph", "bm25"]},
        )
        eval_run_id = record_eval_run(
            connection,
            suite_id="golden:DOC-TEST",
            cases=cases,
            summary={"total": 2, "passed": 2, "failed": 0},
            command="pytest generated",
            success=True,
            output="2 passed",
            code_version="test",
            case_results=[
                {
                    "case_id": connection.execute(
                        "SELECT case_id FROM golden_cases WHERE query = ?",
                        ("什么是控制导引功能？",),
                    ).fetchone()["case_id"],
                    "passed": True,
                    "failure_reason": None,
                    "retrieved_items": [{"result_type": "fact", "result_id": "FACT-1"}],
                    "answer": "控制导引功能",
                    "metrics": {"expected_present": True},
                }
            ],
        )
        connection.commit()

        assert synced == 2
        assert retrieval_run_id
        assert eval_run_id
        assert connection.execute("SELECT COUNT(*) FROM retrieval_runs").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM golden_cases").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM eval_runs").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM eval_results WHERE passed = 1").fetchone()[0] == 2
        metrics = connection.execute(
            """
            SELECT metrics_json FROM eval_results
            WHERE answer_text = '控制导引功能'
            """
        ).fetchone()
        shape = connection.execute(
            """
            SELECT expected_evidence_shape FROM golden_cases
            WHERE query = ?
            """,
            ("什么是控制导引功能？",),
        ).fetchone()
        assert metrics is not None
        assert shape is not None
        assert shape["expected_evidence_shape"] == "term_definition"
    finally:
        connection.close()


def test_retrieval_run_detail_derives_quality_diagnostics(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        run_id = record_retrieval_run(
            connection,
            query="系统集成测试过程域有哪些活动",
            query_type="lifecycle_lookup",
            doc_scope="global",
            retrieved_evidence_ids=[],
            reranked_ids=["fact:FACT-1", "fact:FACT-2", "wiki:WPAGE-1"],
            scores={"fact:FACT-1": 1.2, "fact:FACT-2": 1.1, "wiki:WPAGE-1": 0.8},
            metadata={
                "hit_count": 3,
                "candidate_count_before_limit": 12,
                "direct_routing_hit_count": 0,
                "graph_hit_count": 0,
                "retrieval_plan": {
                    "channels": ["graph", "facts", "evidence", "wiki"],
                    "graph_candidate_count": 0,
                    "routing_summary_hit_count": 0,
                },
                "topic_resolution": {
                    "confidence": 0,
                    "candidate_entity_ids": [],
                    "candidate_entities": [],
                },
            },
        )
        connection.commit()

        assert run_id is not None
        detail = get_retrieval_run_detail(connection, run_id)
        runs = list_retrieval_runs(connection, limit=1)

        assert detail is not None
        diagnostics = detail["diagnostics"]
        assert detail["evidence_hit_count"] == 0
        assert detail["direct_evidence_hit_count"] == 0
        assert detail["linked_evidence_hit_count"] == 0
        assert diagnostics["channel_hit_counts"]["facts"] == 2
        assert diagnostics["channel_hit_counts"]["wiki"] == 1
        assert diagnostics["graph_status"] == "no_topic_entities"
        assert diagnostics["evidence_status"] == "facts_without_evidence_links"
        assert "graph_channel_empty" in diagnostics["risk_flags"]
        assert "evidence_channel_empty" in diagnostics["risk_flags"]
        assert "facts_without_evidence_links" in diagnostics["risk_flags"]
        assert "topic_resolution_empty" in diagnostics["risk_flags"]
        assert runs[0]["diagnostics"]["risk_flags"] == diagnostics["risk_flags"]
    finally:
        connection.close()


def test_retrieval_diagnostics_distinguish_linked_evidence_from_empty_evidence(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        run_id = record_retrieval_run(
            connection,
            query="软件架构设计有哪些活动",
            query_type="lifecycle_lookup",
            doc_scope="global",
            retrieved_evidence_ids=[],
            reranked_ids=["fact:FACT-1", "fact:FACT-2"],
            scores={"fact:FACT-1": 1.2, "fact:FACT-2": 1.1},
            metadata={
                "hit_count": 2,
                "retrieval_plan": {"channels": ["graph", "facts", "evidence"], "graph_candidate_count": 4},
                "graph_hit_count": 4,
                "linked_evidence_ids": ["EV-1", "EV-2"],
                "linked_evidence_count": 2,
                "topic_resolution": {"confidence": 0.8, "candidate_entity_ids": ["ENT-1"]},
            },
        )
        connection.commit()

        assert run_id is not None
        detail = get_retrieval_run_detail(connection, run_id)
        runs = list_retrieval_runs(connection, limit=1)
        assert detail is not None
        diagnostics = detail["diagnostics"]
        assert detail["evidence_hit_count"] == 2
        assert detail["direct_evidence_hit_count"] == 0
        assert detail["linked_evidence_hit_count"] == 2
        assert runs[0]["evidence_hit_count"] == 2
        assert runs[0]["direct_evidence_hit_count"] == 0
        assert runs[0]["linked_evidence_hit_count"] == 2
        assert diagnostics["evidence_status"] == "linked"
        assert diagnostics["channel_hit_counts"]["linked_evidence"] == 2
        assert "evidence_only_linked_to_facts" in diagnostics["risk_flags"]
        assert "evidence_channel_empty" not in diagnostics["risk_flags"]
        assert "facts_without_evidence_links" not in diagnostics["risk_flags"]
    finally:
        connection.close()


def test_failure_analysis_attributes_entity_and_graph_root_causes(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    cases = [
        {"query": "软件架构分析有哪些活动", "must_include": "SWE.2.BP3", "assert_mode": "rich_answer"},
        {"query": "系统集成测试过程域有哪些活动", "must_include": "SYS.4.BP1", "assert_mode": "rich_answer"},
    ]
    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, "DOC-TEST", cases, source="unit_test")
        case_rows = connection.execute("SELECT case_id, query FROM golden_cases ORDER BY query").fetchall()
        case_by_query = {row["query"]: row["case_id"] for row in case_rows}
        eval_run_id = record_eval_run(
            connection,
            suite_id="golden:DOC-TEST",
            cases=cases,
            summary={"total": 2, "passed": 0, "failed": 2},
            command="pytest generated",
            success=False,
            output="2 failed",
            code_version="test",
            case_results=[
                {
                    "case_id": case_by_query["软件架构分析有哪些活动"],
                    "passed": False,
                    "failure_reason": "expected_answer_missing",
                    "retrieved_items": [
                        {
                            "result_type": "wiki",
                            "result_id": "WPAGE-BAD",
                            "snippet": "32 PUBLIC Base Practices",
                        }
                    ],
                    "answer": "32 PUBLIC",
                    "metrics": {
                        "query_type": "lifecycle_lookup",
                        "retrieval_channels": ["graph", "facts", "wiki"],
                        "graph_candidate_count": 0,
                        "topic_resolution_confidence": 0.82,
                        "topic_candidate_names": ["32 PUBLIC"],
                    },
                },
                {
                    "case_id": case_by_query["系统集成测试过程域有哪些活动"],
                    "passed": False,
                    "failure_reason": "retrieval_miss",
                    "retrieved_items": [],
                    "answer": "",
                    "metrics": {
                        "query_type": "lifecycle_lookup",
                        "retrieval_channels": ["graph", "facts", "wiki"],
                        "graph_candidate_count": 0,
                        "topic_resolution_confidence": 0,
                        "topic_candidate_names": [],
                    },
                },
            ],
        )
        connection.commit()

        analysis = build_failure_analysis(connection, eval_run_id)
        assert analysis is not None
        types = {item["query"]: item["failure_type"] for item in analysis["failures"]}
        assert types["软件架构分析有哪些活动"] == "entity_quality_pollution"
        assert types["系统集成测试过程域有哪些活动"] == "graph_not_engaged"
        noisy = next(item for item in analysis["failures"] if item["query"] == "软件架构分析有哪些活动")
        assert "page_header_public" in noisy["diagnostics"]["noise_signals"]
        task_reasons = {task["reason"] for task in analysis["repair_tasks"]}
        assert "entity_quality_pollution" in task_reasons
        assert "graph_not_engaged" in task_reasons
        assert analysis["repair_task_coverage"]["coverage_rate"] == 1.0
        assert analysis["repair_task_coverage"]["uncovered_case_ids"] == []
    finally:
        connection.close()


def test_failure_analysis_attributes_evidence_shape_mismatch(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    cases = [
        {
            "case_id": "CASE-SHAPE-1",
            "query": "软件架构设计有哪些活动",
            "must_include": "SWE.2.BP2",
            "assert_mode": "rich_answer",
            "expected_evidence_shape": "process_activity",
        }
    ]
    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, "DOC-TEST", cases, source="unit_test")
        eval_run_id = record_eval_run(
            connection,
            suite_id="golden:DOC-TEST",
            cases=cases,
            summary={"total": 1, "passed": 0, "failed": 1},
            command="pytest generated",
            success=False,
            output="1 failed",
            code_version="test",
            case_results=[
                {
                    "case_id": "CASE-SHAPE-1",
                    "passed": False,
                    "failure_reason": "evidence_shape_wrong",
                    "retrieved_items": [{"result_type": "fact", "result_id": "FACT-1"}],
                    "answer": "SWE.2.BP2",
                    "metrics": {
                        "query_type": "lifecycle_lookup",
                        "expected_evidence_shape": "process_activity",
                        "evidence_shape": "term_definition",
                        "evidence_shape_diagnostics": {
                            "shape_contract": {
                                "query_type": "lifecycle_lookup",
                                "allowed_shapes": ["process_activity"],
                                "required": True,
                                "matched": False,
                            },
                            "shape_contract_diagnosis": {
                                "reason": "contract_wrong_shape",
                                "action": "召回到了结构化证据，但形状不符合契约",
                                "repair_actions": [
                                    "检查 retrieval_router.py 的 channel 选择和 query_type 路由",
                                    "检查 graph relation / topic_resolution 是否把主题连到错误知识对象",
                                ],
                            },
                        },
                        "answer_quality": {
                            "failure_attribution": "evidence_shape_wrong",
                            "evidence_shape_match": False,
                            "expected_evidence_shape": "process_activity",
                            "evidence_shape": "term_definition",
                        },
                    },
                }
            ],
        )
        connection.commit()

        analysis = build_failure_analysis(connection, eval_run_id)
        assert analysis is not None
        failure = analysis["failures"][0]
        assert failure["failure_type"] == "evidence_shape_wrong"
        assert failure["expected"]["expected_evidence_shape"] == "process_activity"
        assert failure["diagnostics"]["evidence_shape"] == "term_definition"
        assert failure["diagnostics"]["shape_contract"]["allowed_shapes"] == ["process_activity"]
        assert failure["diagnostics"]["shape_contract"]["matched"] is False
        assert failure["diagnostics"]["shape_contract_diagnosis"]["reason"] == "contract_wrong_shape"
        assert analysis["shape_contract_reason_counts"] == {"contract_wrong_shape": 1}
        assert "contract_wrong_shape" in analysis["contract_repair_actions"]
        assert any("retrieval_router.py" in action for action in analysis["contract_repair_actions"]["contract_wrong_shape"])
        assert analysis["repair_tasks"]
        router_task = next(task for task in analysis["repair_tasks"] if task["module"] == "retrieval_router.py")
        assert router_task["reason"] == "contract_wrong_shape"
        assert router_task["status"] == "proposed"
        assert router_task["case_ids"] == ["CASE-SHAPE-1"]
        assert router_task["query_types"] == ["lifecycle_lookup"]
        persisted_tasks = list_repair_tasks(connection)
        assert any(task["task_id"] == router_task["task_id"] for task in persisted_tasks)
        persisted_router_task = next(task for task in persisted_tasks if task["task_id"] == router_task["task_id"])
        assert persisted_router_task["source_eval_run_id"] == eval_run_id
        assert persisted_router_task["impact_count"] == 1
        connection.execute("UPDATE repair_tasks SET status = 'in_progress' WHERE task_id = ?", (router_task["task_id"],))
        analysis_after_status_update = build_failure_analysis(connection, eval_run_id)
        assert analysis_after_status_update is not None
        preserved_task = next(task for task in analysis_after_status_update["repair_tasks"] if task["task_id"] == router_task["task_id"])
        assert preserved_task["status"] == "in_progress"
        updated_task = update_repair_task_status(connection, router_task["task_id"], "done", note="fixed in router")
        assert updated_task is not None
        assert updated_task["status"] == "done"
        assert updated_task["metadata"]["last_status_note"] == "fixed in router"
        assert updated_task["metadata"]["status_history"][-1]["to"] == "done"
        analysis_after_done_reappears = build_failure_analysis(connection, eval_run_id)
        assert analysis_after_done_reappears is not None
        reopened_task = next(task for task in analysis_after_done_reappears["repair_tasks"] if task["task_id"] == router_task["task_id"])
        assert reopened_task["status"] == "reopened"
        assert reopened_task["metadata"]["status_history"][-1]["to"] == "reopened"
        assert "reappeared" in reopened_task["metadata"]["last_status_note"]
        assert any("expected_evidence_shape" in action for action in failure["suggested_actions"])

        draft_result = draft_golden_case_from_failure(connection, eval_run_id, "CASE-SHAPE-1")
        connection.commit()
        assert draft_result is not None
        draft = draft_result["draft_case"]
        assert draft["expected_evidence_shape"] == "process_activity"
        assert draft["readiness_status"] == "ready"
        assert draft["can_activate"] is True
        assert draft["shape_contract_allowed_shapes"] == ["process_activity"]
        assert draft["shape_contract_actual_shape"] == "term_definition"
        assert draft["shape_contract_matched"] is False
    finally:
        connection.close()


def test_failure_analysis_auto_resolves_repair_tasks_for_fixed_failures(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    cases = [
        {
            "case_id": "CASE-FIXED-1",
            "query": "CC电阻有哪些定义",
            "must_include": "CC阻值",
            "assert_mode": "rich_answer",
            "expected_evidence_shape": "parameter_definition",
        }
    ]
    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, "DOC-TEST", cases, source="unit_test")
        baseline_id = record_eval_run(
            connection,
            suite_id="regression:query_repair_smoke",
            cases=cases,
            summary={"total": 1, "passed": 0, "failed": 1},
            command="smoke",
            success=False,
            output="1 failed",
            code_version="test",
            case_results=[
                {
                    "case_id": "CASE-FIXED-1",
                    "case": cases[0],
                    "passed": False,
                    "failure_reason": "evidence_not_sufficient",
                    "retrieved_items": [{"result_type": "fact", "result_id": "FACT-CC"}],
                    "answer": "CC阻值",
                    "metrics": {
                        "query_type": "parameter_lookup",
                        "expected_present": True,
                        "retrieval_quality": {"failure_attribution": "ok", "recall_at_5": 1.0, "mrr": 1.0},
                        "answer_quality": {
                            "answer_pass": False,
                            "failure_attribution": "evidence_not_sufficient",
                            "evidence_sufficient": False,
                            "evidence_gate_applied": True,
                        },
                    },
                }
            ],
        )
        baseline_analysis = build_failure_analysis(connection, baseline_id)
        assert baseline_analysis is not None
        assert baseline_analysis["repair_tasks"]
        assert {task["status"] for task in baseline_analysis["repair_tasks"]} == {"proposed"}

        current_id = record_eval_run(
            connection,
            suite_id="regression:query_repair_smoke",
            cases=cases,
            summary={"total": 1, "passed": 1, "failed": 0},
            command="smoke after fix",
            success=True,
            output="1 passed",
            code_version="test",
            case_results=[
                {
                    "case_id": "CASE-FIXED-1",
                    "case": cases[0],
                    "passed": True,
                    "failure_reason": None,
                    "retrieved_items": [{"result_type": "fact", "result_id": "FACT-CC"}],
                    "answer": "CC阻值",
                    "metrics": {
                        "query_type": "parameter_lookup",
                        "expected_present": True,
                        "retrieval_quality": {"failure_attribution": "ok", "recall_at_5": 1.0, "mrr": 1.0},
                        "answer_quality": {
                            "answer_pass": True,
                            "failure_attribution": "ok",
                            "evidence_sufficient": True,
                            "evidence_gate_applied": True,
                        },
                    },
                }
            ],
        )
        connection.commit()

        current_analysis = build_failure_analysis(connection, current_id)
        assert current_analysis is not None
        assert current_analysis["failure_count"] == 0
        assert current_analysis["comparison"]["fixed_failure_count"] == 1
        assert current_analysis["resolved_repair_tasks"]
        assert {task["status"] for task in current_analysis["resolved_repair_tasks"]} == {"done"}
        persisted_tasks = list_repair_tasks(connection, limit=10)
        assert persisted_tasks
        assert {task["status"] for task in persisted_tasks} == {"done"}
        assert all(task["metadata"]["resolved_by_eval_run_id"] == current_id for task in persisted_tasks)
        assert all(task["metadata"]["resolved_case_ids"] == ["CASE-FIXED-1"] for task in persisted_tasks)
    finally:
        connection.close()


def test_failure_analysis_filters_case_and_attributes_render_artifacts(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    cases = [
        {"case_id": "CASE-ARTIFACT-1", "query": "OBC输入过压怎么测", "must_include": "试验方法及步骤", "assert_mode": "rich_answer"},
        {"case_id": "CASE-OTHER-1", "query": "CP的时序是什么样的", "must_include": "表 A.7", "assert_mode": "rich_answer"},
    ]
    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, "DOC-TEST", cases, source="unit_test")
        eval_run_id = record_eval_run(
            connection,
            suite_id="golden:DOC-TEST",
            cases=cases,
            summary={"total": 2, "passed": 0, "failed": 2},
            command="pytest generated",
            success=False,
            output="2 failed",
            code_version="test",
            case_results=[
                {
                    "case_id": "CASE-ARTIFACT-1",
                    "passed": False,
                    "failure_reason": "answer_render_artifact",
                    "retrieved_items": [{"result_type": "fact", "result_id": "FACT-056351"}],
                    "answer": "5.4.1：&nbsp;&nbsp;试验方法及步骤:\n观\n察状态。；；$ \\pm15\\% $",
                    "metrics": {
                        "query_type": "test_method_lookup",
                        "evidence_shape": "test_method",
                        "answer_quality": {
                            "answer_pass": False,
                            "failure_attribution": "answer_render_artifact",
                            "render_artifact_hit_count": 4,
                            "render_artifact_hits": ["html_entity_nbsp", "latex_math_delimiter", "duplicate_semicolon", "hard_wrapped_cjk_line"],
                        },
                    },
                },
                {
                    "case_id": "CASE-OTHER-1",
                    "passed": False,
                    "failure_reason": "retrieval_miss",
                    "retrieved_items": [],
                    "answer": "",
                    "metrics": {"query_type": "timing_lookup"},
                },
            ],
        )
        connection.commit()

        analysis = build_failure_analysis(connection, eval_run_id, case_id="CASE-ARTIFACT-1")
        assert analysis is not None
        assert analysis["case_filter"] == "CASE-ARTIFACT-1"
        assert analysis["failure_count"] == 1
        failure = analysis["failures"][0]
        assert failure["case_id"] == "CASE-ARTIFACT-1"
        assert failure["failure_type"] == "answer_render_artifact"
        assert failure["diagnostics"]["answer_quality"]["render_artifact_hit_count"] == 4
        assert "html_entity_nbsp" in failure["diagnostics"]["answer_quality"]["render_artifact_hits"]
        assert any("渲染" in action for action in failure["suggested_actions"])
        assert analysis["repair_tasks"]
        assert {task["reason"] for task in analysis["repair_tasks"]} == {"answer_render_artifact"}
        assert analysis["repair_task_coverage"]["coverage_rate"] == 1.0
    finally:
        connection.close()


def test_failure_can_be_drafted_then_activated_as_golden_case(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    cases = [
        {
            "case_id": "CASE-FAIL-1",
            "query": "OBC输入过压怎么测",
            "must_include": "试验方法及步骤",
            "assert_mode": "rich_answer",
            "expected_evidence_shape": "test_method",
        }
    ]
    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, "DOC-TEST", cases, source="unit_test")
        eval_run_id = record_eval_run(
            connection,
            suite_id="golden:DOC-TEST",
            cases=cases,
            summary={"total": 1, "passed": 0, "failed": 1},
            command="pytest generated",
            success=False,
            output="1 failed",
            code_version="test",
            case_results=[
                {
                    "case_id": "CASE-FAIL-1",
                    "passed": False,
                    "failure_reason": "answer_render_artifact",
                    "retrieved_items": [{"result_type": "fact", "result_id": "FACT-056351", "doc_id": "DOC-000009"}],
                    "answer": "dirty",
                    "metrics": {
                        "query_type": "test_method_lookup",
                        "top_hit_doc_ids": ["DOC-000009"],
                        "evidence_shape": "test_method",
                        "answer_quality": {
                            "answer_pass": False,
                            "failure_attribution": "answer_render_artifact",
                            "render_artifact_hit_count": 1,
                            "render_artifact_hits": ["html_entity_nbsp"],
                        },
                    },
                }
            ],
        )
        connection.commit()

        draft_result = draft_golden_case_from_failure(connection, eval_run_id, "CASE-FAIL-1")
        connection.commit()
        assert draft_result is not None
        draft = draft_result["draft_case"]
        assert draft["status"] == "draft"
        assert draft["source"] == "failure_analysis"
        assert draft["doc_id"] == "DOC-000009"
        assert draft["must_hit"] == ["试验方法及步骤"]
        assert draft["expected_evidence_shape"] == "test_method"
        assert draft["readiness_status"] == "ready"
        assert draft["can_activate"] is True

        analysis = build_failure_analysis(connection, eval_run_id)
        assert analysis is not None
        assert analysis["failures"][0]["golden_draft"]["status"] == "draft"

        activated = activate_golden_case_draft(connection, str(draft["case_id"]))
        connection.commit()
        assert activated is not None
        assert activated["status"] == "active"
        row = connection.execute(
            "SELECT status, source FROM golden_cases WHERE case_id = ?",
            (draft["case_id"],),
        ).fetchone()
        assert row["status"] == "active"
        assert row["source"] == "failure_analysis"
    finally:
        connection.close()


def test_batch_drafts_all_eval_failures_without_using_wrong_actual_hits_as_anchors(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    cases = [
        {
            "case_id": "CASE-FAIL-1",
            "query": "OBC输入过压怎么测",
            "must_include": "试验方法及步骤",
            "assert_mode": "rich_answer",
            "expected_evidence_shape": "test_method",
        },
        {
            "case_id": "CASE-FAIL-2",
            "query": "没有明确锚点的问题",
            "assert_mode": "rich_answer",
        },
    ]
    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, "DOC-TEST", cases, source="unit_test")
        eval_run_id = record_eval_run(
            connection,
            suite_id="golden:DOC-TEST",
            cases=cases,
            summary={"total": 2, "passed": 0, "failed": 2},
            command="pytest generated",
            success=False,
            output="2 failed",
            code_version="test",
            case_results=[
                {
                    "case_id": "CASE-FAIL-1",
                    "passed": False,
                    "failure_reason": "answer_render_artifact",
                    "retrieved_items": [{"result_type": "fact", "result_id": "FACT-GOOD", "doc_id": "DOC-000009"}],
                    "answer": "dirty",
                    "metrics": {
                        "top_hit_doc_ids": ["DOC-000009"],
                        "evidence_shape": "test_method",
                        "answer_quality": {"failure_attribution": "answer_render_artifact", "forbidden_hits": ["&nbsp;"]},
                    },
                },
                {
                    "case_id": "CASE-FAIL-2",
                    "passed": False,
                    "failure_reason": "retrieval_miss",
                    "retrieved_items": [{"result_type": "fact", "result_id": "FACT-WRONG", "doc_id": "DOC-WRONG"}],
                    "answer": "wrong",
                    "metrics": {"retrieval_quality": {"failure_attribution": "retrieval_miss"}},
                },
            ],
        )
        connection.commit()

        result = draft_golden_cases_from_eval_failures(connection, eval_run_id)
        connection.commit()

        assert result is not None
        assert result["drafted_count"] == 2
        assert result["existing_count"] == 0
        drafts = {item["source_case_id"]: item for item in result["draft_cases"]}
        assert drafts["CASE-FAIL-1"]["readiness_status"] == "ready"
        assert drafts["CASE-FAIL-1"]["must_hit"] == ["试验方法及步骤"]
        assert drafts["CASE-FAIL-2"]["readiness_status"] == "blocked"
        assert drafts["CASE-FAIL-2"]["must_hit"] == []
        assert "FACT-WRONG" not in drafts["CASE-FAIL-2"]["must_hit"]
        assert "missing_assertion_signal" in drafts["CASE-FAIL-2"]["readiness_blockers"]

        second = draft_golden_cases_from_eval_failures(connection, eval_run_id)
        assert second is not None
        assert second["drafted_count"] == 0
        assert second["existing_count"] == 2
    finally:
        connection.close()


def test_golden_draft_activation_blocks_missing_assertion_signal(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
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

        result = activate_golden_case_draft(connection, "CASE-DRAFT-BLOCKED")
        connection.commit()
        assert result is not None
        assert result["activation_blocked"] is True
        assert result["status"] == "draft"
        assert result["readiness"]["status"] == "blocked"
        assert "missing_assertion_signal" in result["readiness"]["blockers"]
        row = connection.execute(
            "SELECT status, metadata_json FROM golden_cases WHERE case_id = 'CASE-DRAFT-BLOCKED'"
        ).fetchone()
        assert row["status"] == "draft"
        assert "last_readiness" in row["metadata_json"]
    finally:
        connection.close()


def test_golden_draft_activation_blocks_incomplete_shape_contract(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
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
                "CASE-DRAFT-SHAPE-BLOCKED",
                "DOC-TEST",
                "rich_answer",
                "软件架构设计有哪些活动",
                "[]",
                "[]",
                "[]",
                "[]",
                "process_activity",
                "draft",
                "failure_analysis",
                '{"source_eval_run_id":"EVAL-X","source_case_id":"CASE-X","failure_type":"evidence_shape_wrong","shape_contract_expected_shape":"process_activity","shape_contract_matched":false}',
                "2026-04-30T00:00:00+00:00",
                "2026-04-30T00:00:00+00:00",
            ),
        )
        connection.commit()

        result = activate_golden_case_draft(connection, "CASE-DRAFT-SHAPE-BLOCKED")
        connection.commit()
        assert result is not None
        assert result["activation_blocked"] is True
        assert "missing_shape_contract_actual" in result["readiness"]["blockers"]
        row = connection.execute(
            "SELECT status FROM golden_cases WHERE case_id = 'CASE-DRAFT-SHAPE-BLOCKED'"
        ).fetchone()
        assert row["status"] == "draft"
    finally:
        connection.close()


def test_regression_suite_case_results_keep_structured_case_ids(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    cases = [
        {
            "case_id": "CASE-SMOKE-1",
            "query": "CP的时序是什么样的",
            "must_include": "表 A.7",
            "assert_mode": "rich_answer",
            "source": "query_repair_smoke",
        }
    ]
    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, "query_repair_smoke", cases, source="query_repair_smoke")
        eval_run_id = record_eval_run(
            connection,
            suite_id="regression:query_repair_smoke",
            cases=cases,
            summary={"total": 1, "passed": 1, "failed": 0},
            command="eakb run-query-repair-smoke",
            success=True,
            output="",
            case_results=[
                {
                    "case_id": "CASE-SMOKE-1",
                    "passed": True,
                    "failure_reason": None,
                    "retrieved_items": [{"result_type": "fact", "result_id": "FACT-054025"}],
                    "answer": "表 A.7 交流充电控制时序表",
                    "metrics": {
                        "expected_present": True,
                        "query_type": "timing_lookup",
                        "retrieval_quality": {"recall_at_5": 1.0, "mrr": 1.0, "failure_attribution": "ok"},
                    },
                }
            ],
        )
        connection.commit()

        row = connection.execute(
            """
            SELECT passed, failure_reason, metrics_json
            FROM eval_results
            WHERE eval_run_id = ? AND case_id = ?
            """,
            (eval_run_id, "CASE-SMOKE-1"),
        ).fetchone()
        assert row is not None
        assert row["passed"] == 1
        assert row["failure_reason"] is None
        assert "coarse_result_from_pytest" not in row["metrics_json"]
        assert "timing_lookup" in row["metrics_json"]
        assert "retrieval_quality" in row["metrics_json"]
        assert "recall_at_5" in row["metrics_json"]
    finally:
        connection.close()


def test_eval_run_summary_aggregates_retrieval_and_answer_quality(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    cases = [
        {"case_id": "CASE-RQ-1", "query": "Q1", "must_include": "A", "assert_mode": "rich_answer"},
        {"case_id": "CASE-RQ-2", "query": "Q2", "must_include": "B", "assert_mode": "rich_answer"},
    ]
    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, "DOC-TEST", cases, source="unit_test")
        eval_run_id = record_eval_run(
            connection,
            suite_id="golden:DOC-TEST",
            cases=cases,
            summary={"total": 2, "passed": 1, "failed": 1},
            command="pytest generated",
            success=False,
            output="1 passed, 1 failed, 23 deselected in 2.34s",
            case_results=[
                {
                    "case_id": "CASE-RQ-1",
                    "passed": True,
                    "failure_reason": None,
                    "retrieved_items": [],
                    "answer": "A",
                    "metrics": {
                        "answer_quality": {
                            "answer_pass": True,
                            "answer_mode_match": True,
                            "forbidden_hit_count": 0,
                            "evidence_sufficient": True,
                            "failure_attribution": "ok",
                        },
                        "retrieval_quality": {
                            "recall_at_5": 1.0,
                            "recall_at_10": 1.0,
                            "mrr": 1.0,
                            "negative_hit_rate": 0.0,
                            "failure_attribution": "ok",
                        },
                        "query_type": "test_method_lookup",
                        "shape_contract_query_type": "test_method_lookup",
                        "shape_contract_allowed_shapes": ["test_method"],
                        "shape_contract_required": True,
                        "shape_contract_matched": True,
                        "shape_contract_failure_reason": "contract_matched",
                    },
                },
                {
                    "case_id": "CASE-RQ-2",
                    "passed": False,
                    "failure_reason": "retrieval_miss",
                    "retrieved_items": [],
                    "answer": "",
                    "metrics": {
                        "answer_quality": {
                            "answer_pass": False,
                            "answer_mode_match": False,
                            "forbidden_hit_count": 1,
                            "evidence_sufficient": False,
                            "failure_attribution": "forbidden_content",
                        },
                        "retrieval_quality": {
                            "recall_at_5": 0.0,
                            "recall_at_10": 0.0,
                            "mrr": 0.0,
                            "negative_hit_rate": 0.0,
                            "failure_attribution": "retrieval_miss",
                        },
                        "query_type": "lifecycle_lookup",
                        "shape_contract_query_type": "lifecycle_lookup",
                        "shape_contract_allowed_shapes": ["process_activity"],
                        "shape_contract_required": True,
                        "shape_contract_matched": False,
                        "shape_contract_failure_reason": "contract_wrong_shape",
                    },
                },
            ],
        )
        connection.commit()

        detail = connection.execute(
            "SELECT result_summary_json FROM eval_runs WHERE eval_run_id = ?",
            (eval_run_id,),
        ).fetchone()
        assert detail is not None
        assert '"recall_at_5": 0.5' in detail["result_summary_json"]
        assert '"mrr": 0.5' in detail["result_summary_json"]
        assert '"retrieval_miss": 1' in detail["result_summary_json"]
        assert '"answer_pass_rate": 0.5' in detail["result_summary_json"]
        assert '"answer_mode_accuracy": 0.5' in detail["result_summary_json"]
        assert '"forbidden_hit_rate": 0.5' in detail["result_summary_json"]
        assert '"shape_contract_quality"' in detail["result_summary_json"]
        assert '"contract_match_rate": 0.5' in detail["result_summary_json"]
        assert '"contract_mismatch_count": 1' in detail["result_summary_json"]
        assert '"contract_wrong_shape": 1' in detail["result_summary_json"]
        assert '"pytest_counts"' in detail["result_summary_json"]
        assert '"deselected": 23' in detail["result_summary_json"]
        assert '"collected": 25' in detail["result_summary_json"]
        assert '"eval_scope"' in detail["result_summary_json"]
        assert '"declared_case_count": 2' in detail["result_summary_json"]
        assert '"evaluated_case_count": 2' in detail["result_summary_json"]
        assert '"unevaluated_case_count": 0' in detail["result_summary_json"]
        assert '"pytest_summary_detected": true' in detail["result_summary_json"]
    finally:
        connection.close()


def test_eval_scope_detects_unevaluated_structured_cases(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    cases = [
        {"case_id": "CASE-SCOPE-1", "query": "Q1", "must_include": "A", "assert_mode": "rich_answer"},
        {"case_id": "CASE-SCOPE-2", "query": "Q2", "must_include": "B", "assert_mode": "rich_answer"},
    ]
    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, "DOC-TEST", cases, source="unit_test")
        eval_run_id = record_eval_run(
            connection,
            suite_id="regression:scope",
            cases=cases,
            summary={"total": 2, "passed": 1, "failed": 0},
            command="structured scope test",
            success=True,
            output="structured eval completed",
            case_results=[
                {
                    "case_id": "CASE-SCOPE-1",
                    "passed": True,
                    "failure_reason": None,
                    "retrieved_items": [],
                    "answer": "A",
                    "metrics": {},
                }
            ],
        )
        connection.commit()
        row = connection.execute("SELECT result_summary_json FROM eval_runs WHERE eval_run_id = ?", (eval_run_id,)).fetchone()
        assert row is not None
        assert '"declared_case_count": 2' in row["result_summary_json"]
        assert '"evaluated_case_count": 1' in row["result_summary_json"]
        assert '"unevaluated_case_count": 1' in row["result_summary_json"]
        assert '"pytest_summary_detected": false' in row["result_summary_json"]
    finally:
        connection.close()


def test_backfills_legacy_eval_scope_metadata(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        now = "2026-05-01T00:00:00+00:00"
        connection.execute(
            """
            INSERT INTO eval_runs (
                eval_run_id, suite_id, started_at, finished_at, config_hash,
                code_version, result_summary_json, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "EVAL-LEGACY",
                "golden:DOC-TEST",
                now,
                now,
                "cfg",
                "code",
                '{"total": 2, "passed": 1, "failed": 1}',
                "failed",
            ),
        )
        connection.execute(
            """
            INSERT INTO eval_results (
                eval_run_id, case_id, passed, failure_reason,
                retrieved_items_json, answer_text, metrics_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("EVAL-LEGACY", "CASE-1", 1, None, "[]", "A", "{}", now),
        )
        connection.commit()

        result = backfill_eval_run_scope_metadata(connection)
        connection.commit()
        row = connection.execute(
            "SELECT result_summary_json FROM eval_runs WHERE eval_run_id = 'EVAL-LEGACY'"
        ).fetchone()

        assert result["updated_count"] == 1
        assert row is not None
        assert '"eval_scope"' in row["result_summary_json"]
        assert '"declared_case_count": 2' in row["result_summary_json"]
        assert '"evaluated_case_count": 1' in row["result_summary_json"]
        assert '"unevaluated_case_count": 1' in row["result_summary_json"]
        assert '"source": "legacy_inferred"' in row["result_summary_json"]
        assert '"pytest_counts"' in row["result_summary_json"]
        assert '"source": "legacy_unavailable"' in row["result_summary_json"]
    finally:
        connection.close()


def test_compare_eval_runs_attributes_regressions_and_quality_delta(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    cases = [
        {"case_id": "CASE-1", "query": "Q1", "must_include": "A", "assert_mode": "rich_answer"},
        {"case_id": "CASE-2", "query": "Q2", "must_include": "B", "assert_mode": "rich_answer"},
        {"case_id": "CASE-3", "query": "Q3", "must_include": "C", "assert_mode": "rich_answer"},
    ]
    current_cases = [
        {"case_id": "CASE-1", "query": "Q1", "must_include": "A", "assert_mode": "rich_answer"},
        {"case_id": "CASE-3", "query": "Q3", "must_include": "C", "assert_mode": "rich_answer"},
        {"case_id": "CASE-4", "query": "Q4", "must_include": "D", "assert_mode": "rich_answer"},
    ]
    connection = connect(paths.db_file)
    try:
        sync_golden_cases(connection, "DOC-TEST", [*cases, current_cases[-1]], source="unit_test")
        baseline_id = record_eval_run(
            connection,
            suite_id="golden:DOC-TEST",
            cases=cases,
            summary={"total": 3, "passed": 2, "failed": 1},
            command="baseline",
            success=False,
            output="",
            case_results=[
                _case_result("CASE-1", True, None, 1.0, 1.0, "ok"),
                _case_result("CASE-2", False, "retrieval_miss", 0.0, 0.0, "retrieval_miss"),
                _case_result("CASE-3", True, None, 1.0, 1.0, "ok"),
            ],
        )
        current_id = record_eval_run(
            connection,
            suite_id="golden:DOC-TEST",
            cases=current_cases,
            summary={"total": 3, "passed": 1, "failed": 2},
            command="current",
            success=False,
            output="",
            case_results=[
                _case_result("CASE-1", False, "retrieval_miss", 0.0, 0.0, "retrieval_miss"),
                _case_result("CASE-3", True, None, 1.0, 1.0, "ok"),
                _case_result("CASE-4", False, "answer_policy_wrong", 1.0, 1.0, "ok"),
            ],
        )
        connection.commit()

        comparison = compare_eval_runs(connection, current_id, baseline_id)
        assert comparison is not None
        assert comparison["baseline_eval_run_id"] == baseline_id
        assert comparison["new_failure_count"] == 1
        assert comparison["fixed_failure_count"] == 0
        assert comparison["stable_pass_count"] == 1
        assert comparison["removed_case_count"] == 1
        assert comparison["added_case_count"] == 1
        assert comparison["removed_cases"][0]["case_id"] == "CASE-2"
        assert comparison["added_cases"][0]["case_id"] == "CASE-4"
        assert comparison["retrieval_regression_count"] == 1
        assert comparison["answer_regression_count"] == 0
        assert comparison["retrieval_quality_delta"]["recall_at_5_delta"] == 0.0
        assert comparison["retrieval_quality_delta"]["mrr_delta"] == 0.0
        assert comparison["answer_quality_delta"]["answer_pass_rate_delta"] == -0.333334
        assert comparison["answer_quality_delta"]["forbidden_hit_rate_delta"] == 0.0
    finally:
        connection.close()


def _case_result(
    case_id: str,
    passed: bool,
    failure_reason: str | None,
    recall_at_5: float,
    mrr: float,
    attribution: str,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "passed": passed,
        "failure_reason": failure_reason,
        "retrieved_items": [],
        "answer": "answer" if passed else "",
        "metrics": {
            "answer_mode": "rich_answer",
            "answer_quality": {
                "answer_pass": passed,
                "answer_mode_match": True,
                "forbidden_hit_count": 0,
                "evidence_sufficient": passed,
                "failure_attribution": "ok" if passed else "expected_answer_missing",
            },
            "retrieval_quality": {
                "recall_at_5": recall_at_5,
                "recall_at_10": recall_at_5,
                "mrr": mrr,
                "negative_hit_rate": 0.0,
                "failure_attribution": attribution,
            },
        },
    }


def _columns(connection, table: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}
