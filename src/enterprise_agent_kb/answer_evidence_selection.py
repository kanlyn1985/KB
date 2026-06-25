from __future__ import annotations

import re
from pathlib import Path

from .config import AppPaths
from .db import connect

"""Evidence judgement gating, downgrade logic, and evidence selection for answer generation."""


def _should_block_unconstrained_answer(context: dict[str, object], exact_terms: list[str]) -> bool:
    if not exact_terms:
        return False
    # If standard_lookup found a document_standard fact, don't block
    context_facts = context.get("facts", [])
    if any(f.get("fact_type") == "document_standard" for f in context_facts if isinstance(f, dict)):
        return False
    judgement = context.get("evidence_judgement")
    if not isinstance(judgement, dict):
        return False
    if bool(judgement.get("sufficient")):
        return False
    missing = {str(item).upper() for item in judgement.get("missing_anchors") or []}
    requested = {term.upper() for term in exact_terms}
    best_fact_ids = [str(item) for item in judgement.get("best_fact_ids") or [] if item]
    best_evidence_ids = [str(item) for item in judgement.get("best_evidence_ids") or [] if item]
    return bool(missing & requested) or (not best_fact_ids and not best_evidence_ids)


def _empty_context_from_judgement(query: str, context: dict[str, object]) -> dict[str, object]:
    return {
        "query": query,
        "hit_count": 0,
        "documents": [],
        "hits": [],
        "evidence": [],
        "facts": [],
        "entities": [],
        "graph_edges": [],
        "wiki_pages": [],
        "evidence_judgement": context.get("evidence_judgement"),
    }


def _should_downgrade_for_insufficient_evidence(
    context: dict[str, object],
    answer_mode: str,
    fallback_reason: str,
    query_type: str,
) -> bool:
    judgement = context.get("evidence_judgement")
    if not isinstance(judgement, dict):
        return False
    if bool(judgement.get("sufficient")):
        return False
    if fallback_reason in {"fallback_to_related_concept", "clarification_required"}:
        return False
    # standard_lookup with a document_standard fact keeps the standard code as
    # the core answer even when the judge (expecting term_definition) says
    # insufficient. This exemption must run BEFORE the P0 confidence gate so a
    # missing-confidence standard_lookup is not wrongly degraded.
    if answer_mode == "standard_lookup" and query_type == "standard_lookup":
        context_facts = context.get("facts", [])
        if any(f.get("fact_type") == "document_standard" for f in context_facts if isinstance(f, dict)):
            return False
        return True
    # P0 (Sprint 3): hard-degrade when evidence_judge is insufficient AND has
    # near-zero confidence. This catches cross-doc routing misses where no
    # real evidence/fact was judged (best_evidence_ids/best_fact_ids empty,
    # confidence ~0.0) yet build_direct_answer still stitches a low-quality
    # section-title answer. Honest degradation: surface 'insufficient evidence'
    # instead of a wrong section heading. NOTE: this does NOT lift pass_rate
    # (a not-found answer still fails token_overlap) — it is a safety/honesty
    # guard. High-confidence insufficient cases (e.g. suff=False conf=0.95)
    # are left for P1 doc-selection to fix.
    try:
        conf = float(judgement.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    if conf < 0.2:
        return True
    return False


def _build_insufficient_evidence_answer(context: dict[str, object]) -> str:
    judgement = context.get("evidence_judgement") if isinstance(context.get("evidence_judgement"), dict) else {}
    missing = [str(item) for item in judgement.get("missing_anchors") or [] if str(item).strip()]
    rejected = [str(item) for item in judgement.get("rejected_reasons") or [] if str(item).strip()]
    shape_diagnostics = judgement.get("shape_diagnostics") if isinstance(judgement.get("shape_diagnostics"), dict) else {}
    shape_contract = shape_diagnostics.get("shape_contract") if isinstance(shape_diagnostics.get("shape_contract"), dict) else {}
    allowed_shapes = [str(item) for item in shape_contract.get("allowed_shapes") or [] if str(item).strip()]
    parts = ["当前候选证据不足以给出确定性答案。"]
    if missing:
        parts.append(f"缺少关键锚点：{'、'.join(missing[:5])}。")
    if allowed_shapes:
        parts.append(f"期望证据形状：{'、'.join(allowed_shapes[:5])}。")
    if rejected:
        parts.append(f"主要原因：{rejected[0]}")
    else:
        reason = str(judgement.get("reason") or "").strip()
        if reason:
            parts.append(f"主要原因：{reason}")
    return "".join(parts)


def _select_supporting_evidence(
    workspace_root: Path,
    facts: list[dict[str, object]],
    query: str,
    intent: str,
) -> list[dict[str, object]]:
    fact_ids = [item["fact_id"] for item in facts[:6] if item.get("fact_id")]
    if not fact_ids:
        return []

    paths = AppPaths.from_root(workspace_root)
    connection = connect(paths.db_file)
    try:
        placeholders = ",".join("?" for _ in fact_ids)
        rows = connection.execute(
            f"""
            SELECT DISTINCT e.evidence_id, e.doc_id, e.page_no, e.confidence, e.risk_level, e.normalized_text
            FROM fact_evidence_map m
            JOIN evidence e ON e.evidence_id = m.evidence_id
            WHERE m.fact_id IN ({placeholders})
            """,
            fact_ids,
        ).fetchall()
        evidence = [dict(row) for row in rows]
        return _rank_evidence(evidence, query, intent)
    finally:
        connection.close()


def _rank_evidence(evidence: list[dict[str, object]], query: str, intent: str) -> list[dict[str, object]]:
    def score(item: dict[str, object]) -> tuple[float, float]:
        text = item.get("normalized_text", "")
        confidence = float(item.get("confidence") or 0)
        bonus = 0.0
        if intent == "definition":
            if "##" in text and any(token in text for token in (" control pilot ", "控制导引电路", "定义", "术语")):
                bonus += 2.5
            if "##" in text:
                bonus += 0.5
        elif intent == "standard":
            if re.search(r"\d{4}-\d{2}-\d{2}\s*(发布|实施)", text):
                bonus += 1.5
            if re.search(r"\bGB/T\b", text):
                bonus += 1.0
        elif intent == "parameter":
            if "<table" in text.lower() or "|" in text:
                bonus += 1.5
            if re.search(r"(Ω|电阻|阻值|R\d+|检测点\s*\d|CC1|CC2)", text, re.I):
                bonus += 1.6
            if "目 次" in text or "前    言" in text or "前言" in text:
                bonus -= 2.0
        elif intent == "process":
            if "<table" in text.lower() or "|" in text:
                bonus += 1.3
            if re.search(r"(时序|状态|握手|预充|停机|检测点|控制导引)", text):
                bonus += 1.8
            if "目 次" in text or "前    言" in text or "前言" in text:
                bonus -= 2.2
        else:
            if "<table" in text.lower():
                bonus -= 1.2
            if "##" in text:
                bonus += 0.6
            if any(token in text for token in ("定义", "范围", "适用于")):
                bonus += 0.4
        if query and query.replace("？", "").replace("?", "")[:8] in text:
            bonus += 0.8
        return (bonus + confidence, confidence)

    return sorted(evidence, key=score, reverse=True)
