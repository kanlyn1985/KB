from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from functools import lru_cache

from .query_semantic_parser import _call_astron_text, _extract_json_block


QUERY_EXPANSION_PROMPT_VERSION = "v0.1.0"

QUERY_EXPANSION_SYSTEM_PROMPT = """你是标准文档知识库的查询扩写器。

你的任务不是回答问题，而是生成用于检索的结构化查询计划。

当前知识库以电动汽车传导充电、充电接口、控制导引、V2G/V2X、汽车标准和 ASPICE 过程文档为主。
当问题中出现 CP、CC、PWM、检测点、电压状态时，优先按电动汽车充电控制导引语境理解：
- CP 通常关联 control pilot / 控制导引。
- CC 通常关联 connection confirmation / 连接确认。
- 9V、6V、12V、-12V 与 PWM 同时出现时，通常应检索检测点电压状态表、控制导引状态和充电过程状态。
- 不要优先扩写为通用电子领域里的 Control Pin、Charge Pump、Clock Pulse，除非用户明确给出该语境。

要求：
1. 保留原始问题中的硬锚点，包括标准号、章节号、表号、检测点、状态号、电压/电流/电阻数值、缩写、符号。
2. 可以扩展同义词、标准术语、可能相关章节/表格、工程场景。
3. 可以推测用户意图，但必须给出 confidence。
4. 不得改变任何数值、单位、缩写或标准号。
5. 不得编造答案，只生成检索计划。
6. 如果存在多种可能解释，输出多个 intent_candidates。
7. 输出必须是单个 JSON 对象，不允许输出 markdown 或解释文本。

JSON 字段：
- intent_candidates: 字符串数组
- preserved_anchors: 字符串数组
- expanded_terms: 字符串数组
- expanded_queries: 对象数组，每个对象包含 query 和 purpose
- must_not_change: 字符串数组
- possible_answer_shape: 字符串
- confidence: 0 到 1 的数字
- risk_notes: 字符串数组
"""


@dataclass(frozen=True)
class ExpandedQueryItem:
    query: str
    purpose: str


@dataclass(frozen=True)
class QueryExpansion:
    prompt_version: str
    used_llm: bool
    intent_candidates: list[str]
    preserved_anchors: list[str]
    expanded_terms: list[str]
    expanded_queries: list[ExpandedQueryItem]
    must_not_change: list[str]
    possible_answer_shape: str
    confidence: float
    risk_notes: list[str]
    raw_response: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["expanded_queries"] = [asdict(item) for item in self.expanded_queries]
        return payload


def _sanitize_string_list(value: object, limit: int = 16) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result[:limit]


def _sanitize_expanded_queries(value: object, limit: int = 8) -> list[ExpandedQueryItem]:
    if not isinstance(value, list):
        return []
    result: list[ExpandedQueryItem] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            query = str(item.get("query") or "").strip()
            purpose = str(item.get("purpose") or "").strip() or "semantic_recall"
        else:
            query = str(item or "").strip()
            purpose = "semantic_recall"
        if not query or query in seen:
            continue
        seen.add(query)
        result.append(ExpandedQueryItem(query=query, purpose=purpose))
    return result[:limit]


def _extract_hard_anchors(query: str) -> list[str]:
    anchors: list[str] = []

    def add(value: str) -> None:
        cleaned = re.sub(r"\s+", " ", str(value or "").strip())
        if cleaned and cleaned not in anchors:
            anchors.append(cleaned)

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
    return anchors[:12]


def _expansion_prompt(query: str, anchors: list[str]) -> str:
    return (
        f"prompt_version: {QUERY_EXPANSION_PROMPT_VERSION}\n"
        f"用户原始问题：{query}\n"
        f"必须保留的硬锚点：{json.dumps(anchors, ensure_ascii=False)}\n"
        "请输出结构化查询扩写 JSON。"
    )


@lru_cache(maxsize=512)
def expand_query(query: str) -> QueryExpansion:
    stripped = query.strip()
    anchors = _extract_hard_anchors(stripped)
    if not stripped:
        return _fallback_expansion(stripped, anchors)
    if _should_use_rule_expansion(stripped, anchors):
        return _fallback_expansion(stripped, anchors)
    try:
        raw = _call_astron_text(_expansion_prompt(stripped, anchors), system_prompt=QUERY_EXPANSION_SYSTEM_PROMPT)
        payload = _extract_json_block(raw)
        expansion = QueryExpansion(
            prompt_version=QUERY_EXPANSION_PROMPT_VERSION,
            used_llm=True,
            intent_candidates=_sanitize_string_list(payload.get("intent_candidates"), 8),
            preserved_anchors=_merge_unique(anchors, _sanitize_string_list(payload.get("preserved_anchors"), 16))[:16],
            expanded_terms=_sanitize_string_list(payload.get("expanded_terms"), 24),
            expanded_queries=_sanitize_expanded_queries(payload.get("expanded_queries"), 10),
            must_not_change=_merge_unique(anchors, _sanitize_string_list(payload.get("must_not_change"), 16))[:16],
            possible_answer_shape=str(payload.get("possible_answer_shape") or "").strip(),
            confidence=_clamp_confidence(payload.get("confidence")),
            risk_notes=_sanitize_string_list(payload.get("risk_notes"), 8),
            raw_response=raw,
        )
        if not _expansion_is_usable(stripped, expansion):
            return _fallback_expansion(stripped, anchors)
        return expansion
    except Exception:
        return _fallback_expansion(stripped, anchors)


def _should_use_rule_expansion(query: str, anchors: list[str]) -> bool:
    if re.search(r"(GB/T|GBT|GB|ISO|IEC|QC/T|QC)\s*[A-Z]?\s*[\d.]+", query, re.I):
        return True
    if re.search(r"(有哪些活动|要做哪些活动|活动要做|有哪些任务|有哪些步骤|步骤有哪些|任务有哪些|过程域.*(?:是什么|定义|含义))", query, re.I):
        return True
    if re.search(r"(阻值|电阻|电压|电流|频率|检测点|占空比|PWM|时序|状态转换|控制时序)", query, re.I):
        return True
    if anchors and re.search(r"[+-]?\d+(?:\.\d+)?\s*(?:V|A|Ω|kΩ|Hz|%)", query, re.I):
        return True
    return False


def expansion_terms_for_retrieval(expansion: QueryExpansion) -> list[str]:
    terms: list[str] = []
    for value in [*expansion.preserved_anchors, *expansion.expanded_terms]:
        _append_unique(terms, value)
    for item in expansion.expanded_queries:
        _append_unique(terms, item.query)
    return terms[:24]


def _fallback_expansion(query: str, anchors: list[str]) -> QueryExpansion:
    upper = query.upper()
    expanded_terms: list[str] = []
    expanded_queries: list[ExpandedQueryItem] = []
    intent_candidates: list[str] = []
    possible_answer_shape = "freeform"
    risk_notes: list[str] = []

    if "PWM" in upper and _has_cp_anchor(query) and re.search(r"[+-]?\d+(?:\.\d+)?\s*V", query, re.I):
        voltage = re.search(r"([+-]?\d+(?:\.\d+)?)\s*V", query, re.I)
        voltage_text = f"{voltage.group(1)}V" if voltage else ""
        intent_candidates = ["signal_state_explanation", "parameter_meaning", "table_lookup"]
        expanded_terms = [
            "控制导引",
            "检测点1",
            "检测点 1",
            "是否输出 PWM",
            "充电过程状态",
            "表 A.4",
            "供电设备准备就绪",
            "车辆准备就绪",
        ]
        expanded_queries = [
            ExpandedQueryItem(
                query=f"控制导引 CP 检测点1 {voltage_text} 输出 PWM 对应什么充电过程状态".strip(),
                purpose="state_table_lookup",
            ),
            ExpandedQueryItem(
                query=f"表 A.4 检测点 1 电压 {voltage_text} 是否输出 PWM".strip(),
                purpose="table_lookup",
            ),
            ExpandedQueryItem(
                query=f"CP PWM 信号 {voltage_text} 表示什么".strip(),
                purpose="semantic_recall",
            ),
        ]
        possible_answer_shape = "explain_state_meaning"
        risk_notes = [
            "不得改变电压值",
            "PWM 是输出状态或波形信号，不应只解释为占空比公差",
        ]
    elif _has_cp_anchor(query) and re.search(r"(时序|流程|状态转换|控制时序|握手|预充|启动|停止|停机)", query):
        intent_candidates = ["timing_lookup", "process_lookup", "state_transition_lookup"]
        expanded_terms = [
            "控制导引",
            "控制时序",
            "状态转换",
            "表 A.7",
            "交流充电控制时序表",
            "检测点1",
            "PWM",
        ]
        expanded_queries = [
            ExpandedQueryItem(
                query="CP 控制导引 时序 状态转换 表 A.7",
                purpose="timing_table_lookup",
            ),
            ExpandedQueryItem(
                query="交流充电控制时序表 检测点1 PWM 状态",
                purpose="state_transition_lookup",
            ),
            ExpandedQueryItem(
                query="控制导引电路状态转换图 控制时序",
                purpose="semantic_recall",
            ),
        ]
        possible_answer_shape = "process_or_timing"
        risk_notes = [
            "CP 应按 control pilot / 控制导引理解",
            "不要扩写为 Charge Pump、Control Pin 或 Clock Pulse",
        ]
    elif re.search(r"(阻值|电阻|电压|电流|频率|占空比|检测点)", query, re.I):
        intent_candidates = ["parameter_meaning", "parameter_value", "table_lookup"]
        expanded_terms = ["参数", "控制导引", "表格", *anchors]
        possible_answer_shape = "parameter_explanation"
    elif re.search(r"(是什么意思|什么是|定义|含义)", query):
        intent_candidates = ["term_definition", "definition"]
        expanded_terms = [*anchors]
        possible_answer_shape = "definition"

    return QueryExpansion(
        prompt_version=QUERY_EXPANSION_PROMPT_VERSION,
        used_llm=False,
        intent_candidates=intent_candidates or ["general_search"],
        preserved_anchors=anchors,
        expanded_terms=_merge_unique([], expanded_terms)[:24],
        expanded_queries=expanded_queries[:8],
        must_not_change=anchors,
        possible_answer_shape=possible_answer_shape,
        confidence=0.62 if expanded_terms or expanded_queries else 0.3,
        risk_notes=risk_notes,
        raw_response=None,
    )


def _expansion_is_usable(query: str, expansion: QueryExpansion) -> bool:
    if expansion.confidence < 0.2:
        return False
    upper_blob = " ".join([
        *expansion.preserved_anchors,
        *expansion.expanded_terms,
        *[item.query for item in expansion.expanded_queries],
    ]).upper()
    for anchor in _extract_hard_anchors(query):
        if anchor.upper().replace(" ", "") not in upper_blob.replace(" ", ""):
            return False
    if _looks_like_control_pilot_context(query):
        domain_terms = ("控制导引", "检测点", "充电过程状态", "表 A.4", "CONTROL PILOT")
        if not any(term.upper() in upper_blob for term in domain_terms):
            return False
        drift_terms = ("CHARGE PUMP", "CLOCK PULSE", "DC-DC", "CONTROL PIN")
        normalized_blob = upper_blob.replace(" ", "")
        if any(term.replace(" ", "") in normalized_blob for term in drift_terms):
            return False
    return bool(expansion.expanded_terms or expansion.expanded_queries or expansion.intent_candidates)


def _looks_like_control_pilot_signal_query(query: str) -> bool:
    return bool(
        _has_cp_anchor(query)
        and re.search(r"PWM", query, re.I)
        and re.search(r"[+-]?\d+(?:\.\d+)?\s*V", query, re.I)
    )


def _looks_like_control_pilot_context(query: str) -> bool:
    return bool(
        _has_cp_anchor(query)
        and re.search(r"PWM|检测点|电压|时序|流程|状态转换|控制时序|握手|预充|启动|停止|停机", query, re.I)
    )


def _has_cp_anchor(query: str) -> bool:
    return bool(re.search(r"(?<![A-Za-z0-9])CP(?![A-Za-z0-9])|控制导引", query, re.I))


def _clamp_confidence(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(0.0, min(1.0, number))


def _merge_unique(base: list[str], additions: list[str]) -> list[str]:
    result: list[str] = []
    for item in [*base, *additions]:
        _append_unique(result, item)
    return result


def _append_unique(items: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)
