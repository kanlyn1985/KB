#!/usr/bin/env python3
"""Import wiki MD files into wiki_chunks table for KB retrieval.

Reads cleaned per-PDF markdown from output/kb_md/ and splits each file into
section-level chunks (one per ## heading), then inserts into:

  knowledge_base/db/knowledge.db → wiki_chunks (+ wiki_chunks_fts)

Usage:
  python scripts/import_wiki_chunks.py
  python scripts/import_wiki_chunks.py --input output/kb_md --dry-run
  python scripts/import_wiki_chunks.py --file GBT+18487.1-2023.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

MD_DIR = Path("/home/evt/projects/KB1/output/kb_md")
DB_PATH = Path("/home/evt/projects/KB1/knowledge_base/db/knowledge.db")

# MD filename fragment → doc_id (based on standard number / product name)
# Fragments are matched case-insensitively as substrings.
DOC_ID_MAP = {
    "GBT+18487.1-2023": "DOC-000003",
    "GBT+40432-2021": "DOC-000002",
    "GB_T_18487.4-2025": "DOC-000016",
    "GB_T_18487.5-2024": "DOC-000012",
    "V2G": "DOC-000013",
    "CCU": "DOC-000015",
    "AutomotiveSPICE": "DOC-000005",
    "IEC_61851": "DOC-000004",
    "QC_T_1036": "DOC-000019",
    "182-ISO_14229-1": "DOC-000006",
    "183-ISO_14229-2": "DOC-000007",
    "184-ISO_14229-3": "DOC-000011",
    "185-ISO_14229-4": "DOC-000014",
    "186-ISO_14229-5": "DOC-000010",
    "187-ISO_14229-6": "DOC-000009",
    "188-ISO_14229-7": "DOC-000024",
}

# Fragments to skip (not real documents)
SKIP_PATTERNS = ["wiki_GBT18487", "batch_convert"]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _resolve_doc_id(filename: str) -> str | None:
    """Map an MD filename to doc_id via substring matching against DOC_ID_MAP."""
    for frag, doc_id in DOC_ID_MAP.items():
        if frag in filename:
            return doc_id
    return None


def _extract_standard_code(filename: str, first_line: str) -> str:
    """Extract a standard code (e.g., 'GB/T 18487.1-2023') for source_standard."""
    # Try patterns from the first line of the MD
    patterns = [
        r"(GB/T\s*[\d.]+-?\d*)",
        r"(ISO\s*[\d-]+-?\d*)",
        r"(IEC\s*[\d-]+-?\d*)",
        r"(QC/T\s*\d+-?\d*)",
        r"(GB\s*\d+-?\d*)",
    ]
    text = first_line.replace("_", " ").replace("+", " ")
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    # Fall back to filename stem
    return Path(filename).stem


def _detect_split_level(md_text: str) -> int:
    """Detect the heading level to use for chunk splitting.

    Looks at the count of each heading level and picks the shallowest
    level that has at least 3 headings (after the document title).
    Falls back to 2 (##) if no level qualifies.
    """
    counts = {}
    for level in range(2, 7):
        pat = f"^{'#' * level} "
        counts[level] = sum(1 for line in md_text.split("\n") if line.startswith(pat))
    for level in range(2, 7):
        if counts.get(level, 0) >= 3:
            return level
    return 2


def _split_chunks(md_text: str) -> list[dict]:
    """Split markdown into chunks by the detected heading level.

    Returns [{section_path, section_title, body_text, chunk_type}, ...]
    """
    split_level = _detect_split_level(md_text)
    split_prefix = "#" * split_level + " "

    lines = md_text.split("\n")
    chunks: list[dict] = []
    current_title: str | None = None
    current_path: str = ""
    current_lines: list[str] = []

    def _flush():
        nonlocal current_title, current_path, current_lines
        if current_title and current_lines:
            body = "\n".join(current_lines).strip()
            if body:
                chunk_type = "section"
                if re.match(r"^附录|^Appendix", current_title, re.I):
                    chunk_type = "appendix"
                elif "| --- |" in body[:300]:
                    chunk_type = "table"
                chunks.append({
                    "section_path": current_path,
                    "section_title": current_title,
                    "body_text": body,
                    "chunk_type": chunk_type,
                })
        current_title = None
        current_path = ""
        current_lines = []

    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            if line.startswith(split_prefix):
                _flush()
                current_title = title
                current_path = title
                continue
            elif level == 1:
                # Skip document title
                continue
            # Deeper or shallower heading — if no chunk started yet, start one
            # so we don't lose preamble content
            if current_title is None:
                current_title = title
                current_path = title
        if current_title is not None:
            current_lines.append(line)

    _flush()
    return chunks


def _chunk_id(doc_id: str, section_path: str) -> str:
    """Stable chunk ID from doc_id + section path."""
    h = hashlib.sha1(f"{doc_id}|{section_path}".encode("utf-8")).hexdigest()[:12]
    return f"WC-{h}"


def import_file(
    md_path: Path,
    connection: sqlite3.Connection,
    dry_run: bool = False,
) -> int:
    """Import one MD file. Returns chunk count inserted."""
    filename = md_path.name
    doc_id = _resolve_doc_id(filename)
    if not doc_id:
        print(f"  SKIP {filename}: no doc_id mapping", file=sys.stderr)
        return 0

    md_text = md_path.read_text(encoding="utf-8")
    first_line = md_text.split("\n", 1)[0] if md_text else ""
    standard = _extract_standard_code(filename, first_line)

    chunks = _split_chunks(md_text)
    if not chunks:
        print(f"  SKIP {filename}: no chunks extracted", file=sys.stderr)
        return 0

    now = _utc_now()
    inserted = 0
    for chunk in chunks:
        chunk_id = _chunk_id(doc_id, chunk["section_path"])
        if dry_run:
            print(f"  [DRY] {chunk_id} {doc_id} {chunk['section_title'][:50]}")
            inserted += 1
            continue

        connection.execute(
            """
            INSERT INTO wiki_chunks (
                chunk_id, doc_id, source_standard, section_path,
                section_title, body_text, chunk_type, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chunk_id) DO UPDATE SET
                body_text = excluded.body_text,
                section_title = excluded.section_title,
                chunk_type = excluded.chunk_type,
                source_standard = excluded.source_standard
            """,
            (
                chunk_id,
                doc_id,
                standard,
                chunk["section_path"],
                chunk["section_title"],
                chunk["body_text"],
                chunk["chunk_type"],
                now,
            ),
        )
        inserted += 1

    if not dry_run:
        connection.commit()
    print(f"  {filename} → {doc_id} ({standard}): {inserted} chunks")
    return inserted


def ensure_fts_table(connection: sqlite3.Connection) -> None:
    """Create wiki_chunks_fts virtual table if missing."""
    connection.executescript(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS wiki_chunks_fts USING fts5(
            chunk_id UNINDEXED,
            doc_id UNINDEXED,
            source_standard,
            section_title,
            body_text,
            tokenize = 'unicode61'
        );
        """
    )
    connection.commit()


def refresh_wiki_chunks_fts(connection: sqlite3.Connection) -> int:
    """Rebuild wiki_chunks_fts from wiki_chunks table."""
    connection.execute("DELETE FROM wiki_chunks_fts")
    rows = connection.execute(
        """
        SELECT chunk_id, doc_id, source_standard, section_title, body_text
        FROM wiki_chunks
        """
    ).fetchall()
    for row in rows:
        connection.execute(
            """
            INSERT INTO wiki_chunks_fts (
                chunk_id, doc_id, source_standard, section_title, body_text
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                row["chunk_id"],
                row["doc_id"],
                row["source_standard"] or "",
                row["section_title"] or "",
                row["body_text"] or "",
            ),
        )
    connection.commit()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Import wiki MD → wiki_chunks")
    parser.add_argument(
        "--input",
        default=str(MD_DIR),
        help="Input directory with MD files (default: output/kb_md)",
    )
    parser.add_argument(
        "--file",
        default="",
        help="Import a single file by name (substring match)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be inserted without writing",
    )
    parser.add_argument(
        "--skip-fts",
        action="store_true",
        help="Skip FTS refresh after import",
    )
    args = parser.parse_args()

    md_dir = Path(args.input)
    if not md_dir.is_dir():
        print(f"Input dir not found: {md_dir}", file=sys.stderr)
        sys.exit(1)

    # Collect files
    files = sorted(md_dir.glob("*.md"))
    files = [f for f in files if not any(p in f.name for p in SKIP_PATTERNS)]
    if args.file:
        files = [f for f in files if args.file in f.name]

    if not files:
        print("No MD files to import.")
        return

    print(f"Importing {len(files)} MD files into {DB_PATH}")
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = OFF;")

    try:
        ensure_fts_table(connection)
        total = 0
        for md_path in files:
            total += import_file(md_path, connection, dry_run=args.dry_run)

        if not args.dry_run and not args.skip_fts:
            print(f"\nRefreshing FTS index...")
            fts_count = refresh_wiki_chunks_fts(connection)
            print(f"FTS indexed {fts_count} chunks")

        print(f"\nDone. {total} chunks total.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
