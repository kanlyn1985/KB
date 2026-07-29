"""Query understanding: natural language → QueryFrame.

Rule-first intent + slot extraction. Optional LLM refinement when a client
is provided and rules are low-confidence (does not generate SQL).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from kb_ontology.domains.schema import DomainPack
from kb_ontology.llm.llm_client import LLMChatClient, LLMClientError
from kb_ontology.query.frame import (
    KNOWN_INTENTS,
    QueryAmbiguity,
    QueryFrame,
    TargetEntityRef,
)
from kb_ontology.query.resolve import resolve_entity_name
from kb_ontology.storage.store import OntologyStore

_logger = logging.getLogger(__name__)

# Ordered: first match wins. Patterns are searched against the raw query.
_INTENT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    (
        "hierarchy_traversal",
        (
            r"包含哪些",
            r"有哪些子",
            r"子系统",
            r"组成",
            r"层级",
            r"下属",
            r"part\s*of",
            r"consists?\s+of",
            r"components?",
            r"hierarchy",
        ),
    ),
    (
        "cross_entity",
        (
            r"什么关系",
            r"之间.*关系",
            r"和.+关系",
            r"与.+关系",
            r"关系是",
            r"related\s+to",
            r"relationship",
        ),
    ),
    (
        "relation_query",
        (
            r"测试方法",
            r"验证方法",
            r"有哪些.*方法",
            r"关联",
            r"引用了",
            r"依赖于",
            r"verified_by",
            r"references",
        ),
    ),
    (
        "parameter_lookup",
        (
            r"是多少",
            r"多少[？?]",
            r"限值",
            r"限制",
            r"阈值",
            r"参数值",
            r"取值",
            r"value\s+of",
            r"how\s+much",
            r"what\s+is\s+the\s+(value|limit|threshold)",
        ),
    ),
    (
        "attribute_search",
        (
            r"哪些参数",
            r"哪些.*有关",
            r"和.+有关",
            r"涉及.+的",
            r"whose\s+.+=",
            r"attributes?\s+containing",
            r"search\s+by\s+value",
        ),
    ),
    (
        "definition",
        (
            r"是什么",
            r"什么是",
            r"定义",
            r"简介",
            r"介绍",
            r"含义",
            r"工作原理",
            r"原理",
            r"拓扑",
            r"what\s+is",
            r"define",
            r"definition\s+of",
            r"explain",
            r"how\s+does",
            r"principle",
        ),
    ),
]

_ATTR_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("value", (r"值", r"value")),
    ("unit", (r"单位", r"unit")),
    ("operator", (r"运算符", r"operator")),
    ("condition", (r"条件", r"工况", r"condition")),
    ("description", (r"描述", r"说明", r"description")),
]

_RELATION_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("part_of", (r"part_of", r"属于", r"组成", r"包含")),
    ("references", (r"references", r"引用", r"参照")),
    ("verified_by", (r"verified_by", r"验证", r"测试方法", r"测量方法")),
    ("constrained_by", (r"constrained_by", r"约束")),
    ("defined_in", (r"defined_in", r"定义于", r"定义在")),
]


def _detect_intent(query: str) -> tuple[str, float]:
    for intent, patterns in _INTENT_PATTERNS:
        for pat in patterns:
            if re.search(pat, query, flags=re.IGNORECASE):
                return intent, 0.82
    return "unknown", 0.3


def _detect_relation_type(query: str) -> str | None:
    for rel, patterns in _RELATION_HINTS:
        for pat in patterns:
            if re.search(pat, query, flags=re.IGNORECASE):
                return rel
    return None


def _detect_target_attributes(query: str) -> list[str]:
    found: list[str] = []
    for name, patterns in _ATTR_HINTS:
        for pat in patterns:
            if re.search(pat, query, flags=re.IGNORECASE):
                found.append(name)
                break
    return found


def _terminology_mentions(query: str, domain_pack: DomainPack | None) -> list[str]:
    if domain_pack is None:
        return []
    q = query.lower()
    hits: list[tuple[int, str]] = []  # (alias_len, matched_surface)
    for term_id, entry in (domain_pack.terminology or {}).items():
        if isinstance(entry, list):
            aliases = [str(a).strip() for a in entry if str(a).strip()]
        elif isinstance(entry, dict):
            aliases = [str(a).strip() for a in (entry.get("aliases") or []) if str(a).strip()]
        else:
            aliases = []
        candidates = [term_id, term_id.replace("_", " "), *aliases]
        # Prefer the longest alias that actually appears in the query so
        # "车载DC-DC转换器" is not collapsed to a shorter preferred display.
        matched: str | None = None
        matched_len = -1
        for alias in candidates:
            a = str(alias).strip()
            if not a:
                continue
            if a.lower() in q and len(a) > matched_len:
                matched = a
                matched_len = len(a)
        if matched:
            hits.append((matched_len, matched))
    hits.sort(key=lambda x: -x[0])
    out: list[str] = []
    for _, display in hits:
        if display not in out:
            out.append(display)
    return out[:5]


def _fallback_names(name: str, domain_pack: DomainPack | None) -> list[str]:
    """Generate shorter resolve candidates when the full phrase misses the store."""
    raw = (name or "").strip()
    if not raw:
        return []
    out: list[str] = []
    # Drop descriptive suffixes common in OBC/DCDC product questions.
    suffixes = (
        "电路拓扑",
        "拓扑",
        "工作原理",
        "原理",
        "简介",
        "介绍",
        "策略",
        "流程",
        "系统",
    )
    peeled = raw
    for suf in suffixes:
        if peeled.endswith(suf) and len(peeled) > len(suf) + 1:
            peeled = peeled[: -len(suf)].strip(" 的")
            if peeled and peeled not in out:
                out.append(peeled)
    # Terminology mentions inside the phrase, longest first already ordered.
    for m in _terminology_mentions(raw, domain_pack):
        if m != raw and m not in out:
            out.append(m)
    # Significant CJK/ASCII token.
    import re as _re

    cjk = _re.findall(r"[\u4e00-\u9fff]{2,}", raw)
    alnum = _re.findall(r"[A-Za-z][A-Za-z0-9\-]{1,}", raw)
    for tok in sorted(cjk + alnum, key=len, reverse=True):
        if tok != raw and tok not in out:
            out.append(tok)
    return out[:6]


def _strip_question_noise(query: str) -> str:
    text = query.strip()
    # Drop common Chinese/English question wrappers to leave a topic phrase.
    patterns = [
        r"^什么是\s*",
        r"^请问\s*",
        r"^请介绍\s*",
        r"^介绍一下\s*",
        r"^告诉我\s*",
        r"^哪些参数和\s*",
        r"^哪些.*和\s*",
        r"\s*是什么[？?]?$",
        r"\s*是多少[？?]?$",
        r"\s*有哪些(?:子(?:系统|模块|件)?)?[？?]?$",
        r"\s*包含哪些(?:子(?:系统|模块|件)?)?[？?]?$",
        r"\s*由哪些.*组成[？?]?$",
        r"\s*有关[？?]?$",
        r"\s*相关[的参数]?[？?]?$",
        r"\s*的?(限制|限值|定义|简介|含义|测试方法|验证方法|工作原理|原理|拓扑)[是为]?多少?[？?]?$",
        r"\s*工作原理[是为]?[什么]?[？?]?$",
        r"\s*原理[是为]?[什么]?[？?]?$",
        r"^what\s+is\s+(the\s+)?",
        r"^define\s+",
        r"\s*consists?\s+of\s*$",
        r"\?+$",
        r"？+$",
    ]
    for pat in patterns:
        text = re.sub(pat, "", text, flags=re.IGNORECASE)
    return text.strip(" \t，,。:：")


def _extract_cross_pair(query: str) -> tuple[str, str] | None:
    """Try to pull two entity names from 'A 和 B 什么关系' style queries."""
    patterns = [
        r"(.+?)\s*(?:和|与|跟|and)\s*(.+?)\s*(?:之间)?(?:的)?(?:什么)?关系",
        r"(.+?)\s*(?:和|与|跟|and)\s*(.+?)\s*relationship",
        r"relationship\s+between\s+(.+?)\s+and\s+(.+)",
    ]
    for pat in patterns:
        m = re.search(pat, query, flags=re.IGNORECASE)
        if m:
            a = _strip_question_noise(m.group(1))
            b = _strip_question_noise(m.group(2))
            if a and b:
                return a, b
    return None


def _candidate_names(
    query: str,
    intent: str,
    domain_pack: DomainPack | None,
) -> list[tuple[str, str]]:
    """Return (name, role) pairs to resolve."""
    if intent == "cross_entity":
        pair = _extract_cross_pair(query)
        if pair:
            return [(pair[0], "source"), (pair[1], "target")]

    topic = _strip_question_noise(query)
    mentions = _terminology_mentions(query, domain_pack)
    if intent == "cross_entity" and len(mentions) >= 2:
        return [(mentions[0], "source"), (mentions[1], "target")]

    # Prefer the more specific surface form: stripped topic if it contains
    # (or equals) a terminology mention, else the longest mention, else topic.
    if topic and mentions:
        t_l = topic.lower()
        for m in mentions:
            if m.lower() == t_l or m.lower() in t_l or t_l in m.lower():
                # Topic is at least as specific as the mention.
                chosen = topic if len(topic) >= len(m) else m
                return [(chosen, "primary")]
        # Topic and mention disagree — try topic first (store may have it).
        return [(topic, "primary")]
    if mentions:
        return [(mentions[0], "primary")]
    if topic:
        return [(topic, "primary")]
    return []


def understand_query(
    query: str,
    *,
    store: OntologyStore | None = None,
    domain_pack: DomainPack | None = None,
    domain: str | None = None,
    client: LLMChatClient | None = None,
    use_llm: bool = False,
) -> QueryFrame:
    """Build a QueryFrame from a natural-language query.

    Resolution against ``store`` is optional but recommended so templates
    receive entity_ids directly.
    """
    original = (query or "").strip()
    if not original:
        return QueryFrame(
            original_query="",
            intent="unknown",
            intent_confidence=0.0,
            domain=domain or (domain_pack.domain_id if domain_pack else None),
            quality_flags=["empty_query"],
        )

    intent, intent_confidence = _detect_intent(original)
    relation_type = _detect_relation_type(original)
    target_attributes = _detect_target_attributes(original)
    normalized = _strip_question_noise(original) or original
    name_roles = _candidate_names(original, intent, domain_pack)

    # attribute_search: value needle often is the topic itself.
    attribute_value_query = None
    if intent == "attribute_search":
        attribute_value_query = normalized

    target_entities: list[TargetEntityRef] = []
    ambiguity: list[QueryAmbiguity] = []
    quality_flags: list[str] = []
    aliases: list[str] = [n for n, _ in name_roles]

    if store is not None and name_roles:
        for name, role in name_roles:
            hits = resolve_entity_name(
                store,
                name,
                domain_pack=domain_pack,
                domain=domain or (domain_pack.domain_id if domain_pack else None),
                role=role,
            )
            # Fallback: peel topic suffixes / try shorter terminology mentions
            # (e.g. "OBC电路拓扑" → "OBC" when only the product is stored).
            if not hits:
                for alt in _fallback_names(name, domain_pack):
                    hits = resolve_entity_name(
                        store,
                        alt,
                        domain_pack=domain_pack,
                        domain=domain
                        or (domain_pack.domain_id if domain_pack else None),
                        role=role,
                    )
                    if hits:
                        name = alt
                        break
            if not hits:
                target_entities.append(
                    TargetEntityRef(
                        canonical_name=name,
                        matched_text=name,
                        confidence=0.0,
                        role=role,
                    )
                )
                quality_flags.append(f"unresolved:{name}")
                continue
            if len(hits) > 1 and hits[0].confidence - hits[1].confidence < 0.08:
                ambiguity.append(
                    QueryAmbiguity(
                        term=name,
                        candidates=[h.canonical_name for h in hits[:5]],
                        reason="multiple_entities_similar_confidence",
                        clarification=f"“{name}”可能指：{', '.join(h.canonical_name for h in hits[:3])}",
                    )
                )
            target_entities.append(hits[0])
    else:
        for name, role in name_roles:
            target_entities.append(
                TargetEntityRef(
                    canonical_name=name,
                    matched_text=name,
                    confidence=0.4,
                    role=role,
                )
            )

    frame = QueryFrame(
        original_query=original,
        intent=intent,
        intent_confidence=intent_confidence,
        domain=domain or (domain_pack.domain_id if domain_pack else None),
        normalized_query=normalized,
        target_entities=target_entities,
        target_attributes=target_attributes,
        relation_type=relation_type,
        attribute_value_query=attribute_value_query,
        aliases=aliases,
        ambiguity=ambiguity,
        used_llm=False,
        quality_flags=quality_flags,
    )

    if use_llm and client is not None and (
        intent == "unknown" or intent_confidence < 0.6 or quality_flags
    ):
        refined = _llm_refine(frame, client, domain_pack)
        if refined is not None:
            frame = refined
            # Re-resolve if LLM filled names without ids.
            if store is not None:
                frame = _reresolve(frame, store, domain_pack)

    return frame


def _reresolve(
    frame: QueryFrame,
    store: OntologyStore,
    domain_pack: DomainPack | None,
) -> QueryFrame:
    new_targets: list[TargetEntityRef] = []
    flags = list(frame.quality_flags)
    for t in frame.target_entities:
        if t.is_resolved:
            new_targets.append(t)
            continue
        name = t.canonical_name or t.matched_text
        hits = resolve_entity_name(
            store,
            name,
            domain_pack=domain_pack,
            domain=frame.domain,
            role=t.role,
        )
        if hits:
            new_targets.append(hits[0])
            flags = [f for f in flags if f != f"unresolved:{name}"]
        else:
            new_targets.append(t)
    return QueryFrame(
        original_query=frame.original_query,
        intent=frame.intent,
        intent_confidence=frame.intent_confidence,
        domain=frame.domain,
        normalized_query=frame.normalized_query,
        target_entities=new_targets,
        target_attributes=list(frame.target_attributes),
        relation_type=frame.relation_type,
        attribute_value_query=frame.attribute_value_query,
        hierarchy_direction=frame.hierarchy_direction,
        max_depth=frame.max_depth,
        slots=dict(frame.slots),
        aliases=list(frame.aliases),
        ambiguity=list(frame.ambiguity),
        used_llm=frame.used_llm,
        quality_flags=flags,
    )


_LLM_SYSTEM = """你是查询理解器。把用户问题解析为 JSON QueryFrame，不要回答问题，不要生成 SQL。
只输出一个 JSON 对象，字段：
{
  "intent": one of [parameter_lookup, definition, relation_query, hierarchy_traversal, cross_entity, attribute_search, unknown],
  "intent_confidence": 0.0-1.0,
  "normalized_query": "精简后的主题",
  "target_names": [{"name": "...", "role": "primary|source|target|secondary"}],
  "target_attributes": ["value","unit",...],
  "relation_type": "part_of|references|verified_by|null",
  "attribute_value_query": "反向属性搜索时的值子串或 null",
  "hierarchy_direction": "down|up"
}
"""


def _llm_refine(
    frame: QueryFrame,
    client: LLMChatClient,
    domain_pack: DomainPack | None,
) -> QueryFrame | None:
    schema_hint = ""
    if domain_pack is not None:
        classes = ", ".join(domain_pack.classes.keys())
        rels = ", ".join(domain_pack.all_relation_types.keys())
        schema_hint = f"\nDomain={domain_pack.domain_id}; Classes=[{classes}]; Relations=[{rels}]"
    user = (
        f"用户问题：{frame.original_query}\n"
        f"规则初判 intent={frame.intent} conf={frame.intent_confidence}"
        f"{schema_hint}\n"
        "请输出 JSON。"
    )
    try:
        resp = client.chat(user, system_prompt=_LLM_SYSTEM, temperature=0.0, max_tokens=800)
    except LLMClientError as exc:
        _logger.warning("LLM query understanding failed: %s", exc)
        return None
    data = _extract_json(resp.content)
    if not isinstance(data, dict):
        return None
    intent = str(data.get("intent") or frame.intent)
    if intent not in KNOWN_INTENTS:
        intent = frame.intent
    try:
        conf = float(data.get("intent_confidence", frame.intent_confidence))
    except (TypeError, ValueError):
        conf = frame.intent_confidence
    names = data.get("target_names") or []
    target_entities: list[TargetEntityRef] = []
    if isinstance(names, list):
        for item in names:
            if not isinstance(item, dict):
                continue
            target_entities.append(
                TargetEntityRef(
                    canonical_name=str(item.get("name") or "").strip(),
                    matched_text=str(item.get("name") or "").strip(),
                    confidence=0.5,
                    role=str(item.get("role") or "primary"),
                )
            )
    if not target_entities:
        target_entities = list(frame.target_entities)
    attrs = data.get("target_attributes") or frame.target_attributes
    if not isinstance(attrs, list):
        attrs = frame.target_attributes
    rel = data.get("relation_type", frame.relation_type)
    if rel in ("", "null", "None"):
        rel = None
    direction = str(data.get("hierarchy_direction") or frame.hierarchy_direction)
    if direction not in ("up", "down"):
        direction = frame.hierarchy_direction
    value_q = data.get("attribute_value_query", frame.attribute_value_query)
    if value_q in ("", "null", "None"):
        value_q = None
    return QueryFrame(
        original_query=frame.original_query,
        intent=intent,
        intent_confidence=conf,
        domain=frame.domain,
        normalized_query=str(data.get("normalized_query") or frame.normalized_query),
        target_entities=target_entities,
        target_attributes=[str(a) for a in attrs],
        relation_type=str(rel) if rel else None,
        attribute_value_query=str(value_q) if value_q else None,
        hierarchy_direction=direction,
        max_depth=frame.max_depth,
        slots=dict(frame.slots),
        aliases=list(frame.aliases),
        ambiguity=list(frame.ambiguity),
        used_llm=True,
        quality_flags=list(frame.quality_flags),
    )


def _extract_json(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        return None
    # Direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fenced block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # First {...}
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None
