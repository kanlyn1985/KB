# -*- coding: utf-8 -*-
"""L3 Semantic Extractor：Provider Protocol + BuiltinRuleExtractor（默认，strict deterministic）。

红线：provider 不接触 akb_assertions/治理 API/authoritative entity store/ontology 写路径/Evidence。
"""
from __future__ import annotations

import re

from agent_kb.evidence_core.compilation.errors import E_SEMANTIC_EXTRACTION_FAILED
from agent_kb.evidence_core.compilation.models import NormalizedSegment, RawExtraction

BUILTIN_EXTRACTOR_VERSION = "builtin-rules-v1.0"


class SemanticCompilerProvider:
    """Protocol（结构化 duck type——与项目现有 Protocol 风格一致）。

    子类必须实现 provider_id() 与 extract(); 输出 RawExtraction。
    """

    def provider_id(self) -> str:
        raise NotImplementedError

    def extract(self, normalized: NormalizedSegment) -> RawExtraction:
        raise NotImplementedError


class BuiltinRuleExtractor(SemanticCompilerProvider):
    """内置规则 provider：R-01..R-06（V0.2_ENTITY_RELATION_EXTRACTION_SPEC）。"""

    def provider_id(self) -> str:
        return "builtin-rules"

    def extractor_version(self) -> str:
        return BUILTIN_EXTRACTOR_VERSION

    def extract(self, normalized: NormalizedSegment) -> RawExtraction:
        text = normalized.normalized_text
        entities: list[dict] = []
        relations: list[dict] = []
        temporal: list[dict] = []

        # R-01 参数关系 + 数值/单位实体：`<entity> <数值><单位>` 或 `<entity> <数值> <单位>`
        for m in re.finditer(
                r"([\u4e00-\u9fa5A-Za-z_][\u4e00-\u9fa5A-Za-z0-9_\- ]{1,20}?)\s*"
                r"(-?\d+(?:\.\d+)?)\s*(mV|V|A|W|kV|mA|kW|ohm|uF|mF|Hz|kHz|%|℃|°C)(?![0-9A-Za-z])",
                text):
            subj = re.sub(r"(不超过|不大于|不小于|不低于|至少|≥|≤|≧|≦|至)$", "",
                          m.group(1).strip())
            subj = re.sub(r"^(实测|测试结果为|测量值|结果为|测得)", "", subj) or subj
            val, unit = m.group(2), m.group(3)
            if subj:
                entities.append({"surface_form": subj, "normalized_form": subj,
                                 "entity_type": "equipment", "confidence": 0.9,
                                 "source_span": list(m.span(1))})
            entities.append({"surface_form": f"{val}{unit}",
                             "normalized_form": f"{val}{unit}",
                             "entity_type": "parameter", "confidence": 0.95,
                             "source_span": list(m.span(2))})
            if subj:
                relations.append({"subject_surface": subj, "predicate": "has_parameter",
                                  "object_surface": f"{val}{unit}",
                                  "confidence": 0.9, "source_span": list(m.span(2))})

        # R-02 约束关系
        for m in re.finditer(
                r"([\u4e00-\u9fa5A-Za-z_][\u4e00-\u9fa5A-Za-z0-9_\- ]{1,20}?)\s*"
                r"(不超过|不大于|不小于|不低于|至少|≥|≤|≧|≦|至)\s*"
                r"(-?\d+(?:\.\d+)?)\s*(mV|V|A|W|kV|mA|kW|ohm|uF|%|℃|°C)?", text):
            subj = m.group(1).strip()
            if subj:
                entities.append({"surface_form": subj, "normalized_form": subj,
                                 "entity_type": "equipment", "confidence": 0.8,
                                 "source_span": list(m.span(1))})
            obj_surface = f"{m.group(2)}{m.group(3)}{m.group(4) or ''}".strip()
            entities.append({"surface_form": obj_surface, "normalized_form": obj_surface,
                             "entity_type": "constraint", "confidence": 0.8,
                             "source_span": list(m.span(2))})
            relations.append({"subject_surface": subj,
                              "predicate": "constrained_by",
                              "object_surface": obj_surface,
                              "confidence": 0.85, "source_span": list(m.span())})

        # R-03 定义关系
        for m in re.finditer(r"([\u4e00-\u9fa5A-Za-z0-9_\- ]{2,24})是指(.{2,40})", text):
            entities.append({"surface_form": m.group(1).strip(), "normalized_form": m.group(1).strip(),
                             "entity_type": "concept", "confidence": 0.85,
                             "source_span": list(m.span(1))})
            obj_text = m.group(2).strip().rstrip("。.")
            entities.append({"surface_form": obj_text, "normalized_form": obj_text,
                             "entity_type": "concept", "confidence": 0.8,
                             "source_span": list(m.span(2))})
            relations.append({"subject_surface": m.group(1).strip(), "predicate": "defined_as",
                              "object_surface": obj_text, "confidence": 0.85,
                              "source_span": list(m.span(2))})

        # R-04 测试关系
        for m in re.finditer(r"([\u4e00-\u9fa5A-Za-z0-9_\- ]{2,24}?(?:测试|试验|验证))\s*([\u4e00-\u9fa5A-Za-z0-9_\-]{2,20})",
                             text):
            entities.append({"surface_form": m.group(1).strip(),
                             "normalized_form": m.group(1).strip(),
                             "entity_type": "test_method", "confidence": 0.8,
                             "source_span": list(m.span(1))})
            entities.append({"surface_form": m.group(2).strip(),
                             "normalized_form": m.group(2).strip(),
                             "entity_type": "equipment", "confidence": 0.8,
                             "source_span": list(m.span(2))})
            relations.append({"subject_surface": m.group(2).strip(), "predicate": "verified_by",
                              "object_surface": m.group(1).strip(), "confidence": 0.8,
                              "source_span": list(m.span())})

        # R-05 条件关系（"当…时"/"在…下"）
        for m in re.finditer(r"(当|在)([^，。；]{2,30}?)(时|的情况下|条件下)", text):
            temporal.append({"kind": "condition", "raw": m.group(0).strip(),
                             "conditions": [m.group(2).strip()]})

        # R-06 观测关系（测试结果句）
        if re.search(r"(实测|测试结果|测量值|结果为|测得)", text):
            for m in re.finditer(r"([\u4e00-\u9fa5A-Za-z_][\u4e00-\u9fa5A-Za-z0-9_\- ]{1,20}?)\s*"
                                 r"(-?\d+(?:\.\d+)?)\s*(mV|V|A|W|%|℃|°C)(?![0-9A-Za-z])", text):
                subj_obs = re.sub(r"^(实测|测试结果为|测量值|结果为|测得)", "",
                                  m.group(1).strip()) or m.group(1).strip()
                if subj_obs:
                    entities.append({"surface_form": subj_obs,
                                     "normalized_form": subj_obs,
                                     "entity_type": "equipment", "confidence": 0.75,
                                     "source_span": list(m.span(1))})
                obj_obs = f"{m.group(2)}{m.group(3)}"
                entities.append({"surface_form": obj_obs, "normalized_form": obj_obs,
                                 "entity_type": "parameter", "confidence": 0.75,
                                 "source_span": list(m.span(2))})
                relations.append({"subject_surface": subj_obs,
                                  "predicate": "observed_value",
                                  "object_surface": obj_obs,
                                  "confidence": 0.75, "source_span": list(m.span(1))})

        # T-01 绝对日期 / T-02 相对标记 / T-03 有效期（原始表达式交 Temporal Parser）
        for m in re.finditer(r"\d{4}-\d{2}-\d{2}|\d{4}年\d{1,2}月|\d{4}年", text):
            temporal.append({"kind": "absolute_date", "raw": m.group(0)})
        for m in re.finditer(r"(自|从)[^，。；]{0,12}(起|之日起)", text):
            temporal.append({"kind": "relative_from", "raw": m.group(0)})
        for m in re.finditer(r"(有效至|有效期至|有效期至)[^，。；]{0,14}", text):
            temporal.append({"kind": "valid_until", "raw": m.group(0)})

        raw = RawExtraction(entities_raw=entities, relations_raw=relations,
                            temporal_expressions=temporal)
        violations = raw.validate()
        if violations:  # 内置规则亦受 schema 约束（防御性）
            raise ValueError(f"{E_SEMANTIC_EXTRACTION_FAILED}: {violations}")
        return raw


class FakeSemanticCompilerProvider(SemanticCompilerProvider):
    """测试用 provider（CMP-010/013）：可注入任意 RawExtraction 或异常。"""

    def __init__(self, result: RawExtraction | None = None, error: Exception | None = None,
                 pid: str = "fake-provider"):
        self._result = result or RawExtraction()
        self._error = error
        self._pid = pid
        self.calls = 0

    def provider_id(self) -> str:
        return self._pid

    def extract(self, normalized: NormalizedSegment) -> RawExtraction:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._result


def validate_provider_output(raw: RawExtraction) -> None:
    """Schema validation（CMP-013）：非法输出 → E-SEMANTIC-EXTRACTION-FAILED。"""
    violations = raw.validate()
    if violations:
        raise ValueError(f"{E_SEMANTIC_EXTRACTION_FAILED}: {violations}")