from __future__ import annotations

from .layout_cleaner import CleanedDocumentIR


def restore_reading_order(cleaned: CleanedDocumentIR) -> CleanedDocumentIR:
    # 当前第一版直接按 page_no + reading_order 排序。
    # 先把“单页整块 markdown 拆分后的顺序”稳定下来，后续再扩展双栏/复杂版式规则。
    pages = []
    for page in cleaned.pages:
        blocks = sorted(page.blocks, key=lambda item: (item.page_no, item.reading_order, item.id))
        pages.append(type(page)(page_no=page.page_no, width=page.width, height=page.height, blocks=blocks))
    return CleanedDocumentIR(
        doc_id=cleaned.doc_id,
        parser_engine=cleaned.parser_engine,
        source_type=cleaned.source_type,
        page_count=cleaned.page_count,
        block_count=cleaned.block_count,
        pages=pages,
    )
