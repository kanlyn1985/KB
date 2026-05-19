from __future__ import annotations

import argparse
import json
from pathlib import Path

from enterprise_agent_kb.pdf_chunking import (
    preprocess_cache_dir,
    render_chunk_to_images,
    save_manifest,
    split_pdf_into_chunks,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Split a large PDF into chunks and render chunk pages to PNG for MiniMax preprocessing.",
    )
    parser.add_argument("--pdf", type=Path, required=True, help="Path to the source PDF.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to write chunk PDFs, PNGs, and manifest. Defaults to tmp/minimax_preprocessed/<pdf-stem>.",
    )
    parser.add_argument("--chunk-size", type=int, default=25, help="Pages per chunk PDF.")
    parser.add_argument("--scale", type=float, default=1.8, help="Render scale for PNG images.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    pdf_path = args.pdf.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else preprocess_cache_dir(Path.cwd(), pdf_path)
    chunk_dir = output_dir / "chunks"
    image_dir = output_dir / "images"

    chunks = split_pdf_into_chunks(pdf_path, chunk_dir, chunk_size=args.chunk_size)
    manifest: list[dict[str, object]] = []
    for chunk in chunks:
        images = render_chunk_to_images(chunk, image_dir, scale=args.scale)
        manifest.append(
            {
                "start_page": chunk.start_page,
                "end_page": chunk.end_page,
                "chunk_pdf": str(chunk.pdf_path),
                "images": [
                    {"page_no": image.page_no, "image_path": str(image.image_path)}
                    for image in images
                ],
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = save_manifest(
        output_dir / "manifest.json",
        {
            "pdf": str(pdf_path),
            "chunk_size": args.chunk_size,
            "scale": args.scale,
            "chunk_count": len(chunks),
            "chunks": manifest,
        },
    )
    print(manifest_path)


if __name__ == "__main__":
    main()
