from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from functools import lru_cache

from .query_semantic_parser import _call_astron_text, _extract_json_block


ADVANCED_QUERY_PLANNER_VERSION = "v0.1.0"

_BASE_SYSTEM_RULES = """你是标准文档知识库的查询规划器。

你不是答案生成器，不要回答问题，只生成检索规划。

通用约束：
1. 保留用户原始问题中的硬锚点：缩写、标准号、表号、章节号、检测点、状态号、数值和单位。
2. 不得改变数值、单位、标准号和缩写。
3. 如果出现 CP、CC、PWM、检测点、电压状态，优先按电动汽车传导充电/控制导引语境理解。
4. CP 不要默认扩写为 Charge Pump、Control Pin 或 Clock Pulse，除非用户明确给出该语境。
5. 输出必须是单个 JSON 对象，不允许 markdown。
"""

PLANNER_PROMPTS = {
    "standard_structure": _BASE_SYSTEM_RULES
    + """
你当前只从标准文档结构视角规划检索。
重点关注：标准号、章节、条款、附录、图、表、规范性要求。

JSON 字段：
- intent: 字符串
- target_object: 字符串
- must_terms: 字符串数组
- should_terms: 字符串数组
- negative_terms: 字符串数组
- retrieval_queries: 字符串数组
- answer_shape: 字符串
- confidence: 0 到 1 的数字
- risk_notes: 字符串数组
""",
    "engineering_semantics": _BASE_SYSTEM_RULES
    + """
你当前只从工程语义视角规划检索。
重点关注：用户真实场景、接口、信号、状态、流程、时序、故障、工程动作。

JSON 字段：
- intent: 字符串
- target_object: 字符串
- must_terms: 字符串数组
- should_terms: 字符串数组
- negative_terms: 字符串数组
- retrieval_queries: 字符串数组
- answer_shape: 字符串
- confidence: 0 到 1 的数字
- risk_notes: 字符串数组
""",
    "terminology_alias": _BASE_SYSTEM_RULES
    + """
你当前只从术语、缩写、同义词和易混淆概念视角规划检索。
重点关注：中文名、英文名、缩写、别名、参数名、表述变体、容易误召回的负向概念。

JSON 字段：
- intent: 字符串
- target_object: 字符串
- must_terms: 字符串数组
- should_terms: 字符串数组
- negative_terms: 字符串数组
- retrieval_queries: 字符串数组
- answer_shape: 字符串
- confidence: 0 到 1 的数字
- risk_notes: 字符串数组
""",
}

SYNTHESIZER_SYSTEM_PROMPT = _BASE_SYSTEM_RULES + """
你是查询规划综合器。你的任务是把多个 planner 的结果合并成一个稳定、可机器消费的 RetrievalPlan。

合并规则：
1. hard_anchors 必须保留原始问题中的硬锚点。
2. 如果多个 planner 冲突，不要强行丢弃，保留到 risk_notes 或 should_terms。
3. negative_terms 只放明确会造成误召回的词。
4. retrieval_queries 要短、可检索、包含关键锚点。
5. 不要回答问题。

输出 JSON 字段：
- query_intent: 字符串
- target_object: 字符串
- hard_anchors: 字符串数组
- must_terms: 字符串数组
- should_terms: 字符串数组
- negative_terms: 字符串数组
- retrieval_queries: 字符串数组
- answer_shape: 字符串
- confidence: 0 到 1 的数字
- risk_notes: 字符串数组
"""


@dataclass(frozen=True)
class AdvancedQueryPlan:
    prompt_version: str
    enabled: bool
    used_llm: bool
    query_intent: str
    target_object: str
    hard_anchors: list[str]
    must_terms: list[str]
    should_terms: list[str]
    negative_terms: list[str]
    retrieval_queries: list[str]
    answer_shape: str
    confidence: float
    risk_notes: list[str]
    planner_outputs: dict[str, object]
    skip_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@lru_cache(maxsize=256)
def plan_advanced_query(
    query: str,
    rewritten_json: str = "{}",
    expansion_json: str = "{}",
) -> AdvancedQueryPlan:
    stripped = query.strip()
    if os.environ.get("EAKB_ENABLE_ADVANCED_QUERY_PLANNER", "0") != "1":
        return _disabled_plan(stripped, "disabled_by_env")
    if not stripped:
        return _disabled_plan(stripped, "empty_query")

    anchors = _extract_hard_anchors(stripped)
    try:
        rewritten = json.loads(rewritten_json)
    except json.JSONDecodeError:
        rewritten = {}
    try:
        expansion = json.loads(expansion_json)
    except json.JSONDecodeError:
        expansion = {}

    planner_outputs: dict[str, object] = {}
    try:
        for planner_name, system_prompt in PLANNER_PROMPTS.items():
            raw = _call_astron_text(
                _planner_prompt(stripped, anchors, rewritten, expansion, planner_name),
                system_prompt=system_prompt,
            )
            payload = _extract_json_block(raw)
            if _planner_payload_usable(stripped, anchors, payload):
                planner_outputs[planner_name] = payload
            else:
                planner_outputs[planner_name] = {"rejected": True, "raw": raw[:1200]}

        raw_synth = _call_astron_text(
            _synthesizer_prompt(stripped, anchors, rewritten, expansion, planner_outputs),
            system_prompt=SYNTHESIZER_SYSTEM_PROMPT,
        )
        payload = _extract_json_block(raw_synth)
        plan = AdvancedQueryPlan(
            prompt_version=ADVANCED_QUERY_PLANNER_VERSION,
            enabled=True,
            used_llm=True,
            query_intent=str(payload.get("query_intent") or "").strip(),
            target_object=str(payload.get("target_object") or "").strip(),
            hard_anchors=_merge_unique(anchors, _sanitize_string_list(payload.get("hard_anchors"), 16))[:16],
            must_terms=_sanitize_string_list(payload.get("must_terms"), 24),
            should_terms=_sanitize_string_list(payload.get("should_terms"), 32),
            negative_terms=_sanitize_string_list(payload.get("negative_terms"), 16),
            retrieval_queries=_sanitize_string_list(payload.get("retrieval_queries"), 12),
            answer_shape=str(payload.get("answer_shape") or "").strip(),
            confidence=_clamp_confidence(payload.get("confidence")),
            risk_notes=_sanitize_string_list(payload.get("risk_notes"), 12),
            planner_outputs=planner_outputs,
        )
        if not _advanced_plan_usable(stripped, anchors, plan):
            return _disabled_plan(stripped, "quality_gate_rejected", planner_outputs)
        return plan
    except Exception as exc:
        return _disabled_plan(stripped, f"llm_error:{type(exc).__name__}", planner_outputs)


def advanced_terms_for_retrieval(plan: AdvancedQueryPlan) -> list[str]:
    if not plan.enabled or not plan.used_llm:
        return []
    terms: list[str] = []
    for value in [*plan.hard_anchors, *plan.must_terms, *plan.should_terms, *plan.retrieval_queries]:
        text = str(value or "").strip()
        if text and text not in terms:
            terms.append(text)
    return terms[:36]


def _disabled_plan(
    query: str,
    reason: str,
    planner_outputs: dict[str, object] | None = None,
) -> AdvancedQueryPlan:
    return AdvancedQueryPlan(
        prompt_version=ADVANCED_QUERY_PLANNER_VERSION,
        enabled=False,
        used_llm=False,
        query_intent="",
        target_object="",
        hard_anchors=_extract_hard_anchors(query),
        must_terms=[],
        should_terms=[],
        negative_terms=[],
        retrieval_queries=[],
        answer_shape="",
        confidence=0.0,
        risk_notes=[],
        planner_outputs=planner_outputs or {},
        skip_reason=reason,
    )


def _planner_prompt(
    query: str,
    anchors: list[str],
    rewritten: dict[str, object],
    expansion: dict[str, object],
    planner_name: str,
) -> str:
    payload = {
        "prompt_version": ADVANCED_QUERY_PLANNER_VERSION,
        "planner_name": planner_name,
        "user_query": query,
        "hard_anchors": anchors,
        "current_rewrite": rewritten,
        "current_query_expansion": expansion,
    }
    return "请基于以下输入输出该视角的检索规划 JSON。\n" + json.dumps(payload, ensure_ascii=False)


def _synthesizer_prompt(
    query: str,
    anchors: list[str],
    rewritten: dict[str, object],
    expansion: dict[str, object],
    planner_outputs: dict[str, object],
) -> str:
    payload = {
        "prompt_version": ADVANCED_QUERY_PLANNER_VERSION,
        "user_query": query,
        "hard_anchors": anchors,
        "current_rewrite": rewritten,
        "current_query_expansion": expansion,
        "planner_outputs": planner_outputs,
    }
    return "请把多个 planner 输出合并成最终 RetrievalPlan JSON。\n" + json.dumps(payload, ensure_ascii=False)


def _planner_payload_usable(query: str, anchors: list[str], payload: dict[str, object]) -> bool:
    blob = json.dumps(payload, ensure_ascii=False).upper().replace(" ", "")
    for anchor in anchors:
        if anchor.upper().replace(" ", "") not in blob:
            return False
    if _looks_like_control_pilot_context(query):
        drift_terms = ("CHARGEPUMP", "CONTROLPIN", "CLOCKPULSE")
        if any(term in blob for term in drift_terms):
            return False
    return True


def _advanced_plan_usable(query: str, anchors: list[str], plan: AdvancedQueryPlan) -> bool:
    if plan.confidence < 0.2:
        return False
    positive_payload = {
        "query_intent": plan.query_intent,
        "target_object": plan.target_object,
        "hard_anchors": plan.hard_anchors,
        "must_terms": plan.must_terms,
        "should_terms": plan.should_terms,
        "retrieval_queries": plan.retrieval_queries,
        "answer_shape": plan.answer_shape,
    }
    blob = json.dumps(positive_payload, ensure_ascii=False).upper().replace(" ", "")
    for anchor in anchors:
        if anchor.upper().replace(" ", "") not in blob:
            return False
    if _looks_like_control_pilot_context(query):
        drift_terms = ("CHARGEPUMP", "CONTROLPIN", "CLOCKPULSE")
        if any(term in blob for term in drift_terms):
            return False
    return bool(plan.must_terms or plan.should_terms or plan.retrieval_queries)


def _extract_hard_anchors(query: str) -> list[str]:
    anchors: list[str] = []

    def add(value: str) -> None:
        text = re.sub(r"\s+", " ", str(value or "").strip())
        if text and text not in anchors:
            anchors.append(text)

    for pattern in [
        r"(?:GB/T|GBT|GB|ISO|IEC|QC/T|QC)\s*[A-Z]?\s*[\d.]+(?:[—-]\d{2,4})?",
        r"(表\s*[A-Z]?\d+(?:\.\d+)*)",
        r"(检测点\s*\d+)",
        r"(状态\s*\d+'?)",
        r"([+-]?\d+(?:\.\d+)?\s*(?:V|A|Ω|kΩ|Hz|%))",
        r"(?<![A-Za-z0-9])([A-Z]{1,6}\d*)(?![A-Za-z0-9])",
    ]:
        for match in re.finditer(pattern, query, re.I):
            add(match.group(1) if match.lastindex else match.group(0))
    return anchors[:16]


def _sanitize_string_list(value: object, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result[:limit]


def _merge_unique(left: list[str], right: list[str]) -> list[str]:
    result: list[str] = []
    for item in [*left, *right]:
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


def _looks_like_control_pilot_context(query: str) -> bool:
    return bool(re.search(r"\bCP\b|控制导引|PWM|检测点", query, re.I))
