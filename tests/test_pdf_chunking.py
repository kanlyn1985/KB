from __future__ import annotations

from pathlib import Path

import fitz

from enterprise_agent_kb.pdf_chunking import render_chunk_to_images, split_pdf_into_chunks


def test_split_pdf_into_chunks_and_render(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    try:
        for index in range(3):
            page = doc.new_page()
            page.insert_text((72, 72), f"Page {index + 1}")
        doc.save(pdf_path)
    finally:
        doc.close()

    chunk_dir = tmp_path / "chunks"
    image_dir = tmp_path / "images"
    chunks = split_pdf_into_chunks(pdf_path, chunk_dir, chunk_size=2)

    assert len(chunks) == 2
    assert chunks[0].start_page == 1
    assert chunks[0].end_page == 2
    assert chunks[1].start_page == 3
    assert chunks[1].end_page == 3

    images = render_chunk_to_images(chunks[0], image_dir, scale=1.2)
    assert len(images) == 2
    assert images[0].page_no == 1
    assert images[0].image_path.exists()
    assert images[0].data_url.startswith("data:image/png;base64,")

