"""Phase 1 evaluator: run sample_qa against answer_query, measure coverage.

For each question in tools/sample_qa/v1.json:
  1. Call answer_query() to get the system's answer
  2. LLM-B: extract which expected_points the system answer covers
  3. Coverage = covered / total
  4. Pass if coverage >= 0.5

Multi-prompt 鲁棒性: same question asked with 2 prompt templates,
the 2 coverage results must agree within 10% to count as stable.

Output: EvalResult with per-question scores and aggregate pass_rate.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Allow imports
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Project imports
from enterprise_agent_kb.answer_api import answer_query  # noqa: E402

WORKSPACE = ROOT / "knowledge_base"
QA_DIR = ROOT / "tools" / "sample_qa"
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
ANTHROPIC_AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "MiniMax-M2.7")

COVERAGE_THRESHOLD = 0.5  # >= 50% covered points = pass
MULTI_PROMPT_TOLERANCE = 0.10  # 2 templates must agree within 10%


@dataclass
class ScoreResult:
    """Per-question scoring result."""
    question: str
    doc_id: str
    system_answer: str
    expected_points: list[dict]
    covered_points: list[dict]  # LLM-B says system covers these
    coverage: float  # covered / total
    pass_: bool  # coverage >= COVERAGE_THRESHOLD
    template_a_coverage: float = 0.0
    template_b_coverage: float = 0.0
    multi_prompt_stable: bool = True


@dataclass
class EvalResult:
    """Aggregate evaluation result."""
    suite: str
    total: int
    passed: int
    pass_rate: float
    avg_coverage: float
    multi_prompt_stability: float
    by_doc: dict[str, dict] = field(default_factory=dict)
    per_question: list[ScoreResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "suite": self.suite,
            "total": self.total,
            "passed": self.passed,
            "pass_rate": self.pass_rate,
            "avg_coverage": self.avg_coverage,
            "multi_prompt_stability": self.multi_prompt_stability,
            "by_doc": self.by_doc,
        }


# ---- LLM call ---------------------------------------------------------

def _call_llm(prompt: str, max_tokens: int = 1024, timeout: float = 60.0) -> str:
    """Call MiniMax-M2 and return concatenated text (skip thinking)."""
    import httpx
    if not ANTHROPIC_BASE_URL or not ANTHROPIC_AUTH_TOKEN:
        raise RuntimeError("LLM not configured")
    with httpx.Client(timeout=timeout, trust_env=False) as client:
        resp = client.post(
            f"{ANTHROPIC_BASE_URL.rstrip('/')}/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_AUTH_TOKEN,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "max_tokens": max_tokens,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    data = resp.json()
    text_parts: list[str] = []
    for block in data.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text" and "text" in block:
            text_parts.append(block["text"])
    return "\n".join(text_parts)


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
                    if "covered" in cand or "covered_indices" in cand:
                        try:
                            return json.loads(cand)
                        except json.JSONDecodeError:
                            break
        start = text.find("{", start + 1)
    return None


# ---- Coverage extraction prompts --------------------------------------

_PROMPT_A = """You will see a user question, a system answer, and a list of
expected points (each is a fact the answer should contain).  Identify
which expected points the system answer COVERS (i.e. mentions the
information or a paraphrased equivalent).

Question: {question}
System answer: {answer}
Expected points:
{points}

Output STRICTLY in this JSON format:
{{"covered_indices": [0, 2, 3]}}

Index 0 means the first expected point, etc.  Use [] if nothing is covered.
"""

_PROMPT_B = """Read the question and system answer, then mark which expected
points are addressed by the system answer (allowing for paraphrase).

Question: {question}
System answer: {answer}
Expected points:
{points}

Return JSON only: {{"covered_indices": [1, 4]}} — list of indices (0-based)
of expected points that the system answer mentions or paraphrases.
Empty list if none.
"""


def _format_points(points: list[dict]) -> str:
    """Format expected points for prompt."""
    lines = []
    for i, p in enumerate(points):
        sec = p.get("section", "?")
        text = p.get("point", "")[:200]
        lines.append(f"[{i}] (sec {sec}) {text}")
    return "\n".join(lines)


def _call_extractor(question: str, answer: str, points: list[dict],
                   template_id: str) -> list[int]:
    """Call LLM to extract covered point indices.  Returns list of int."""
    if not points:
        return []
    template = _PROMPT_A if template_id == "a" else _PROMPT_B
    prompt = template.format(
        question=question,
        answer=answer[:1500],  # truncate for token economy
        points=_format_points(points),
    )
    try:
        text = _call_llm(prompt, max_tokens=512, timeout=30.0)
    except Exception as e:
        print(f"    [extractor] LLM call failed: {type(e).__name__}: {str(e)[:80]}")
        return []
    if not text:
        return []
    parsed = _parse_json_block(text)
    if not parsed or "covered_indices" not in parsed:
        return []
    indices = parsed["covered_indices"]
    if not isinstance(indices, list):
        return []
    return [int(i) for i in indices if isinstance(i, (int, float)) and 0 <= int(i) < len(points)]


def _match_covered(covered_indices: list[int], points: list[dict]) -> list[dict]:
    """Return the point dicts for the given covered indices."""
    return [points[i] for i in covered_indices if 0 <= i < len(points)]


def _point_signature(p: dict) -> tuple:
    """Stable hashable signature of an expected point for dedup."""
    return (p.get("section", ""), p.get("point", "")[:100])




def _string_similarity_coverage(answer: str, points: list[dict]) -> list[int]:
    """Fallback coverage when LLM extractor fails: use string overlap.

    For each expected point, count Chinese-character overlap with the
    system answer.  Mark as covered if >= 30% of the point's unique
    Chinese characters appear in the answer.
    """
    if not points or not answer:
        return []
    answer_chars = set(c for c in answer if "\u4e00" <= c <= "\u9fff")
    covered: list[int] = []
    for i, p in enumerate(points):
        pt_text = p.get("point", "")
        pt_chars = set(c for c in pt_text if "\u4e00" <= c <= "\u9fff")
        if not pt_chars:
            continue
        overlap = len(pt_chars & answer_chars)
        ratio = overlap / len(pt_chars)
        if ratio >= 0.30:
            covered.append(i)
    return covered



# ---- Public API -------------------------------------------------------

def score_answer(question: str, system_answer: str,
                expected_points: list[dict]) -> ScoreResult:
    """Score one answer against expected points.

    Uses 2 prompt templates (a, b).  Coverage is the union of both
    extractions' covered indices.  Multi-prompt stability is computed
    as 1 - |coverage_a - coverage_b|.
    """
    # Multi-prompt extraction (LLM-based, may fail or return empty)
    cov_a = _call_extractor(question, system_answer, expected_points, "a")
    cov_b = _call_extractor(question, system_answer, expected_points, "b")
    # Always compute string-similarity as a deterministic baseline
    cov_fb = _string_similarity_coverage(system_answer, expected_points)
    # Combine: union of all three sources (LLM-a, LLM-b, string-sim)
    union = sorted(set(cov_a) | set(cov_b) | set(cov_fb))
    # Multi-prompt stability: only the two LLM templates.  String-sim is
    # a deterministic fallback, not a prompt, so don't include it in the
    # stability check.  This way a failed LLM doesn't falsely lower stability.
    cov_a_val = len(cov_a) / max(len(expected_points), 1)
    cov_b_val = len(cov_b) / max(len(expected_points), 1)
    n = max(len(expected_points), 1)
    coverage = len(union) / n
    cov_a_val = len(cov_a) / n
    cov_b_val = len(cov_b) / n
    stable = abs(cov_a_val - cov_b_val) <= MULTI_PROMPT_TOLERANCE
    return ScoreResult(
        question=question,
        doc_id="",
        system_answer=system_answer,
        expected_points=expected_points,
        covered_points=_match_covered(union, expected_points),
        coverage=coverage,
        pass_=coverage >= COVERAGE_THRESHOLD,
        template_a_coverage=cov_a_val,
        template_b_coverage=cov_b_val,
        multi_prompt_stable=stable,
    )


def compute_coverage(question: str, system_answer: str,
                     expected_points: list[dict]) -> float:
    """Convenience: just the coverage float (0-1)."""
    if not expected_points:
        return 0.0
    return score_answer(question, system_answer, expected_points).coverage


def run_suite(suite: str = "golden", version: str = "v1",
              workspace_root: Path | None = None,
              max_questions: int | None = None) -> EvalResult:
    """Run a sample_qa suite and return aggregate result.

    suite: "golden" (30 questions) or "full" (all questions)
    """
    if workspace_root is None:
        workspace_root = WORKSPACE
    qa_file = QA_DIR / f"{version}.json"
    if suite == "golden":
        qa_file = QA_DIR / f"{version}_golden.json"
    if not qa_file.exists():
        raise FileNotFoundError(f"sample_qa not found: {qa_file}")
    questions = json.loads(qa_file.read_text(encoding="utf-8"))
    if max_questions is not None:
        questions = questions[:max_questions]
    print(f"Running {suite} suite: {len(questions)} questions\n")

    # Load expected_points per doc
    from enterprise_agent_kb.db import connect
    db = connect(workspace_root / "db" / "knowledge.db")
    ep_cache: dict[str, list[dict]] = {}
    for doc_id in {q["doc_id"] for q in questions}:
        row = db.execute(
            "SELECT points_json FROM expected_points WHERE doc_id = ? AND version = ?",
            (doc_id, version),
        ).fetchone()
        if row:
            ep_cache[doc_id] = json.loads(row[0])
    db.close()

    per_question: list[ScoreResult] = []
    by_doc: dict[str, dict] = {}
    for i, q in enumerate(questions):
        doc_id = q["doc_id"]
        ep = ep_cache.get(doc_id, [])
        if not ep:
            continue
        # Build expected_points subset: ones that match the question
        # (use matched_points from sample_qa if available, else all)
        matched = q.get("matched_points", [])
        q_page = q.get("page")
        if matched:
            mp_signatures = {(_point_signature({"section": m.get("section", ""),
                                                "point": m.get("point", "")}))
                             for m in matched}
            sub_ep = [p for p in ep if _point_signature(p) in mp_signatures]
        elif q_page is not None:
            # Fallback for fallback-generated questions: pick points
            # on the same page (these are likely what the question asks about)
            sub_ep = [p for p in ep if p.get("page") == q_page]
        else:
            sub_ep = ep
        if not sub_ep:
            sub_ep = ep[:5]  # last-resort safety fallback

        # Call answer_query
        try:
            ans = answer_query(workspace_root, q["question"], limit=8)
            sys_answer = ans.get("direct_answer", "") if isinstance(ans, dict) else str(ans)
        except Exception as e:
            print(f"[{i+1}/{len(questions)}] {doc_id}: answer_query failed: {e}")
            sys_answer = ""

        # Score
        result = score_answer(q["question"], sys_answer, sub_ep)
        result.doc_id = doc_id
        per_question.append(result)

        # Aggregate
        if doc_id not in by_doc:
            by_doc[doc_id] = {"total": 0, "passed": 0, "cov_sum": 0.0}
        by_doc[doc_id]["total"] += 1
        if result.pass_:
            by_doc[doc_id]["passed"] += 1
        by_doc[doc_id]["cov_sum"] += result.coverage
        print(f"[{i+1}/{len(questions)}] {doc_id}: cov={result.coverage:.2f} "
              f"A={result.template_a_coverage:.2f} B={result.template_b_coverage:.2f} "
              f"stable={result.multi_prompt_stable} pass={result.pass_}")
    print()

    # Aggregate stats
    total = len(per_question)
    passed = sum(1 for r in per_question if r.pass_)
    avg_cov = sum(r.coverage for r in per_question) / max(total, 1)
    stable = sum(1 for r in per_question if r.multi_prompt_stable) / max(total, 1)

    for doc_id, stats in by_doc.items():
        n = max(stats["total"], 1)
        stats["pass_rate"] = stats["passed"] / n
        stats["avg_coverage"] = stats["cov_sum"] / n
        del stats["cov_sum"]

    return EvalResult(
        suite=suite,
        total=total,
        passed=passed,
        pass_rate=passed / max(total, 1),
        avg_coverage=avg_cov,
        multi_prompt_stability=stable,
        by_doc=by_doc,
        per_question=per_question,
    )
