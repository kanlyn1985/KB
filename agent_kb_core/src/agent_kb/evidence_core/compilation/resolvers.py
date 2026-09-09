# -*- coding: utf-8 -*-
"""L4 Entity / L5 Relation Candidate Resolver + L6 Temporal Parser + L7 Ontology Mapper。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from agent_kb.evidence_core.compilation.models import (
    EntityCandidate,
    OntologyMapping,
    RawExtraction,
    RelationCandidate,
    TemporalParse,
)


class EntityCandidateResolver:
    """L4：raw entities → EntityCandidate[]（稳定排序 (span_start, normalized_form)）。"""

    def resolve(self, raw: RawExtraction) -> list[EntityCandidate]:
        out: list[EntityCandidate] = []
        seen_spans = set()
        for e in raw.entities_raw:
            span = tuple(e.get("source_span") or ())
            key = (e["surface_form"], e.get("normalized_form") or e["surface_form"], span)
            if key in seen_spans:  # R-01/R-03 可能对同一表面形重复登记——去重保持稳定
                continue
            seen_spans.add(key)
            out.append(EntityCandidate(
                candidate_id=f"ec_{len(out) + 1:04d}",
                surface_form=e["surface_form"],
                normalized_form=(e.get("normalized_form") or e["surface_form"]).strip(),
                entity_type=e.get("entity_type", "unknown"),
                confidence=round(float(e.get("confidence", 0.0)), 4),
                source_span=span,
                ontology_hint=e.get("ontology_hint")))
        out.sort(key=lambda c: c.sort_key())
        # 重排序号（排序后重编，保证 run 内稳定序号）
        for i, c in enumerate(out):
            c.candidate_id = f"ec_{i + 1:04d}"
        return out


class RelationCandidateResolver:
    """L5：raw relations → RelationCandidate[]（subject/object 必须引用当前 run 候选）。"""

    def resolve(self, raw: RawExtraction, entities: list[EntityCandidate]) -> list[RelationCandidate]:
        by_surface: dict[str, EntityCandidate] = {}
        for e in entities:
            by_surface.setdefault(e.surface_form, e)
            by_surface.setdefault(e.normalized_form, e)
        out: list[RelationCandidate] = []
        for r in raw.relations_raw:
            subj = by_surface.get(r["subject_surface"].strip())
            obj = by_surface.get(r["object_surface"].strip())
            if subj is None or obj is None:
                continue  # 孤儿引用丢弃（候选级隔离；warning 由编排层按 raw/reduced 差额记录）
            out.append(RelationCandidate(
                relation_candidate_id=f"rc_{len(out) + 1:04d}",
                subject_candidate_id=subj.candidate_id,
                predicate_candidate=r["predicate"].strip(),
                object_candidate_id=obj.candidate_id,
                confidence=round(float(r.get("confidence", 0.0)), 4),
                source_span=tuple(r.get("source_span") or ()),
                ontology_hint=r.get("ontology_hint")))
        out.sort(key=lambda c: c.sort_key())
        for i, c in enumerate(out):
            c.relation_candidate_id = f"rc_{i + 1:04d}"
        return out


_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


class TemporalParser:
    """L6：五类时间分离；相对时间锚定 document_effective_time；禁止当前时钟。"""

    def parse(self, expressions: list[dict], *,
              observation_time: str | None, document_effective_time: str | None,
              ingestion_time: str | None) -> TemporalParse | None:
        if not expressions:
            return None
        parse = TemporalParse(
            observation_time=observation_time,
            document_effective_time=document_effective_time,
            ingestion_time=ingestion_time,
            raw_expressions=[e.get("raw", "") for e in expressions])
        statuses = set()
        for expr in expressions:
            kind = expr.get("kind")
            raw_text = expr.get("raw", "")
            if kind == "condition":
                parse.conditions.extend(expr.get("conditions", []))
            elif kind == "absolute_date":
                m = _DATE_RE.search(raw_text)
                if m:
                    parse.event_time = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                    statuses.add("resolved")
                else:
                    statuses.add("unresolved")
            elif kind == "relative_from":
                # T-02：相对表达锚定 document_effective_time（禁止当前时钟）
                if document_effective_time:
                    parse.valid_time = {"valid_from": document_effective_time}
                    statuses.add("resolved")
                else:
                    statuses.add("unresolved")
            elif kind == "valid_until":
                m = _DATE_RE.search(raw_text)
                if m:
                    parse.valid_time = {"valid_until": f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"}
                    statuses.add("resolved")
                else:
                    statuses.add("unresolved")
            else:
                statuses.add("unresolved")
        if "failed" in statuses:
            parse.parse_status = "failed"
        elif statuses == {"resolved"}:
            parse.parse_status = "resolved"
        else:
            parse.parse_status = "unresolved"
        return parse


class OntologyMapper:
    """L7：三段式 candidate mapping；unknown → quarantined；DomainPack 只读。"""

    def __init__(self, domain_pack=None):
        self._pack = domain_pack  # 只读引用；V0.2 禁止修改 ontology
        # 词表（精确 O-01 / 规范化 O-02 / 别名 O-03）——构造时展开一次，匹配 deterministic
        self._exact: dict[str, str] = {}
        self._alias: dict[str, str] = {}
        if domain_pack is not None:
            for name in domain_pack.object_types:
                self._exact[name] = f"object_type:{name}"
            for name in domain_pack.relation_types:
                self._exact.setdefault(name, f"relation_type:{name}")
            for term, aliases in (domain_pack.terminology or {}).items():
                self._exact.setdefault(term, f"terminology:{term}")
                for a in aliases or []:
                    self._alias[a] = f"terminology:{term}"

    @staticmethod
    def _normalize(form: str) -> str:
        import unicodedata
        t = unicodedata.normalize("NFC", form)
        t = re.sub(r"\s+", " ", t).strip().lower()
        return t.translate({ord(f): ord(t2) for f, t2 in zip("，。：；", ",.:;")})

    def map(self, entities: list[EntityCandidate],
            relations: list[RelationCandidate]) -> list[OntologyMapping]:
        out: list[OntologyMapping] = []
        for e in entities:
            ref = self._exact.get(e.normalized_form) or self._exact.get(self._normalize(e.normalized_form))
            conf = 1.0 if ref else None
            if ref is None:
                ref = self._alias.get(e.normalized_form) or self._alias.get(self._normalize(e.normalized_form))
                conf = 0.8 if ref else None
            if ref is None:
                ref2 = self._exact.get(self._normalize(e.surface_form)) or self._alias.get(self._normalize(e.surface_form))
                if ref2:
                    ref, conf = ref2, 0.9  # O-02 规范化命中
            if ref:
                out.append(OntologyMapping(concept_surface=e.normalized_form,
                                           ontology_ref=ref, mapping_status="candidate",
                                           confidence=round(conf, 4)))
            elif self._pack is None:
                # 无词表（generic 编译）：无词表背书即无 quarantine 依据 → candidate（ref 待治理）
                out.append(OntologyMapping(concept_surface=e.normalized_form,
                                           ontology_ref=None, mapping_status="candidate",
                                           confidence=0.0))
            else:
                out.append(OntologyMapping(concept_surface=e.normalized_form,
                                           ontology_ref=None, mapping_status="quarantined",
                                           confidence=0.0))
        has_vocab = self._pack is not None
        for r in relations:
            ref = self._exact.get(r.predicate_candidate) or self._alias.get(r.predicate_candidate)
            if ref:
                out.append(OntologyMapping(concept_surface=r.predicate_candidate,
                                           ontology_ref=ref, mapping_status="candidate",
                                           confidence=1.0))
            elif not has_vocab:
                out.append(OntologyMapping(concept_surface=r.predicate_candidate,
                                           ontology_ref=None, mapping_status="candidate",
                                           confidence=0.0))
            else:
                out.append(OntologyMapping(concept_surface=r.predicate_candidate,
                                           ontology_ref=None, mapping_status="quarantined",
                                           confidence=0.0))
        return out