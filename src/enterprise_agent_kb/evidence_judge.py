from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field

from .evidence_shapes import (
    EvidenceShape,
    SCORED_ROW,
    active_shapes,
    allowed_evidence_shapes_for_query,
    best_shape,
    bp_codes_from_text,
    diagnose_shape_contract_failure,
    evidence_shape_matches_contract,
    evidence_shape_required,
    is_parameter_definition_query,
    is_preface_or_index_blob,
    is_process_activity_query,
    is_signal_state_query,
    is_term_definition_query,
    is_timing_query,
    looks_like_exact_signal_state_blob,
    looks_like_process_activity_blob,
    looks_like_timing_blob,
    normalize,
    process_codes_from_text,
    shape_diagnostics,
)
from .query_semantic_parser import _call_astron_text, _extract_json_block
from .graph_retrieval import STRONG_RELATIONS_BY_QUERY_TYPE
from .exceptions import LLMError, NetworkError, TimeoutError


EVIDENCE_JUDGE_PROMPT_VERSION = "v0.1.0"

EVIDENCE_JUDGE_SYSTEM_PROMPT = """你是标准文档知识库的 RAG 证据判定器。

你的任务不是回答用户问题，而是判断给定候选 evidence/fact 是否足以支撑回答。

规则：
1. 只能基于输入的候选证据判断，不得引入外部知识。
2. best_fact_ids 和 best_evidence_ids 只能从候选列表中选择。
3. 如果证据只包含相似主题但缺少关键数值、表号、条款号或对象，应判定为 insufficient。
4. 如果证据足够，说明它覆盖了哪些关键锚点。
5. 输出必须是单个 JSON 对象，不允许 markdown 或解释文本。

JSON 字段：
- sufficient: 布尔值
- confidence: 0 到 1 的数字
- best_fact_ids: 字符串数组
- best_evidence_ids: 字符串数组
- rejected_reasons: 字符串数组
- suggested_followup_queries: 字符串数组
- reason: 字符串
"""


@dataclass(frozen=True)
class EvidenceJudgement:
    sufficient: bool
    confidence: float
    matched_anchors: list[str]
    missing_anchors: list[str]
    best_evidence_ids: list[str]
    best_fact_ids: list[str]
    rejected_reasons: list[str]
    suggested_followup_queries: list[str]
    reason: str
    evidence_shape: str | None = None
    shape_diagnostics: dict[str, object] = field(default_factory=dict)
    judge_source: str = "rules"
    used_llm: bool = False
    prompt_version: str = EVIDENCE_JUDGE_PROMPT_VERSION

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def judge_evidence(
    query: str,
    context: dict[str, object],
    expansion: dict[str, object] | None = None,
    *,
    use_llm: bool = True,
    force_llm: bool = False,
) -> EvidenceJudgement:
    """Decide whether the candidate facts+evidence are sufficient for *query*.

    Always computes a rule-based judgement (the cheap path); only delegates to
    the LLM judge when the rule-based pass is uncertain or `force_llm=True`.
    """
    rule_judgement = _rule_judge_evidence(query, context, expansion or {})
    if not _should_use_llm_judge(rule_judgement, use_llm=use_llm, force_llm=force_llm):
        return rule_judgement
    anchors = _anchors(query, expansion or {})
    return _judge_with_llm(
        query=query,
        context=context,
        expansion=expansion or {},
        anchors=anchors,
        rule_judgement=rule_judgement,
        force_llm=force_llm,
    )


def _rule_judge_evidence(
    query: str,
    context: dict[str, object],
    expansion: dict[str, object],
) -> EvidenceJudgement:
    """Cheap, deterministic evidence judgement — no LLM calls.

    Stages: (1) collect candidates, (2) score each candidate against the
    query anchors and active evidence shapes, (3) decide sufficiency using
    top score + missing-anchor count + shape contract, (4) build a
    human-readable reason.
    """
    anchors = _anchors(query, expansion)
    query_type = _query_type_from_context(context)
    strong_relations = _strong_relations_for(query_type)
    facts = list(context.get("facts") or [])
    evidence = list(context.get("evidence") or [])
    candidates = [
        *_candidate_items("fact", facts),
        *_candidate_items("evidence", evidence),
    ]
    active_shape_items = active_shapes(query, query_type)
    scored: list[SCORED_ROW] = _score_candidates(query, candidates, anchors, active_shape_items, strong_relations)
    matched_anchors, best_fact_ids, best_evidence_ids = _collect_top_hits(scored[:5])
    missing = [anchor for anchor in anchors if anchor not in matched_anchors]
    top_score = scored[0][0] if scored else 0.0
    allowed_shapes = allowed_evidence_shapes_for_query(query, query_type)
    selected_shape = best_shape(scored, allowed_shapes)
    shape_sufficiency = _shape_sufficiency(query, query_type, active_shape_items, scored)
    sufficient = top_score >= 1.1 and len(missing) <= max(0, len(anchors) // 3) and shape_sufficiency["sufficient"]

    rejected = _rejection_notes(query, scored)
    followups = [] if sufficient else _followup_queries(query, missing, expansion)
    confidence = min(0.95, max(0.0, top_score / 1.8))
    diagnostics = shape_diagnostics(query, active_shape_items, scored)
    diagnostics["shape_sufficiency"] = shape_sufficiency
    diagnostics["shape_contract"] = {
        "query_type": query_type,
        "allowed_shapes": list(allowed_shapes),
        "required": evidence_shape_required(query_type),
        "matched": evidence_shape_matches_contract(query_type, selected_shape),
    }
    diagnostics["shape_contract_diagnosis"] = diagnose_shape_contract_failure(
        query=query,
        query_type=query_type,
        selected_shape=selected_shape,
        candidate_shape_counts=diagnostics.get("candidate_shape_counts") if isinstance(diagnostics.get("candidate_shape_counts"), dict) else {},
        top_shape_counts=diagnostics.get("top_shape_counts") if isinstance(diagnostics.get("top_shape_counts"), dict) else {},
    )
    if evidence_shape_required(query_type) and evidence_shape_matches_contract(query_type, selected_shape) is not True:
        sufficient = False
        rejected.append(
            f"evidence shape contract mismatch: query_type={query_type}, expected={','.join(allowed_shapes) or '-'}, actual={selected_shape or '-'}"
        )
    reason = _select_reason(query, query_type, scored, sufficient, selected_shape, active_shape_items, strong_relations)
    return EvidenceJudgement(
        sufficient=sufficient,
        confidence=round(confidence, 3),
        matched_anchors=matched_anchors[:12],
        missing_anchors=missing[:12],
        best_evidence_ids=best_evidence_ids[:5],
        best_fact_ids=best_fact_ids[:8],
        rejected_reasons=rejected[:6],
        suggested_followup_queries=followups[:6],
        reason=reason,
        evidence_shape=selected_shape,
        shape_diagnostics=diagnostics,
    )


def _score_candidates(
    query: str,
    candidates: list[tuple[str, dict[str, object]]],
    anchors: list[str],
    active_shape_items: list[object],
    strong_relations: object,
) -> list[SCORED_ROW]:
    """Score each candidate against anchors and active shapes; sort by score desc."""
    scored: list[SCORED_ROW] = []
    for kind, item in candidates:
        blob = _blob(item)
        if _is_preface_or_index_blob(blob):
            continue
        matched = [anchor for anchor in anchors if _contains(blob, anchor)]
        score = len(matched) * 0.22
        shape_hits: list[str] = []
        for shape in active_shape_items:
            contribution = shape.score_candidate(query, kind, item, blob)
            if contribution > 0:
                score += contribution
                shape_hits.append(shape.name)
        if kind == "fact" and _has_strong_graph_support(item, query, strong_relations):
            score += 1.05
        if kind == "fact" and str(item.get("fact_type") or "") == "table_requirement":
            score += 0.18
        scored.append((score, kind, item, matched, shape_hits))
    scored.sort(key=lambda row: row[0], reverse=True)
    return scored


def _collect_top_hits(scored: list[SCORED_ROW]) -> tuple[list[str], list[str], list[str]]:
    """Aggregate matched anchors and best fact/evidence ids from the top-K rows."""
    matched_anchors: list[str] = []
    best_fact_ids: list[str] = []
    best_evidence_ids: list[str] = []
    for _score, kind, item, matched, _shape_hits in scored:
        if _score <= 0:
            continue
        for anchor in matched:
            if anchor not in matched_anchors:
                matched_anchors.append(anchor)
        if kind == "fact" and item.get("fact_id"):
            best_fact_ids.append(str(item["fact_id"]))
        if kind == "evidence" and item.get("evidence_id"):
            best_evidence_ids.append(str(item["evidence_id"]))
    return matched_anchors, best_fact_ids, best_evidence_ids


def _select_reason(
    query: str,
    query_type: str,
    scored: list[SCORED_ROW],
    sufficient: bool,
    selected_shape: str,
    active_shape_items: list[object],
    strong_relations: object,
) -> str:
    """Pick a human-readable explanation that justifies the sufficiency decision."""
    if sufficient and selected_shape:
        return next(
            (shape.reason for shape in active_shape_items if shape.name == selected_shape),
            "top evidence covers expected evidence shape",
        )
    if sufficient and any(_has_strong_graph_support(row[2], query, strong_relations) for row in scored[:5]):
        return "top fact is connected to the query anchor through a trusted graph relation and supporting evidence"
    if sufficient:
        return "top evidence covers required anchors and expected signal-state table"
    return "top evidence does not cover enough required anchors or expected evidence shape"


def _query_type_from_context(context: dict[str, object]) -> str:
    rewrite = context.get("rewrite")
    if isinstance(rewrite, dict):
        return str(rewrite.get("query_type") or "").strip()
    retrieval_plan = context.get("retrieval_plan")
    if isinstance(retrieval_plan, dict):
        return str(retrieval_plan.get("query_type") or "").strip()
    return ""


def _shape_sufficiency(
    query: str,
    query_type: str,
    active_shape_items: list[EvidenceShape],
    scored: list[SCORED_ROW],
) -> dict[str, object]:
    allowed_shapes = set(allowed_evidence_shapes_for_query(query, query_type))
    per_shape = {
        shape.name: bool(shape.is_sufficient(query, scored))
        for shape in active_shape_items
    }
    if allowed_shapes:
        allowed_results = {
            name: matched
            for name, matched in per_shape.items()
            if name in allowed_shapes
        }
        return {
            "mode": "any_allowed_shape",
            "sufficient": any(allowed_results.values()),
            "per_shape": allowed_results,
        }
    return {
        "mode": "all_implied_shapes",
        "sufficient": all(per_shape.values()) if per_shape else True,
        "per_shape": per_shape,
    }


def _should_use_llm_judge(
    judgement: EvidenceJudgement,
    *,
    use_llm: bool,
    force_llm: bool,
) -> bool:
    if force_llm:
        return True
    if not use_llm:
        return False
    if os.environ.get("EAKB_ENABLE_LLM_EVIDENCE_JUDGE", "1") == "0":
        return False
    return not judgement.sufficient or judgement.confidence < 0.75


def _judge_with_llm(
    *,
    query: str,
    context: dict[str, object],
    expansion: dict[str, object],
    anchors: list[str],
    rule_judgement: EvidenceJudgement,
    force_llm: bool = False,
) -> EvidenceJudgement:
    candidates = _llm_candidate_payload(context)
    if not candidates:
        return EvidenceJudgement(
            **{
                **rule_judgement.to_dict(),
                "judge_source": "rules_no_llm_candidates",
                "used_llm": False,
            }
        )
    allowed_fact_ids = {str(item["fact_id"]) for item in candidates if item.get("fact_id")}
    allowed_evidence_ids = {str(item["evidence_id"]) for item in candidates if item.get("evidence_id")}
    try:
        raw = _call_astron_text(
            _llm_judge_prompt(query, anchors, expansion, rule_judgement, candidates),
            system_prompt=EVIDENCE_JUDGE_SYSTEM_PROMPT,
        )
        payload = _extract_json_block(raw)
        best_fact_ids = _filter_allowed_ids(payload.get("best_fact_ids"), allowed_fact_ids, 8)
        best_evidence_ids = _filter_allowed_ids(payload.get("best_evidence_ids"), allowed_evidence_ids, 5)
        llm_sufficient = bool(payload.get("sufficient"))
        if llm_sufficient and not best_fact_ids and not best_evidence_ids:
            llm_sufficient = False
        contract = rule_judgement.shape_diagnostics.get("shape_contract")
        if (
            llm_sufficient
            and isinstance(contract, dict)
            and contract.get("required") is True
            and contract.get("matched") is not True
        ):
            llm_sufficient = False
        confidence = _clamp_confidence(payload.get("confidence"))
        if llm_sufficient:
            return EvidenceJudgement(
                sufficient=True,
                confidence=round(max(rule_judgement.confidence, confidence), 3),
                matched_anchors=rule_judgement.matched_anchors,
                missing_anchors=rule_judgement.missing_anchors,
                best_evidence_ids=best_evidence_ids or rule_judgement.best_evidence_ids,
                best_fact_ids=best_fact_ids or rule_judgement.best_fact_ids,
                rejected_reasons=_merge_unique(
                    rule_judgement.rejected_reasons,
                    _sanitize_string_list(payload.get("rejected_reasons"), 8),
                )[:8],
                suggested_followup_queries=[],
                reason=str(payload.get("reason") or "llm judge found sufficient candidate evidence").strip(),
                evidence_shape=rule_judgement.evidence_shape,
                shape_diagnostics=rule_judgement.shape_diagnostics,
                judge_source="llm",
                used_llm=True,
            )
        return EvidenceJudgement(
            sufficient=False,
            confidence=round(max(rule_judgement.confidence, min(confidence, 0.74)), 3),
            matched_anchors=rule_judgement.matched_anchors,
            missing_anchors=rule_judgement.missing_anchors,
            best_evidence_ids=best_evidence_ids or rule_judgement.best_evidence_ids,
            best_fact_ids=best_fact_ids or rule_judgement.best_fact_ids,
            rejected_reasons=_merge_unique(
                rule_judgement.rejected_reasons,
                _sanitize_string_list(payload.get("rejected_reasons"), 8),
            )[:8],
            suggested_followup_queries=_merge_unique(
                _sanitize_string_list(payload.get("suggested_followup_queries"), 8),
                rule_judgement.suggested_followup_queries,
            )[:8],
            reason=str(payload.get("reason") or rule_judgement.reason).strip(),
            evidence_shape=rule_judgement.evidence_shape,
            shape_diagnostics=rule_judgement.shape_diagnostics,
            judge_source="llm",
            used_llm=True,
        )
    except (LLMError, NetworkError, TimeoutError, RuntimeError, ValueError, json.JSONDecodeError):
        return EvidenceJudgement(
            **{
                **rule_judgement.to_dict(),
                "judge_source": "rules_llm_fallback",
                "used_llm": False,
            }
        )


def _llm_candidate_payload(context: dict[str, object]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for item in list(context.get("facts") or [])[:10]:
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "kind": "fact",
                "fact_id": item.get("fact_id"),
                "evidence_id": item.get("evidence_id"),
                "fact_type": item.get("fact_type"),
                "doc_id": item.get("doc_id"),
                "page": item.get("page"),
                "text": _clip_text(_blob(item), 1200),
            }
        )
    for item in list(context.get("evidence") or [])[:8]:
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "kind": "evidence",
                "evidence_id": item.get("evidence_id"),
                "doc_id": item.get("doc_id"),
                "page": item.get("page"),
                "text": _clip_text(_blob(item), 900),
            }
        )
    return candidates[:14]


def _llm_judge_prompt(
    query: str,
    anchors: list[str],
    expansion: dict[str, object],
    rule_judgement: EvidenceJudgement,
    candidates: list[dict[str, object]],
) -> str:
    payload = {
        "prompt_version": EVIDENCE_JUDGE_PROMPT_VERSION,
        "user_query": query,
        "required_anchors": anchors,
        "expansion_intents": expansion.get("intent_candidates") or [],
        "rule_judgement": rule_judgement.to_dict(),
        "candidate_evidence": candidates,
    }
    return "请判断候选证据是否足以回答用户问题，并输出 JSON。\n" + json.dumps(payload, ensure_ascii=False)


def _anchors(query: str, expansion: dict[str, object]) -> list[str]:
    anchors: list[str] = []

    def add(value: str) -> None:
        text = str(value or "").strip()
        if re.fullmatch(r"[A-Z]", text, re.I):
            return
        if text and text not in anchors:
            anchors.append(text)

    for pattern in [
        r"([+-]?\d+(?:\.\d+)?\s*V)",
        r"(?<![A-Za-z0-9.])([A-Z]{2,6}\d*)(?![A-Za-z0-9.])",
        r"(检测点\s*\d+)",
        r"(表\s*[A-Z]\s*[.．]\s*\d+|表\s*\d+(?:\.\d+)*)",
    ]:
        for match in re.finditer(pattern, query, re.I):
            value = match.group(1)
            if value.upper() == "OBC":
                add("车载充电机")
            elif value.upper() == "CP":
                add("控制导引")
            else:
                add(value)
    for value in expansion.get("preserved_anchors") or []:
        text = str(value)
        if text.strip().upper() == "OBC":
            add("车载充电机")
        else:
            add(text)
    if re.search(r"PWM", query, re.I):
        add("PWM")
    if re.search(r"\bCP\b|控制导引", query, re.I):
        add("控制导引")
    if _is_signal_state_query(query):
        add("状态")
        add("电压")
    if _is_timing_query(query):
        add("时序")
        add("控制时序")
        add("状态转换")
    return anchors[:16]


def _candidate_items(kind: str, items: list[dict[str, object]]) -> list[tuple[str, dict[str, object]]]:
    return [(kind, item) for item in items]


def _blob(item: dict[str, object]) -> str:
    return json.dumps(item, ensure_ascii=False)


def _contains(blob: str, anchor: str) -> bool:
    return _normalize(anchor) in _normalize(blob)


def _sanitize_string_list(value: object, limit: int = 16) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result[:limit]


def _filter_allowed_ids(value: object, allowed: set[str], limit: int) -> list[str]:
    result: list[str] = []
    for item in _sanitize_string_list(value, limit * 2):
        if item in allowed and item not in result:
            result.append(item)
    return result[:limit]


def _merge_unique(*groups: list[str]) -> list[str]:
    result: list[str] = []
    for group in groups:
        for item in group:
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text)
    return result


def _clamp_confidence(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, number))


def _clip_text(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _normalize(value: str) -> str:
    return normalize(value)


def _is_signal_state_query(query: str) -> bool:
    return is_signal_state_query(query)


def _is_timing_query(query: str) -> bool:
    return is_timing_query(query)


def _is_process_activity_query(query: str) -> bool:
    return is_process_activity_query(query)


def _looks_like_signal_state_blob(blob: str) -> bool:
    normalized = _normalize(blob)
    return "pwm" in normalized and "电压" in normalized and "状态" in normalized


def _looks_like_exact_signal_state_blob(query: str, blob: str) -> bool:
    return looks_like_exact_signal_state_blob(query, blob)


def _looks_like_timing_blob(blob: str) -> bool:
    return looks_like_timing_blob(blob)


def _looks_like_process_activity_blob(query: str, blob: str) -> bool:
    return looks_like_process_activity_blob(query, blob)


def _process_codes(text: str) -> set[str]:
    return process_codes_from_text(text)


def _bp_codes(text: str) -> set[str]:
    return bp_codes_from_text(text)


def _strong_relations_for(query_type: str) -> set[str]:
    """Return set of strong graph relations allowed for given query_type."""
    return set(STRONG_RELATIONS_BY_QUERY_TYPE.get(query_type, ()))


def _has_strong_graph_support(item: dict[str, object], query: str, strong_relations: set[str]) -> bool:
    """Check if item has strong graph support allowed for query_type."""
    if str(item.get("graph_trust_tier") or "") != "strong":
        return False
    relation = str(item.get("graph_relation") or "")
    if relation not in strong_relations:
        return False
    # Additional check: ensure graph path exists
    graph_path = item.get("graph_path")
    if not isinstance(graph_path, list) or len(graph_path) == 0:
        return False
    # Verify path structure has src_name, relation, dst_name pattern
    for step in graph_path:
        if not isinstance(step, dict):
            return False
        if "src_name" not in step or "relation" not in step or "dst_name" not in step:
            return False
    return True


def _is_preface_or_index_blob(blob: str) -> bool:
    return is_preface_or_index_blob(blob)


def _rejection_notes(query: str, scored: list[SCORED_ROW]) -> list[str]:
    notes: list[str] = []
    if _is_signal_state_query(query):
        for _score, _kind, item, _matched, _shape_hits in scored[:8]:
            blob = _blob(item)
            if "输出占空比公差" in blob:
                notes.append("参数表 A.1 的输出占空比公差不直接解释 9V PWM 对应状态")
            if "term_definition" in blob and "9V" not in blob:
                notes.append("术语定义未覆盖电压/PWM状态组合")
    return list(dict.fromkeys(notes))


def _followup_queries(query: str, missing: list[str], expansion: dict[str, object]) -> list[str]:
    queries: list[str] = []
    for item in expansion.get("expanded_queries") or []:
        if isinstance(item, dict) and item.get("query"):
            queries.append(str(item["query"]))
    if _is_signal_state_query(query):
        voltage = re.search(r"([+-]?\d+(?:\.\d+)?)\s*V", query, re.I)
        voltage_text = f"{voltage.group(1)}V" if voltage else ""
        queries.insert(0, f"表 A.4 检测点 1 电压 {voltage_text} 是否输出 PWM 充电过程状态".strip())
    if missing:
        queries.append(" ".join(missing))
    return list(dict.fromkeys(query for query in queries if query.strip()))
