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
# Generic intros / table-of-contents lines that show up repeatedly and
# aren't useful as expected_points.  Filtered at decompose time.
NOISE_PREFIXES = (
    "下列", "本标准", "本规范", "本部分", "本文件",
    "本标准规定了", "本标准适用于",
    "下列文件", "下列术语",
    "见 ", "参见 ", "详见 ",
    "GB ", "GB/T", "GB 1", "QC/T ", "ISO ", "IEC ", "JT/T ",
    "前    言", "前 言", "前  言",
    "目 次", "目次",
    "ICS ", "ICS",
    "T 36", "T 35",
)



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

    Sections are de-duplicated: if the same section_id appears in multiple
    blocks (e.g. OCR put the heading on a different page than the content,
    or the same chapter is repeated because of PDF structure), the
    texts are concatenated and the lowest page_no is kept.

    Returns a list of {section: "3.5", title: "电压滞回功能",
                       page: 9, text: "..."} dicts.
    """
    raw: list[dict] = []
    current: dict | None = None
    for page in doc_ir.get("pages", []):
        page_no = page.get("page_no", 0)
        page_text = "\n".join(
            str(b.get("text", "")) for b in page.get("blocks", [])
        )
        for line in page_text.split("\n"):
            m = HEADING_PATTERN.match(line.strip())
            if m:
                if current is not None:
                    raw.append(current)
                current = {
                    "section": m.group(2).strip(),
                    "title": m.group(3).strip(),
                    "page": page_no,
                    "text": "",
                }
            elif current is not None:
                current["text"] += line + "\n"
    if current is not None:
        raw.append(current)

    # Deduplicate by section id: concatenate text, keep lowest page_no.
    by_sec: dict[str, dict] = {}
    for sec in raw:
        key = sec["section"]
        if key in by_sec:
            by_sec[key]["text"] += "\n" + sec["text"]
            by_sec[key]["page"] = min(by_sec[key]["page"], sec["page"])
        else:
            by_sec[key] = sec
    # Preserve original order (first-seen)
    seen: set[str] = set()
    deduped: list[dict] = []
    for sec in raw:
        if sec["section"] in seen:
            continue
        seen.add(sec["section"])
        deduped.append(by_sec[sec["section"]])
    # Fallback: if no headings were found, treat each page as a synthetic
    # section ("p1", "p2", ...).  This handles docs that were parsed as
    # flat text without Markdown headings.
    if not deduped:
        for page in doc_ir.get("pages", []):
            pn = page.get("page_no", 0)
            page_text = "\n".join(str(b.get("text") or "") for b in (page.get("blocks") or []))
            if page_text.strip():
                deduped.append({
                    "section": f"p{pn}",
                    "title": f"Page {pn}",
                    "page": pn,
                    "text": page_text,
                })
        return deduped
    # Chunked fallback: if deduped has only 1-2 sections but the doc has
    # many pages with text, the heading detection missed most pages.
    # Synthesize per-page sections for those missed pages.
    pages_with_text = [
        p for p in doc_ir.get("pages", [])
        if any((b.get("text") or "").strip() for b in (p.get("blocks") or []))
    ]
    covered_pages = {s["page"] for s in deduped}
    missed_pages = [p for p in pages_with_text if p.get("page_no") not in covered_pages]
    if missed_pages and len(deduped) <= 3 and len(pages_with_text) > 10:
        for p in missed_pages:
            pn = p.get("page_no", 0)
            page_text = "\n".join(str(b.get("text", "")) for b in p.get("blocks", []))
            if page_text.strip():
                deduped.append({
                    "section": f"p{pn}",
                    "title": f"Page {pn}",
                    "page": pn,
                    "text": page_text,
                })
    return deduped



def _refine_llm_section_labels(parent_section: str, section_text: str,
                                llm_points: list[dict]) -> list[dict]:
    """Refine the section field of LLM-extracted points.

    LLM returns all points labeled with parent_section.  Scan the original
    section_text for #### N.M.K markers that match child subsections
    and re-assign the points by their position in the text.
    """
    import re
    if not llm_points:
        return llm_points
    sub_pat = re.compile(r"^#{2,4}\s+(\d+(?:\.\d+)+)\s+", re.MULTILINE)
    boundaries: list[tuple[int, str]] = []
    for m in sub_pat.finditer(section_text):
        sec_id = m.group(1)
        if sec_id != parent_section and sec_id.startswith(parent_section + "."):
            boundaries.append((m.start(), sec_id))
    if not boundaries:
        return llm_points
    boundaries.sort()
    out: list[dict] = []
    for pt in llm_points:
        # Naive: use the order of points in the text.  Approximate using
        # the index in the points list — first point → first boundary, etc.
        idx = llm_points.index(pt)
        if idx < len(boundaries):
            pt["section"] = boundaries[idx][1]
        out.append(pt)
    return out



def _llm_decompose_points(section: dict) -> list[dict]:
    """Ask MiniMax-M2 to decompose a long section into 2-5 coarse points."""
    import httpx

    if not ANTHROPIC_BASE_URL or not ANTHROPIC_AUTH_TOKEN:
        return _naive_decompose(section)

    # Truncate to ~1200 chars on a sentence boundary.  MiniMax-M2 sometimes
    # silently filters longer Chinese policy/standards content (returning
    # only a "thinking" block with no "text").  Keep the prompt body
    # short to avoid this.
    body = section["text"][:1200]
    if len(section["text"]) > 1200:
        last_period = max(body.rfind("。"), body.rfind("."), body.rfind("!"), body.rfind("?"))
        if last_period > 600:
            body = body[:last_period + 1]

    prompt = f"""Decompose the following document section into 2-5 independent claims. Each claim must:
1. Be a fact actually stated in the section (no extrapolation)
2. Be a complete sentence
3. Not duplicate other claims in the same section
4. NOT be a generic intro like "the following..." or "this standard..."

Section title: {section['section']} {section['title']}
Section body:
{body}

Output STRICTLY in this JSON format (no extra text, comments, or Markdown code blocks):
{{"points": ["claim 1", "claim 2", "claim 3"]}}
"""
    try:
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
                    "temperature": 0,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        data = resp.json()
        # Robust text extraction. MiniMax-M2 returns a list of blocks:
        #   [{"type": "thinking", "thinking": "..."},
        #    {"type": "text", "text": "..."}]
        # Older APIs may return a single string.  We concatenate all
        # "text" blocks (skip "thinking" reasoning).
        text = ""
        if "content" in data and data["content"]:
            text_parts = []
            for block in data["content"]:
                if isinstance(block, dict) and block.get("type") == "text" and "text" in block:
                    text_parts.append(block["text"])
                elif isinstance(block, dict) and "text" in block and "thinking" not in block:
                    text_parts.append(block["text"])
                elif isinstance(block, str):
                    text_parts.append(block)
            text = "\n".join(text_parts)
        if not text:
            raise ValueError("no text in LLM response")
        # Strip Markdown code fences
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        # Find first balanced { ... } block (handles nested quotes/braces)
        m = None
        start = text.find("{")
        while start != -1:
            depth = 0
            for i in range(start, len(text)):
                ch = text[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        cand = text[start:i+1]
                        if '"points"' in cand:
                            m = type("M", (), {"group": lambda s, _=0: cand})()
                            class _M:
                                def __init__(s, g): s.g = g
                                def group(s, *a): return s.g
                            m = _M(cand)
                        break
            if m:
                break
            start = text.find("{", start + 1)
        if m:
            parsed = json.loads(m.group(0))
            points = parsed.get("points", [])
            if isinstance(points, list) and points:
                out_points = [{"section": section["section"], "page": section["page"],
                               "point": p, "source": "llm"} for p in points
                              if isinstance(p, str) and not _is_noise(p)]
                return _refine_llm_section_labels(
                    section["section"], section["text"], out_points)
    except Exception as e:
        print(f"  LLM decompose failed for {section['section']}: {type(e).__name__}: {str(e)[:100]}")
    return _naive_decompose(section)
def _is_noise(point: str) -> bool:
    """Detect intros / TOCs / reference lists that aren't useful as expected_points.

    A point is noise if it:
    - is empty
    - starts with a generic intro prefix ("下列", "本标准", ...)
    - is a pure table row (3+ | separators)
    - is a pure reference list (3+ standard codes)
    """
    p = point.strip()
    if not p:
        return True
    for prefix in NOISE_PREFIXES:
        if p.startswith(prefix):
            return True
    # Pure tables (heavy on | and digits but no Chinese sentence)
    if p.count("|") >= 3 and len(p) < 150:
        return True
    # Pure reference lists: many standard codes without a complete sentence
    if (p.count("GB") + p.count("QC/T") + p.count("ISO") + p.count("IEC")) >= 3:
        return True
    return False



def _split_by_subsections(parent_section: str, text: str) -> list[tuple[str, str]]:
    """Split a section's text by embedded #### N.M subsection markers.

    If the section text contains Markdown headings like "#### 4.2" that are
    children of the parent section (e.g. "4.1"), split the text there and
    return (subsection_id, sub_text) pairs.  This keeps the subsection
    label correct instead of attributing child content to the parent.

    Returns [(parent_section, text)] when no sub-headings are found.
    """
    import re
    # Match subsection markers: #### 4.1 / 4.1.1 etc.
    # Match #### N.M or #### N.M.K (any depth), or just #### N (one level deeper)
    escaped = re.escape(parent_section)
    sub_pat = re.compile(
        r"^#{2,4}\s+(" + escaped + r"(?:\.\d+)*)\s+",
        re.MULTILINE,
    )
    matches = list(sub_pat.finditer(text))
    if not matches:
        return [(parent_section, text)]
    out: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        sec_id = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((sec_id, text[start:end]))
    return out


def _naive_decompose(section: dict) -> list[dict]:
    """Fallback: split by sub-section markers then sentences, take first 3."""
    text = section["text"].strip()
    if not text:
        return []
    # First, split by embedded #### N.M subsection markers
    sub_chunks = _split_by_subsections(section["section"], text)
    out: list[dict] = []
    for sub_sec, sub_text in sub_chunks:
        sub_text = sub_text.strip()
        if not sub_text:
            continue
        sentences = re.split(r"(?<=[。!?])\s+|(?<=[.!?])\s+", sub_text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 30]
        sentences = [s for s in sentences if not _is_noise(s)]
        # Take first 1-3 sentences from each sub-chunk
        for sent in sentences[:3]:
            if not _is_noise(sent):
                out.append({"section": sub_sec, "page": section["page"],
                            "point": sent, "source": "naive"})
    if not out and text:
        out.append({"section": section["section"], "page": section["page"],
                    "point": text[:200], "source": "naive"})
    return out


def _embedding_decompose_points(section: dict) -> list[dict]:
    """Cluster sentences of a short section by embedding similarity.

    Uses sentence-transformers locally.  Falls back to naive if not installed.
    First splits by embedded #### N.M subsection markers so each sub-chunk
    gets its own correct section label.
    """
    text = section["text"].strip()
    if not text:
        return []
    sub_chunks = _split_by_subsections(section["section"], text)
    out: list[dict] = []
    for sub_sec, sub_text in sub_chunks:
        sub_text = sub_text.strip()
        if not sub_text:
            continue
        sentences = re.split(r"(?<=[。!?])\s+|(?<=[.!?])\s+", sub_text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 30]
        sentences = [s for s in sentences if not _is_noise(s)]
        if not sentences:
            continue
        if len(sentences) <= 3:
            for sent in sentences:
                if not _is_noise(sent):
                    out.append({"section": sub_sec, "page": section["page"],
                                "point": sent, "source": "embedding"})
            continue
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
            model = SentenceTransformer("all-MiniLM-L6-v2")
            embeddings = model.encode(sentences)
            groups: list[list[str]] = [[sentences[0]]]
            anchors = [embeddings[0]]
            for sent, emb in zip(sentences[1:], embeddings[1:]):
                sims = [float(np.dot(emb, a) / (np.linalg.norm(emb) * np.linalg.norm(a)))
                        for a in anchors]
                if max(sims) > 0.55:
                    best = sims.index(max(sims))
                    groups[best].append(sent)
                else:
                    groups.append([sent])
                    anchors.append(emb)
            groups = groups[:3]
            for g in groups:
                joined = " ".join(g)
                if not _is_noise(joined):
                    out.append({"section": sub_sec, "page": section["page"],
                                "point": joined, "source": "embedding"})
        except ImportError:
            for sent in sentences[:3]:
                if not _is_noise(sent):
                    out.append({"section": sub_sec, "page": section["page"],
                                "point": sent, "source": "embedding"})
        except Exception as e:
            print(f"  Embedding decompose failed for {sub_sec}: {e}")
    if not out and text:
        out.append({"section": section["section"], "page": section["page"],
                    "point": text[:200], "source": "embedding"})
    return out


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
        # For very large sections (>10K chars) use embedding only — the
        # LLM path is too slow and frequently trips the safety filter
        # on long Chinese policy content.  Embedding still produces
        # coarse points via sentence clustering.
        if sec_len > 10000:
            points = _embedding_decompose_points(sec)
        elif sec_len > LONG_SECTION_THRESHOLD:
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
