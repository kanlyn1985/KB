"""Term review CLI for ontology dictionary.

Provides an interactive command-line interface for domain experts to
review, verify, edit, and reject automatically extracted terms.

Usage:
    python scripts/ontology_demo/review_terms.py

This is Phase 7.4 of the ontology roadmap.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Ensure src/ is on the import path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from kb1_ontology.db import connect, default_db_path


class TermReviewCLI:
    """Interactive CLI for term review."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.db_path = default_db_path(workspace_root)
        self.conn = connect(self.db_path)
        self.current_term: dict[str, str | None] | None = None

    def _get_unverified_terms(self, limit: int = 10) -> list[dict[str, str | None]]:
        """Get unverified terms sorted by confidence."""
        cur = self.conn.execute(
            "SELECT term_id, canonical_name, category, definition_zh, "
            "       definition_en, source_standard, confidence, extracted_at "
            "FROM term WHERE verified = 0 "
            "ORDER BY confidence DESC, extracted_at DESC "
            "LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    def _get_term_by_id(self, term_id: str) -> dict[str, str | None] | None:
        """Get a single term by ID."""
        cur = self.conn.execute(
            "SELECT term_id, canonical_name, category, definition_zh, "
            "       definition_en, source_standard, confidence, extracted_at "
            "FROM term WHERE term_id = ?",
            (term_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def _get_aliases(self, term_id: str) -> list[dict[str, str | None]]:
        """Get aliases for a term."""
        cur = self.conn.execute(
            "SELECT alias, alias_type FROM term_alias WHERE term_id = ?",
            (term_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def _update_term(self, term_id: str, **kwargs: str | None) -> None:
        """Update a term's fields."""
        allowed = {"canonical_name", "definition_zh", "definition_en", "category"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values())
        values.append(term_id)

        self.conn.execute(
            f"UPDATE term SET {set_clause} WHERE term_id = ?",
            values,
        )
        self.conn.commit()

    def _verify_term(self, term_id: str, verified: bool = True) -> None:
        """Mark a term as verified or rejected."""
        self.conn.execute(
            "UPDATE term SET verified = ? WHERE term_id = ?",
            (1 if verified else -1, term_id),
        )
        self.conn.execute(
            "DELETE FROM term_alias WHERE term_id = ?",
            (term_id,),
        )
        self.conn.commit()

    def _delete_term(self, term_id: str) -> None:
        """Delete a term and its aliases."""
        self.conn.execute(
            "DELETE FROM term_alias WHERE term_id = ?",
            (term_id,),
        )
        self.conn.execute(
            "DELETE FROM term WHERE term_id = ?",
            (term_id,),
        )
        self.conn.commit()

    def _display_term(self, term: dict[str, str | None]) -> None:
        """Display a term in a formatted way."""
        print("-" * 50)
        print(f"ID:        {term['term_id']}")
        print(f"Name:      {term['canonical_name']}")
        print(f"Category:  {term['category']}")
        print(f"Chinese:   {term['definition_zh'] or '(none)'}")
        print(f"English:   {term['definition_en'] or '(none)'}")
        print(f"Source:    {term['source_standard']}")
        print(f"Confidence: {term['confidence']}")

        aliases = self._get_aliases(term['term_id'])
        if aliases:
            print(f"Aliases:   {', '.join(a['alias'] for a in aliases)}")
        print("-" * 50)

    def _get_stats(self) -> dict[str, int]:
        """Get review statistics."""
        cur = self.conn.execute(
            "SELECT verified, COUNT(*) FROM term GROUP BY verified"
        )
        stats = {row[0]: row[1] for row in cur.fetchall()}
        return {
            "unverified": stats.get(0, 0),
            "verified": stats.get(1, 0),
            "rejected": stats.get(-1, 0),
            "total": sum(stats.values()),
        }

    def run(self) -> None:
        """Main review loop."""
        print("=" * 50)
        print("KB1 Ontology Term Review CLI")
        print("=" * 50)
        print()

        while True:
            stats = self._get_stats()
            print(f"Stats: {stats['verified']} verified, "
                  f"{stats['unverified']} unverified, "
                  f"{stats['rejected']} rejected")
            print()

            terms = self._get_unverified_terms(limit=1)
            if not terms:
                print("No more unverified terms!")
                break

            term = terms[0]
            self._display_term(term)

            print()
            print("Commands:")
            print("  [y]es    - Verify this term")
            print("  [n]o     - Reject this term")
            print("  [e]dit   - Edit this term")
            print("  [s]kip   - Skip to next")
            print("  [q]uit   - Exit")
            print()

            choice = input("Choice [y/n/e/s/q]: ").strip().lower()

            if choice in ("y", "yes"):
                self._verify_term(term['term_id'], verified=True)
                print(f"✓ Verified {term['term_id']}")

            elif choice in ("n", "no"):
                self._verify_term(term['term_id'], verified=False)
                print(f"✗ Rejected {term['term_id']}")

            elif choice in ("e", "edit"):
                self._edit_term(term)

            elif choice in ("s", "skip"):
                print("Skipped.")

            elif choice in ("q", "quit"):
                print("Exiting...")
                break

            print()

    def _edit_term(self, term: dict[str, str | None]) -> None:
        """Interactive term editing."""
        print("\nEdit term (press Enter to keep current value):")

        name = input(f"Name [{term['canonical_name']}]: ").strip()
        if name:
            term['canonical_name'] = name

        zh = input(f"Chinese [{term['definition_zh'] or ''}]: ").strip()
        if zh:
            term['definition_zh'] = zh

        en = input(f"English [{term['definition_en'] or ''}]: ").strip()
        if en:
            term['definition_en'] = en

        cat = input(f"Category [{term['category']}]: ").strip()
        if cat:
            term['category'] = cat

        self._update_term(
            term['term_id'],
            canonical_name=term['canonical_name'],
            definition_zh=term['definition_zh'],
            definition_en=term['definition_en'],
            category=term['category'],
        )
        print(f"✓ Updated {term['term_id']}")


def main() -> None:
    workspace = ROOT / "knowledge_base"
    cli = TermReviewCLI(workspace)
    try:
        cli.run()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        cli.conn.close()


if __name__ == "__main__":
    main()
