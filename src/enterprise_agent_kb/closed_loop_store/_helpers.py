"""Pure utility helpers used throughout the closed-loop store.

These have no DB or I/O dependencies and can be tested in isolation.
The implementations are exact copies of the original functions in
closed_loop_store_mono.py; this module exists to make them independently
testable and discoverable.
"""
from __future__ import annotations

import json
import re

from ._runtime import _short_hash


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _mean_metric(items: list[dict[str, object]], key: str) -> float:
    values: list[float] = []
    for item in items:
        try:
            values.append(float(item.get(key)))
        except (TypeError, ValueError):
            continue
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


def re_sub_whitespace(value: str) -> str:
    return " ".join(str(value or "").split())


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split())


_PYTEST_COUNT_KEYS: tuple[str, ...] = (
    "passed",
    "failed",
    "deselected",
    "skipped",
    "xfailed",
    "xpassed",
    "error",
    "errors",
)


def _pytest_output_counts(output: str) -> dict[str, int]:
    text = str(output or "")
    counts = {key: 0 for key in _PYTEST_COUNT_KEYS}
    for key in _PYTEST_COUNT_KEYS:
        matches = re.findall(rf"(\d+)\s+{re.escape(key)}\b", text, flags=re.IGNORECASE)
        if matches:
            counts[key] = int(matches[-1])
    counts["selected"] = (
        counts["passed"] + counts["failed"] + counts["skipped"]
        + counts["xfailed"] + counts["xpassed"] + counts["error"] + counts["errors"]
    )
    counts["collected"] = counts["selected"] + counts["deselected"]
    return counts


def _safe_json(value: object, fallback: object) -> object:
    if not isinstance(value, str) or not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _json_list(value: object) -> str:
    if value is None:
        items: list[object] = []
    elif isinstance(value, list):
        items = value
    elif isinstance(value, tuple):
        items = list(value)
    else:
        items = [value]
    return json.dumps(
        [item for item in items if item is not None and item != ""],
        ensure_ascii=False,
    )


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _as_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _clip(value: str, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[-limit:]


def _json_object(value: object) -> dict[str, object]:
    if not value:
        return {}
    try:
        payload = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _string_ids(value: object) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = [str(item) for item in value]
    else:
        values = []
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _text_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item or "").strip()]
    return []


def _stable_id(prefix: str, *parts: object) -> str:
    """Build a deterministic id from a prefix and arbitrary hashable parts.

    The id is a SHA-1 (truncated) of the JSON-serialized parts, prefixed
    by `prefix-`. Used to derive stable unit/case/run ids from the row's
    identifying fields.
    """
    return f"{prefix}-{_short_hash(parts)}"


def _suggested_actions(failure_type: str) -> list[str]:
    """Default repair-action suggestions for a closed-loop failure type.

    Used by both the failure-diagnostic and repair-task layers when no
    context-specific actions are available. The mapping is intentionally
    conservative — callers should prefer richer context-driven actions
    when possible.
    """
    mapping = {
        "parse_missing": ["重新解析文档", "检查 OCR/版面解析风险页", "补充 parse quality 回归"],
        "evidence_missing": ["检查 source unit 是否生成 evidence", "修 evidence 抽取规则", "查看 page/block 链路"],
        "source_unit_missing": ["重建 coverage source units", "检查 unit 抽取规则", "调整 source unit 噪声过滤"],
        "retrieval_miss": ["补 metadata / synonym", "检查 query rewrite 和 expansion", "增加 retrieval_quality case"],
        "rerank_wrong": ["检查 rerank explanation", "调整 query_type/type bonus", "补 negative_expected 回归"],
        "graph_path_missing": ["检查 topic resolution entity", "修 graph relation 或 edge_evidence_map", "降低 weak relation 权重"],
        "graph_not_engaged": ["检查 topic_resolution 是否命中 ready entity", "检查 graph_edges 是否存在强关系", "补 process/entity alias 或 relation 构建规则"],
        "topic_resolution_wrong": ["检查 target_topic 与候选实体", "修 generic term 过滤和 alias 归一化", "补 topic_resolution 回归"],
        "entity_quality_pollution": ["清理低质量 entity/status", "修实体构建噪声过滤", "重建 wiki/graph/FTS 并补 entity hygiene 回归"],
        "stale_entity_exposed": ["检查检索 SQL 是否过滤 stale entity", "刷新 FTS/wiki 索引", "补 stale entity 暴露回归"],
        "evidence_judge_wrong": ["检查 matched/missing anchors", "增加 relation/evidence shape 规则", "补 judge 单测"],
        "evidence_shape_wrong": ["检查 expected_evidence_shape 与实际 evidence_shape", "修 evidence shape 适用条件或候选打分", "补 shape mismatch 回归"],
        "answer_policy_wrong": ["检查 answer_mode", "修 answer policy 选择", "增加 answer_quality case"],
        "answer_render_artifact": ["检查 answer_policy 渲染模板", "修通用答案清洗/去重规则", "补 render artifact 回归"],
        "llm_generation_wrong": ["收紧 LLM 输出约束", "增加 forbidden_contains", "优先规则模板修复"],
        "unknown_pytest_failure": ["查看 pytest output", "补结构化 eval result", "将失败 case 转为可归因结果"],
        "unknown": ["查看 eval output", "补 failure_reason", "补 Failure Analysis 归因规则"],
    }
    return mapping.get(failure_type, mapping["unknown"])
