from __future__ import annotations

from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.db import connect
from enterprise_agent_kb.parse_views import (
    ParseViewCandidate,
    list_parse_view_pages,
    prepare_parse_view_selection,
    score_parse_view,
    select_best_views,
    sync_parse_views_for_pages,
)


SCHEMA_PATH = Path("src/enterprise_agent_kb/schema.sql")


def test_score_parse_view_prefers_structured_readable_candidate() -> None:
    weak = score_parse_view(text="@@@ ... 1 2 3", block_count=1, view_type="native_text")
    structured = score_parse_view(
        text="# 1 Scope\n\n<table><tr><td>Requirement</td></tr></table>\n\n1. item",
        block_count=3,
        view_type="html",
    )

    assert structured["score"] > weak["score"]
    assert structured["heading_count"] == 1
    assert structured["table_signal_count"] >= 1
    assert "structure_quality_score" in structured
    assert "table_density" in structured


def test_score_parse_view_rewards_table_and_clause_structure() -> None:
    flat = score_parse_view(
        text="Requirement voltage current state " * 40,
        block_count=1,
        view_type="native_text",
    )
    structured = score_parse_view(
        text=(
            "5 Test method\n"
            "5.1 Input protection\n"
            "5.2 Output protection\n"
            "| Item | Voltage | Current |\n"
            "| A | 220 V | 10 A |\n"
            "| B | 230 V | 16 A |\n"
            "Table 1 continued\n"
        ),
        block_count=1,
        view_type="html",
    )

    assert structured["structure_quality_score"] > flat["structure_quality_score"]
    assert structured["row_column_signal_count"] >= 3
    assert structured["clause_number_count"] >= 2
    assert structured["continuation_signal_count"] >= 1
    assert structured["score"] > flat["score"]


def test_score_parse_view_flags_noise_and_weak_table_structure() -> None:
    noisy = score_parse_view(
        text="\n".join(["Page 1", "Page 1", "DOI: 10.12677/sg.2024.142002", "A | B | C"]),
        block_count=1,
        view_type="native_text",
    )

    assert "header_footer_noise" in noisy["risk_flags"]
    assert noisy["duplicate_line_ratio"] > 0
    assert 0 <= noisy["structure_quality_score"] <= 1


def test_score_parse_view_does_not_promote_mojibake_structure_noise() -> None:
    mojibake = (
        "' / % / !\" ! &‹op ! (&16&*)$2.7&'&/)0* < \x9d;\u201eÓ st @¸- % G 9\n"
        "* ' / % / !* ! klFs ! 7'0/.$/)6..&'/%)*( < V¼3é D Q , 45 % P\n"
        "* ' / % / %& ! Œ\x8d&RklŽ ! '.2)-5\n"
    ) * 8
    readable = (
        "3.1 控制导引功能 control pilot function; CP\n"
        "通过电子或者机械的方式，反映车辆插头连接到车辆和供电设备上的状态的功能。\n"
        "5.1 输入过压保护试验\n"
        "a) 按照图 1 接好试验电路，逐步调节交流输入电压至过压保护值。"
    )

    noisy = score_parse_view(text=mojibake, block_count=1, view_type="html")
    clean = score_parse_view(text=readable, block_count=1, view_type="native_text")

    assert "symbol_noise" in noisy["risk_flags"]
    assert "low_readability" in noisy["risk_flags"]
    assert noisy["score"] < clean["score"]
    assert noisy["structure_quality_score"] < 0.35


def test_select_best_views_is_rule_based_and_explainable() -> None:
    candidates = [
        ParseViewCandidate(
            doc_id="DOC-X",
            page_no=1,
            view_type="native_text",
            parser_name="pymupdf",
            parser_version=None,
            text="short",
            structure={},
            quality={"score": 0.2},
        ),
        ParseViewCandidate(
            doc_id="DOC-X",
            page_no=1,
            view_type="html",
            parser_name="html-provider",
            parser_version=None,
            text="# Heading\n\nbody",
            structure={},
            quality={"score": 0.8},
        ),
    ]

    selections = select_best_views(candidates)

    assert selections[1].selected_view_id == "PV-DOC-X-0001-html"
    assert "highest_score:0.800" in selections[1].selected_reason
    assert "structure:" in selections[1].selected_reason
    assert selections[1].fallback_chain[0].startswith("html:candidate")


def test_sync_parse_views_for_pages_persists_candidates_and_selection(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    connection = connect(paths.db_file)
    try:
        summary = sync_parse_views_for_pages(
            connection,
            doc_id="DOC-X",
            parser_engine="pymupdf",
            parsed_pages=[
                {
                    "page_no": 1,
                    "page_status": "parsed",
                    "risk_level": "unknown",
                    "blocks": [
                        {"block_type": "text", "text": "1 Scope\n\nThis standard defines requirements."},
                    ],
                },
                {
                    "page_no": 2,
                    "page_status": "parsed",
                    "risk_level": "unknown",
                    "blocks": [],
                },
            ],
            generated_at="2026-05-17T00:00:00+00:00",
        )
        connection.commit()

        assert summary["view_count"] == 2
        assert summary["selection_count"] == 2
        assert summary["selected_by_type"]["native_text"] == 2
        rows = connection.execute("SELECT status FROM parse_views WHERE doc_id = 'DOC-X' ORDER BY page_no").fetchall()
        assert [row["status"] for row in rows] == ["selected", "selected"]
        selection = connection.execute(
            "SELECT selected_reason FROM page_parse_selection WHERE doc_id = 'DOC-X' AND page_no = 1"
        ).fetchone()
        assert "highest_score" in selection["selected_reason"]

        detail = list_parse_view_pages(connection, "DOC-X", text_limit=20)
        assert detail["summary"]["selection_count"] == 2
        assert detail["pages"][0]["selected_view_id"] == "PV-DOC-X-0001-native_text"
        assert detail["pages"][0]["candidates"][0]["selected"] is True
        assert len(detail["pages"][0]["candidates"][0]["text_preview"]) <= 20
    finally:
        connection.close()


def test_prepare_parse_view_selection_materializes_selected_html_page() -> None:
    candidates, selections, selected_pages = prepare_parse_view_selection(
        doc_id="DOC-X",
        primary_parser_engine="pymupdf",
        primary_pages=[
            {
                "page_no": 1,
                "width": 100,
                "height": 100,
                "parser_confidence": 1.0,
                "ocr_confidence": None,
                "risk_level": "unknown",
                "page_status": "parsed",
                "blocks": [{"block_type": "text", "reading_order": 1, "text": "###", "raw_text": "###", "bbox": None}],
            }
        ],
        extra_views=[
            (
                "pymupdf_html",
                [
                    {
                        "page_no": 1,
                        "width": 100,
                        "height": 100,
                        "parser_confidence": 0.72,
                        "ocr_confidence": None,
                        "risk_level": "unknown",
                        "page_status": "parsed",
                        "blocks": [
                            {
                                "block_type": "html",
                                "reading_order": 1,
                                "text": "# Heading\n\n1. structured item",
                                "raw_text": "<h1>Heading</h1>",
                                "bbox": None,
                            }
                        ],
                    }
                ],
            )
        ],
    )

    assert len(candidates) == 2
    assert selections[1].selected_view_id == "PV-DOC-X-0001-html"
    assert selected_pages[0]["blocks"][0]["block_type"] == "html"
    assert selected_pages[0]["selected_parse_view"]["view_type"] == "html"
