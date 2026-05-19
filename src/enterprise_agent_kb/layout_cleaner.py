from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .doc_ir import DocIRBlock, DocIRPage, DocumentIR


@dataclass(frozen=True)
class CleanedDocumentIR:
    doc_id: str
    parser_engine: str
    source_type: str
    page_count: int
    block_count: int
    pages: list[DocIRPage]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_doc_ir(doc_ir_path: Path) -> DocumentIR:
    payload = json.loads(doc_ir_path.read_text(encoding="utf-8"))
    pages: list[DocIRPage] = []
    for page in payload.get("pages", []):
        blocks = [DocIRBlock(**block) for block in page.get("blocks", [])]
        pages.append(
            DocIRPage(
                page_no=int(page["page_no"]),
                width=page.get("width"),
                height=page.get("height"),
                blocks=blocks,
            )
        )
    return DocumentIR(
        doc_id=str(payload["doc_id"]),
        parser_engine=str(payload["parser_engine"]),
        source_type=str(payload["source_type"]),
        page_count=int(payload["page_count"]),
        block_count=int(payload["block_count"]),
        pages=pages,
    )


def clean_doc_ir(doc_ir: DocumentIR) -> CleanedDocumentIR:
    cleaned_pages: list[DocIRPage] = []
    block_count = 0

    for page in doc_ir.pages:
        cleaned_blocks: list[DocIRBlock] = []
        for block in sorted(page.blocks, key=lambda item: item.reading_order):
            if not block.text:
                continue
            if block.type in {"table", "figure", "formula"}:
                cleaned_blocks.append(block)
                continue
            cleaned_blocks.extend(_split_markdown_block(block))
        reindexed_blocks: list[DocIRBlock] = []
        for index, block in enumerate(cleaned_blocks, start=1):
            reindexed_blocks.append(
                DocIRBlock(
                    id=f"{block.id}_c{index:03d}",
                    page_no=block.page_no,
                    type=block.type,
                    text=block.text,
                    bbox=block.bbox,
                    confidence=block.confidence,
                    source=block.source,
                    reading_order=index,
                    image_path=block.image_path,
                    html=block.html,
                    parent_id=block.parent_id,
                    needs_llm=block.needs_llm,
                    repair_status=block.repair_status,
                )
            )
        block_count += len(reindexed_blocks)
        cleaned_pages.append(
            DocIRPage(
                page_no=page.page_no,
                width=page.width,
                height=page.height,
                blocks=reindexed_blocks,
            )
        )

    return CleanedDocumentIR(
        doc_id=doc_ir.doc_id,
        parser_engine=doc_ir.parser_engine,
        source_type=doc_ir.source_type,
        page_count=len(cleaned_pages),
        block_count=block_count,
        pages=cleaned_pages,
    )


def save_cleaned_doc_ir(cleaned: CleanedDocumentIR, output_path: Path) -> Path:
    output_path.write_text(json.dumps(cleaned.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _split_markdown_block(block: DocIRBlock) -> list[DocIRBlock]:
    text = _normalize_text(block.text or "")
    if not text:
        return []

    segments = _segment_markdown(text)
    output: list[DocIRBlock] = []
    for index, segment in enumerate(segments, start=1):
        segment_text = segment.strip()
        if not segment_text:
            continue
        segment_type = _infer_segment_type(segment_text, block.type)
        output.append(
            DocIRBlock(
                id=f"{block.id}_s{index:03d}",
                page_no=block.page_no,
                type=segment_type,
                text=segment_text,
                bbox=block.bbox,
                confidence=block.confidence,
                source=block.source,
                reading_order=block.reading_order + index - 1,
                image_path=block.image_path,
                html=segment_text if segment_type == "table" and "<table" in segment_text.lower() else None,
                parent_id=block.parent_id,
                needs_llm=segment_type in {"table", "figure", "formula"} or "<table" in segment_text.lower(),
                repair_status=block.repair_status,
            )
        )
    return output


def _normalize_text(text: str) -> str:
    value = text.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _segment_markdown(text: str) -> list[str]:
    parts = re.split(r"\n(?=#{1,6}\s)", text)
    segments: list[str] = []
    for part in parts:
        if "<table" in part.lower():
            subparts = re.split(r"(?=<table)", part, flags=re.I)
            for subpart in subparts:
                if subpart.strip():
                    segments.extend(_split_non_table_segment(subpart))
        else:
            segments.extend(_split_non_table_segment(part))
    return [segment for segment in segments if segment.strip()]


def _split_non_table_segment(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.lower().startswith("<table"):
        return [stripped]
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", stripped) if item.strip()]
    return paragraphs or [stripped]


def _infer_segment_type(text: str, fallback_type: str) -> str:
    lowered = text.lower()
    if lowered.startswith("<table"):
        return "table"
    if text.startswith("#"):
        return "heading"
    if re.match(r"^(附录\s*[A-ZＡ-Ｚ]|\d+(?:\.\d+){0,5}\s+\S+)", text):
        return "heading"
    return "paragraph"
