from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.closed_loop_store import record_eval_run, sync_golden_cases, sync_source_units_from_matrix
from enterprise_agent_kb.cli import build_parser
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.golden_generation import (
    evaluate_activation_readiness,
    generate_eval_failure_candidates,
    generate_golden_candidates,
    generate_source_unit_candidates,
    make_assertion_contract,
    make_golden_candidate,
    summarize_candidates,
)


SCHEMA_PATH = Path("src/enterprise_agent_kb/schema.sql")


def test_generate_source_unit_candidates_uses_corpus_contract_without_activating(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    _insert_document(paths.db_file, "DOC-TEST")
    connection = connect(paths.db_file)
    try:
        sync_source_units_from_matrix(
            connection,
            "DOC-TEST",
            [
                {
                    "unit_id": "SU-DEF-1",
                    "unit_type": "definition_unit",
                    "page_no": 1,
                    "canonical_title": "连接确认功能 connection confirm",
                    "canonical_key": "连接确认功能 connection confirm",
                    "content_role": "definition",
                    "source_text": "连接确认功能 connection confirm: 通过电子或者机械方式反映连接状态的功能。",
                    "covered_by": {"fact_ids": ["FACT-1"], "evidence_ids": ["EVID-1"]},
                    "coverage_status": "covered",
                },
                {
                    "unit_id": "SU-NOISE-1",
                    "unit_type": "definition_unit",
                    "page_no": 2,
                    "canonical_title": "前言",
                    "content_role": "preface",
                    "source_text": "GB：代替 GB/T 0000-2015",
                    "covered_by": {"fact_ids": ["FACT-N"], "evidence_ids": ["EVID-N"]},
                    "coverage_status": "covered",
                },
            ],
            generated_at="2026-05-12T00:00:00+00:00",
        )
        connection.commit()
    finally:
        connection.close()

    result = generate_source_unit_candidates(paths.root, limit_per_type=10)

    assert result.summary["candidate_count"] == 1
    assert result.summary["by_origin"] == {"source_unit": 1}
    assert result.summary["by_confidence_tier"] == {"corpus_eval": 1}
    assert result.summary["readiness_counts"] == {"review_required": 1}
    assert result.summary["skipped_counts"] == {"noise_or_preface": 1}
    candidate = result.candidates[0]
    assert candidate.query == "连接确认功能是什么意思"
    assert candidate.confidence_tier == "corpus_eval"
    assert candidate.assertion_contract.expected_evidence_shape == "term_definition"
    assert candidate.to_golden_case()["status"] == "draft"


def test_generate_golden_candidates_writes_dry_run_reports(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    _insert_document(paths.db_file, "DOC-TEST")
    connection = connect(paths.db_file)
    try:
        sync_source_units_from_matrix(
            connection,
            "DOC-TEST",
            [
                {
                    "unit_id": "SU-DEF-1",
                    "unit_type": "definition_unit",
                    "page_no": 1,
                    "canonical_title": "连接确认功能 connection confirm",
                    "canonical_key": "连接确认功能 connection confirm",
                    "content_role": "definition",
                    "source_text": "连接确认功能 connection confirm: 通过电子或者机械方式反映连接状态的功能。",
                    "covered_by": {"fact_ids": ["FACT-1"], "evidence_ids": ["EVID-1"]},
                    "coverage_status": "covered",
                },
            ],
            generated_at="2026-05-12T00:00:00+00:00",
        )
        connection.commit()
    finally:
        connection.close()

    result = generate_golden_candidates(paths.root, output_dir=tmp_path / "out")

    assert result.summary["dry_run"] is True
    assert result.summary["auto_activation"] is False
    assert result.json_path.exists()
    assert result.report_path.exists()
    assert "Golden Generation Candidates" in result.report_path.read_text(encoding="utf-8")


def test_generate_golden_candidates_cli_parser() -> None:
    parser = build_parser()

    parsed = parser.parse_args(
        [
            "--root",
            "knowledge_base",
            "generate-golden-candidates",
            "--origin",
            "source_unit",
            "--doc-id",
            "DOC-000013",
            "--limit-per-type",
            "3",
            "--output-dir",
            "out",
        ]
    )

    assert parsed.command == "generate-golden-candidates"
    assert parsed.origin == ["source_unit"]
    assert parsed.doc_id == ["DOC-000013"]
    assert parsed.limit_per_type == 3


def test_generate_eval_failure_candidates_uses_expected_contract_not_wrong_retrieved_item(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        cases = [
            {
                "case_id": "CASE-FAIL-1",
                "query": "传导充电是什么意思",
                "assert_mode": "context_contains",
                "must_hit": ["传导充电"],
                "expected_evidence_shape": "term_definition",
            }
        ]
        sync_golden_cases(connection, "DOC-TEST", cases, source="unit_test")
        eval_run_id = record_eval_run(
            connection,
            suite_id="golden:DOC-TEST",
            cases=cases,
            summary={"total": 1, "passed": 0, "failed": 1},
            command="pytest",
            success=False,
            output="failed",
            case_results=[
                {
                    "case_id": "CASE-FAIL-1",
                    "passed": False,
                    "failure_reason": "retrieval_miss",
                    "retrieved_items": [{"result_id": "WRONG-TOP-HIT", "text": "不相关内容"}],
                    "answer": "",
                    "metrics": {},
                }
            ],
        )
        connection.commit()

        result = generate_eval_failure_candidates(connection, eval_run_id)
    finally:
        connection.close()

    assert result is not None
    assert result.summary["candidate_count"] == 1
    candidate = result.candidates[0]
    assert candidate.origin == "eval_failure"
    assert candidate.assertion_contract.must_hit == ("传导充电",)
    assert "WRONG-TOP-HIT" not in candidate.assertion_contract.must_hit
    assert candidate.trace["actual_top_items"] == ["WRONG-TOP-HIT"]


def test_golden_candidate_with_stable_assertion_contract_is_ready() -> None:
    candidate = make_golden_candidate(
        query="OBC输入过压怎么测",
        origin="source_unit",
        confidence_tier="draft",
        assertion_contract={
            "must_hit": ["交流输入过、欠压保护试验"],
            "expected_evidence_shape": "test_method",
            "expected_answer_mode": "test_method_lookup",
        },
        trace={"coverage_unit_id": "UNIT-1", "source_fact_ids": ["FACT-1"]},
    )

    readiness = candidate.readiness()

    assert candidate.case_id.startswith("GGV1-")
    assert readiness.can_activate is True
    assert readiness.readiness_status == "ready"
    assert candidate.to_golden_case()["status"] == "draft"


def test_candidate_without_assertion_signal_is_blocked() -> None:
    candidate = make_golden_candidate(
        query="这个怎么测",
        origin="eval_failure",
        confidence_tier="draft",
        assertion_contract=make_assertion_contract({}),
    )

    readiness = evaluate_activation_readiness(candidate)

    assert readiness.can_activate is False
    assert readiness.readiness_status == "blocked"
    assert "missing_assertion_signal" in readiness.reasons
    assert "eval_failure_missing_stable_expected_contract" in readiness.reasons


def test_corpus_eval_candidate_requires_review_even_with_assertions() -> None:
    candidate = make_golden_candidate(
        query="连接确认功能是什么意思",
        origin="source_unit",
        confidence_tier="corpus_eval",
        assertion_contract={
            "must_hit": ["连接确认功能"],
            "expected_evidence_shape": "term_definition",
        },
    )

    readiness = candidate.readiness()

    assert readiness.can_activate is False
    assert readiness.readiness_status == "review_required"
    assert readiness.reasons == ("corpus_eval_requires_review",)


def test_candidate_summary_groups_origin_tier_and_blocked_reasons() -> None:
    ready = make_golden_candidate(
        query="CC阻值代表什么意思",
        origin="manual_query",
        confidence_tier="draft",
        assertion_contract={"must_hit": ["CC", "阻值"]},
    )
    blocked = make_golden_candidate(
        query="",
        origin="ontology_gap",
        confidence_tier="blocked",
        assertion_contract={},
    )

    summary = summarize_candidates([ready, blocked])

    assert summary["candidate_count"] == 2
    assert summary["by_origin"] == {"manual_query": 1, "ontology_gap": 1}
    assert summary["readiness_counts"] == {"blocked": 1, "ready": 1}
    assert summary["blocked_reasons"]["missing_query"] == 1
    assert summary["blocked_reasons"]["ontology_gap_generation_not_implemented"] == 1


def _insert_document(db_file: Path, doc_id: str) -> None:
    connection = connect(db_file)
    try:
        connection.execute(
            """
            INSERT INTO documents(
                doc_id, source_filename, source_type, mime_type, sha256, file_size,
                page_count, language, version_label, source_path, ingest_time,
                update_time, parse_status, quality_status, is_active
            )
            VALUES (?, 'doc.pdf', 'pdf', 'application/pdf', 'sha', 100, 1, 'zh', NULL, 'doc.pdf', 'now', 'now', 'parsed', 'ok', 1)
            """,
            (doc_id,),
        )
        connection.commit()
    finally:
        connection.close()
