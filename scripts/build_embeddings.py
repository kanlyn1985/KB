#!/usr/bin/env python3
"""Vector embedding store for wiki_chunks.

Provides:
  - build_embeddings(): compute embeddings for all wiki_chunks, store in DB
  - search_embeddings(): cosine-similarity search against stored embeddings
  - Hybrid retrieval: FTS (keyword) + embedding (semantic) fusion

Uses sentence-transformers (all-MiniLM-L6-v2, ~80MB, fast on CPU).

Usage:
  python scripts/build_embeddings.py                    # build all
  python scripts/build_embeddings.py --doc-id DOC-000003  # single doc
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Clear proxy env vars
for k in ("all_proxy", "ALL_PROXY", "https_proxy", "http_proxy"):
    os.environ.pop(k, None)

DB_PATH = ROOT / "knowledge_base" / "db" / "knowledge.db"
MODEL_NAME = "all-MiniLM-L6-v2"


def ensure_embedding_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS wiki_chunk_embeddings (
            chunk_id TEXT PRIMARY KEY,
            embedding_json TEXT NOT NULL,
            model_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (chunk_id) REFERENCES wiki_chunks(chunk_id)
        );
        CREATE INDEX IF NOT EXISTS idx_wce_chunk_id ON wiki_chunk_embeddings(chunk_id);
        """
    )
    conn.commit()


def build_embeddings(
    conn: sqlite3.Connection,
    doc_id: str | None = None,
    batch_size: int = 32,
) -> int:
    """Compute embeddings for wiki_chunks and store in DB.

    Returns number of chunks embedded.
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME)
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    if doc_id:
        rows = conn.execute(
            "SELECT chunk_id, body_text FROM wiki_chunks WHERE doc_id = ? AND length(body_text) > 50",
            (doc_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT chunk_id, body_text FROM wiki_chunks WHERE length(body_text) > 50"
        ).fetchall()

    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        texts = [r["body_text"] for r in batch]
        embeddings = model.encode(texts, show_progress_bar=False)

        for row, emb in zip(batch, embeddings):
            conn.execute(
                """
                INSERT OR REPLACE INTO wiki_chunk_embeddings
                (chunk_id, embedding_json, model_name, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (row["chunk_id"], json.dumps(emb.tolist()), MODEL_NAME, now),
            )
        total += len(batch)
        if i % (batch_size * 5) == 0:
            print(f"  {total}/{len(rows)} chunks embedded...", flush=True)

    conn.commit()
    return total


def search_embeddings(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search wiki_chunks by embedding cosine similarity.

    Returns [{chunk_id, doc_id, source_standard, section_title, body_text, score}, ...]
    """
    from sentence_transformers import SentenceTransformer
    import numpy as np

    model = SentenceTransformer(MODEL_NAME)
    query_emb = model.encode([query], show_progress_bar=False)[0]
    query_norm = np.linalg.norm(query_emb)

    if query_norm == 0:
        return []

    rows = conn.execute(
        """
        SELECT e.chunk_id, e.embedding_json, wc.doc_id, wc.source_standard,
               wc.section_title, wc.body_text
        FROM wiki_chunk_embeddings e
        JOIN wiki_chunks wc ON wc.chunk_id = e.chunk_id
        """
    ).fetchall()

    scores = []
    for row in rows:
        emb = np.array(json.loads(row["embedding_json"]))
        emb_norm = np.linalg.norm(emb)
        if emb_norm == 0:
            continue
        score = float(np.dot(query_emb, emb) / (query_norm * emb_norm))
        scores.append((score, dict(row)))

    scores.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, row in scores[:limit]:
        row["score"] = round(score, 6)
        results.append(row)

    return results


def main():
    parser = argparse.ArgumentParser(description="Build/query vector embeddings for wiki_chunks")
    parser.add_argument("--doc-id", help="Single document ID")
    parser.add_argument("--query", help="Search query (skip build)")
    parser.add_argument("--limit", type=int, default=10, help="Max results for search")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        ensure_embedding_table(conn)

        if args.query:
            results = search_embeddings(conn, args.query, limit=args.limit)
            print(f"\nQuery: {args.query}")
            print(f"Results: {len(results)}")
            for r in results:
                print(f"  [{r['score']:.4f}] [{r['source_standard']}] {r['section_title'][:50]}")
                print(f"         {r['body_text'][:100]}...")
            return

        print(f"Building embeddings with {MODEL_NAME}")
        t0 = time.time()
        count = build_embeddings(conn, doc_id=args.doc_id)
        elapsed = time.time() - t0
        print(f"\nDone. {count} chunks embedded in {elapsed:.0f}s ({elapsed/count:.1f}s/chunk)")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
