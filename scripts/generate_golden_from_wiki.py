#!/usr/bin/env python3
"""Generate golden test cases from wiki_chunks for ontology evaluation.

Unlike scripts/ontology_demo/generate_golden.py (which reads raw PDF text),
this reads the cleaned wiki_chunks from knowledge.db and generates testable
QA pairs with expected answers.

Each golden case has: {query, category, entity, target, expected_answer}

Usage:
  python scripts/generate_golden_from_wiki.py --doc-id DOC-000003
  python scripts/generate_golden_from_wiki.py --all
  python scripts/generate_golden_from_wiki.py --all --limit 5   # smoke test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for k in ("all_proxy", "ALL_PROXY", "https_proxy", "http_proxy"):
    os.environ.pop(k, None)

ONTOLOGY_DB = ROOT / "knowledge_base" / "ontology" / "ontology.db"
KNOWLEDGE_DB = ROOT / "knowledge_base" / "db" / "knowledge.db"


_GOLDEN_PROMPT = """\
You are a test-case generator for an automotive engineering knowledge base.
Given a section of a technical standard document, generate test cases that
a structured knowledge graph SHOULD be able to answer.

The knowledge graph CAN answer:
- DEFINITION: what a standard/code means, what an abbreviation/term means
- PARAMETER: specific numeric value of a named parameter (with unit)
- REFERENCE: which standards a given standard references (by standard code)

CRITICAL RULES for the "entity" field:
- MUST use a standard code: "GB/T 18487.1", "ISO 14229-3", "IEC 61851-1",
  "QC/T 1036", "GB/T 40432", "NB/T 33001", "DL/T 584"
- NEVER use generic terms like "本文件", "试验环境条件", "仪器设备要求"
- If no specific standard code is mentioned, use the document's own standard
  code (check the document title or section headers for it)
- If a parameter belongs to a specific standard mentioned in the text, use
  THAT standard's code

Other rules:
1. Only generate cases for facts EXPLICITLY stated in this section
2. The expected answer MUST be extractable from this section's text
3. Use natural Chinese query phrasing
4. For the entity field, ALWAYS use a standard code format
5. Strip year suffixes: "GB/T 18487.1—2023" → "GB/T 18487.1"
6. For parameter queries, include the unit in the expected answer
7. Skip cases where the answer is ambiguous or requires interpretation
8. Do NOT generate cases where the entity is a section title or generic concept

Return a JSON array of test cases:
[
  {
    "category": "definition|parameter|reference",
    "entity": "GB/T 18487.1",   ← MUST be a standard code
    "target": "额定交流电压",
    "query": "GB/T 18487.1 的额定交流电压是多少",
    "expected": "220 V"
  }
]

Return ONLY the JSON array, nothing else. Generate 2-5 cases per section."""


def _call_llm(text: str, max_retries: int = 3) -> list[dict[str, Any]]:
    from enterprise_agent_kb.infrastructure.llm_client import LLMClient, Message, Provider

    for attempt in range(max_retries):
        try:
            client = LLMClient(provider=Provider.CLAUDE, timeout=120.0, max_retries=1)
            response = client.chat(
                messages=[Message(role="user", content=text)],
                system_prompt=_GOLDEN_PROMPT,
                temperature=0.2,
                max_tokens=4000,
            )
            content = (response.content or "").strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
            return json.loads(content)
        except Exception:
            if attempt == max_retries - 1:
                return []
            time.sleep(5)
    return []


def _store_golden(ont_conn, cases: list[dict], doc_id: str, chunk_id: str) -> int:
    """Insert golden cases into ontology_golden. Returns count inserted."""
    now = datetime.now(UTC).isoformat(timespec="seconds")
    count = 0
    for c in cases:
        query = (c.get("query") or "").strip()
        category = (c.get("category") or "").strip()
        entity = (c.get("entity") or "").strip()
        target = (c.get("target") or "").strip() or None
        expected = json.dumps(c.get("expected", ""), ensure_ascii=False)
        if not query or category not in ("definition", "parameter", "reference", "traversal"):
            continue
        case_id = f"GOLDEN-{abs(hash(query + expected)):016X}"[:24]
        try:
            ont_conn.execute(
                """
                INSERT OR REPLACE INTO ontology_golden
                (case_id, doc_id, query, category, entity, target, expected_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (case_id, doc_id, query, category, entity, target, expected, now, now),
            )
            count += 1
        except Exception:
            pass
    ont_conn.commit()
    return count


def _ensure_table(ont_conn):
    ont_conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ontology_golden (
            case_id TEXT PRIMARY KEY,
            doc_id TEXT,
            query TEXT NOT NULL,
            category TEXT NOT NULL,
            entity TEXT,
            target TEXT,
            expected_json TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_og_doc_id ON ontology_golden(doc_id);
        CREATE INDEX IF NOT EXISTS idx_og_status ON ontology_golden(status);
        """
    )
    ont_conn.commit()


def generate_for_doc(
    ont_conn: sqlite3.Connection,
    knowledge_db: Path,
    doc_id: str,
    limit: int | None = None,
) -> dict:
    """Generate golden cases from wiki_chunks for one document."""
    kb_conn = sqlite3.connect(str(knowledge_db))
    kb_conn.row_factory = sqlite3.Row
    chunks = [
        dict(r) for r in kb_conn.execute(
            """
            SELECT chunk_id, doc_id, source_standard, section_title, body_text
            FROM wiki_chunks
            WHERE doc_id = ? AND length(body_text) > 100
            ORDER BY chunk_id
            """,
            (doc_id,),
        ).fetchall()
    ]
    kb_conn.close()

    if not chunks:
        return {"doc_id": doc_id, "error": "no chunks"}

    if limit:
        chunks = chunks[:limit]

    print(f"\n[{doc_id}] {len(chunks)} chunks", flush=True)

    # Mark old cases for this doc as superseded
    ont_conn.execute(
        "UPDATE ontology_golden SET status = 'superseded' WHERE doc_id = ?",
        (doc_id,),
    )
    ont_conn.commit()

    total = 0
    for i, c in enumerate(chunks):
        sec = c.get("section_title", "")[:30]
        text = c.get("body_text", "")
        print(f"  [{i+1}/{len(chunks)}] {sec!r} ({len(text)} chars)...", end=" ", flush=True)

        if len(text) < 100:
            print("skip (too short)")
            continue

        # Only process sections likely to contain testable facts
        # Skip TOC, foreword, bibliography, pure-definition pages
        if re.match(r"^(目次|前言|引言|参考文献|Bibliography|Contents|Foreword)", sec, re.I):
            print("skip (metadata)")
            continue

        cases = _call_llm(text)
        if not cases:
            print("empty")
            continue

        stored = _store_golden(ont_conn, cases, doc_id, c["chunk_id"])
        total += stored
        print(f"{len(cases)} generated, {stored} stored")

    print(f"  TOTAL stored: {total}")
    return {"doc_id": doc_id, "stored": total}


def main():
    parser = argparse.ArgumentParser(
        description="Generate ontology golden test cases from wiki_chunks"
    )
    parser.add_argument("--doc-id", help="Single document ID")
    parser.add_argument("--all", action="store_true", help="All documents")
    parser.add_argument("--limit", type=int, default=None, help="Max chunks per doc")
    args = parser.parse_args()

    if not args.doc_id and not args.all:
        parser.print_help()
        sys.exit(1)

    ont_conn = sqlite3.connect(str(ONTOLOGY_DB))
    ont_conn.row_factory = sqlite3.Row
    _ensure_table(ont_conn)

    if args.doc_id:
        r = generate_for_doc(ont_conn, KNOWLEDGE_DB, args.doc_id, args.limit)
        print(r)
    elif args.all:
        kb_conn = sqlite3.connect(str(KNOWLEDGE_DB))
        kb_conn.row_factory = sqlite3.Row
        doc_ids = [
            r["doc_id"] for r in kb_conn.execute(
                "SELECT DISTINCT doc_id FROM wiki_chunks ORDER BY doc_id"
            ).fetchall()
        ]
        kb_conn.close()

        grand = 0
        for doc_id in doc_ids:
            r = generate_for_doc(ont_conn, KNOWLEDGE_DB, doc_id, args.limit)
            grand += r.get("stored", 0)
        print(f"\n{'='*50}")
        print(f"GRAND TOTAL: {grand} cases")

    ont_conn.close()


if __name__ == "__main__":
    main()
