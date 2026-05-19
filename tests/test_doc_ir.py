from __future__ import annotations

import json
from pathlib import Path

import fitz

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.doc_ir import build_doc_ir
from enterprise_agent_kb.ingest import register_document
from enterprise_agent_kb.parse import PdfTextProfile, _backfill_empty_pdf_pages_from_text, _parse_pdf, _split_plain_pdf_text_block
from enterprise_agent_kb.parse import parse_document


def test_build_doc_ir_maps_markdown_blocks() -> None:
    parsed_pages = [
        {
            "page_no": 1,
            "width": 100.0,
            "height": 200.0,
            "parser_confidence": 0.9,
            "ocr_confidence": 0.8,
            "blocks": [
                {"reading_order": 1, "block_type": "ocr_markdown", "text": "## 1 范围", "bbox": None},
                {"reading_order": 2, "block_type": "ocr_markdown", "text": "<table><tr><td>A</td></tr></table>", "bbox": None},
            ],
        }
    ]

    doc_ir = build_doc_ir(
        doc_id="DOC-TEST",
        parser_engine="paddlevl",
        source_type="pdf",
        parsed_pages=parsed_pages,
    )

    assert doc_ir.page_count == 1
    assert doc_ir.block_count == 2
    assert doc_ir.pages[0].blocks[0].type == "heading"
    assert doc_ir.pages[0].blocks[1].type == "table"
    assert doc_ir.pages[0].blocks[1].needs_llm is True


def test_parse_document_writes_doc_ir(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "knowledge_base", Path("src/enterprise_agent_kb/schema.sql"))
    source_file = tmp_path / "sample.md"
    source_file.write_text("# 1 范围\n\n本文件规定了测试要求。", encoding="utf-8")
    registered = register_document(paths.root, source_file)

    result = parse_document(paths.root, registered.doc_id)
    doc_ir_path = paths.normalized / f"{registered.doc_id}.doc_ir.json"
    normalized_path = paths.normalized / f"{registered.doc_id}.json"
    assert doc_ir_path.exists()
    payload = json.loads(doc_ir_path.read_text(encoding="utf-8"))
    normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
    assert payload["doc_id"] == registered.doc_id
    assert payload["page_count"] >= 1
    assert payload["block_count"] >= 1
    assert normalized["pages"][0]["page_status"] == "parsed"
    assert result.doc_id == registered.doc_id


def test_pdf_text_fallback_backfills_empty_parser_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Annex D Reference standards\nISO/IEC 33001:2015")
    document.new_page()
    document.save(pdf_path)
    document.close()
    parsed_pages = [
        {
            "page_no": 1,
            "width": 100.0,
            "height": 100.0,
            "parser_confidence": 0.1,
            "ocr_confidence": 0.1,
            "risk_level": "unknown",
            "page_status": "parsed",
            "blocks": [],
        },
        {
            "page_no": 2,
            "width": 100.0,
            "height": 100.0,
            "parser_confidence": 0.1,
            "ocr_confidence": 0.1,
            "risk_level": "unknown",
            "page_status": "parsed",
            "blocks": [],
        },
    ]

    backfilled, stats = _backfill_empty_pdf_pages_from_text(pdf_path, parsed_pages)

    assert stats == {"text_backfilled_pages": 1, "blank_pages": 1}
    assert backfilled[0]["blocks"][0]["block_type"] == "pdf_text_fallback"
    assert "ISO/IEC 33001" in backfilled[0]["blocks"][0]["text"]
    assert backfilled[1]["page_status"] == "blank"
    assert backfilled[1]["risk_level"] == "low"


def test_parse_pdf_uses_fast_text_path_for_digital_pdf(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "digital.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    calls: list[str] = []

    monkeypatch.setattr(
        "enterprise_agent_kb.parse._profile_pdf_text_layer",
        lambda _path: PdfTextProfile(
            page_count=2,
            text_page_count=2,
            average_chars=300.0,
            coverage_rate=1.0,
            digital_text_sufficient=True,
        ),
    )

    def fake_pymupdf(_path: Path):
        calls.append("pymupdf")
        return "pymupdf", [
            {
                "page_no": 1,
                "width": 100.0,
                "height": 100.0,
                "parser_confidence": 1.0,
                "ocr_confidence": None,
                "risk_level": "unknown",
                "page_status": "parsed",
                "blocks": [
                    {
                        "reading_order": 1,
                        "block_type": "text",
                        "text": "digital text",
                        "raw_text": "digital text",
                        "bbox": None,
                    }
                ],
            }
        ]

    def fail_slow_path(_path: Path):
        raise AssertionError("slow VLM/OCR path should not be called for digital PDFs")

    monkeypatch.setattr("enterprise_agent_kb.parse._parse_pdf_with_pymupdf", fake_pymupdf)
    monkeypatch.setattr("enterprise_agent_kb.parse._parse_pdf_with_minimax_and_paddlevl", fail_slow_path)

    engine, pages = _parse_pdf(pdf_path)

    assert engine == "pymupdf_fast_text"
    assert calls == ["pymupdf"]
    assert pages[0]["blocks"][0]["text"] == "digital text"


def test_parse_pdf_uses_slow_path_when_text_layer_is_weak(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "scanned.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        "enterprise_agent_kb.parse._profile_pdf_text_layer",
        lambda _path: PdfTextProfile(
            page_count=2,
            text_page_count=0,
            average_chars=0.0,
            coverage_rate=0.0,
            digital_text_sufficient=False,
        ),
    )
    monkeypatch.setattr(
        "enterprise_agent_kb.parse._parse_pdf_with_minimax_and_paddlevl",
        lambda _path: ("minimax_primary+astron_backup", []),
    )

    engine, pages = _parse_pdf(pdf_path)

    assert engine == "minimax_primary+astron_backup"
    assert pages == []


def test_plain_pdf_text_block_is_split_into_headings_and_steps() -> None:
    blocks = _split_plain_pdf_text_block(
        "５．４．１　交流输入过、欠压保护试验\n"
        "试验方法及步骤：\n"
        "ａ）　按照图１接好试验电路，电子负载设置为恒压负载模式；\n"
        "ｃ）　逐步调节交流输入电压至过压保护值或欠压保护值，观察车载充电机的输出状态；",
        raw_text="raw",
        bbox=[0, 0, 10, 10],
        start_order=1,
    )

    assert blocks[0]["block_type"] == "ocr_markdown"
    assert blocks[0]["text"] == "### 5.4.1 交流输入过、欠压保护试验"
    assert any(str(block["text"]).startswith("a)") for block in blocks)
    assert any("逐步调节交流输入电压至过压保护值" in str(block["text"]) for block in blocks)
