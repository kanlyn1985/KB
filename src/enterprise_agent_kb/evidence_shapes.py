from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass


SCORED_ROW = tuple[float, str, dict[str, object], list[str], list[str]]


@dataclass(frozen=True)
class EvidenceShape:
    name: str
    applies: Callable[[str], bool]
    score_candidate: Callable[[str, str, dict[str, object], str], float]
    is_sufficient: Callable[[str, list[SCORED_ROW]], bool]
    reason: str


@dataclass(frozen=True)
class EvidenceShapeContract:
    query_type: str
    allowed_shapes: tuple[str, ...]
    required: bool = True
    fallback_policy: str = "clarify_or_insufficient"


SHAPE_CONTRACTS: dict[str, EvidenceShapeContract] = {
    "test_method_lookup": EvidenceShapeContract("test_method_lookup", ("test_method",)),
    "timing_lookup": EvidenceShapeContract("timing_lookup", ("timing_table",)),
    "lifecycle_lookup": EvidenceShapeContract("lifecycle_lookup", ("process_activity",)),
    "parameter_lookup": EvidenceShapeContract("parameter_lookup", ("parameter_definition", "signal_state_table")),
    "parameter_meaning": EvidenceShapeContract("parameter_meaning", ("parameter_definition", "signal_state_table")),
    "signal_state_lookup": EvidenceShapeContract("signal_state_lookup", ("signal_state_table",)),
    "definition": EvidenceShapeContract("definition", ("term_definition", "parameter_definition")),
}


CONTRACT_REASON_ACTIONS: dict[str, list[str]] = {
    "contract_not_defined": [
        "在 evidence_shapes.py 为该 query_type 增加 EvidenceShapeContract",
        "检查 query_rewrite.py 是否产出了过宽泛或未知的 query_type",
        "补充该 query_type 的 shape contract 单测",
    ],
    "contract_query_type_wrong": [
        "检查 query_rewrite.py 的规则优先级和语义覆盖",
        "检查 advanced_query_planner 输出是否把问法归到错误 query_type",
        "检查 ambiguity/short acronym 路由是否提前澄清了歧义",
    ],
    "contract_wrong_shape": [
        "检查 retrieval_router.py 的 channel 选择和 query_type 路由",
        "检查 graph relation / topic_resolution 是否把主题连到错误知识对象",
        "检查 query_expansion 是否引入漂移词导致错误证据形状",
    ],
    "contract_rerank_suppressed_shape": [
        "检查 reranker.py 的 shape boost 是否不足",
        "检查 top-k 截断是否把允许证据形状挤出答案上下文",
        "检查 evidence_judge 对 allowed shape 的打分是否低于错误形状",
    ],
    "contract_candidate_missing": [
        "检查 retrieval channel 覆盖是否包含 graph / evidence / facts",
        "检查 routing_summary 或 direct routing 是否漏召回目标表/过程",
        "检查 graph 是否参与以及 topic_resolution confidence 是否过低",
    ],
    "contract_parse_gap": [
        "检查 source_units 是否覆盖目标页面/表格/过程块",
        "检查 evidence/facts 是否从 source unit 生成",
        "检查 PDF 解析、表格抽取和 coverage gaps",
    ],
    "contract_matched": [
        "无需处理",
    ],
}


def contract_reason_actions(reason: str) -> list[str]:
    return list(CONTRACT_REASON_ACTIONS.get(str(reason or "").strip(), []))


def evidence_shape_contract(query_type: str) -> EvidenceShapeContract | None:
    return SHAPE_CONTRACTS.get(str(query_type or "").strip())


def allowed_evidence_shapes(query_type: str) -> tuple[str, ...]:
    contract = evidence_shape_contract(query_type)
    return contract.allowed_shapes if contract else ()


def evidence_shape_required(query_type: str) -> bool:
    contract = evidence_shape_contract(query_type)
    return bool(contract and contract.required)


def evidence_shape_matches_contract(query_type: str, evidence_shape: str | None) -> bool | None:
    allowed = allowed_evidence_shapes(query_type)
    if not allowed:
        return None
    return str(evidence_shape or "").strip() in allowed


def diagnose_shape_contract_failure(
    *,
    query: str,
    query_type: str,
    selected_shape: str | None,
    candidate_shape_counts: dict[str, int],
    top_shape_counts: dict[str, int],
) -> dict[str, object]:
    allowed = allowed_evidence_shapes(query_type)
    if not allowed:
        return {
            "reason": "contract_not_defined",
            "action": "为该 query_type 定义 evidence shape contract，或修正 query rewrite 类型",
            "repair_actions": contract_reason_actions("contract_not_defined"),
        }
    text_implied = [shape.name for shape in EVIDENCE_SHAPES if shape.applies(query)]
    if text_implied and not any(shape in allowed for shape in text_implied):
        return {
            "reason": "contract_query_type_wrong",
            "action": "优先检查 query rewrite / planner，当前 query_type 与用户问法暗示的证据形状不一致",
            "repair_actions": contract_reason_actions("contract_query_type_wrong"),
            "text_implied_shapes": text_implied,
        }
    if selected_shape and selected_shape in allowed:
        return {
            "reason": "contract_matched",
            "action": "无需处理",
            "repair_actions": contract_reason_actions("contract_matched"),
        }
    if any(candidate_shape_counts.get(shape, 0) for shape in allowed):
        return {
            "reason": "contract_rerank_suppressed_shape",
            "action": "候选里存在允许的证据形状，但未成为最终 best shape；优先检查 reranker、top-k 截断和 evidence judge 打分",
            "repair_actions": contract_reason_actions("contract_rerank_suppressed_shape"),
        }
    if candidate_shape_counts:
        return {
            "reason": "contract_wrong_shape",
            "action": "召回到了结构化证据，但形状不符合契约；优先检查 retrieval router、graph relation 和 query expansion",
            "repair_actions": contract_reason_actions("contract_wrong_shape"),
        }
    if top_shape_counts:
        return {
            "reason": "contract_candidate_missing",
            "action": "top 候选没有允许的证据形状；优先检查 retrieval channel 覆盖和 graph/topic routing",
            "repair_actions": contract_reason_actions("contract_candidate_missing"),
        }
    return {
        "reason": "contract_parse_gap",
        "action": "未发现可判定的证据形状；优先检查 source units、evidence/fact 抽取和解析覆盖率",
        "repair_actions": contract_reason_actions("contract_parse_gap"),
    }


def evidence_gate_applies_for_contract(
    *,
    query_type: str,
    evidence_shape: str,
    evidence_judge_reason: str = "",
    require_evidence_judge: bool | None = None,
) -> bool:
    if require_evidence_judge is not None:
        return require_evidence_judge
    if evidence_shape_required(query_type):
        return True
    if str(evidence_shape or "").strip() in _ALL_CONTRACT_SHAPES:
        return True
    reason = str(evidence_judge_reason or "").lower()
    return str(query_type or "").strip() == "lifecycle_lookup" and ("process activity" in reason or "process/bp" in reason)


def active_shapes(query: str, query_type: str = "") -> list[EvidenceShape]:
    contract_shapes = set(allowed_evidence_shapes(query_type))
    return [
        shape
        for shape in EVIDENCE_SHAPES
        if shape.applies(query) or shape.name in contract_shapes
    ]


def best_shape(scored: list[SCORED_ROW], allowed_shapes: tuple[str, ...] | list[str] = ()) -> str | None:
    counts: dict[str, int] = {}
    for score, _kind, _item, _matched, shape_hits in scored[:5]:
        if score <= 0:
            continue
        for name in shape_hits:
            counts[name] = counts.get(name, 0) + 1
    if not counts:
        return None
    if allowed_shapes:
        allowed = set(allowed_shapes)
        allowed_counts = {name: count for name, count in counts.items() if name in allowed}
        if allowed_counts:
            counts = allowed_counts
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def shape_diagnostics(query: str, shapes: list[EvidenceShape], scored: list[SCORED_ROW]) -> dict[str, object]:
    candidate_shape_counts: dict[str, int] = {}
    top_shape_counts: dict[str, int] = {}
    for _score, _kind, _item, _matched, shape_hits in scored:
        for name in shape_hits:
            candidate_shape_counts[name] = candidate_shape_counts.get(name, 0) + 1
    for _score, _kind, _item, _matched, shape_hits in scored[:5]:
        for name in shape_hits:
            top_shape_counts[name] = top_shape_counts.get(name, 0) + 1
    top_blobs = [_blob(row[2]) for row in scored[:8]]
    process_codes = sorted(set().union(*[process_codes_from_text(blob) for blob in top_blobs])) if top_blobs else []
    bp_codes = sorted(set().union(*[bp_codes_from_text(blob) for blob in top_blobs])) if top_blobs else []
    parameter_names = sorted(set().union(*[_parameter_names(blob) for blob in top_blobs])) if top_blobs else []
    term_names = sorted(set().union(*[_term_names(blob) for blob in top_blobs])) if top_blobs else []
    return {
        "active_shapes": [shape.name for shape in shapes],
        "candidate_shape_counts": dict(sorted(candidate_shape_counts.items())),
        "top_shape_counts": dict(sorted(top_shape_counts.items())),
        "process_codes": process_codes[:12],
        "query_process_codes": sorted(process_codes_from_text(query)),
        "matched_bp_codes": bp_codes[:24],
        "parameter_names": parameter_names[:12],
        "term_names": term_names[:12],
    }


_ALL_CONTRACT_SHAPES = tuple(sorted({shape for contract in SHAPE_CONTRACTS.values() for shape in contract.allowed_shapes}))


def is_signal_state_query(query: str) -> bool:
    return bool(re.search(r"PWM", query, re.I) and re.search(r"[+-]?\d+(?:\.\d+)?\s*V", query, re.I))


def is_timing_query(query: str) -> bool:
    return bool(re.search(r"(时序|流程|状态转换|控制时序|握手|预充|启动|停止|停机)", str(query or "")))


def is_process_activity_query(query: str) -> bool:
    text = str(query or "")
    if re.search(r"\b(?:SWE|SYS|SUP|MAN|ACQ|ENG|HWE|MLE|PIM|REU)\.\d+\b", text, re.I):
        return True
    has_process_topic = bool(re.search(r"(过程域|过程|软件架构|系统集成|系统架构|需求分析|测试|验证|ASPICE|Automotive\s*SPICE)", text, re.I))
    asks_activity = bool(re.search(r"(活动|任务|实践|基本实践|BP\d*|有哪些|要做|是什么|做什么|process\s+domain|base\s+practice|activity|activities)", text, re.I))
    return has_process_topic and asks_activity


def is_test_method_query(query: str) -> bool:
    return bool(re.search(r"(怎么测|如何测|怎样测|怎么测试|如何测试|怎样测试|试验方法|测试方法|检测方法|测量方法)", str(query or "")))


def is_parameter_definition_query(query: str) -> bool:
    if is_test_method_query(query):
        return False
    return bool(re.search(r"(阻值|电阻|电压|电流|占空比|PWM|检测点|参数)", str(query or ""), re.I))


def is_term_definition_query(query: str) -> bool:
    text = str(query or "")
    if is_signal_state_query(text) or is_timing_query(text) or is_process_activity_query(text) or is_parameter_definition_query(text):
        return False
    return bool(re.search(r"(是什么|定义|含义|什么意思|表示什么|解释)", text))


def looks_like_exact_signal_state_blob(query: str, blob: str) -> bool:
    voltage = re.search(r"([+-]?\d+(?:\.\d+)?)\s*V", query, re.I)
    voltage_text = voltage.group(1) if voltage else ""
    normalized = normalize(blob)
    return (
        bool(voltage_text)
        and voltage_text in normalized
        and "pwm" in normalized
        and "电压" in normalized
        and "状态" in normalized
        and ("检测点1" in normalized or "表a.4" in normalized)
    )


def looks_like_timing_blob(blob: str) -> bool:
    normalized = normalize(blob)
    if is_preface_or_index_blob(blob):
        return False
    return (
        ("表a.7" in normalized or "控制时序" in normalized or "状态转换" in normalized)
        and ("时序" in normalized or "状态" in normalized)
    )


def looks_like_process_activity_blob(query: str, blob: str) -> bool:
    if is_preface_or_index_blob(blob):
        return False
    normalized = normalize(blob)
    process_codes = process_codes_from_text(blob)
    bp_codes = bp_codes_from_text(blob)
    if not bp_codes:
        return False
    if not any(token in normalized for token in ("step_text", "process_name", "基本实践", "basepractice", "practice", "活动")):
        return False
    query_process_codes = process_codes_from_text(query)
    if query_process_codes and not any(code in process_codes for code in query_process_codes):
        return False
    return bool(process_codes) or bool(re.search(r"\b[A-Z]{2,4}\.\d+\.BP\d+\b", blob, re.I))


def looks_like_test_method_blob(query: str, blob: str) -> bool:
    if is_preface_or_index_blob(blob):
        return False
    normalized = normalize(blob)
    if not any(token in normalized for token in ("试验", "测试", "测量", "检测")):
        return False
    if not any(token in normalized for token in ("试验方法及步骤", "按照图", "接好试验电路", "调节", "测量", "观察", "施加")):
        return False
    query_tokens = _test_method_topic_tokens(query)
    if query_tokens and not any(normalize(token) in normalized for token in query_tokens):
        return False
    positives, negatives = _object_anchor_terms(query)
    if positives and not any(normalize(term) in normalized for term in positives):
        return False
    if negatives and any(normalize(term) in normalized for term in negatives) and not any(normalize(term) in normalized for term in positives):
        return False
    return True


def is_preface_or_index_blob(blob: str) -> bool:
    normalized = normalize(blob)
    return any(token in normalized for token in ("前言", "目次", "目录")) or '"scope_type":"preface"' in normalized


def normalize(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def process_codes_from_text(text: str) -> set[str]:
    return {
        f"{match.group(1).upper()}.{match.group(2)}"
        for match in re.finditer(r"\b(SWE|SYS|SUP|MAN|ACQ|ENG|HWE|MLE|PIM|REU)\.(\d+)\b", str(text or ""), re.I)
    }


def bp_codes_from_text(text: str) -> set[str]:
    return {
        f"{match.group(1).upper()}.{match.group(2)}.BP{match.group(3)}"
        for match in re.finditer(r"\b(SWE|SYS|SUP|MAN|ACQ|ENG|HWE|MLE|PIM|REU)\.(\d+)\.BP\s*(\d+)\b", str(text or ""), re.I)
    }


def _blob(item: dict[str, object]) -> str:
    return json.dumps(item, ensure_ascii=False)


def _looks_like_signal_state_blob(blob: str) -> bool:
    normalized = normalize(blob)
    return "pwm" in normalized and "电压" in normalized and "状态" in normalized


def _looks_like_parameter_definition_blob(query: str, blob: str) -> bool:
    if is_preface_or_index_blob(blob):
        return False
    normalized = normalize(blob)
    query_tokens = _query_anchor_tokens(query)
    if query_tokens and not any(normalize(token) in normalized for token in query_tokens):
        return False
    return any(token in normalized for token in ("参数", "标称值", "最小值", "最大值", "等效电阻", "占空比", "电压", "电流", "定义"))


def _looks_like_term_definition_blob(query: str, blob: str) -> bool:
    if is_preface_or_index_blob(blob):
        return False
    normalized = normalize(blob)
    query_tokens = _query_anchor_tokens(query)
    if query_tokens and not any(normalize(token) in normalized for token in query_tokens):
        return False
    return any(token in normalized for token in ("term_definition", "defines_term", "定义", "功能", "表示", "是指"))


def _signal_state_score(query: str, _kind: str, _item: dict[str, object], blob: str) -> float:
    score = 0.0
    if looks_like_exact_signal_state_blob(query, blob):
        score += 1.8
    elif _looks_like_signal_state_blob(blob):
        score += 0.9
    if "表 A.4" in blob or "检测点 1 的电压状态" in blob:
        score += 0.9
    if "表 A.7" in blob:
        score += 0.15
    return score


def _signal_state_sufficient(query: str, scored: list[SCORED_ROW]) -> bool:
    return any(looks_like_exact_signal_state_blob(query, _blob(row[2])) for row in scored[:5])


def _timing_score(_query: str, _kind: str, _item: dict[str, object], blob: str) -> float:
    return 1.9 if looks_like_timing_blob(blob) else 0.0


def _timing_sufficient(_query: str, scored: list[SCORED_ROW]) -> bool:
    return any(looks_like_timing_blob(_blob(row[2])) for row in scored[:5])


def _process_activity_score(query: str, _kind: str, _item: dict[str, object], blob: str) -> float:
    return 1.35 if looks_like_process_activity_blob(query, blob) else 0.0


def _process_activity_sufficient(query: str, scored: list[SCORED_ROW]) -> bool:
    return any(looks_like_process_activity_blob(query, _blob(row[2])) for row in scored[:5])


def _test_method_score(query: str, _kind: str, item: dict[str, object], blob: str) -> float:
    if not looks_like_test_method_blob(query, blob):
        return 0.0
    score = 1.35
    if str(item.get("fact_type") or "") == "process_fact":
        score += 0.45
    if "试验方法及步骤" in normalize(blob):
        score += 0.25
    return score


def _test_method_sufficient(query: str, scored: list[SCORED_ROW]) -> bool:
    return any("test_method" in row[4] and looks_like_test_method_blob(query, _blob(row[2])) for row in scored[:5])


def _parameter_definition_score(query: str, _kind: str, item: dict[str, object], blob: str) -> float:
    if not _looks_like_parameter_definition_blob(query, blob):
        return 0.0
    relation = str(item.get("graph_relation") or "")
    if relation in {"has_parameter_topic", "has_parameter_group"}:
        return 1.45
    if str(item.get("fact_type") or "") in {"parameter_definition", "table_requirement"}:
        return 1.05
    return 0.7


def _parameter_definition_sufficient(query: str, scored: list[SCORED_ROW]) -> bool:
    return any("parameter_definition" in row[4] and _looks_like_parameter_definition_blob(query, _blob(row[2])) for row in scored[:5])


def _term_definition_score(query: str, _kind: str, item: dict[str, object], blob: str) -> float:
    if not _looks_like_term_definition_blob(query, blob):
        return 0.0
    relation = str(item.get("graph_relation") or "")
    if relation == "defines_term":
        return 1.4
    if str(item.get("fact_type") or "") == "term_definition":
        return 1.05
    return 0.65


def _term_definition_sufficient(query: str, scored: list[SCORED_ROW]) -> bool:
    return any("term_definition" in row[4] and _looks_like_term_definition_blob(query, _blob(row[2])) for row in scored[:5])


def _query_anchor_tokens(query: str) -> list[str]:
    tokens: list[str] = []
    for match in re.finditer(r"(?<![A-Za-z0-9])([A-Z]{1,8}\d*)(?![A-Za-z0-9])", str(query or ""), re.I):
        value = match.group(1).upper()
        if value not in tokens:
            tokens.append(value)
    for match in re.finditer(r"(检测点\s*\d+|[A-Z]{1,8}阻值|[A-Z]{1,8}占空比)", str(query or ""), re.I):
        value = match.group(1)
        if value not in tokens:
            tokens.append(value)
    return tokens[:8]


def _test_method_topic_tokens(query: str) -> list[str]:
    text = str(query or "")
    tokens: list[str] = []
    if "输入过压" in text:
        tokens.extend(["输入过压", "输入过、欠压", "交流输入过、欠压", "直流输入过、欠压"])
    if "输出过压" in text:
        tokens.extend(["输出过压", "输出过压保护"])
    return [term for index, term in enumerate(tokens) if term and term not in tokens[:index]][:8]


def _object_anchor_terms(query: str) -> tuple[list[str], list[str]]:
    if re.search(r"\bOBC\b|车载充电机|on-?board charger", str(query or ""), re.I):
        return (
            ["OBC", "车载充电机", "电动汽车用传导式车载充电机", "on-board charger", "onboard charger"],
            [] if "逆变器" in str(query or "") else ["汽车电源逆变器", "逆变器"],
        )
    return ([], [])


def _parameter_names(blob: str) -> set[str]:
    result: set[str] = set()
    payload = _extract_json_objects(blob)
    for item in payload:
        for key in ("name", "parameter", "parameter_name", "target_topic", "title"):
            value = str(item.get(key) or "").strip()
            if value and len(value) <= 80:
                result.add(value)
    return result


def _term_names(blob: str) -> set[str]:
    result: set[str] = set()
    payload = _extract_json_objects(blob)
    for item in payload:
        for key in ("term", "name", "subject", "title"):
            value = str(item.get(key) or "").strip()
            if value and len(value) <= 80:
                result.add(value)
    return result


def _extract_json_objects(blob: str) -> list[dict[str, object]]:
    objects: list[dict[str, object]] = []
    for match in re.finditer(r"\{.*?\}", str(blob or "")):
        try:
            value = json.loads(match.group(0))
        except Exception:
            continue
        if isinstance(value, dict):
            objects.append(value)
    return objects[:8]


EVIDENCE_SHAPES: list[EvidenceShape] = [
    EvidenceShape(
        name="signal_state_table",
        applies=is_signal_state_query,
        score_candidate=_signal_state_score,
        is_sufficient=_signal_state_sufficient,
        reason="top evidence covers required anchors and expected signal-state table",
    ),
    EvidenceShape(
        name="timing_table",
        applies=is_timing_query,
        score_candidate=_timing_score,
        is_sufficient=_timing_sufficient,
        reason="top evidence covers required anchors and expected timing table or state-transition evidence",
    ),
    EvidenceShape(
        name="process_activity",
        applies=is_process_activity_query,
        score_candidate=_process_activity_score,
        is_sufficient=_process_activity_sufficient,
        reason="top evidence covers process activity facts with process/BP anchors",
    ),
    EvidenceShape(
        name="test_method",
        applies=is_test_method_query,
        score_candidate=_test_method_score,
        is_sufficient=_test_method_sufficient,
        reason="top evidence covers test method facts with object anchors and procedure steps",
    ),
    EvidenceShape(
        name="parameter_definition",
        applies=is_parameter_definition_query,
        score_candidate=_parameter_definition_score,
        is_sufficient=_parameter_definition_sufficient,
        reason="top evidence covers parameter definition facts with parameter anchors",
    ),
    EvidenceShape(
        name="term_definition",
        applies=is_term_definition_query,
        score_candidate=_term_definition_score,
        is_sufficient=_term_definition_sufficient,
        reason="top evidence covers term definition facts with term anchors",
    ),
]
