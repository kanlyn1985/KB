from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.doc_diagnostics import build_document_diagnostics, _build_parse_quality_profile
from test_helpers import resolve_doc_id_by_filename


WORKSPACE = Path("knowledge_base")


def test_doc7_diagnostics_exposes_core_metrics() -> None:
    doc_id = resolve_doc_id_by_filename("QC_T 1036", "逆变器")
    diagnostics = build_document_diagnostics(WORKSPACE, doc_id)

    assert diagnostics["doc_id"] == doc_id
    assert diagnostics["counts"]["page_count"] >= 20
    assert diagnostics["counts"]["evidence_count"] >= 10
    assert diagnostics["counts"]["fact_count"] >= 50
    assert diagnostics["coverage"]["answerability_score"] > 0
    assert "metadata_coverage" in diagnostics["coverage"]
    assert "text_coverage_rate" in diagnostics["coverage"]
    assert "uncovered_counts" in diagnostics["coverage"]
    assert diagnostics["artifacts"]["coverage_summary_path"].endswith(".summary.json")
    assert diagnostics["artifacts"]["coverage_report_path"].endswith(".coverage_report.md")
    assert "warnings" in diagnostics
    assert "parse_quality" in diagnostics
    assert "parse_views" in diagnostics


def test_parse_quality_profile_separates_review_only_from_actionable_gaps() -> None:
    profile = _build_parse_quality_profile(
        page_rows=[
            {"page_no": 1, "risk_level": "high", "page_status": "review_required"},
            {"page_no": 2, "risk_level": "high", "page_status": "review_required"},
            {"page_no": 3, "risk_level": "high", "page_status": "review_required"},
        ],
        evidence_rows=[
            {"page_no": 2},
            {"page_no": 3},
        ],
        fact_rows=[
            {"qualifiers_json": '{"page_no": 3}'},
        ],
        source_unit_rows=[
            {"unit_id": "UNIT-3", "page_no": 3, "status": "covered"},
        ],
        source_unit_fact_rows=[
            {"unit_id": "UNIT-3", "linked_fact_count": 1},
        ],
        quality_payload={
            "pages": [
                {"page_no": 1, "risk_flags": ["low_readability"], "readability_score": 0.2},
                {"page_no": 2, "risk_flags": ["low_readability"], "readability_score": 0.3},
                {"page_no": 3, "risk_flags": ["low_readability"], "readability_score": 0.31},
            ]
        },
        parse_view_pages=[
            {
                "page_no": 1,
                "candidates": [
                    {"selected": True, "view_id": "PV-1", "quality": {"score": 0.2, "total_chars": 20, "risk_flags": ["low_text_density"]}},
                    {"selected": False, "view_id": "PV-2", "quality": {"score": 0.25, "total_chars": 30, "risk_flags": ["low_text_density"]}},
                ],
            },
            {
                "page_no": 2,
                "candidates": [
                    {"selected": True, "view_id": "PV-3", "quality": {"score": 0.7, "total_chars": 300, "risk_flags": []}},
                ],
            },
            {
                "page_no": 3,
                "candidates": [
                    {"selected": True, "view_id": "PV-4", "quality": {"score": 0.7, "total_chars": 300, "risk_flags": []}},
                ],
            },
        ],
        coverage_summary={"test_coverage_rate": 0.1, "uncovered_counts": {"u3_not_tested": 1}},
    )

    assert profile["high_risk_page_count"] == 3
    assert profile["actionable_parse_risk_pages"] == 1
    assert profile["chain_gap_pages"] == 0
    assert profile["review_only_pages"] == 2
    assert profile["root_cause_counts"] == {
        "no_evidence": 1,
        "evidence_without_source_unit": 1,
        "source_unit_without_fact": 0,
        "fully_backed": 1,
    }
    assert profile["attribution_counts"]["provider_quality_issue"] == 1
    assert profile["attribution_counts"]["extraction_chain_issue"] == 1
    assert profile["attribution_counts"]["test_coverage_gap"] == 1
    assert profile["pages"][0]["attribution"] == "provider_quality_issue"
    assert profile["pages"][2]["attribution"] == "test_coverage_gap"


def test_parse_quality_profile_does_not_treat_ocr_derived_as_high_risk() -> None:
    profile = _build_parse_quality_profile(
        page_rows=[
            {"page_no": 1, "risk_level": "medium", "page_status": "ready"},
            {"page_no": 2, "risk_level": "high", "page_status": "review_required"},
        ],
        evidence_rows=[
            {"page_no": 1},
            {"page_no": 2},
        ],
        fact_rows=[],
        source_unit_rows=[],
        source_unit_fact_rows=[],
        quality_payload={
            "pages": [
                {"page_no": 1, "risk_flags": ["ocr_derived"], "readability_score": 0.9},
                {"page_no": 2, "risk_flags": ["ocr_derived", "low_readability"], "readability_score": 0.1},
            ]
        },
        parse_view_pages=[],
        coverage_summary={},
    )

    assert profile["high_risk_page_count"] == 1
    assert [page["page_no"] for page in profile["pages"]] == [2]


def test_parse_quality_profile_detects_selection_rule_issue() -> None:
    profile = _build_parse_quality_profile(
        page_rows=[
            {"page_no": 1, "risk_level": "high", "page_status": "review_required"},
        ],
        evidence_rows=[{"page_no": 1}],
        fact_rows=[],
        source_unit_rows=[],
        source_unit_fact_rows=[],
        quality_payload={"pages": [{"page_no": 1, "risk_flags": ["symbol_noise"], "readability_score": 0.2}]},
        parse_view_pages=[
            {
                "page_no": 1,
                "candidates": [
                    {"selected": True, "view_id": "PV-low", "quality": {"score": 0.3, "total_chars": 200, "risk_flags": ["symbol_noise"]}},
                    {"selected": False, "view_id": "PV-high", "quality": {"score": 0.75, "total_chars": 400, "risk_flags": []}},
                ],
            }
        ],
        coverage_summary={},
    )

    assert profile["attribution_counts"]["selection_rule_issue"] == 1
    assert profile["pages"][0]["recommended_action"].startswith("存在分数更高")


def test_parse_quality_profile_treats_contents_pages_as_structural_navigation_noise() -> None:
    profile = _build_parse_quality_profile(
        page_rows=[
            {"page_no": 7, "page_status": "review_required", "risk_level": "high"},
        ],
        evidence_rows=[{"page_no": 7}],
        fact_rows=[],
        source_unit_rows=[],
        source_unit_fact_rows=[],
        quality_payload={"pages": [{"page_no": 7, "risk_flags": ["symbol_noise"], "readability_score": 0.1}]},
        parse_view_pages=[
            {
                "page_no": 7,
                "candidates": [
                    {
                        "selected": True,
                        "view_id": "PV-1",
                        "quality": {"score": 0.1, "total_chars": 5000, "risk_flags": ["symbol_noise"]},
                        "text_preview": (
                            "CONTENTS FOREWORD ................................ 9 INTRODUCTION ........................ 11 "
                            "Annex D ................................ 93 Figure D.9 ........................ 130 Table D.19 ............. 127"
                        ),
                    }
                ],
            }
        ],
        coverage_summary={},
    )

    assert profile["attribution_counts"]["structural_navigation_noise"] == 1
    assert profile["pages"][0]["attribution"] == "structural_navigation_noise"


def test_parse_quality_profile_treats_continued_contents_pages_as_navigation_noise() -> None:
    profile = _build_parse_quality_profile(
        page_rows=[
            {"page_no": 8, "page_status": "review_required", "risk_level": "high"},
        ],
        evidence_rows=[{"page_no": 8}],
        fact_rows=[],
        source_unit_rows=[],
        source_unit_fact_rows=[],
        quality_payload={"pages": [{"page_no": 8, "risk_flags": ["symbol_noise"], "readability_score": 0.1}]},
        parse_view_pages=[
            {
                "page_no": 8,
                "candidates": [
                    {
                        "selected": True,
                        "view_id": "PV-1",
                        "quality": {"score": 0.1, "total_chars": 5000, "risk_flags": ["symbol_noise"]},
                        "text_preview": (
                            "D.1.1 General ......................................... 93 "
                            "D.1.2 LIN-CP features ................................ 93 "
                            "Figure D.9 Control pilot circuit ..................... 130 "
                            "Table D.19 Signals for EV status information ......... 127"
                        ),
                    }
                ],
            }
        ],
        coverage_summary={},
    )

    assert profile["pages"][0]["attribution"] == "structural_navigation_noise"
