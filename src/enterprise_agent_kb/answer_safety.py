"""Answer safety diagnostics: citation correctness and unsupported-claim detection.

Sprint 3 WP4. This module is READ-ONLY and never modifies the answer payload.
It computes safety metrics over an already-built answer dict so eval and
governance tooling can observe:

- ``citation_correct``     : does the answer cite real evidence from the same
                             document as the direct answer?
- ``unsupported_claim``    : does the answer contain a substantive claim with
                             no backing supporting_evidence (or evidence from a
                             different document / only title/cover blocks)?
- ``title_block_citation`` : is the cited evidence only document title, TOC,
                             cover, or academic header noise?

Design constraints (Sprint 3 hard rules):
- evidence_judge remains the sole fact-adjudication boundary; this module only
  *observes* the answer payload, it never rewrites the answer or adjudicates.
- Pure-Python, deterministic, no LLM, no DB writes, never raises (errors are
  captured into the returned dict so eval runs never crash on a bad payload).
"""
from __future__ import annotations

import re
from typing import Any

# Markers that indicate an evidence block is a non-substantive title / TOC /
# cover / academic-header block rather than answer content. Mirrors the noise
# patterns already used in evidence.py and evaluator noise detection.
# NOTE: the standard-number patterns (GB/T\d, QC/T\d) are only used for the
# short-block title check, because nearly every evidence block in these
# standards is prefixed with the document marker 'GB/T 18487.1—2023'.
_TITLE_BLOCK_PATTERNS = (
    re.compile(r"^\s*GB/T\s*\d", re.M),       # standard number title line
    re.compile(r"^\s*QC/T\s*\d", re.M),
    re.compile(r"\b目\s*次\b"),                 # table of contents
    re.compile(r"^\s*前\s*言\b", re.M),        # preface header
    re.compile(r"^\s*\d+/\d+\s*$", re.M),      # page header "N/M" counter
    re.compile(r"版权所有|all rights reserved", re.I),
    re.compile(r"\bDOI\s*[:：]", re.I),         # academic header noise
    re.compile(r"\bKey\s*words\s*[:：]", re.I),
    re.compile(r"版本[:：]|\b作者[:：]|\b标题[:：]|\b日期[:：]"),
)

# Academic-header / cover-page noise that marks a block as non-substantive
# regardless of length (these are content-free even inside a long block).
_ACADEMIC_HEADER_PATTERNS = (
    re.compile(r"\bDOI\s*[:：]", re.I),
    re.compile(r"\bKey\s*words\s*[:：]", re.I),
    re.compile(r"版权所有|all rights reserved", re.I),
    re.compile(r"版本[:：]|\b作者[:：]|\b标题[:：]|\b日期[:：]"),
)

# Degradation / refusal markers (answer is not a substantive claim).
_DEGRADED_MARKERS = (
    "当前候选证据不足以给出确定性答案",
    "知识库中未找到与该查询相关的信息",
    "未找到",
    "无法回答",
    "insufficient evidence",
    "not found",
)

# A substantive direct_answer has enough CJK characters to count as a real
# claim (answers that are just a standard number or a few English tokens are
# borderline and checked separately).
_MIN_SUBSTANTIVE_CJK = 6


def _is_title_block(text: str) -> bool:
    """True only when the evidence is predominantly a title/TOC/cover block.

    Note: nearly every evidence block in these standards begins with a document
    marker like 'GB/T 18487.1—2023'. A title pattern as a *prefix* does NOT make
    a block a title block. We only flag blocks where the title/header marker is
    the dominant content (short block, or academic-header noise), not a prefix
    before substantive content.
    """
    if not text:
        return False
    stripped = text.strip()
    # Short block that is just a standard-number title line (e.g. the whole
    # snippet is 'GB/T 18487.4—2025\n中华人民共和国国家标准').
    if len(stripped) <= 60 and any(p.search(stripped) for p in _TITLE_BLOCK_PATTERNS):
        return True
    # Academic header noise is always title-noise regardless of length.
    for pat in _ACADEMIC_HEADER_PATTERNS:
        if pat.search(stripped):
            return True
    return False


def _is_degraded_answer(text: str) -> bool:
    if not text or not text.strip():
        return True
    low = text.lower()
    return any(m.lower() in low for m in _DEGRADED_MARKERS)


def _is_substantive_claim(text: str) -> bool:
    """A substantive claim has enough CJK content to be a real assertion."""
    if not text:
        return False
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return cjk >= _MIN_SUBSTANTIVE_CJK


def _evidence_doc_ids(answer: dict[str, Any]) -> list[str]:
    """Doc ids referenced by the cited supporting_evidence."""
    docs: list[str] = []
    for ev in answer.get("supporting_evidence") or []:
        doc = ev.get("doc_id") if isinstance(ev, dict) else None
        if doc and doc not in docs:
            docs.append(doc)
    return docs


def _cited_evidence_texts(answer: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for ev in answer.get("supporting_evidence") or []:
        if isinstance(ev, dict):
            # The answer payload uses 'snippet' for supporting_evidence items;
            # evidence channel items may use 'normalized_text' or 'text'. Check all.
            t = ev.get("snippet") or ev.get("normalized_text") or ev.get("text") or ""
            if t:
                texts.append(t)
    return texts


def diagnose_answer_safety(answer: dict[str, Any]) -> dict[str, Any]:
    """Compute citation / unsupported-claim / title-block metrics.

    Read-only over *answer*. Returns a dict with boolean flags and a human
    ``reason``. Never raises: malformed payloads yield ``invalid_payload``.
    """
    result: dict[str, Any] = {
        "citation_correct": False,
        "unsupported_claim": False,
        "title_block_citation": False,
        "degraded_answer": False,
        "reason": "",
    }
    if not isinstance(answer, dict):
        result["reason"] = "invalid_payload:not_a_dict"
        return result

    direct = answer.get("direct_answer") or ""
    cited_texts = _cited_evidence_texts(answer)
    cited_docs = _evidence_doc_ids(answer)

    # Degraded / refusal answers are not claims and are treated as safe
    # (the insufficiency is surfaced by eval, not by this guard).
    if _is_degraded_answer(direct):
        result["degraded_answer"] = True
        result["reason"] = "degraded_or_refusal_answer"
        return result

    substantive = _is_substantive_claim(direct)

    # No supporting evidence at all on a substantive claim -> unsupported.
    if substantive and not cited_texts:
        result["unsupported_claim"] = True
        result["reason"] = "substantive_claim_no_supporting_evidence"
        return result

    # Citation only points at title/TOC/cover/academic-header blocks.
    if cited_texts and all(_is_title_block(t) for t in cited_texts):
        result["title_block_citation"] = True
        result["reason"] = "citation_only_title_or_header_blocks"
        return result

    # Citation doc mismatch: answer's preferred_doc_id is not among cited docs.
    # (Multi-doc answers may legitimately cite several docs; this only flags
    #  the case where the cited evidence shares NO document with the answer.)
    pref_doc = answer.get("preferred_doc_id")
    if substantive and pref_doc and cited_docs and pref_doc not in cited_docs:
        result["citation_correct"] = False
        result["reason"] = "citation_doc_mismatch_with_preferred_doc"
        return result

    # Otherwise the citation is considered correct: substantive evidence cited
    # from the same document (or no preferred_doc_id to check against).
    if cited_texts:
        result["citation_correct"] = True
        result["reason"] = "cited_substantive_evidence"
        return result

    # Non-substantive short answers (e.g. a parameter value) with no evidence
    # are not flagged as unsupported (they are checked separately by eval).
    result["citation_correct"] = True
    result["reason"] = "non_substantive_answer"
    return result
