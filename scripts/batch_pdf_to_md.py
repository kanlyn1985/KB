#!/usr/bin/env python3
"""Batch convert all unique PDFs in knowledge_base/raw/ to clean KB-ready markdown.

For each unique PDF (deduplicated by content MD5):
  1. Submit to remote PaddleOCR-VL service
  2. Wait for completion, download per-page markdown
  3. Run vl_md_to_kb_md.py post-processing (table repair, symbol normalization,
     content filtering)
  4. Output one MD file per PDF: output/kb_md/<short_name>.md

Usage:
  .venv-paddle/bin/python scripts/batch_pdf_to_md.py
  .venv-paddle/bin/python scripts/batch_pdf_to_md.py --only "QC_T 1036,V2G"
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
import time
from pathlib import Path

# Clear proxy env vars before any network imports
for v in ("all_proxy", "ALL_PROXY", "https_proxy", "HTTPS_PROXY",
          "http_proxy", "HTTP_PROXY"):
    os.environ.pop(v, None)

VENV_SITE = Path("/home/evt/projects/KB1/.venv-paddle/lib/python3.12/site-packages")
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.insert(0, str(VENV_SITE))

# Import VL submission functions from ocr_layout_to_html.py
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from ocr_layout_to_html import (  # noqa: E402
    submit_vl_task,
    wait_vl_done,
    fetch_vl_paged_mds,
)

# Import post-processor
from vl_md_to_kb_md import process_page  # noqa: E402

RAW_DIR = Path("/home/evt/projects/KB1/knowledge_base/raw")
OUTPUT_DIR = Path("/home/evt/projects/KB1/output/kb_md")
WORK_BASE = Path("/tmp/vl_batch")


def _short_name(filename: str) -> str:
    """Derive a filesystem-safe short name from a PDF filename."""
    # Strip DOC-XXXXX_ prefix(es)
    name = re.sub(r"^(DOC-\d+_)+", "", filename)
    # Strip .pdf
    name = re.sub(r"\.pdf$", "", name, flags=re.I)
    # Replace filesystem-unsafe chars
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    # Collapse whitespace
    name = re.sub(r"\s+", "_", name)
    # Truncate to reasonable length
    if len(name) > 80:
        name = name[:80]
    return name


def list_unique_pdfs() -> list[tuple[str, Path, str]]:
    """Return [(md5_prefix, pdf_path, short_name), ...] deduplicated by content."""
    seen: dict[str, tuple[str, Path, str]] = {}
    for f in sorted(os.listdir(RAW_DIR)):
        if not f.lower().endswith(".pdf"):
            continue
        path = RAW_DIR / f
        h = hashlib.md5(path.read_bytes()).hexdigest()
        if h in seen:
            continue
        seen[h] = (h[:8], path, _short_name(f))
    return list(seen.values())


def convert_one(pdf_path: Path, short_name: str, work_dir: Path) -> Path | None:
    """Convert a single PDF to clean MD. Returns output path or None on failure."""
    work_dir.mkdir(parents=True, exist_ok=True)

    # VL service rejects filenames > ~128 chars (MySQL column limit).
    # Copy to a short-named temp file if the original name is long.
    orig_name = Path(pdf_path).name
    if len(orig_name) > 100:
        short_pdf = work_dir / "input.pdf"
        shutil.copy2(pdf_path, short_pdf)
        submit_path = str(short_pdf)
        print(f"  (renamed: {len(orig_name)}ch -> input.pdf)", flush=True)
    else:
        submit_path = str(pdf_path)

    # Step 1: Submit to VL
    t0 = time.time()
    print(f"  VL submit...", end="", flush=True)
    try:
        task_id = submit_vl_task(submit_path, "")
        print(f" task={task_id[:16]}", end="", flush=True)
    except Exception as e:
        print(f" FAILED: {e}")
        return None

    # Step 2: Wait for completion
    print(f" waiting...", end="", flush=True)
    try:
        wait_vl_done(task_id, timeout_s=1800)  # 30 min max
    except Exception as e:
        print(f" FAILED: {e}")
        return None

    # Step 3: Fetch per-page MDs
    print(f" fetching...", end="", flush=True)
    try:
        paged_mds = fetch_vl_paged_mds(task_id)
    except Exception as e:
        print(f" FAILED: {e}")
        return None

    # Step 4: Save as vl_{pi}.md in work_dir
    for pi, md_text in paged_mds.items():
        (work_dir / f"vl_{pi}.md").write_text(md_text, encoding="utf-8")

    vl_elapsed = time.time() - t0
    print(f" {len(paged_mds)} pages ({vl_elapsed:.0f}s)", flush=True)

    # Step 5: Post-process each page
    print(f"  post-processing...", end="", flush=True)
    t1 = time.time()
    all_pages = []
    for pi in sorted(paged_mds.keys()):
        md = process_page(pi, str(pdf_path), str(work_dir))
        if md.strip():
            all_pages.append(md)

    # Step 6: Write final MD
    out_path = OUTPUT_DIR / f"{short_name}.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# {short_name}\n\n")
        f.write("\n\n".join(all_pages))

    pp_elapsed = time.time() - t1
    print(f" wrote {out_path.name} ({pp_elapsed:.1f}s)", flush=True)

    # Step 7: Clean up work_dir to save space
    shutil.rmtree(work_dir, ignore_errors=True)

    return out_path


def main():
    parser = argparse.ArgumentParser(description="Batch convert all PDFs to MD")
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated substrings to filter PDFs (e.g. 'QC_T,V2G')",
    )
    parser.add_argument(
        "--skip",
        default="",
        help="Comma-separated substrings to skip PDFs",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    unique_pdfs = list_unique_pdfs()

    # Apply filters
    if args.only:
        keep = [s.strip() for s in args.only.split(",") if s.strip()]
        unique_pdfs = [p for p in unique_pdfs if any(k in p[2] for k in keep)]
    if args.skip:
        skip = [s.strip() for s in args.skip.split(",") if s.strip()]
        unique_pdfs = [p for p in unique_pdfs if not any(k in p[2] for k in skip)]

    # Skip already-converted
    pending = []
    for h, path, short in unique_pdfs:
        out = OUTPUT_DIR / f"{short}.md"
        if out.exists() and out.stat().st_size > 1000:
            print(f"[skip] {short}.md already exists ({out.stat().st_size} bytes)")
            continue
        pending.append((h, path, short))

    print(f"\n{len(pending)} PDFs to convert:\n")
    for h, path, short in pending:
        print(f"  {h}  {short}")
    print()

    if not pending:
        print("Nothing to do.")
        return

    # Process each PDF sequentially
    succeeded = []
    failed = []
    for i, (h, path, short) in enumerate(pending, 1):
        print(f"\n[{i}/{len(pending)}] {short}")
        work_dir = WORK_BASE / h
        try:
            out = convert_one(path, short, work_dir)
            if out:
                succeeded.append((short, out))
            else:
                failed.append((short, "conversion returned None"))
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            failed.append((short, str(e)))

    # Summary
    print(f"\n{'='*60}")
    print(f"Done. {len(succeeded)} succeeded, {len(failed)} failed.")
    if failed:
        print("\nFailed:")
        for short, reason in failed:
            print(f"  - {short}: {reason}")
    print(f"\nOutput: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
