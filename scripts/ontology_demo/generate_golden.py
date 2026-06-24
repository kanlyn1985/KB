"""Generate ontology golden test cases from documents using LLM.

Reads PDF raw text independently of the legacy pipeline, uses LLM
to extract testable knowledge points, and writes golden cases to
the ontology DB.

Usage:
    python scripts/ontology_demo/generate_golden.py --doc-id DOC-000003
    python scripts/ontology_demo/generate_golden.py --all
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from enterprise_agent_kb.config import AppPaths


_GOLDEN_SYSTEM_PROMPT = """\
You are a test-case generator for an automotive engineering knowledge base.
Given a document text, extract test cases that a structured knowledge graph
CAN answer.

A knowledge graph CAN answer:
- DEFINITION: what a standard number means, what an abbreviation/term means
- PARAMETER: numeric value of a named parameter with a unit
- REFERENCE: which standards a given standard references
- SERVICE: which UDS diagnostic services a standard defines
- TRAVERSAL: multi-hop relationships between standards

A knowledge graph CANNOT answer:
- Free-text questions ("what are the requirements for...")
- Section numbers ("what is section 3.1.9")
- Internal requirement codes ("SC4100048")
- Generic concepts without a standard identifier ("放电设备是什么")
- Document metadata like version/date/status unless explicitly listed

Generate test cases ONLY for knowledge points that meet ALL criteria:
1. The knowledge point is explicitly NAMED in the document
2. It can be identified by a STANDARD NUMBER or well-known ABBREVIATION
3. It has a STRUCTURED answer (not a paragraph of text)

For each valid knowledge point, output:
{
  "query": "template-based question",
  "category": "parameter|definition|reference|service|traversal",
  "entity": "the EXACT standard number or abbreviation found in the document",
  "target": "the parameter name if category is parameter, otherwise null",
  "expected": "the structured answer from the document"
}

TEMPLATES (use EXACTLY these formats):
- parameter:  "{standard_number} {parameter_name} 是多少"
- definition: "{standard_number_or_abbreviation} 是什么"
- reference:  "{standard_number} 引用了哪些标准"
- service:    "{standard_number} 定义了哪些服务"
- traversal:  "从 {standard_number} 出发 1 跳可达的标准"

CRITICAL CONSTRAINTS:
- Every query MUST contain a standard number or LATIN ABBREVIATION (like V2L, OBC, UDS)
- entity field for definition queries MUST be a latin abbreviation, NOT a Chinese phrase
- For Chinese concepts without an abbreviation, do NOT generate a definition query
- parameter queries MUST have a numeric value with a unit in expected
- DO NOT generate queries for: section numbers, requirement IDs, generic nouns
- If the entity is a Chinese phrase with no abbreviation, skip it
- Quality over quantity — 10 good cases are better than 50 bad ones

Return ONLY a JSON array of test cases, nothing else."""


def _call_llm_for_golden(text: str) -> list[dict[str, Any]]:
    """Call LLM to generate golden test cases from document text."""
    from enterprise_agent_kb.infrastructure.llm_client import LLMClient, Message, Provider
    import os as _os

    saved = {}
    for key in ("all_proxy", "ALL_PROXY"):
        if key in _os.environ:
            saved[key] = _os.environ.pop(key)

    try:
        client = LLMClient(provider=Provider.CLAUDE, timeout=180.0, max_retries=3)
        response = client.chat(
            messages=[Message(role="user", content=text[:8000])],
            system_prompt=_GOLDEN_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=4000,
        )
    except Exception as e:
        print(f"    LLM error: {e}")
        return []
    finally:
        _os.environ.update(saved)

    content = (response.content or "").strip()
    # Extract JSON block
    if content.startswith("```"):
        import re
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

    try:
        result = json.loads(content)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    return []


def _get_document_raw_text(workspace_root: Path, doc_id: str) -> str:
    """Read raw text from document evidence (independent of facts pipeline)."""
    db_path = AppPaths.from_root(workspace_root).db_file
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT page_no, raw_text FROM evidence "
            "WHERE doc_id = ? ORDER BY page_no",
            (doc_id,),
        ).fetchall()

        if not rows:
            rows = conn.execute(
                "SELECT page_no, normalized_text FROM evidence "
                "WHERE doc_id = ? ORDER BY page_no",
                (doc_id,),
            ).fetchall()

        texts = []
        for r in rows:
            page = r[0]
            text = r[1] or ""
            texts.append(f"--- Page {page} ---\n{text}")

        # Truncate to first 25 pages for large documents
        if len(texts) > 25:
            texts = texts[:25]

        return "\n\n".join(texts)
    finally:
        conn.close()


def _store_golden_case(
    ont_conn: sqlite3.Connection,
    case: dict[str, Any],
    doc_id: str,
) -> None:
    """Store a generated golden case in the ontology DB."""
    import uuid
    case_id = f"GOLDEN-{uuid.uuid4().hex[:16].upper()}"

    query = (case.get("query") or "").strip()
    category = (case.get("category") or "free_form").strip()
    entity = (case.get("entity") or "").strip() or None
    target = (case.get("target") or "").strip() or None
    expected = case.get("expected")

    if not query:
        return

    now = datetime.now(UTC).isoformat(timespec="seconds")

    ont_conn.execute(
        """
        INSERT OR REPLACE INTO ontology_golden
        (case_id, doc_id, query, category, entity, target, expected_json, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            case_id, doc_id, query, category, entity, target,
            json.dumps(expected, ensure_ascii=False),
            "active", now, now,
        ),
    )
    ont_conn.commit()


def ensure_golden_schema(conn: sqlite3.Connection) -> None:
    """Create ontology golden cases table if missing."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ontology_golden (
            case_id     TEXT PRIMARY KEY,
            doc_id      TEXT NOT NULL,
            query       TEXT NOT NULL,
            category    TEXT NOT NULL DEFAULT 'free_form',
            entity      TEXT,
            target      TEXT,
            expected_json TEXT,
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_ontology_golden_doc
        ON ontology_golden(doc_id)
    """)
    conn.commit()


def generate_for_document(
    workspace_root: Path,
    ontology_db_path: Path,
    doc_id: str,
) -> dict[str, Any]:
    """Generate ontology golden test cases for a single document."""
    print(f"Reading document: {doc_id}")
    text = _get_document_raw_text(workspace_root, doc_id)

    if not text:
        return {"doc_id": doc_id, "error": "No text found"}

    print(f"  Text length: {len(text)} chars")

    # Split text into chunks for processing
    pages = text.split("--- Page ")
    chunks = []
    current = ""
    for p in pages:
        if not p.strip():
            continue
        candidate = f"--- Page {p}" if not current else current + "\n" + f"--- Page {p}"
        if len(candidate) > 8000:
            chunks.append(current)
            current = f"--- Page {p}"
        else:
            current = candidate
    if current:
        chunks.append(current)

    all_cases = []
    for i, chunk in enumerate(chunks):
        print(f"  Processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...")
        cases = _call_llm_for_golden(chunk)
        all_cases.extend(cases)
        print(f"    Got {len(cases)} cases")

    if not all_cases:
        return {"doc_id": doc_id, "error": "LLM returned no cases"}

    # Store in ontology DB
    ont_conn = sqlite3.connect(str(ontology_db_path))
    ensure_golden_schema(ont_conn)

    try:
        # Delete old cases for this doc
        ont_conn.execute(
            "DELETE FROM ontology_golden WHERE doc_id = ?",
            (doc_id,),
        )

        for case in all_cases:
            _store_golden_case(ont_conn, case, doc_id)

        ont_conn.commit()
    finally:
        ont_conn.close()

    # Count by category
    cats = {}
    for c in all_cases:
        cat = c.get("category", "free_form")
        cats[cat] = cats.get(cat, 0) + 1

    for cat, cnt in sorted(cats.items()):
        print(f"    {cat}: {cnt}")

    return {"doc_id": doc_id, "cases": len(all_cases), "by_category": cats}


def generate_all(workspace_root: Path, ontology_db_path: Path) -> dict[str, Any]:
    """Generate golden cases for all documents."""
    db_path = AppPaths.from_root(workspace_root).db_file
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    docs = conn.execute(
        "SELECT doc_id, source_filename FROM documents WHERE parse_status = 'parsed' ORDER BY doc_id"
    ).fetchall()
    conn.close()

    results = {}
    for doc in docs:
        doc_id = doc["doc_id"]
        print(f"\n{'='*60}")
        print(f"Document: {doc_id} - {doc['source_filename'][:60]}")
        print(f"{'='*60}")
        try:
            results[doc_id] = generate_for_document(workspace_root, ontology_db_path, doc_id)
        except Exception as e:
            print(f"  FAILED: {e}")
            results[doc_id] = {"doc_id": doc_id, "error": str(e)}

    return results


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Generate ontology golden test cases")
    parser.add_argument("--doc-id", help="Specific document ID")
    parser.add_argument("--all", action="store_true", help="Process all documents")
    parser.add_argument("--workspace", default="knowledge_base", help="Workspace path")
    args = parser.parse_args()

    workspace = ROOT / args.workspace
    ontology_db = workspace / "ontology" / "ontology.db"

    if args.all:
        results = generate_all(workspace, ontology_db)
        total = sum(r.get("cases", 0) for r in results.values())
        print(f"\n{'='*60}")
        print(f"Total golden cases generated: {total}")
    elif args.doc_id:
        result = generate_for_document(workspace, ontology_db, args.doc_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
