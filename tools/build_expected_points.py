"""Build expected_points table for the Phase 1 evaluation framework.

Reads each document's parsed `doc_ir.json` (PaddleVL-minimax output),
splits it into sections by Markdown heading level, then decomposes each
section into independent points:

  - Big section  (>500 chars): MiniMax-M2 (long-context LLM) decomposes
                                into 2-5 coarse points.
  - Small section (<=500 chars): sentence-transformers (local) clusters
                                  sentences by embedding similarity
                                  into 1-3 points.

The output is a row per (doc_id, version) in the `expected_points` table,
with `points_json` storing the full point list for the QA evaluator.

Usage:
    python tools/build_expected_points.py --version v1
    python tools/build_expected_points.py --doc-id DOC-000001 --version v1
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

# Allow imports from src/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from enterprise_agent_kb.db import connect  # noqa: E402


WORKSPACE = ROOT / "knowledge_base"
NORMALIZED_DIR = WORKSPACE / "normalized"
SCHEMA_VERSION = 1  # bump to force re-apply on schema changes

# Heading pattern: lines starting with # (1-4 #) followed by section number
HEADING_PATTERN = re.compile(r"^\s*(#{1,4})\s+(\d[\d\.]*)\s+(.+?)(?:\n|$)", re.MULTILINE)

# MiniMax-M2 (Anthropic-compatible) is configured via env
import os  # noqa: E402

ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
ANTHROPIC_AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "MiniMax-M2.7")

LONG_SECTION_THRESHOLD = 500  # chars; above this, LLM decomposes


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _split_sections(doc_ir: dict) -> list[dict]:
    """Split a doc_ir into sections by Markdown heading.

    Returns a list of {section: "3.5", title: "电压滞回功能",
                       page: 9, text: "..."} dicts.
    """
    sections: list[dict] = []
    current: dict | None = None
    for page in doc_ir.get("pages", []):
        page_no = page.get("page_no", 0)
        # Each page is a list of blocks; concatenate text
        page_text = "\n".join(
            str(b.get("text", "")) for b in page.get("blocks", [])
        )
        # Walk line by line to find headings
        for line in page_text.split("\n"):
            m = HEADING_PATTERN.match(line.strip())
            if m:
                # New heading found: close current, start new
                if current is not None:
                    sections.append(current)
                current = {
                    "section": m.group(2).strip(),
                    "title": m.group(3).strip(),
                    "page": page_no,
                    "text": "",
                }
            elif current is not None:
                current["text"] += line + "\n"
    if current is not None:
        sections.append(current)
    return sections


def _llm_decompose_points(section: dict) -> list[dict]:
    """Ask MiniMax-M2 to decompose a long section into 2-5 coarse points."""
    import httpx

    if not ANTHROPIC_BASE_URL or not ANTHROPIC_AUTH_TOKEN:
        # Fall back to naive sentence split if LLM not configured
        return _naive_decompose(section)

    prompt = f"""将以下文档章节拆解为 2-5 个独立论点。每个论点必须:
1. 是该章节确实陈述的事实 (不要外推)
2. 用一个完整句子表达
3. 不与该章节其他论点重复

章节标题: {section['section']} {section['title']}
章节正文:
{section['text'][:2000]}

输出 JSON 格式:
{{"points": ["论点 1...", "论点 2..."]}}
"""
    try:
        # trust_env=False bypasses the SOCKS proxy set in env
        with httpx.Client(timeout=60.0, trust_env=False) as client:
            resp = client.post(
                f"{ANTHROPIC_BASE_URL.rstrip('/')}/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_AUTH_TOKEN,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        data = resp.json()
        text = data["content"][0]["text"]
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            parsed = json.loads(m.group(0))
            return [{"section": section["section"], "page": section["page"],
                     "point": p, "source": "llm"} for p in parsed.get("points", [])]
    except Exception as e:
        print(f"  LLM decompose failed for {section['section']}: {e}")
    return _naive_decompose(section)


def _naive_decompose(section: dict) -> list[dict]:
    """Fallback: split by sentences, take first 3 as coarse points."""
    text = section["text"].strip()
    if not text:
        return []
    # Split on Chinese + English sentence boundaries
    sentences = re.split(r"(?<=[。!?])\s+|(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    points = sentences[:3] if sentences else [text[:200]]
    return [{"section": section["section"], "page": section["page"],
             "point": p, "source": "naive"} for p in points]


def _embedding_decompose_points(section: dict) -> list[dict]:
    """Cluster sentences of a short section by embedding similarity.

    Uses sentence-transformers locally.  Falls back to naive if not installed.
    """
    text = section["text"].strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[。!?])\s+|(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if len(sentences) <= 1:
        return [{"section": section["section"], "page": section["page"],
                 "point": sentences[0] if sentences else text[:200],
                 "source": "embedding"}]
    if len(sentences) <= 3:
        return [{"section": section["section"], "page": section["page"],
                 "point": s, "source": "embedding"} for s in sentences]
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
        model = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = model.encode(sentences)
        # Greedy cluster: start new group when similarity to anchor drops
        groups: list[list[str]] = [[sentences[0]]]
        anchors = [embeddings[0]]
        for sent, emb in zip(sentences[1:], embeddings[1:]):
            sims = [float(np.dot(emb, a) / (np.linalg.norm(emb) * np.linalg.norm(a)))
                    for a in anchors]
            if max(sims) > 0.55:  # similar to some existing group
                best = sims.index(max(sims))
                groups[best].append(sent)
            else:
                groups.append([sent])
                anchors.append(emb)
        # Cap at 3 points for short sections
        groups = groups[:3]
        return [{"section": section["section"], "page": section["page"],
                 "point": " ".join(g), "source": "embedding"} for g in groups]
    except ImportError:
        return _naive_decompose(section)
    except Exception as e:
        print(f"  Embedding decompose failed for {section['section']}: {e}")
        return _naive_decompose(section)


def build_doc_points(doc_id: str, version: str) -> dict:
    """Build expected points for a single document."""
    ir_path = NORMALIZED_DIR / f"{doc_id}.doc_ir.json"
    if not ir_path.exists():
        print(f"  skip: {ir_path} not found")
        return None
    with open(ir_path, encoding="utf-8") as f:
        doc_ir = json.load(f)

    sections = _split_sections(doc_ir)
    print(f"  {doc_id}: {len(sections)} sections found")

    all_points: list[dict] = []
    for sec in sections:
        sec_len = len(sec["text"].strip())
        # Skip empty / trivial sections (e.g. section 4.5 with only "4.5" label)
        if sec_len < 30:
            print(f"    sec {sec['section']} ({sec_len} chars): skipped (too short)")
            continue
        if sec_len > LONG_SECTION_THRESHOLD:
            points = _llm_decompose_points(sec)
        else:
            points = _embedding_decompose_points(sec)
        all_points.extend(points)
        print(f"    sec {sec['section']} ({sec_len} chars): {len(points)} points")

    return {
        "doc_id": doc_id,
        "version": version,
        "points": all_points,
    }


def apply_migration(db_path: Path) -> None:
    """Apply migration 001 if not already applied."""
    with connect(db_path) as conn:
        v = conn.execute("PRAGMA user_version").fetchone()[0]
        if v >= 1:
            print(f"migration 001 already applied (user_version={v})")
            return
    sql_file = ROOT / "src/enterprise_agent_kb/migrations/001_expected_points.sql"
    with connect(db_path) as conn:
        conn.executescript(sql_file.read_text(encoding="utf-8"))
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    print(f"migration 001 applied (user_version={SCHEMA_VERSION})")


def write_points(db_path: Path, result: dict) -> None:
    """Write a single doc's points to the expected_points table."""
    with connect(db_path) as conn:
        # Replace existing version
        conn.execute(
            "DELETE FROM expected_points WHERE doc_id = ? AND version = ?",
            (result["doc_id"], result["version"]),
        )
        conn.execute(
            """
            INSERT INTO expected_points
                (doc_id, version, points_json, point_count, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                result["doc_id"],
                result["version"],
                json.dumps(result["points"], ensure_ascii=False),
                len(result["points"]),
                _now(),
                "tools/build_expected_points.py",
            ),
        )


def list_doc_ids(db_path: Path) -> list[str]:
    """List all active document IDs from the workspace DB."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT doc_id FROM documents WHERE is_active = 1 ORDER BY doc_id"
        ).fetchall()
    return [r[0] for r in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="v1", help="expected_points version tag")
    parser.add_argument("--doc-id", help="restrict to one doc_id (default: all)")
    parser.add_argument("--limit", type=int, help="limit number of docs (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="don't write to DB")
    args = parser.parse_args()

    db_path = WORKSPACE / "db" / "knowledge.db"
    apply_migration(db_path)
    if args.dry_run:
        print("dry-run: skipping DB writes")
        return 0

    if args.doc_id:
        doc_ids = [args.doc_id]
    else:
        doc_ids = list_doc_ids(db_path)
        if args.limit:
            doc_ids = doc_ids[: args.limit]
    print(f"Building expected_points for {len(doc_ids)} docs (version={args.version})\n")

    succeeded = 0
    for doc_id in doc_ids:
        print(f"[{doc_id}]")
        result = build_doc_points(doc_id, args.version)
        if result and result["points"]:
            write_points(db_path, result)
            print(f"  wrote {len(result['points'])} points to expected_points\n")
            succeeded += 1
        else:
            print(f"  skipped (no points)\n")

    print(f"Done. {succeeded}/{len(doc_ids)} docs succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
