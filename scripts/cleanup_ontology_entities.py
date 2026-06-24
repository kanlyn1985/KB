#!/usr/bin/env python3
"""Clean up noisy entities produced by LLM extraction.

Background:
  The LLM extraction in extract_from_wiki.py sometimes creates entities for
  section titles (e.g. "7.6 直接接触防护", "附录F") instead of only proper
  standard codes (GB/T x, ISO x, etc.). These pollute the KG with non-real
  entities and bogus relations.

This script removes:
  - Entities whose canonical_name looks like a section heading (starts with
    a number, contains "附录", or doesn't match standard naming patterns)
  - Relations where either endpoint is such an entity

Usage:
  python scripts/cleanup_ontology_entities.py --dry-run
  python scripts/cleanup_ontology_entities.py            # actually delete
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DB = ROOT / "knowledge_base" / "ontology" / "ontology.db"

# Regex of entity names that look like proper standard codes
_PROPER_STD_RE = re.compile(
    r"^(?:"
    r"GB/T\s*\d+"                  # GB/T 18487.1
    r"|GB\s*\d+"                    # GB 50057
    r"|ISO\s*\d+(?:[-.]\d+)?"       # ISO 14229-1, ISO 9001.1
    r"|IEC\s*\d+(?:[-.]\d+)?"       # IEC 61851-1
    r"|QC/T\s*\d+"                  # QC/T 1036
    r"|DL/T\s*\d+"                  # DL/T 584
    r"|IEEE\s*\d+(?:\.\d+)*"       # IEEE 802.3
    r"|SAE\s*\d+"                  # SAE J1939
    r"|AUTOSAR"                    # AUTOSAR
    r")"
)


def is_noisy_section_heading(name: str) -> bool:
    """Return True if the name looks like a section heading (noise).

    Real entities we keep: standard codes (GB/T x, ISO x, IEC x, NB/T x,
    ISO/IEC x, IEEE x, SAE x), product names (V2G, CCU, OBC), process
    names (AutomotiveSPICE), concept names.
    """
    name = name.strip()
    if not name:
        return True
    # Section heading patterns (these are the noise):
    # "7.6 直接接触防护", "11.4 爬电距离", "4.4 分类"
    if re.match(r"^[0-9]+(\.[0-9]+)*\s+\S", name):
        return True
    # "附录F", "附录 A", "附录 B"
    if re.match(r"^附录\s*[A-Z0-9]?$", name):
        return True
    # "术语定义章节", "范围", "规范性引用文件" (single-word chapter titles)
    if name in ("范围", "规范性引用文件", "术语和定义", "附录"):
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Clean up noisy entities in ontology")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be deleted without actually deleting")
    args = parser.parse_args()

    if not DB.exists():
        print(f"Ontology DB not found: {DB}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    # Find noisy entities (section headings only)
    rows = conn.execute("SELECT entity_id, canonical_name FROM entity").fetchall()
    noisy_ids = []
    noisy_names = []
    for r in rows:
        if is_noisy_section_heading(r["canonical_name"]):
            noisy_ids.append(r["entity_id"])
            noisy_names.append(r["canonical_name"])

    print(f"Total entities: {len(rows)}")
    print(f"Noisy entities (not matching standard code pattern): {len(noisy_ids)}")

    if noisy_ids:
        print("\nSample noisy entities:")
        for n in noisy_names[:15]:
            print(f"  {n[:60]}")
        if len(noisy_names) > 15:
            print(f"  ... and {len(noisy_names) - 15} more")

    if not noisy_ids:
        print("\nNothing to clean.")
        return

    # Count affected relations
    placeholders = ",".join("?" for _ in noisy_ids)
    rel_count = conn.execute(
        f"""
        SELECT COUNT(*) FROM relation
        WHERE src_id IN ({placeholders}) OR dst_id IN ({placeholders})
        """,
        noisy_ids + noisy_ids,
    ).fetchone()[0]

    print(f"\nRelations involving noisy entities: {rel_count}")

    if args.dry_run:
        print("\nDRY-RUN — nothing deleted.")
        return

    # Delete
    conn.execute(
        f"DELETE FROM relation WHERE src_id IN ({placeholders}) OR dst_id IN ({placeholders})",
        noisy_ids + noisy_ids,
    )
    # Also delete attribute entries for noisy entities
    conn.execute(
        f"DELETE FROM attribute WHERE subject_kind='entity' AND subject_id IN ({placeholders})",
        noisy_ids,
    )
    conn.execute(
        f"DELETE FROM entity WHERE entity_id IN ({placeholders})",
        noisy_ids,
    )
    conn.commit()

    print(f"\nDeleted {len(noisy_ids)} noisy entities")
    print(f"Deleted {rel_count} affected relations")
    print("\nRemaining entities:",
          conn.execute("SELECT COUNT(*) FROM entity").fetchone()[0])
    print("Remaining relations:",
          conn.execute("SELECT COUNT(*) FROM relation").fetchone()[0])

    conn.close()


if __name__ == "__main__":
    main()