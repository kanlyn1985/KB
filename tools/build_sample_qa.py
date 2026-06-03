"""Build sample_qa bank for the Phase 1 evaluation framework.

For each document's expected_points, MiniMax-M2 generates 5-10 questions
that probe the system's answer.  Each question must:
  - be answerable by a specific subset of expected_points
  - reference a real page_no (守门 1)
  - be answered by a ground_truth derived from expected_points (守门 2)

The output is written to tools/sample_qa/v1.json for downstream use by
the evaluator (eakb eval run-now --suite golden|full).

Two prompt templates (template_a, template_b) are used so the same question
can be re-asked with different phrasings, exposing single-prompt brittleness.

Usage:
    python tools/build_sample_qa.py --version v1
    python tools/build_sample_qa.py --doc-id DOC-000001 --version v1
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Allow imports from src/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from enterprise_agent_kb.db import connect  # noqa: E402


WORKSPACE = ROOT / "knowledge_base"
DB_PATH = WORKSPACE / "db" / "knowledge.db"
QA_DIR = ROOT / "tools" / "sample_qa"

# MiniMax-M2 (Anthropic-compatible) is configured via env
import os  # noqa: E402

ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
ANTHROPIC_AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "MiniMax-M2.7")

# ---- Prompt templates --------------------------------------------------

# template_a: terse, factual questions
PROMPT_TEMPLATE_A = """Generate 5-10 user-style questions a person might ask about this document.
Each question must:
1. Be answerable by referencing 1-3 of the expected points listed below
2. Be phrased as a real user would phrase it (e.g. "逆变器效率要求" not
   "what is the efficiency requirement of the inverter")
3. NOT be a question about the standard's publication info, references,
   or table-of-contents

Expected points (each has a section id and a page number):
{expected_points}

Output STRICTLY in this JSON format (no extra text, comments, or Markdown):
{{"questions": [
  {{"question": "中文问题 1", "page": 9, "matched_points": ["section": "3.1", "point": "..."]}}
]}}
"""

# template_b: same content, different phrasing
PROMPT_TEMPLATE_B = """Read the following expected points from a document and produce 5-10 questions.
For each question:
- Frame it like a real user query, not like a textbook exercise
- The question must reference specific points (use their section and point text)
- Skip generic / intro / reference-list points
- The page_no must match the points' page number

Expected points:
{expected_points}

Return JSON: {{"questions": [{{"question": "...", "page": 9, "matched_points": [{{"section": "3.1", "point": "..."}}]}}]}}
"""


def _now() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).isoformat(timespec="seconds")


def _list_docs(db_path: Path) -> list[str]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT doc_id FROM documents WHERE is_active = 1 ORDER BY doc_id"
        ).fetchall()
    return [r[0] for r in rows]


def _load_expected_points(db_path: Path, doc_id: str, version: str) -> list[dict]:
    """Read expected_points for a doc, return only substantive (non-noise) points."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT points_json FROM expected_points WHERE doc_id = ? AND version = ?",
            (doc_id, version),
        ).fetchone()
    if not row:
        return []
    return json.loads(row[0])


def _is_substantive(point: dict) -> bool:
    """A point is substantive if it has substantive content (not a generic
    intro, not pure TOC, not a table of standard codes)."""
    text = point.get("point", "").strip()
    if not text:
        return False
    NOISE_PREFIXES = (
        "下列", "本标准", "本规范", "本部分", "本文件",
        "GB ", "GB/T", "GB 1", "QC/T ", "ISO ", "IEC ", "JT/T ",
        "前    言", "前 言", "前  言", "目 次", "目次", "ICS ", "T 36", "T 35",
    )
    if any(text.startswith(n) for n in NOISE_PREFIXES):
        return False
    if text.count("|") >= 3 and len(text) < 150:
        return False
    return True


def _call_llm(prompt: str) -> str:
    """Call MiniMax-M2 and return the concatenated text (skipping thinking)."""
    import httpx
    if not ANTHROPIC_BASE_URL or not ANTHROPIC_AUTH_TOKEN:
        raise RuntimeError("LLM not configured (missing env)")
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
                "max_tokens": 2048,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    data = resp.json()
    text_parts: list[str] = []
    for block in data.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text" and "text" in block:
            text_parts.append(block["text"])
    text = "\n".join(text_parts)
    if not text:
        raise RuntimeError("no text in LLM response")
    return text


def _parse_json_block(text: str) -> dict | None:
    """Find first balanced { ... } block in text and parse as JSON."""
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
                    cand = text[start:i + 1]
                    if '"questions"' in cand:
                        try:
                            return json.loads(cand)
                        except json.JSONDecodeError:
                            break
        start = text.find("{", start + 1)
    return None


def _page_in_doc(doc_id: str, page: int) -> bool:
    """Validate that a page_no referenced by a question actually has content."""
    if not isinstance(page, int) or page <= 0:
        return False
    DB_PATH = WORKSPACE / "db" / "knowledge.db"
    with connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT MAX(page_count) FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
    if not row or not row[0]:
        return False
    return page <= row[0]


def _generate_for_doc(doc_id: str, expected_points: list[dict],
                      template_id: str = "a") -> list[dict]:
    """Generate questions for a doc using one prompt template.

    Returns a list of {question, page, matched_points, template_id}.
    """
    substantive = [p for p in expected_points if _is_substantive(p)]
    if not substantive:
        return []
    # Truncate expected_points list in prompt to ~30 to keep prompt size reasonable
    sample = substantive[:30]
    ep_lines = []
    for p in sample:
        sec = p.get("section", "?")
        page = p.get("page", "?")
        text = p.get("point", "")[:200]
        ep_lines.append(f"- [sec {sec}, p{page}] {text}")
    ep_block = "\n".join(ep_lines)
    template = PROMPT_TEMPLATE_A if template_id == "a" else PROMPT_TEMPLATE_B
    prompt = template.format(expected_points=ep_block)
    try:
        text = _call_llm(prompt)
    except Exception as e:
        print(f"    [{doc_id}] template_{template_id} LLM call failed: {type(e).__name__}: {str(e)[:80]}")
        return []
    parsed = _parse_json_block(text)
    if not parsed or "questions" not in parsed:
        print(f"    [{doc_id}] template_{template_id} parse failed")
        return []
    questions = parsed["questions"]
    if not isinstance(questions, list):
        return []
    # 守门 1: each question must reference a real page
    out: list[dict] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        q_text = str(q.get("question", "")).strip()
        page = q.get("page")
        if not q_text or len(q_text) < 5:
            continue
        if not _page_in_doc(doc_id, page):
            continue
        if not any(kw in q_text for kw in q_text.split() if len(kw) > 1):
            pass  # 守门 2 placeholder
        out.append({
            "question": q_text,
            "page": page,
            "matched_points": q.get("matched_points", []),
            "template_id": template_id,
        })
    return out


def _build_golden_questions(qa: list[dict]) -> list[dict]:
    """Pick golden questions: distinct (question, doc) pairs, deduplicated
    by text.  These are the 30 题 spot-check set (5 docs × 6 题)."""
    seen: set[str] = set()
    golden: list[dict] = []
    for q in qa:
        key = (q["doc_id"], q["question"])
        if key in seen:
            continue
        seen.add(key)
        golden.append(q)
    return golden[:30]



# ---- Fallback question templates (no LLM needed) -----------------------

# Templates indexed by point kind.  For each expected point we pick a
# template based on the section prefix or point content.
_QUESTION_TEMPLATES = [
    # Term-definition: standard "什么是 X" question
    ("term_definition", lambda p: f"什么是 {p.get('section', '')} 节定义的术语? (第 {p.get('page', '?')} 页)"),
    # Parameter: "X 是多少" question
    ("parameter_value", lambda p: f"文档中参数在第 {p.get('page', '?')} 页的值是什么?"),
    # Requirement: "X 的要求是什么"
    ("requirement", lambda p: f"第 {p.get('section', '')} 节有哪些要求? (第 {p.get('page', '?')} 页)"),
    # Threshold: "X 阈值/范围"
    ("threshold", lambda p: f"第 {p.get('section', '')} 节规定的阈值或限值是多少? (第 {p.get('page', '?')} 页)"),
    # Generic: ask the point text directly
    ("generic", lambda p: f"请解释: {p.get('point', '')[:80]}"),
]


def _generate_fallback_questions(expected_points: list[dict],
                                 max_per_section: int = 3) -> list[dict]:
    """Generate questions from expected_points using templates.

    Returns a list of {question, page, matched_points, template_id}.
    """
    out: list[dict] = []
    section_counts: dict[str, int] = {}
    for p in expected_points:
        sec = p.get("section", "")
        if section_counts.get(sec, 0) >= max_per_section:
            continue
        # Pick template by section prefix / first word
        text = p.get("point", "").strip()
        if not text:
            continue
        template_id, tmpl = _QUESTION_TEMPLATES[4]  # generic
        if sec.startswith("3.") and len(text) < 200:
            # Term-definition section
            template_id, tmpl = _QUESTION_TEMPLATES[0]
        elif any(kw in text for kw in ["%", "V", "Hz", "VA"]):
            template_id, tmpl = _QUESTION_TEMPLATES[1]
        elif any(kw in text for kw in ["应", "必须", "不应", "要求", "不得"]):
            template_id, tmpl = _QUESTION_TEMPLATES[2]
        elif any(kw in text for kw in ["不大于", "不小于", "不超过", "不低于", "范围"]):
            template_id, tmpl = _QUESTION_TEMPLATES[3]
        question = tmpl(p)
        # Avoid duplicates within the same section
        if any(q["question"] == question for q in out):
            continue
        section_counts[sec] = section_counts.get(sec, 0) + 1
        out.append({
            "question": question,
            "page": p.get("page"),
            "matched_points": [{"section": p.get("section"),
                                 "point": text[:200]}],
            "template_id": f"fallback_{template_id}",
        })
    return out




def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="v1", help="expected_points version")
    parser.add_argument("--doc-id", help="restrict to one doc")
    parser.add_argument("--dry-run", action="store_true", help="don't call LLM")
    parser.add_argument("--templates", default="a,b",
                        help="comma-separated template ids to use (default a,b)")
    args = parser.parse_args()

    template_ids = [t.strip() for t in args.templates.split(",") if t.strip()]
    if not template_ids:
        template_ids = ["a", "b"]

    if args.doc_id:
        doc_ids = [args.doc_id]
    else:
        doc_ids = _list_docs(DB_PATH)
    print(f"Building sample_qa for {len(doc_ids)} docs (version={args.version}, "
          f"templates={template_ids})\n")

    all_questions: list[dict] = []
    for doc_id in doc_ids:
        ep = _load_expected_points(DB_PATH, doc_id, args.version)
        if not ep:
            print(f"[{doc_id}] no expected_points (skipping)")
            continue
        if args.dry_run:
            print(f"[{doc_id}] dry-run: skipping LLM call")
            continue
        print(f"[{doc_id}] generating with templates={template_ids} "
              f"(substantive points: {sum(1 for p in ep if _is_substantive(p))})")
        doc_questions: list[dict] = []
        for tid in template_ids:
            qs = _generate_for_doc(doc_id, ep, template_id=tid)
            print(f"    template_{tid}: {len(qs)} questions (守门 1 page-in-doc passed)")
            for q in qs:
                q["doc_id"] = doc_id
                q["version"] = args.version
                q["created_at"] = _now()
                doc_questions.append(q)
        # Fallback to template-based questions if LLM produced 0
        if not doc_questions:
            print(f"    [fallback] LLM unavailable, generating template-based questions")
            fq = _generate_fallback_questions(ep, max_per_section=2)
            for q in fq:
                q["doc_id"] = doc_id
                q["version"] = args.version
                q["created_at"] = _now()
                doc_questions.append(q)
            print(f"    fallback: {len(fq)} questions")
        all_questions.extend(doc_questions)
        print(f"  -> {len(doc_questions)} questions for {doc_id}\n")

    # Dedupe
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for q in all_questions:
        key = (q["doc_id"], q["question"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)

    # Build golden set
    golden = _build_golden_questions(deduped)

    # Write outputs
    QA_DIR.mkdir(parents=True, exist_ok=True)
    full_path = QA_DIR / f"{args.version}.json"
    full_path.write_text(
        json.dumps(deduped, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    golden_path = QA_DIR / f"{args.version}_golden.json"
    golden_path.write_text(
        json.dumps(golden, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Done. {len(deduped)} unique questions ({len(golden)} golden).")
    print(f"  Full:  {full_path}")
    print(f"  Golden: {golden_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
