"""LLM-powered ontology extraction engine.

Reads document text, calls an LLM to extract Entity/Attribute/Relation
triples following the Domain Pack schema, and persists them into the
OntologyStore with evidence traceability.

Extraction contract (LLM output JSON):
{
  "entities": [
    {
      "local_key": "e1",
      "class": "Parameter",
      "canonical_name": "输出纹波",
      "attributes": {"value": 30, "unit": "mVpp", "operator": "<=", "condition": "额定负载"},
      "text_span": "DCDC输出纹波在额定负载下应不大于30mVpp",
      "location": "第3段",
      "confidence": 0.9
    }
  ],
  "relations": [
    {"source_key": "e1", "relation_type": "verified_by", "target_key": "e2", "confidence": 0.85}
  ]
}
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from kb_ontology.domains.schema import DomainPack
from kb_ontology.extraction.schema_prompt import build_schema_description
from kb_ontology.llm.llm_client import LLMChatClient, LLMClientError
from kb_ontology.storage.store import OntologyStore

_logger = logging.getLogger(__name__)

EXTRACTION_PROMPT_VERSION = "v1.0.0"

# ── System prompt ──

_EXTRACTION_SYSTEM_PROMPT = """你是一个知识萃取引擎。你的唯一任务是把文档内容提取为结构化的本体知识（Entity + Attribute + Relation）。

你不是答案生成器。不要回答问题、不要总结、不要推测文档中没有的知识。
你只能从文档中提取已明确存在的信息。

输出规则：
1. 只输出单个 JSON 对象，不要输出解释、前后缀、markdown 代码块。
2. JSON 结构必须是：
   {
     "entities": [
       {
         "local_key": "e1",         // 文档内唯一标识，relations 用它引用
         "class": "Class名",         // 只能使用 schema 中定义的 Class
         "canonical_name": "实体名",  // 实体的规范名称
         "attributes": {},           // 按该 Class 的属性模板填充
         "text_span": "原文摘录",     // 提取该实体时的原文句子
         "location": "位置",          // 在文档中的位置（标题/段落/表格）
         "confidence": 0.0~1.0
       }
     ],
     "relations": [
       {
         "source_key": "e1",        // 引用 entities 中的 local_key
         "relation_type": "关系类型", // 只能使用 schema 中定义的关系类型
         "target_key": "e2",
         "confidence": 0.0~1.0
       }
     ]
   }

提取原则：
- 只提取 schema 中已定义的 Class。无法归入任何已定义 Class 的内容跳过。
- canonical_name 用该实体在该领域中最常见的中文名称。
- attributes 按该 Class 的属性模板填充。不存在的属性不要编造。
- 如果文档中同一个概念出现多次，只提取一次（用同一个 local_key）。
- relations 只在文档明确描述了两者关系时才提取。不要推测关系。
- text_span 必须是文档中的原文，不是你的改写。
- confidence 反映你对这次提取的把握：原文明确=0.9+，需要推断=0.6-0.8，不确定=<0.5。
- 如果文档内容与本体 schema 完全不相关，返回空 entities 和 relations。

你必须严格输出 JSON，不允许输出任何额外文本。"""


# ── JSON extraction (copied from semantic_parser pattern) ──

_LLM_JSON_MARKER = re.compile(r"\{.*\}", re.S)


def _extract_json_block(raw: str) -> dict[str, Any]:
    """Strip markdown fences and extract the first JSON object."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = _LLM_JSON_MARKER.search(text)
    if match:
        text = match.group(0)
    return json.loads(text)


# ── Extraction data structures ──


@dataclass(frozen=True)
class ExtractedEntity:
    """An entity extracted by the LLM, before storage resolution."""

    local_key: str
    class_name: str
    canonical_name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    text_span: str = ""
    location: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_key": self.local_key,
            "class": self.class_name,
            "canonical_name": self.canonical_name,
            "attributes": dict(self.attributes),
            "text_span": self.text_span,
            "location": self.location,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ExtractedRelation:
    """A relation extracted by the LLM, referencing entities by local_key."""

    source_key: str
    relation_type: str
    target_key: str
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "relation_type": self.relation_type,
            "target_key": self.target_key,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ExtractionResult:
    """Full extraction output from one document."""

    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)
    raw_response: dict[str, Any] = field(default_factory=dict)

    @property
    def entity_count(self) -> int:
        return len(self.entities)

    @property
    def relation_count(self) -> int:
        return len(self.relations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "relations": [r.to_dict() for r in self.relations],
        }


# ── Prompt builder ──


def _build_user_prompt(text: str, domain_pack: DomainPack) -> str:
    schema_desc = build_schema_description(domain_pack)
    return (
        f"prompt_version: {EXTRACTION_PROMPT_VERSION}\n"
        f"以下是本体 schema 定义：\n\n"
        f"{schema_desc}\n\n"
        f"---\n\n"
        f"请从以下文档中提取知识。严格按上面的 schema 定义提取，"
        f"只提取已定义的 Class 和关系类型。\n\n"
        f"文档内容：\n{text}"
    )


# ── Extraction engine ──


def extract_document(
    text: str,
    *,
    document_id: str,
    domain_pack: DomainPack,
    store: OntologyStore,
    client: LLMChatClient,
    max_tokens: int = 4000,
) -> ExtractionResult:
    """Extract entities/relations from a document and persist to store.

    Args:
        text: Clean document text (pre-processing already done externally).
        document_id: Identifier for the source document (for evidence).
        domain_pack: Domain pack defining the Class/Relation schema.
        store: OntologyStore to write into.
        client: LLM chat client.
        max_tokens: Max LLM response tokens.

    Returns:
        ExtractionResult with what was extracted and stored.
    """
    if not text.strip():
        return ExtractionResult()

    # 1. Call LLM
    try:
        user_prompt = _build_user_prompt(text, domain_pack)
        response = client.chat(
            user_message=user_prompt,
            system_prompt=_EXTRACTION_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=max_tokens,
        )
        llm_json = _extract_json_block(response.content)
    except (LLMClientError, json.JSONDecodeError, ValueError, KeyError) as exc:
        _logger.warning("LLM extraction failed for doc %s: %s", document_id, exc)
        return ExtractionResult()

    # 2. Parse entities and relations from LLM output
    result = _parse_extraction_output(llm_json)
    result = ExtractionResult(
        entities=result.entities,
        relations=result.relations,
        raw_response=llm_json,
    )

    # 3. Persist to store
    _persist_extraction(result, document_id, domain_pack, store)

    return result


def _parse_extraction_output(llm_json: dict[str, Any]) -> ExtractionResult:
    """Parse raw LLM JSON into ExtractionResult dataclasses."""
    entities: list[ExtractedEntity] = []
    relations: list[ExtractedRelation] = []

    for raw_entity in llm_json.get("entities", []):
        if not isinstance(raw_entity, dict):
            continue
        local_key = str(raw_entity.get("local_key") or raw_entity.get("key") or "").strip()
        class_name = str(raw_entity.get("class") or raw_entity.get("type") or "").strip()
        canonical_name = str(raw_entity.get("canonical_name") or raw_entity.get("name") or "").strip()
        if not local_key or not class_name or not canonical_name:
            continue
        attributes = raw_entity.get("attributes") or {}
        if not isinstance(attributes, dict):
            attributes = {}
        try:
            confidence = max(0.0, min(float(raw_entity.get("confidence", 1.0)), 1.0))
        except (ValueError, TypeError):
            confidence = 1.0
        entities.append(
            ExtractedEntity(
                local_key=local_key,
                class_name=class_name,
                canonical_name=canonical_name,
                attributes=attributes,
                text_span=str(raw_entity.get("text_span") or ""),
                location=str(raw_entity.get("location") or ""),
                confidence=confidence,
            )
        )

    for raw_rel in llm_json.get("relations", []):
        if not isinstance(raw_rel, dict):
            continue
        source_key = str(raw_rel.get("source_key") or raw_rel.get("source") or "").strip()
        relation_type = str(raw_rel.get("relation_type") or raw_rel.get("type") or "").strip()
        target_key = str(raw_rel.get("target_key") or raw_rel.get("target") or "").strip()
        if not source_key or not relation_type or not target_key:
            continue
        try:
            confidence = max(0.0, min(float(raw_rel.get("confidence", 1.0)), 1.0))
        except (ValueError, TypeError):
            confidence = 1.0
        relations.append(
            ExtractedRelation(
                source_key=source_key,
                relation_type=relation_type,
                target_key=target_key,
                confidence=confidence,
            )
        )

    return ExtractionResult(entities=entities, relations=relations)


def _persist_extraction(
    result: ExtractionResult,
    document_id: str,
    domain_pack: DomainPack,
    store: OntologyStore,
) -> None:
    """Persist extraction result into the OntologyStore.

    Resolves local_keys to entity_ids via find_or_create_entity,
    then upserts attributes, relations, and evidence.
    """
    domain_id = domain_pack.domain_id
    key_to_entity_id: dict[str, str] = {}

    # Validate class names against domain pack
    valid_classes = set(domain_pack.classes.keys())

    # Process entities
    for ext_entity in result.entities:
        if ext_entity.class_name not in valid_classes:
            _logger.debug(
                "Skipping entity '%s': class '%s' not in domain pack",
                ext_entity.canonical_name,
                ext_entity.class_name,
            )
            continue

        # Build canonical name — for multi-attribute identity, fold condition into name
        cls_spec = domain_pack.get_class(ext_entity.class_name)
        canonical_name = ext_entity.canonical_name
        if cls_spec and len(cls_spec.identity_attributes) > 1:
            # If identity uses name + condition, incorporate condition into name for lookup
            condition = ext_entity.attributes.get("condition", "")
            if condition:
                canonical_name = f"{ext_entity.canonical_name} ({condition})"

        # Find or create entity
        entity = store.find_or_create_entity(
            class_name=ext_entity.class_name,
            canonical_name=canonical_name,
            domain=domain_id,
        )
        key_to_entity_id[ext_entity.local_key] = entity.id

        # Add entity-level evidence
        if ext_entity.text_span:
            store.add_evidence(
                ref_type="entity",
                ref_id=entity.id,
                document_id=document_id,
                text_span=ext_entity.text_span,
                location=ext_entity.location,
                confidence=ext_entity.confidence,
            )

        # Get attribute specs for this class
        if cls_spec:
            for attr_name, attr_value in ext_entity.attributes.items():
                attr_spec = cls_spec.attribute_template.get(attr_name)
                if attr_spec is None:
                    # Attribute not in template — skip or store as string
                    _logger.debug(
                        "Attribute '%s' not in class '%s' template, storing as string",
                        attr_name,
                        ext_entity.class_name,
                    )
                    attr = store.upsert_attribute(
                        entity_id=entity.id,
                        name=attr_name,
                        value=str(attr_value),
                        value_type="string",
                        confidence=ext_entity.confidence,
                    )
                else:
                    attr = store.upsert_attribute(
                        entity_id=entity.id,
                        name=attr_name,
                        value=attr_value,
                        value_type=attr_spec.value_type,
                        confidence=ext_entity.confidence,
                    )
                    # Add attribute-level evidence
                    if ext_entity.text_span:
                        store.add_evidence(
                            ref_type="attribute",
                            ref_id=attr.id,
                            document_id=document_id,
                            text_span=ext_entity.text_span,
                            location=ext_entity.location,
                            confidence=ext_entity.confidence,
                        )

    # Process relations
    valid_relation_types = set(domain_pack.all_relation_types.keys())
    for ext_rel in result.relations:
        if ext_rel.relation_type not in valid_relation_types:
            _logger.debug(
                "Skipping relation '%s': type not in domain pack",
                ext_rel.relation_type,
            )
            continue

        source_id = key_to_entity_id.get(ext_rel.source_key)
        target_id = key_to_entity_id.get(ext_rel.target_key)
        if not source_id or not target_id:
            _logger.debug(
                "Skipping relation: unresolved keys source=%s target=%s",
                ext_rel.source_key,
                ext_rel.target_key,
            )
            continue

        rel = store.upsert_relation(
            source_id=source_id,
            relation_type=ext_rel.relation_type,
            target_id=target_id,
            confidence=ext_rel.confidence,
        )
