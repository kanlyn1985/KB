from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from enterprise_agent_kb.layout_cleaner import clean_doc_ir, load_doc_ir
from enterprise_agent_kb.parse import parse_document
from test_helpers import resolve_doc_id_by_filename


def _source_path_resolves(doc_id: str) -> bool:
    """Skip guard: the recorded source_path must be readable on this OS.

    Knowledge bases built on Windows have Windows-style paths stored in
    the documents table; on Linux those paths don't resolve. The test
    is environment-dependent, so skip when the source file can't be
    opened rather than fail.
    """
    db_path = Path("knowledge_base/db/knowledge.db")
    if not db_path.exists():
        return False
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT source_path FROM documents WHERE doc_id = ?", (doc_id,),
            ).fetchone()
    except sqlite3.Error:
        return False
    if not row or not row[0]:
        return False
    return Path(str(row[0])).exists()


def test_clean_doc_ir_splits_large_markdown_blocks() -> None:
    doc_id = resolve_doc_id_by_filename("QC_T 1036", "逆变器")
    doc_ir = load_doc_ir(Path(f"knowledge_base/normalized/{doc_id}.doc_ir.json"))
    cleaned = clean_doc_ir(doc_ir)

    assert cleaned.block_count >= doc_ir.block_count
    mid_page = max(2, min(8, cleaned.page_count // 2))
    page8 = next(page for page in cleaned.pages if page.page_no == mid_page)
    assert len(page8.blocks) >= 2
    assert any(block.type == "heading" for block in page8.blocks)
    assert any(block.type in {"paragraph", "table"} for block in page8.blocks)


def test_parse_document_writes_cleaned_doc_ir() -> None:
    doc_id = resolve_doc_id_by_filename("QC_T 1036", "逆变器")
    if not _source_path_resolves(doc_id):
        pytest.skip(f"recorded source_path for {doc_id} is not accessible on this OS")
    parse_document(Path("knowledge_base"), doc_id)
    path = Path(f"knowledge_base/normalized/{doc_id}.cleaned_doc_ir.json")
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["doc_id"] == doc_id
    assert payload["block_count"] >= 24
