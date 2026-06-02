from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from .infrastructure.llm_client import LLMClient, Message, Provider
from .exceptions import LLMError, NetworkError, TimeoutError
from .config import AppEndpoints


ALLOWED_QUERY_TYPES = {
    "definition",
    "standard_lookup",
    "lifecycle_lookup",
    "comparison",
    "timing_lookup",
    "parameter_lookup",
    "constraint",
    "section_lookup",
    "scope",
    "general_search",
    "no_answer_candidate",
}

SEMANTIC_PARSER_PROMPT_VERSION = "v1.1.0"
_PROVIDER_FAILURE_UNTIL: dict[str, float] = {}

SEMANTIC_PARSER_SYSTEM_PROMPT = """你是企业知识库的查询语义解析器。

你的唯一职责是把外部自然语言问题解析成稳定、可机器消费的结构化查询对象。

你不是答案生成器，不要回答问题，不要总结文档内容，不要推测知识库中一定存在某条事实。
你只能基于问题本身做语义理解，并输出 JSON。

输出规则：
1. 只输出单个 JSON 对象，不要输出解释、前后缀、markdown 代码块。
2. query_type 只能是以下之一：
   definition, standard_lookup, lifecycle_lookup, comparison, timing_lookup,
   parameter_lookup, constraint, section_lookup, scope, general_search, no_answer_candidate
3. normalized_query 必须是去掉语气词、冗余问法后的核心查询。
4. target_topic 必须是用户真正关注的知识主题，而不是整句照抄。
5. answer_shape 只能使用：
   definition, list, process, requirement_set, table, value, freeform
6. aliases 只能放主题的等价表达、英文名、缩写或常见别称。
7. must_terms 只能放必须保留的实体词、缩写、标准号或主题锚点。
8. should_terms 只能放辅助检索的主题词，不要堆无意义近义词。
9. confidence 输出 0 到 1 的浮点数。

判定原则：
- 问“是什么/定义/如何理解”时，优先 definition。
- 问“是什么意思/代表什么意思/表示什么/指什么/含义是什么”时，如果问题核心是术语释义，也按 definition 处理。
- 问“有哪些类型/种类/包括哪些/分为哪些”时，优先 comparison。
- 问“流程/时序/阶段/状态转换/握手/预充/停机”时，优先 timing_lookup。
- 问“参数/阻值/电压/电流/频率/检测点/占空比”时，优先 parameter_lookup。
- 问“有什么要求/应满足什么/应符合什么/不应超过什么/不小于什么”时，优先 constraint。
- 如果问题没有明确语义目标，再退到 general_search。

通用性要求：
- 不要靠单个词做机械匹配，要尽量抽象出问题真正的主题对象。
- 不要把整句原样塞进 target_topic。
- 如果问题里包含英文缩写和中文主题，两者都要合理保留到 target_topic / aliases / must_terms 中。
- 如果问题里出现“缩写 + 参数词/属性词”（例如 CC阻值、CP占空比、检测点1电压），target_topic 必须保留完整词组，不能只剩裸缩写。
- 不允许输出 undefined、未知主题、未知实体 这类占位词作为 target_topic。
- 如果问题明显无有效内容，才输出 no_answer_candidate。

你必须严格输出 JSON，不允许输出任何额外文本。"""


@dataclass(frozen=True)
class SemanticQuery:
    query_type: str
    normalized_query: str
    target_topic: str
    answer_shape: str
    aliases: list[str]
    must_terms: list[str]
    should_terms: list[str]
    confidence: float
    used_llm: bool
    quality_flags: list[str]
    raw_response: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_minimax_text_settings() -> tuple[str, str, str]:
    _load_env_file(_project_root() / ".env")
    api_base = (
        os.environ.get("MINIMAX_ANTHROPIC_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or AppEndpoints.from_env().minimax_anthropic_base
    )
    api_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("MINIMAX_MODEL") or os.environ.get("LLM_MODEL") or "MiniMax-M2.7"
    if not api_key:
        raise RuntimeError("MiniMax text LLM configuration unavailable")
    return api_base.rstrip("/"), api_key, model


def _load_astron_settings() -> tuple[str, str, str]:
    _load_env_file(_project_root() / ".env")
    auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
    api_base = os.environ.get("ANTHROPIC_BASE_URL", "https://maas-coding-api.cn-huabei-1.xf-yun.com/anthropic")
    model = os.environ.get("ANTHROPIC_MODEL", "astron-code-latest")
    if not auth_token:
        raise RuntimeError("astron query semantic parser configuration unavailable")
    return api_base.rstrip("/"), auth_token, model


def _extract_json_block(content: str) -> dict[str, object]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        text = match.group(0)
    return json.loads(text)


def _text_llm_timeout_seconds() -> float:
    explicit = os.environ.get("EAKB_TEXT_LLM_TIMEOUT_SEC")
    if explicit:
        try:
            return max(1.0, min(float(explicit), 60.0))
        except ValueError:
            return 5.0
    # Default: use a shorter timeout for semantic parsing to avoid blocking answer queries
    try:
        timeout_ms = int(os.environ.get("API_TIMEOUT_MS", "5000"))
    except ValueError:
        timeout_ms = 5000
    return max(1.0, min(timeout_ms / 1000.0, 8.0))


def _provider_failure_cooldown_seconds() -> float:
    try:
        return max(0.0, min(float(os.environ.get("EAKB_LLM_PROVIDER_FAILURE_COOLDOWN_SEC", "120")), 600.0))
    except ValueError:
        return 120.0


def _provider_failure_key(provider_name: str, api_base: str = "", model: str = "") -> str:
    return "|".join(part.strip() for part in (provider_name, api_base.rstrip("/"), model) if part.strip())


def _ensure_provider_available(provider_name: str, api_base: str = "", model: str = "") -> None:
    key = _provider_failure_key(provider_name, api_base, model)
    failure_until = _PROVIDER_FAILURE_UNTIL.get(key, 0.0)
    if failure_until > time.monotonic():
        remaining = round(failure_until - time.monotonic(), 1)
        raise RuntimeError(f"{provider_name} temporarily disabled after recent failure; retry in {remaining}s")


def _mark_provider_failure(provider_name: str, api_base: str = "", model: str = "") -> None:
    cooldown = _provider_failure_cooldown_seconds()
    if cooldown:
        key = _provider_failure_key(provider_name, api_base, model)
        _PROVIDER_FAILURE_UNTIL[key] = time.monotonic() + cooldown


def _sanitize_string_list(value: object, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in items:
            items.append(text)
    return items[:limit]


def _default_semantic(query: str) -> SemanticQuery:
    normalized = query.strip()
    return SemanticQuery(
        query_type="general_search" if normalized else "no_answer_candidate",
        normalized_query=normalized,
        target_topic=normalized,
        answer_shape="freeform",
        aliases=[],
        must_terms=[],
        should_terms=[],
        confidence=0.0,
        used_llm=False,
        quality_flags=[],
        raw_response=None,
    )


def _semantic_prompt(query: str) -> str:
    return (
        f"prompt_version: {SEMANTIC_PARSER_PROMPT_VERSION}\n"
        "请把下面这个用户问题解析成结构化 JSON。\n"
        "字段要求：\n"
        "- query_type: 只能是 definition, standard_lookup, lifecycle_lookup, comparison, timing_lookup, "
        "parameter_lookup, constraint, section_lookup, scope, general_search, no_answer_candidate 之一\n"
        "- normalized_query: 去掉语气和冗余后的核心查询\n"
        "- target_topic: 用户真正关注的主题对象\n"
        "- answer_shape: one_of(definition, list, process, requirement_set, table, value, freeform)\n"
        "- aliases: 主题的等价表达、英文或缩写\n"
        "- must_terms: 必须保留的实体词或缩写\n"
        "- should_terms: 可以辅助检索的主题词\n"
        "- confidence: 0 到 1 的浮点数\n"
        "- 如果 query 中存在缩写 + 参数限定词，target_topic 必须保留完整对象\n"
        "- 不允许输出 undefined、未知主题、未知实体 作为 target_topic\n"
        f"用户问题：{query}"
    )


def _looks_meaningful_query(query: str) -> bool:
    cleaned = re.sub(r"[\s?？!！,，。.:：;；()（）/\\-]+", "", query)
    return len(cleaned) >= 2 and bool(re.search(r"[\u4e00-\u9fffA-Za-z0-9]", cleaned))


def _is_placeholder_topic(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered in {"", "undefined", "unknown", "未知主题", "未知实体", "未定义"}


def _extract_query_anchors(query: str) -> list[str]:
    anchors: list[str] = []
    patterns = [
        r"([A-Z]{1,5}\d*(?:[A-Z0-9'/-]{0,6})?(?:阻值|电阻|电压|电流|频率|占空比))",
        r"(检测点\s*\d+\s*(?:电压|电流|频率|占空比|阻值))",
        r"([A-Z][A-Z0-9/-]{1,10})",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, query, re.I):
            value = re.sub(r"\s+", "", match.group(1).strip())
            if value and value not in anchors:
                anchors.append(value)
    return anchors[:8]


def _semantic_quality_flags(
    *,
    original_query: str,
    query_type: str,
    normalized_query: str,
    target_topic: str,
    must_terms: list[str],
    confidence: float,
) -> list[str]:
    flags: list[str] = []
    anchors = _extract_query_anchors(original_query)
    meaningful = _looks_meaningful_query(original_query)
    if _is_placeholder_topic(target_topic):
        flags.append("placeholder_target_topic")
    if meaningful and query_type == "no_answer_candidate":
        flags.append("meaningful_query_marked_no_answer")
    if anchors and not any(anchor.lower() in normalized_query.lower() for anchor in anchors):
        flags.append("anchor_missing_in_normalized_query")
    if anchors and not any(anchor.lower() in target_topic.lower() for anchor in anchors):
        flags.append("anchor_missing_in_target_topic")
    if meaningful and not must_terms and query_type != "no_answer_candidate":
        flags.append("empty_must_terms")
    if confidence >= 0.75 and {"placeholder_target_topic", "meaningful_query_marked_no_answer"} & set(flags):
        flags.append("high_confidence_low_quality")
    return flags


def _call_llm_message(
    *,
    api_base: str,
    auth_token: str,
    model: str,
    prompt: str,
    system_prompt: str,
    provider_name: str,
) -> str:
    """Call LLM using unified client."""
    timeout_sec = _text_llm_timeout_seconds()

    # Determine provider type from api_base/model
    if "minimax" in api_base.lower() or "minimax" in model.lower():
        provider = Provider.CLAUDE  # MiniMax uses Claude-compatible API
    else:
        provider = Provider.CLAUDE  # Default to Claude (Anthropic-compatible)

    client = LLMClient(
        provider=provider,
        api_base=api_base,
        api_key=auth_token,
        timeout=timeout_sec,
        max_retries=1,
    )

    response = client.chat(
        messages=[Message(role="user", content=prompt)],
        model=model,
        system_prompt=system_prompt,
        temperature=0.0,
        max_tokens=1000,
    )

    if not response.content:
        raise RuntimeError(f"{provider_name} text LLM returned empty content")
    return response.content.strip()


def _call_minimax_text(prompt: str, system_prompt: str = SEMANTIC_PARSER_SYSTEM_PROMPT) -> str:
    api_base, api_key, model = _load_minimax_text_settings()
    _ensure_provider_available("minimax", api_base, model)
    try:
        return _call_llm_message(
            api_base=api_base,
            auth_token=api_key,
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            provider_name="MiniMax",
        )
    except (LLMError, NetworkError, TimeoutError, RuntimeError, ValueError, json.JSONDecodeError):
        _mark_provider_failure("minimax", api_base, model)
        raise


def _call_astron_backup_text(prompt: str, system_prompt: str = SEMANTIC_PARSER_SYSTEM_PROMPT) -> str:
    api_base, auth_token, model = _load_astron_settings()
    _ensure_provider_available("astron", api_base, model)
    try:
        return _call_llm_message(
            api_base=api_base,
            auth_token=auth_token,
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            provider_name="astron",
        )
    except (LLMError, NetworkError, TimeoutError, RuntimeError, ValueError, json.JSONDecodeError):
        _mark_provider_failure("astron", api_base, model)
        raise


def _call_astron_text(prompt: str, system_prompt: str = SEMANTIC_PARSER_SYSTEM_PROMPT) -> str:
    """Call the configured text LLM, with MiniMax as primary and astron as backup.

    The function name is kept for compatibility with existing query modules and tests.
    """
    errors: list[str] = []
    try:
        return _call_minimax_text(prompt, system_prompt=system_prompt)
    except Exception as exc:
        errors.append(f"minimax:{type(exc).__name__}:{exc}")
    try:
        return _call_astron_backup_text(prompt, system_prompt=system_prompt)
    except Exception as exc:
        errors.append(f"astron:{type(exc).__name__}:{exc}")
    raise RuntimeError(f"text LLM failed; {'; '.join(errors)}")


@lru_cache(maxsize=512)
def parse_semantic_query(query: str) -> SemanticQuery:
    stripped = query.strip()
    if not stripped:
        return _default_semantic(query)

    try:
        raw = _call_astron_text(_semantic_prompt(stripped))
        payload = _extract_json_block(raw)
        query_type = str(payload.get("query_type") or "").strip()
        if query_type not in ALLOWED_QUERY_TYPES:
            query_type = "general_search"
        normalized_query = str(payload.get("normalized_query") or stripped).strip() or stripped
        target_topic = str(payload.get("target_topic") or normalized_query).strip() or normalized_query
        answer_shape = str(payload.get("answer_shape") or "freeform").strip() or "freeform"
        aliases = _sanitize_string_list(payload.get("aliases"))
        must_terms = _sanitize_string_list(payload.get("must_terms"))
        should_terms = _sanitize_string_list(payload.get("should_terms"))
        confidence = float(payload.get("confidence") or 0.0)
        confidence = max(0.0, min(1.0, confidence))
        if _is_placeholder_topic(target_topic):
            target_topic = normalized_query
        quality_flags = _semantic_quality_flags(
            original_query=stripped,
            query_type=query_type,
            normalized_query=normalized_query,
            target_topic=target_topic,
            must_terms=must_terms,
            confidence=confidence,
        )
        if "meaningful_query_marked_no_answer" in quality_flags:
            confidence = min(confidence, 0.2)
        return SemanticQuery(
            query_type=query_type,
            normalized_query=normalized_query,
            target_topic=target_topic,
            answer_shape=answer_shape,
            aliases=aliases,
            must_terms=must_terms,
            should_terms=should_terms,
            confidence=confidence,
            used_llm=True,
            quality_flags=quality_flags,
            raw_response=raw,
        )
    except (LLMError, NetworkError, TimeoutError, RuntimeError, ValueError, json.JSONDecodeError):
        return _default_semantic(query)
