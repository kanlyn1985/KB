from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass(frozen=True)
class PdfChunk:
    start_page: int
    end_page: int
    pdf_path: Path


@dataclass(frozen=True)
class PageImage:
    page_no: int
    image_path: Path
    data_url: str


def preprocess_cache_dir(root_dir: Path, source_path: Path) -> Path:
    stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", source_path.stem).strip("_")
    return root_dir / "tmp" / "minimax_preprocessed" / stem


def split_pdf_into_chunks(source_path: Path, output_dir: Path, *, chunk_size: int = 25) -> list[PdfChunk]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source = fitz.open(source_path)
    chunks: list[PdfChunk] = []
    try:
        total_pages = len(source)
        if total_pages == 0:
            return []
        for start_page in range(1, total_pages + 1, chunk_size):
            end_page = min(start_page + chunk_size - 1, total_pages)
            chunk_name = f"{source_path.stem}_p{start_page:03d}-{end_page:03d}.pdf"
            chunk_path = output_dir / chunk_name
            chunk_doc = fitz.open()
            try:
                chunk_doc.insert_pdf(source, from_page=start_page - 1, to_page=end_page - 1)
                chunk_doc.save(chunk_path)
            finally:
                chunk_doc.close()
            chunks.append(PdfChunk(start_page=start_page, end_page=end_page, pdf_path=chunk_path))
        return chunks
    finally:
        source.close()


def render_chunk_to_images(
    chunk: PdfChunk,
    output_dir: Path,
    *,
    scale: float = 1.8,
) -> list[PageImage]:
    output_dir.mkdir(parents=True, exist_ok=True)
    chunk_doc = fitz.open(chunk.pdf_path)
    try:
        images: list[PageImage] = []
        for index, page in enumerate(chunk_doc):
            page_no = chunk.start_page + index
            image_path = output_dir / f"{chunk.pdf_path.stem}_page_{page_no:03d}.png"
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            pix.save(image_path)
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
            images.append(
                PageImage(
                    page_no=page_no,
                    image_path=image_path,
                    data_url=f"data:image/png;base64,{encoded}",
                )
            )
        return images
    finally:
        chunk_doc.close()


def load_manifest(manifest_path: Path) -> dict[str, object]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def save_manifest(manifest_path: Path, payload: dict[str, object]) -> Path:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path
