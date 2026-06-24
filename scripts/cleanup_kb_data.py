#!/usr/bin/env python3
"""
KB1 System Data Cleanup Tool

Usage:
    python scripts/cleanup_kb_data.py [--doc-id DOC_ID] [--dry-run] [--yes]

Options:
    --doc-id DOC_ID   Clean specific doc (e.g., DOC-000008)
    --dry-run         Show what would be deleted without deleting
    --yes             Skip confirmation prompt
    --all             Clean ALL documents (use with caution!)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


# Tables that store per-document data (ordered for FK safety)
PER_DOC_TABLES = [
    # FTS virtual tables (no FK constraints, safe to delete first)
    "evidence_fts",
    "facts_fts",
    "wiki_fts",
    # Junction tables
    "edge_evidence_map",
    "fact_evidence_map",
    "source_unit_evidence_map",
    "source_unit_fact_map",
    # Core tables
    "facts",
    "evidence",
    "entities",
    "graph_edges",
    "wiki_pages",
    "source_units",
    "quality_reports",
    "parse_views",
    "page_parse_selection",
    "blocks",
    "pages",
    # Metadata
    "expected_points",
    "golden_cases",
    # Main table (last)
    "documents",
]

# Global/system tables that should NOT be touched
SYSTEM_TABLES = {
    "answer_feedback",
    "audit_log",
    "dependencies",
    "eval_results",
    "eval_runs",
    "jobs",
    "low_confidence_queries",
    "repair_tasks",
    "retrieval_runs",
    "sqlite_sequence",
    "system_counters",
}


def get_workspace_root() -> Path:
    """Find workspace root from script location."""
    script_dir = Path(__file__).resolve().parent
    return script_dir.parent / "knowledge_base"


def get_db_path() -> Path:
    return get_workspace_root() / "db" / "knowledge.db"


def get_normalized_dir() -> Path:
    return get_workspace_root() / "normalized"


def get_evidence_dir() -> Path:
    return get_workspace_root() / "evidence"


def get_facts_dir() -> Path:
    return get_workspace_root() / "facts"


def get_acceptance_reports_dir() -> Path:
    return get_workspace_root() / "acceptance_reports"


def get_coverage_reports_dir() -> Path:
    return get_workspace_root() / "coverage_reports"


def get_wiki_dir() -> Path:
    return get_workspace_root() / "wiki"


def get_db_counts(doc_id: str | None = None) -> dict[str, int]:
    """Get row counts per table, optionally filtered by doc_id."""
    db_path = get_db_path()
    if not db_path.exists():
        return {}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    counts = {}
    for table in PER_DOC_TABLES:
        try:
            if table.endswith("_fts"):
                # FTS tables use docid, not doc_id
                if doc_id:
                    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE docid LIKE ?", (f"%{doc_id}%",))
                else:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
            elif table == "documents":
                if doc_id:
                    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE doc_id = ?", (doc_id,))
                else:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
            else:
                if doc_id:
                    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE doc_id = ?", (doc_id,))
                else:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            counts[table] = -1  # Table doesn't exist

    conn.close()
    return counts


def get_files_to_delete(doc_id: str | None = None) -> dict[str, list[Path]]:
    """Get list of intermediate files to delete."""
    files: dict[str, list[Path]] = {
        "normalized": [],
        "evidence": [],
        "facts": [],
        "acceptance": [],
        "coverage": [],
        "wiki": [],
    }

    norm_dir = get_normalized_dir()
    if norm_dir.exists():
        for pattern in ["*.cleaned_doc_ir.json", "*.doc_ir.json", "*.json", "*.kb.jsonl", "*.knowledge_units.json"]:
            for f in norm_dir.glob(pattern):
                if doc_id is None or doc_id in f.name:
                    files["normalized"].append(f)

    evidence_dir = get_evidence_dir()
    if evidence_dir.exists():
        for f in evidence_dir.glob("*.evidence.json"):
            if doc_id is None or doc_id in f.name:
                files["evidence"].append(f)

    facts_dir = get_facts_dir()
    if facts_dir.exists():
        for f in facts_dir.glob("*.facts.json"):
            if doc_id is None or doc_id in f.name:
                files["facts"].append(f)

    acc_dir = get_acceptance_reports_dir()
    if acc_dir.exists():
        for f in acc_dir.glob("*.ingestion_acceptance.*"):
            if doc_id is None or doc_id in f.name:
                files["acceptance"].append(f)

    cov_dir = get_coverage_reports_dir()
    if cov_dir.exists():
        for f in cov_dir.glob("*"):
            if f.is_file() and (doc_id is None or doc_id in f.name):
                files["coverage"].append(f)

    wiki_dir = get_wiki_dir()
    if wiki_dir.exists():
        for f in wiki_dir.glob("*"):
            if f.is_file() and (doc_id is None or doc_id in f.name):
                files["wiki"].append(f)

    return files


def delete_db_data(doc_id: str | None = None, dry_run: bool = False) -> dict[str, int]:
    """Delete database rows for a specific doc or all docs."""
    db_path = get_db_path()
    if not db_path.exists():
        print(f"  [WARN] Database not found: {db_path}")
        return {}

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    deleted = {}

    # Tables with explicit doc_id column
    DOC_ID_TABLES = [
        "documents", "evidence", "pages", "blocks", "expected_points",
        "quality_reports", "parse_views", "page_parse_selection",
        "source_units", "retrieval_runs",
    ]
    # Tables with source_doc_id column
    SOURCE_DOC_ID_TABLES = ["facts", "golden_cases"]
    # Junction tables (no direct doc_id) - need fact/evidence based deletion
    JUNCTION_TABLES = [
        ("fact_evidence_map", "facts", "fact_id"),
        ("edge_evidence_map", "evidence", "evidence_id"),
        ("source_unit_evidence_map", "evidence", "evidence_id"),
        ("source_unit_fact_map", "facts", "fact_id"),
    ]

    # Delete from tables with doc_id
    for table in DOC_ID_TABLES:
        try:
            if doc_id:
                cursor.execute(f"DELETE FROM {table} WHERE doc_id = ?", (doc_id,))
            else:
                cursor.execute(f"DELETE FROM {table}")
            deleted[table] = cursor.rowcount
        except sqlite3.OperationalError as e:
            deleted[table] = -1
            if "no such table" not in str(e).lower():
                print(f"  [WARN] Error deleting from {table}: {e}")

    # Delete from tables with source_doc_id
    for table in SOURCE_DOC_ID_TABLES:
        try:
            if doc_id:
                cursor.execute(f"DELETE FROM {table} WHERE source_doc_id = ?", (doc_id,))
            else:
                cursor.execute(f"DELETE FROM {table}")
            deleted[table] = cursor.rowcount
        except sqlite3.OperationalError as e:
            deleted[table] = -1

    # Delete from junction tables (via fact/evidence references)
    for table, ref_table, ref_col in JUNCTION_TABLES:
        try:
            if doc_id:
                # Get fact/evidence IDs for this doc
                if ref_table == "facts":
                    cursor.execute(f"SELECT fact_id FROM {ref_table} WHERE source_doc_id = ?", (doc_id,))
                else:
                    cursor.execute(f"SELECT evidence_id FROM {ref_table} WHERE doc_id = ?", (doc_id,))
                ids = [row[0] for row in cursor.fetchall()]
                if ids:
                    placeholders = ",".join("?" * len(ids))
                    cursor.execute(f"DELETE FROM {table} WHERE {ref_col} IN ({placeholders})", ids)
                    deleted[table] = cursor.rowcount
                else:
                    deleted[table] = 0
            else:
                cursor.execute(f"DELETE FROM {table}")
                deleted[table] = cursor.rowcount
        except sqlite3.OperationalError as e:
            deleted[table] = -1

    # Delete from entities and graph_edges (need to find via fact references)
    for table in ["entities", "graph_edges", "wiki_pages"]:
        try:
            if doc_id:
                # For entities: no direct doc link, but we can skip if no facts reference them
                # For graph_edges and wiki_pages: similar
                # These are shared/global tables; safer to skip
                deleted[table] = 0
            else:
                cursor.execute(f"DELETE FROM {table}")
                deleted[table] = cursor.rowcount
        except sqlite3.OperationalError as e:
            deleted[table] = -1

    # Delete from FTS tables
    for fts_table in ["evidence_fts", "facts_fts", "wiki_fts"]:
        try:
            if doc_id:
                # FTS tables use rowid; need to join with main table
                if fts_table == "evidence_fts":
                    cursor.execute(
                        f"DELETE FROM {fts_table} WHERE rowid IN (SELECT rowid FROM evidence WHERE doc_id = ?)",
                        (doc_id,),
                    )
                elif fts_table == "facts_fts":
                    cursor.execute(
                        f"DELETE FROM {fts_table} WHERE rowid IN (SELECT rowid FROM facts WHERE source_doc_id = ?)",
                        (doc_id,),
                    )
                else:
                    cursor.execute(f"DELETE FROM {fts_table}")
                deleted[fts_table] = cursor.rowcount
            else:
                cursor.execute(f"DELETE FROM {fts_table}")
                deleted[fts_table] = cursor.rowcount
        except sqlite3.OperationalError as e:
            deleted[fts_table] = -1

    if not dry_run:
        conn.commit()
    conn.close()
    return deleted


def delete_files(files: dict[str, list[Path]], dry_run: bool = False) -> int:
    """Delete files and return count."""
    count = 0
    for category, file_list in files.items():
        for f in file_list:
            if dry_run:
                print(f"  [DRY-RUN] Would delete: {f}")
            else:
                try:
                    f.unlink()
                    count += 1
                except OSError as e:
                    print(f"  [WARN] Failed to delete {f}: {e}")
    return count


def main():
    parser = argparse.ArgumentParser(description="KB1 System Data Cleanup Tool")
    parser.add_argument("--doc-id", help="Clean specific doc (e.g., DOC-000008)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    parser.add_argument("--all", action="store_true", help="Clean ALL documents (use with caution!)")
    args = parser.parse_args()

    if not args.doc_id and not args.all:
        print("Usage: python scripts/cleanup_kb_data.py [--doc-id DOC_ID | --all] [--dry-run] [--yes]")
        print("\nExamples:")
        print("  # Preview what would be deleted for DOC-000008")
        print("  python scripts/cleanup_kb_data.py --doc-id DOC-000008 --dry-run")
        print("\n  # Actually delete DOC-000008 data")
        print("  python scripts/cleanup_kb_data.py --doc-id DOC-000008 --yes")
        print("\n  # Delete ALL document data (keeps system tables)")
        print("  python scripts/cleanup_kb_data.py --all --yes")
        sys.exit(1)

    doc_id = args.doc_id
    dry_run = args.dry_run

    # Show current state
    print("=" * 60)
    if doc_id:
        print(f"KB1 Cleanup: Document {doc_id}")
    else:
        print("KB1 Cleanup: ALL DOCUMENTS")
    print("=" * 60)

    # Get DB counts
    print("\n📊 Database row counts:")
    counts = get_db_counts(doc_id)
    total_rows = sum(c for c in counts.values() if c > 0)
    for table, count in counts.items():
        if count > 0:
            print(f"  {table}: {count} rows")
    print(f"  Total: {total_rows} rows")

    # Get files
    print("\n📁 Files to delete:")
    files = get_files_to_delete(doc_id)
    total_files = sum(len(flist) for flist in files.values())
    for category, flist in files.items():
        if flist:
            print(f"  {category}: {len(flist)} files")
            for f in flist[:3]:
                print(f"    - {f.name}")
            if len(flist) > 3:
                print(f"    ... and {len(flist) - 3} more")
    print(f"  Total: {total_files} files")

    if dry_run:
        print("\n🏃 Dry run complete. No data was deleted.")
        sys.exit(0)

    # Confirmation
    if not args.yes:
        print("\n" + "=" * 60)
        action = f"document {doc_id}" if doc_id else "ALL DOCUMENTS"
        confirm = input(f"Type 'yes' to delete {action}: ")
        if confirm.lower() != "yes":
            print("Cancelled.")
            sys.exit(0)

    # Execute deletion
    print("\n🗑️  Deleting database rows...")
    deleted = delete_db_data(doc_id, dry_run=False)
    total_deleted = sum(c for c in deleted.values() if c > 0)
    print(f"  Deleted {total_deleted} rows from {sum(1 for c in deleted.values() if c > 0)} tables")

    print("\n🗑️  Deleting files...")
    files_deleted = delete_files(files, dry_run=False)
    print(f"  Deleted {files_deleted} files")

    print("\n✅ Cleanup complete!")
    print(f"   Database rows deleted: {total_deleted}")
    print(f"   Files deleted: {files_deleted}")

    # Show remaining state
    remaining = get_db_counts()
    remaining_total = sum(c for c in remaining.values() if c > 0)
    if remaining_total > 0:
        print(f"\n📊 Remaining data: {remaining_total} rows across all tables")
    else:
        print("\n📊 Database is now empty (except system tables)")


if __name__ == "__main__":
    main()
