"""Decomposer: break a query into parts that match the ingestion structure.

Unlike the router (which only classifies a query into a category), the
decomposer extracts the concrete anchors and concept tokens that the matcher
joins against the actual ingestion tables — entity, term, term_alias,
attribute. This keeps query understanding aligned with what was ingested.
"""
from __future__ import annotations

import json
import re

from .legacy_bridge import llm_chat
from .types import QueryDecomposition


_DECOMPOSE_SYSTEM_PROMPT = """\
You are a query parser for an automotive engineering knowledge base.
Your ONLY job is to output JSON. Do NOT answer the query, do NOT explain,
do NOT provide information — only output the decomposition JSON.

The knowledge base stores: entity (standards/components), term
(abbreviations/concepts), param (named numeric parameters), attribute
(per-entity key=value pairs), relation (standard-to-standard references).

Return EXACTLY: {"target_artifact": "...", "operation": "...", "scope": str|null, "tokens": [str]}

- target_artifact: one of term, service, attribute, param, relation, entity
- operation: "lookup" or "enumerate"
- scope: standard/component abbreviation (e.g. "CCU","GB/T 18487.1","ISO 14229"), or null
- tokens: concept words including ALL abbreviations (e.g. "cp","v2g","pwm") and CJK terms

CRITICAL: If the query contains ANY abbreviation (cp, v2g, obc, pwm, cc, ccu, can, uds, pe),
it MUST appear in tokens. "cp的幅值范围" → tokens MUST include "cp".

Return ONLY the JSON object, no other text."""


def decompose_query(query: str) -> QueryDecomposition:
    """Decompose a query via the LLM. Falls back to rules on failure."""
    if not query or not query.strip():
        return QueryDecomposition(
            target_artifact="term", operation="lookup", scope=None, tokens=()
        )

    try:
        raw = llm_chat(query, _DECOMPOSE_SYSTEM_PROMPT, max_tokens=1024)
    except Exception:
        return _fallback_decomposition(query)

    data = _parse_json(raw)
    if data is None:
        return _fallback_decomposition(query)

    from .types import _ARTIFACTS

    artifact = str(data.get("target_artifact") or "").strip().lower()
    if artifact not in _ARTIFACTS:
        return _fallback_decomposition(query)

    operation = str(data.get("operation") or "lookup").strip().lower()
    if operation not in ("lookup", "enumerate"):
        operation = "lookup"

    scope = (str(data.get("scope") or "").strip() or None)

    tokens_raw = data.get("tokens") or []
    if not isinstance(tokens_raw, list):
        tokens_raw = []
    tokens = tuple(
        str(t).strip() for t in tokens_raw
        if str(t).strip() and str(t).strip() != scope
    )

    # Ensure short abbreviations from the query are always in tokens,
    # even if the LLM missed them. Critical for queries like "cp幅值范围".
    if not scope:
        abbr_extra = re.findall(r"[a-zA-Z]{2,4}", query)
        for a in abbr_extra:
            a_upper = a.upper()
            if a_upper not in ("GB", "ISO", "IEC", "QC") and a_upper not in tokens:
                tokens = tokens + (a_upper,)

    return QueryDecomposition(
        target_artifact=artifact,
        operation=operation,
        scope=scope,
        tokens=tokens,
    )


def _fallback_decomposition(query: str) -> QueryDecomposition:
    """Minimal rule-based decomposition when the LLM is unavailable."""
    operation = "enumerate" if re.search(r"有哪些|哪些|所有|全部", query) else "lookup"

    # Hex code → service lookup
    m = re.search(r"\b0x[0-9A-Fa-f]{2}\b", query)
    if m:
        return QueryDecomposition(
            target_artifact="service", operation=operation,
            scope=None, tokens=(m.group(0),),
        )

    # Standard/component anchor as scope
    scope = None
    m = re.search(r"(GB/T|GBT|ISO|IEC|QC/T|SAE)\s*[A-Z]?\s*[\d.:\-]+", query)
    if m:
        scope = m.group(0).strip()

    # Also catch product abbreviations as scope (CCU, OBC, V2G, etc.)
    # \b doesn't work across Latin/CJK boundaries, so use case-insensitive
    # substring matching with CJK-aware boundaries.
    if not scope:
        for abbr in ("CCU", "OBC", "V2G", "V2L", "V2V", "DCDC", "EVCC", "CP", "PWM", "CAN"):
            if re.search(rf"(?:^|[^A-Za-z]){abbr}(?:[^A-Za-z]|$)", query, re.I):
                scope = abbr
                break

    # Relation queries
    if re.search(r"引用|参考标准|引用了哪些", query):
        return QueryDecomposition(
            target_artifact="relation", operation=operation, scope=scope, tokens=()
        )

    tokens = tuple(re.findall(r"[一-鿿]{2,8}", query))

    # Attribute queries: scoped + asks for value/list
    if scope and (operation == "enumerate" or re.search(r"是多少|多大|阈值|限值|要求|保护", query)):
        artifact = "attribute"
    elif re.search(r"\d+\s*跳|包含哪些标准", query):
        return QueryDecomposition(
            target_artifact="relation", operation="enumerate", scope=scope, tokens=tokens
        )
    else:
        artifact = "term"
        if not scope:
            # Catch abbreviations that may be adjacent to CJK characters.
            # \b doesn't work across Latin/CJK boundaries.
            abbr = re.findall(r"\b[A-Z][A-Za-z0-9\-]{1,10}\b", query)
            if not abbr:
                abbr = re.findall(r"[a-zA-Z]{2,4}", query)
            if abbr and abbr[0].upper() not in ("GB", "ISO", "IEC", "QC"):
                tokens = tuple(list(tokens) + [abbr[0].upper()]) if not tokens else tokens

    return QueryDecomposition(
        target_artifact=artifact, operation=operation, scope=scope, tokens=tokens
    )


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
