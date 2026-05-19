from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocIRBlock:
    id: str
    page_no: int
    type: str
    text: str | None
    bbox: list[float] | None
    confidence: float | None
    source: str
    reading_order: int
    image_path: str | None = None
    html: str | None = None
    parent_id: str | None = None
    needs_llm: bool = False
    repair_status: str = "not_needed"


@dataclass(frozen=True)
class DocIRPage:
    page_no: int
    width: float | None
    height: float | None
    blocks: list[DocIRBlock]


@dataclass(frozen=True)
class DocumentIR:
    doc_id: str
    parser_engine: str
    source_type: str
    page_count: int
    block_count: int
    pages: list[DocIRPage]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_doc_ir(
    *,
    doc_id: str,
    parser_engine: str,
    source_type: str,
    parsed_pages: list[dict[str, object]],
) -> DocumentIR:
    pages: list[DocIRPage] = []
    total_blocks = 0

    for page in parsed_pages:
        page_no = int(page["page_no"])
        page_blocks: list[DocIRBlock] = []
        for index, block in enumerate(page.get("blocks", []), start=1):
            block_id = f"docir_p{page_no:03d}_b{index:04d}"
            block_type = _normalize_block_type(str(block.get("block_type", "text")), str(block.get("text", "")))
            confidence = page.get("ocr_confidence")
            if confidence is None:
                confidence = page.get("parser_confidence")
            page_blocks.append(
                DocIRBlock(
                    id=block_id,
                    page_no=page_no,
                    type=block_type,
                    text=str(block.get("text", "")).strip() or None,
                    bbox=_float_bbox(block.get("bbox")),
                    confidence=float(confidence) if confidence is not None else None,
                    source=parser_engine,
                    reading_order=int(block.get("reading_order", index)),
                    needs_llm=_needs_llm(block_type, str(block.get("text", ""))),
                )
            )
        total_blocks += len(page_blocks)
        pages.append(
            DocIRPage(
                page_no=page_no,
                width=float(page["width"]) if page.get("width") is not None else None,
                height=float(page["height"]) if page.get("height") is not None else None,
                blocks=page_blocks,
            )
        )

    return DocumentIR(
        doc_id=doc_id,
        parser_engine=parser_engine,
        source_type=source_type,
        page_count=len(pages),
        block_count=total_blocks,
        pages=pages,
    )


def save_doc_ir(doc_ir: DocumentIR, output_path: Path) -> Path:
    output_path.write_text(json.dumps(doc_ir.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _normalize_block_type(block_type: str, text: str) -> str:
    lowered = block_type.lower().strip()
    if lowered in {"table", "table_html"}:
        return "table"
    if lowered in {"image", "figure"}:
        return "figure"
    if lowered in {"formula", "equation"}:
        return "formula"
    if lowered == "ocr_markdown":
        if text.lstrip().startswith("#"):
            return "heading"
        if "<table" in text.lower():
            return "table"
        return "paragraph"
    if lowered == "structure_markdown":
        if text.lstrip().startswith("#"):
            return "heading"
        if "<table" in text.lower() or "|" in text:
            return "table"
        return "paragraph"
    if lowered == "text":
        stripped = text.strip()
        if stripped.startswith("#") or stripped.startswith("##"):
            return "heading"
        return "paragraph"
    return "paragraph"


def _needs_llm(block_type: str, text: str) -> bool:
    lowered = text.lower()
    if block_type in {"table", "figure", "formula"}:
        return True
    if "<table" in lowered or "<img" in lowered:
        return True
    return False


def _float_bbox(value) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, list):
        try:
            return [float(item) for item in value]
        except Exception:
            return None
    return None
