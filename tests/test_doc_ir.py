from __future__ import annotations

import json
from pathlib import Path

import fitz

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.doc_ir import build_doc_ir
from enterprise_agent_kb.ingest import register_document
from enterprise_agent_kb.parse import _backfill_empty_pdf_pages_from_text
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
