from __future__ import annotations

import argparse
from pathlib import Path

from enterprise_agent_kb.parse import (
    _call_minimax_vlm,
    _load_minimax_settings,
    _minimax_ocr_prompt,
    _page_image_batches,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pre-cache MiniMax OCR results for PDF page images with progress output.",
    )
    parser.add_argument("--pdf", type=Path, required=True, help="Path to source PDF.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process the first N pages. 0 means all pages.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    pdf_path = args.pdf.resolve()

    cache_dir, batches = _page_image_batches(pdf_path)
    api_host, api_key = _load_minimax_settings()
    ocr_cache_dir = cache_dir / "ocr_text"
    ocr_cache_dir.mkdir(parents=True, exist_ok=True)

    all_pages = [(page_no, image_url) for batch in batches for page_no, image_url in batch]
    if args.limit > 0:
        all_pages = all_pages[: args.limit]

    total = len(all_pages)
    completed = 0
    for page_no, image_url in all_pages:
        cache_path = ocr_cache_dir / f"page_{page_no:03d}.md"
        if cache_path.exists():
            completed += 1
            print(f"[{completed}/{total}] cached page {page_no}")
            continue

        text = _call_minimax_vlm(api_host, api_key, _minimax_ocr_prompt(page_no, total), image_url)
        cache_path.write_text(text, encoding="utf-8")
        completed += 1
        print(f"[{completed}/{total}] generated page {page_no} chars={len(text)}")

    print(cache_dir)


if __name__ == "__main__":
    main()
