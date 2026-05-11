from __future__ import annotations

import json
from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.cli import build_parser
from enterprise_agent_kb.closed_loop_store import sync_source_units_from_matrix
from enterprise_agent_kb.corpus_eval import generate_corpus_eval_cases, run_corpus_retrieval_eval
from enterprise_agent_kb.db import connect


SCHEMA_PATH = Path("src/enterprise_agent_kb/schema.sql")


def test_generate_corpus_eval_cases_from_source_units(tmp_path: Path) -> None:
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
                    "semantic_key": "连接确认功能 connection confirm",
                    "canonical_title": "连接确认功能 connection confirm",
                    "canonical_key": "连接确认功能 connection confirm",
                    "content_role": "definition",
                    "importance": "high",
                    "source_text": "连接确认功能 connection confirm: 通过电子或者机械方式反映连接状态的功能。",
                    "covered_by": {"fact_ids": ["FACT-DEF-1"], "evidence_ids": ["EV-DEF-1"]},
                    "coverage_status": "covered",
                },
                {
                    "unit_id": "SU-PARAM-1",
                    "unit_type": "parameter_row_unit",
                    "page_no": 2,
                    "semantic_key": "CC阻值",
                    "canonical_title": "**表 A.2 参数**",
                    "canonical_key": "CC阻值",
                    "content_role": "parameter_row",
                    "importance": "high",
                    "source_text": "车辆接口 | 等效电阻 | Rc | Ω | 1000",
                    "covered_by": {"fact_ids": ["FACT-PARAM-1"], "evidence_ids": ["EV-PARAM-1"]},
                    "coverage_status": "covered",
                },
                {
                    "unit_id": "SU-PROC-1",
                    "unit_type": "process_unit",
                    "page_no": 3,
                    "semantic_key": "SWE.2",
                    "canonical_title": "SWE.2 基本实践",
                    "canonical_key": "SWE.2",
                    "content_role": "process_practice",
                    "importance": "high",
                    "source_text": "**SWE.2.BP1: 定义软件架构。** Develop software architectural design.",
                    "covered_by": {"fact_ids": ["FACT-PROC-1"], "evidence_ids": ["EV-PROC-1"]},
                    "coverage_status": "covered",
                },
                {
                    "unit_id": "SU-PREFACE-1",
                    "unit_type": "definition_unit",
                    "page_no": 4,
                    "canonical_title": "前言",
                    "content_role": "preface",
                    "source_text": "GB：代替 GB/T 0000-2015",
                    "covered_by": {"fact_ids": ["FACT-NOISE-1"], "evidence_ids": ["EV-NOISE-1"]},
                    "coverage_status": "covered",
                },
                {
                    "unit_id": "SU-MISSING-COVERAGE",
                    "unit_type": "definition_unit",
                    "page_no": 5,
                    "canonical_title": "未覆盖术语",
                    "content_role": "definition",
                    "source_text": "未覆盖术语: 没有映射到 fact 或 evidence。",
                    "coverage_status": "covered",
                },
            ],
            generated_at="2026-05-11T00:00:00+00:00",
        )
        connection.commit()
    finally:
        connection.close()

    result = generate_corpus_eval_cases(paths.root, limit_per_type=10, output_dir=tmp_path / "out")

    assert result.case_count == 3
    by_type = {str(case["case_type"]): case for case in result.cases}
    assert by_type["definition"]["query"] == "连接确认功能是什么意思"
    assert by_type["definition"]["expected_evidence_shape"] == "term_definition"
    assert by_type["parameter"]["query"] == "CC阻值车辆接口等效电阻参数是什么"
    assert by_type["parameter"]["retrieval_must_hit"][:4] == ["等效电阻", "Rc", "车辆接口", "CC阻值"]
    assert by_type["process_activity"]["query"] == "SWE.2有哪些活动"
    assert by_type["process_activity"]["expected_min_graph_candidates"] == 1
    assert result.summary["skipped_counts"] == {
        "missing_traceable_coverage": 1,
        "noise_or_preface": 1,
    }


def test_run_corpus_retrieval_eval_records_eval_run(tmp_path: Path, monkeypatch) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    cases = [
        {
            "case_id": "CORPUS-CASE-1",
            "query": "SWE.2有哪些活动",
            "assert_mode": "context_contains",
            "source": "corpus_eval",
            "case_type": "process_activity",
            "coverage_unit_id": "SU-PROC-1",
            "expected_doc_id": "DOC-TEST",
            "expected_query_type": "lifecycle_lookup",
            "expected_evidence_shape": "process_activity",
            "expected_min_graph_candidates": 1,
            "retrieval_must_hit": ["SWE.2.BP1"],
        }
    ]
    case_file = tmp_path / "cases.json"
    case_file.write_text(json.dumps({"cases": cases}, ensure_ascii=False), encoding="utf-8")

    def fake_build_query_context(workspace_root: Path, query: str, limit: int = 8, preferred_doc_id: str | None = None) -> dict[str, object]:
        assert workspace_root == paths.root
        assert query == "SWE.2有哪些活动"
        assert preferred_doc_id == "DOC-TEST"
        return {
            "rewrite": {"query_type": "lifecycle_lookup"},
            "retrieval_plan": {"channels": ["graph", "facts"], "graph_candidate_count": 2},
            "topic_resolution": {"confidence": 1.0, "candidate_entities": [{"canonical_name": "SWE.2"}]},
            "hits": [
                {
                    "result_type": "fact",
                    "result_id": "fact:FACT-PROC-1",
                    "doc_id": "DOC-TEST",
                    "page_no": 3,
                    "score": 1.2,
                    "snippet": "SWE.2.BP1 定义软件架构。",
                    "graph_source": True,
                    "channels": ["graph", "facts"],
                }
            ],
            "evidence_judgement": {
                "sufficient": True,
                "reason": "top evidence covers expected evidence shape",
                "evidence_shape": "process_activity",
                "shape_diagnostics": {
                    "shape_contract": {
                        "query_type": "lifecycle_lookup",
                        "allowed_shapes": ["process_activity"],
                        "required": True,
                        "matched": True,
                    },
                    "shape_contract_diagnosis": {"reason": "contract_matched", "action": "无需处理"},
                },
            },
        }

    monkeypatch.setattr("enterprise_agent_kb.corpus_eval.build_query_context", fake_build_query_context)

    result = run_corpus_retrieval_eval(paths.root, case_file=case_file, output_dir=tmp_path / "out")

    assert result.success is True
    assert result.passed == 1
    connection = connect(paths.db_file)
    try:
        eval_row = connection.execute("SELECT suite_id, status FROM eval_runs WHERE eval_run_id = ?", (result.eval_run_id,)).fetchone()
        result_row = connection.execute(
            "SELECT passed, failure_reason, metrics_json FROM eval_results WHERE eval_run_id = ? AND case_id = ?",
            (result.eval_run_id, "CORPUS-CASE-1"),
        ).fetchone()
        golden_row = connection.execute(
            "SELECT source, expected_evidence_shape FROM golden_cases WHERE case_id = ?",
            ("CORPUS-CASE-1",),
        ).fetchone()
    finally:
        connection.close()

    assert eval_row is not None
    assert eval_row["suite_id"] == "regression:corpus_retrieval"
    assert eval_row["status"] == "passed"
    assert result_row is not None
    assert result_row["passed"] == 1
    assert result_row["failure_reason"] is None
    stored_metrics = json.loads(result_row["metrics_json"])
    assert stored_metrics["evidence_shape"] == "process_activity"
    assert stored_metrics["contract"]["expected_evidence_shape"] == "process_activity"
    assert golden_row is not None
    assert golden_row["source"] == "corpus_eval"
    assert golden_row["expected_evidence_shape"] == "process_activity"


def test_corpus_eval_cli_commands_parse() -> None:
    parser = build_parser()

    generated = parser.parse_args(
        [
            "--root",
            "knowledge_base",
            "generate-corpus-eval-cases",
            "--doc-id",
            "DOC-000005",
            "--limit-per-type",
            "3",
            "--case-type",
            "process_activity",
        ]
    )
    evaluated = parser.parse_args(
        [
            "--root",
            "knowledge_base",
            "run-corpus-retrieval-eval",
            "--case-limit",
            "5",
            "--generation-limit-per-type",
            "2",
        ]
    )

    assert generated.command == "generate-corpus-eval-cases"
    assert generated.doc_id == ["DOC-000005"]
    assert generated.case_type == ["process_activity"]
    assert evaluated.command == "run-corpus-retrieval-eval"
    assert evaluated.case_limit == 5
    assert evaluated.generation_limit_per_type == 2


def _insert_document(db_file: Path, doc_id: str) -> None:
    connection = connect(db_file)
    try:
        connection.execute(
            """
            INSERT INTO documents (
                doc_id, source_filename, source_type, mime_type, sha256,
                file_size, page_count, language, version_label, source_path,
                ingest_time, update_time, parse_status, quality_status, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                "test.pdf",
                "pdf",
                "application/pdf",
                "sha",
                123,
                5,
                "zh",
                "",
                "raw/test.pdf",
                "2026-05-11T00:00:00+00:00",
                "2026-05-11T00:00:00+00:00",
                "parsed",
                "passed",
                1,
            ),
        )
        connection.commit()
    finally:
        connection.close()
