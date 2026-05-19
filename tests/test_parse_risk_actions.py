from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.parse_risk_actions import build_parse_risk_action_plan
from enterprise_agent_kb.parse_risk_actions import build_parse_risk_repair_review
from enterprise_agent_kb.parse_risk_actions import generate_parse_risk_action_plan
from enterprise_agent_kb.parse_risk_actions import persist_parse_risk_repair_tasks


def test_parse_risk_action_plan_keeps_upstream_issues_out_of_golden_requests() -> None:
    plan = build_parse_risk_action_plan(
        "DOC-TEST",
        {
            "parse_quality": {
                "high_risk_page_count": 4,
                "attribution_counts": {
                    "provider_quality_issue": 1,
                    "selection_rule_issue": 1,
                    "extraction_chain_issue": 1,
                    "test_coverage_gap": 1,
                    "review_only": 0,
                },
                "pages": [
                    {"page_no": 1, "attribution": "provider_quality_issue"},
                    {"page_no": 2, "attribution": "selection_rule_issue"},
                    {"page_no": 3, "attribution": "extraction_chain_issue"},
                    {"page_no": 4, "attribution": "test_coverage_gap"},
                ],
            }
        },
    )

    reasons = {task.reason for task in plan.repair_tasks}
    assert "parse_provider_quality_issue" in reasons
    assert "parse_selection_rule_issue" in reasons
    assert "parse_extraction_chain_issue" in reasons
    assert "parse_test_coverage_gap" in reasons
    assert len(plan.golden_candidate_requests) == 1
    assert plan.golden_candidate_requests[0].page_no == 4
    assert plan.status == "action_required"


def test_parse_risk_action_plan_reports_no_risk_without_mutation() -> None:
    plan = build_parse_risk_action_plan("DOC-EMPTY", {"parse_quality": {"pages": []}})

    assert plan.status == "no_parse_risk"
    assert plan.repair_tasks == []
    assert plan.golden_candidate_requests == []
    assert "does not activate golden cases" in plan.guardrails[2]


def test_persist_parse_risk_repair_tasks_groups_systemic_tasks(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", Path("src/enterprise_agent_kb/schema.sql"))
    connection = connect(paths.db_file)
    try:
        plan_a = build_parse_risk_action_plan(
            "DOC-A",
            {
                "parse_quality": {
                    "attribution_counts": {"provider_quality_issue": 1},
                    "pages": [{"page_no": 7, "attribution": "provider_quality_issue"}],
                }
            },
        )
        plan_b = build_parse_risk_action_plan(
            "DOC-B",
            {
                "parse_quality": {
                    "attribution_counts": {"provider_quality_issue": 1},
                    "pages": [{"page_no": 9, "attribution": "provider_quality_issue"}],
                }
            },
        )

        first = persist_parse_risk_repair_tasks(connection, plan_a)
        second = persist_parse_risk_repair_tasks(connection, plan_b)
        connection.commit()

        assert len(first) == 1
        assert len(second) == 1
        assert first[0]["task_id"] == second[0]["task_id"]
        metadata = second[0]["metadata"]
        assert sorted(metadata["parse_risk_docs"]) == ["DOC-A", "DOC-B"]
        assert metadata["parse_risk_docs"]["DOC-A"]["page_numbers"] == [7]
        assert metadata["parse_risk_docs"]["DOC-B"]["page_numbers"] == [9]
        assert metadata["parse_risk_doc_count"] == 2
        assert metadata["parse_risk_total_page_count"] == 2
        assert second[0]["impact_count"] == 2
    finally:
        connection.close()


def test_persist_parse_risk_repair_tasks_reopens_closed_systemic_task(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", Path("src/enterprise_agent_kb/schema.sql"))
    connection = connect(paths.db_file)
    try:
        plan_a = build_parse_risk_action_plan(
            "DOC-A",
            {
                "parse_quality": {
                    "attribution_counts": {"provider_quality_issue": 1},
                    "pages": [{"page_no": 7, "attribution": "provider_quality_issue"}],
                }
            },
        )
        first = persist_parse_risk_repair_tasks(connection, plan_a)
        connection.execute("UPDATE repair_tasks SET status = 'done' WHERE task_id = ?", (first[0]["task_id"],))
        plan_b = build_parse_risk_action_plan(
            "DOC-B",
            {
                "parse_quality": {
                    "attribution_counts": {"provider_quality_issue": 1},
                    "pages": [{"page_no": 9, "attribution": "provider_quality_issue"}],
                }
            },
        )
        second = persist_parse_risk_repair_tasks(connection, plan_b)

        assert second[0]["task_id"] == first[0]["task_id"]
        assert second[0]["status"] == "reopened"
    finally:
        connection.close()


def test_parse_risk_repair_review_suggests_done_improved_and_expanded(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", Path("src/enterprise_agent_kb/schema.sql"))
    connection = connect(paths.db_file)
    try:
        original = build_parse_risk_action_plan(
            "DOC-REVIEW",
            {
                "parse_quality": {
                    "attribution_counts": {
                        "provider_quality_issue": 2,
                        "extraction_chain_issue": 2,
                        "test_coverage_gap": 1,
                    },
                    "pages": [
                        {"page_no": 1, "attribution": "provider_quality_issue"},
                        {"page_no": 2, "attribution": "provider_quality_issue"},
                        {"page_no": 3, "attribution": "extraction_chain_issue"},
                        {"page_no": 4, "attribution": "extraction_chain_issue"},
                        {"page_no": 5, "attribution": "test_coverage_gap"},
                    ],
                }
            },
        )
        persist_parse_risk_repair_tasks(connection, original)
        current = build_parse_risk_action_plan(
            "DOC-REVIEW",
            {
                "parse_quality": {
                    "attribution_counts": {
                        "provider_quality_issue": 1,
                        "extraction_chain_issue": 3,
                    },
                    "pages": [
                        {"page_no": 1, "attribution": "provider_quality_issue"},
                        {"page_no": 3, "attribution": "extraction_chain_issue"},
                        {"page_no": 4, "attribution": "extraction_chain_issue"},
                        {"page_no": 6, "attribution": "extraction_chain_issue"},
                    ],
                }
            },
        )

        review = build_parse_risk_repair_review(connection, "DOC-REVIEW", current)
        by_reason = {item["reason"]: item for item in review.reviews}

        assert by_reason["parse_provider_quality_issue"]["suggested_status"] == "improved"
        assert by_reason["parse_provider_quality_issue"]["resolved_pages"] == [2]
        assert by_reason["parse_extraction_chain_issue"]["suggested_status"] == "expanded"
        assert by_reason["parse_extraction_chain_issue"]["new_pages"] == [6]
        assert by_reason["parse_test_coverage_gap"]["suggested_status"] == "done"
        assert review.status_counts == {"done": 1, "expanded": 1, "improved": 1}
    finally:
        connection.close()


def test_generate_parse_risk_action_plan_writes_latest_and_history_reports(tmp_path: Path, monkeypatch) -> None:
    paths = initialize_workspace(tmp_path / "kb", Path("src/enterprise_agent_kb/schema.sql"))

    def fake_diagnostics(_workspace_root: Path, doc_id: str) -> dict[str, object]:
        return {
            "parse_quality": {
                "attribution_counts": {"provider_quality_issue": 1},
                "pages": [{"page_no": 1, "attribution": "provider_quality_issue"}],
            }
        }

    monkeypatch.setattr("enterprise_agent_kb.parse_risk_actions.build_document_diagnostics", fake_diagnostics)
    plan = generate_parse_risk_action_plan(paths.root, "DOC-HISTORY")

    assert plan.json_path is not None
    assert plan.report_path is not None
    assert plan.history_json_path is not None
    assert plan.history_report_path is not None
    assert Path(plan.json_path).exists()
    assert Path(plan.report_path).exists()
    assert Path(plan.history_json_path).exists()
    assert Path(plan.history_report_path).exists()
    assert plan.history_json_path != plan.json_path
