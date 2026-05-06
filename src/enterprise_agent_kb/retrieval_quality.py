from __future__ import annotations

import re
import unicodedata


def evaluate_retrieval_quality(
    *,
    case: dict[str, object],
    retrieved_items: list[dict[str, object]],
    trace_metrics: dict[str, object] | None = None,
    k_values: tuple[int, ...] = (5, 10),
) -> dict[str, object]:
    """Score whether retrieval results contain the case anchors before answer generation."""

    metrics = trace_metrics or {}
    must_hit = _string_list(case.get("retrieval_must_hit") or case.get("must_hit") or case.get("must_include"))
    negative_expected = _string_list(case.get("negative_expected"))
    normalized_must = [_normalize(item) for item in must_hit if _normalize(item)]
    normalized_negative = [_normalize(item) for item in negative_expected if _normalize(item)]
    item_texts = [_item_text(item) for item in retrieved_items if isinstance(item, dict)]
    normalized_items = [_normalize(text) for text in item_texts]

    matched_ranks: list[int] = []
    missing_must_hit: list[str] = []
    for original, anchor in zip(must_hit, normalized_must, strict=False):
        rank = _first_matching_rank(anchor, normalized_items)
        if rank is None:
            missing_must_hit.append(original)
        else:
            matched_ranks.append(rank)

    negative_hits: list[dict[str, object]] = []
    for original, anchor in zip(negative_expected, normalized_negative, strict=False):
        rank = _first_matching_rank(anchor, normalized_items)
        if rank is not None:
            negative_hits.append({"anchor": original, "rank": rank})

    must_total = len(normalized_must)
    must_found = len(matched_ranks)
    best_rank = min(matched_ranks) if matched_ranks else None
    result: dict[str, object] = {
        "must_hit_total": must_total,
        "must_hit_found": must_found,
        "must_hit_missing": missing_must_hit,
        "must_hit_best_rank": best_rank,
        "mrr": round(1.0 / best_rank, 6) if best_rank else 0.0,
        "negative_hit_count": len(negative_hits),
        "negative_hits": negative_hits,
        "negative_hit_rate": round(len(negative_hits) / max(1, len(normalized_negative)), 6),
        "top_k": max(k_values) if k_values else len(retrieved_items),
        "hit_count": len(retrieved_items),
        "failure_attribution": _failure_attribution(
            must_total=must_total,
            must_found=must_found,
            best_rank=best_rank,
            negative_hits=negative_hits,
            trace_metrics=metrics,
        ),
    }
    for k in k_values:
        found_at_k = sum(1 for rank in matched_ranks if rank <= k)
        result[f"recall_at_{k}"] = round(found_at_k / max(1, must_total), 6)
    return result


def _failure_attribution(
    *,
    must_total: int,
    must_found: int,
    best_rank: int | None,
    negative_hits: list[dict[str, object]],
    trace_metrics: dict[str, object],
) -> str:
    if negative_hits:
        return "negative_hit"
    if must_total and must_found <= 0:
        if int(trace_metrics.get("graph_candidate_count") or 0) <= 0 and _expects_graph(trace_metrics):
            return "graph_not_engaged"
        if float(trace_metrics.get("topic_resolution_confidence") or 0.0) <= 0:
            return "topic_resolution_empty"
        if not trace_metrics.get("top_hit_ids"):
            return "retrieval_empty"
        return "retrieval_miss"
    if best_rank and best_rank > 5:
        return "rank_too_low"
    return "ok"


def _expects_graph(trace_metrics: dict[str, object]) -> bool:
    channels = [str(item) for item in trace_metrics.get("retrieval_channels") or []]
    query_type = str(trace_metrics.get("query_type") or "")
    return "graph" in channels and query_type in {"definition", "parameter_lookup", "timing_lookup", "lifecycle_lookup"}


def _first_matching_rank(anchor: str, normalized_items: list[str]) -> int | None:
    if _looks_like_structured_code_anchor(anchor):
        for index, item in enumerate(normalized_items, start=1):
            if anchor and anchor in item:
                return index
        return None
    tokens = _anchor_tokens(anchor)
    for index, item in enumerate(normalized_items, start=1):
        if anchor and anchor in item:
            return index
        if len(tokens) >= 2 and all(token in item for token in tokens):
            return index
    return None


def _looks_like_structured_code_anchor(anchor: str) -> bool:
    return bool(re.fullmatch(r"[a-z]{2,6}\.\d+(?:\.bp\d+)?|[a-z]{2,6}\d+bp\d+", anchor, re.I))


def _anchor_tokens(anchor: str) -> list[str]:
    value = str(anchor or "")
    raw_tokens = re.findall(r"[a-z]{2,}|\d+(?:\.\d+)?|[\u4e00-\u9fff]+", value, flags=re.I)
    tokens: list[str] = []
    for token in raw_tokens:
        normalized = _normalize(token)
        normalized = normalized.strip("且和及与的是了")
        if not normalized:
            continue
        if re.fullmatch(r"[a-z]", normalized):
            continue
        if len(normalized) < 2 and not normalized.isdigit():
            continue
        if normalized not in tokens:
            tokens.append(normalized)
    return tokens


def _item_text(item: dict[str, object]) -> str:
    return "\n".join(
        str(value or "")
        for value in (
            item.get("result_type"),
            item.get("result_id"),
            item.get("doc_id"),
            item.get("page_no"),
            item.get("snippet"),
        )
    )


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"\s+", "", text)
    return text
