from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from agent_kb.domains.schema import DomainPack

from .source_units import SourceUnit


@dataclass(frozen=True)
class Fact:
    """Evidence-bound atomic or semi-atomic fact candidate."""

    fact_id: str
    fact_type: str
    subject: str | None
    predicate: str
    object_value: Any
    qualifiers: dict[str, Any] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)
    source_unit_id: str | None = None
    confidence: float = 0.0
    status: str = "candidate"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_facts(source_units: list[SourceUnit], *, domain_pack: DomainPack | None = None) -> list[Fact]:
    """Extract generic fact candidates from source units.

    This extractor is intentionally conservative. It creates traceable fact
    candidates; promotion into domain objects remains a later projection/review
    concern.
    """

    facts: list[Fact] = []
    for unit in source_units:
        fact = _extract_fact_from_unit(unit, domain_pack=domain_pack)
        if fact:
            facts.append(fact)
    return facts


def _extract_fact_from_unit(unit: SourceUnit, *, domain_pack: DomainPack | None) -> Fact | None:
    text = unit.normalized_text.strip()
    if not text:
        return None

    subject = _find_domain_subject(text, domain_pack) or _fallback_subject(text)
    qualifiers = _extract_numeric_constraint(text)

    if unit.unit_type == "definition":
        return _fact(unit, "term_definition", subject, "defines", text, qualifiers, 0.72)
    if unit.unit_type == "requirement":
        fact_type = "parameter_constraint" if subject and qualifiers else "requirement_constraint"
        return _fact(unit, fact_type, subject, "constrains", text, qualifiers, 0.7 if qualifiers else 0.62)
    if unit.unit_type == "test_method":
        return _fact(unit, "test_method", subject, "verified_by_method", text, qualifiers, 0.66)
    if unit.unit_type == "test_result":
        return _fact(unit, "test_result", subject, "has_test_result", text, qualifiers, 0.66)
    if unit.unit_type == "table_like":
        return _fact(unit, "table_row", subject, "contains_structured_row", text, qualifiers, 0.58)
    if unit.unit_type == "warning_or_exception":
        return _fact(unit, "risk_or_exception", subject, "has_risk_context", text, qualifiers, 0.55)
    return None


def _fact(
    unit: SourceUnit,
    fact_type: str,
    subject: str | None,
    predicate: str,
    object_value: Any,
    qualifiers: dict[str, Any],
    confidence: float,
) -> Fact:
    digest = hashlib.sha256(
        f"{unit.unit_id}:{fact_type}:{subject or ''}:{predicate}:{str(object_value)[:200]}".encode("utf-8")
    ).hexdigest()
    return Fact(
        fact_id=f"fact_{digest[:16]}",
        fact_type=fact_type,
        subject=subject,
        predicate=predicate,
        object_value=object_value,
        qualifiers=qualifiers,
        evidence_ids=[unit.evidence_id],
        source_unit_id=unit.unit_id,
        confidence=confidence,
    )


def _find_domain_subject(text: str, domain_pack: DomainPack | None) -> str | None:
    if not domain_pack:
        return None
    lowered = text.lower()
    for canonical, aliases in domain_pack.terminology.items():
        candidates = [canonical, *aliases]
        for alias in candidates:
            if str(alias).strip() and str(alias).lower() in lowered:
                return canonical
    return None


def _fallback_subject(text: str) -> str | None:
    first = text.split("。", 1)[0].split(";", 1)[0].strip()
    match = re.match(r"^(.{2,40}?)(?:是指|定义为|应|必须|不得|不应|shall|must|不大于|不小于|≤|>=|<=|≥)", first, re.I)
    if match:
        return match.group(1).strip(" ：:，,。") or None
    return None


def _extract_numeric_constraint(text: str) -> dict[str, Any]:
    qualifiers: dict[str, Any] = {}
    operator = _extract_operator(text)
    if operator:
        qualifiers["operator"] = operator

    value_match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(mVpp|mV|V|A|kW|W|%|ms|s|Ω|kΩ|Hz|℃|C)\b", text, re.I)
    if value_match:
        raw = value_match.group(1)
        qualifiers["value_numeric"] = float(raw) if "." in raw else int(raw)
        qualifiers["unit"] = value_match.group(2)

    condition_match = re.search(r"(?:在|于|under|when)\s*([^。；;，,]{2,60}?)(?:下|时|条件|condition|,|，|。|；|;)", text, re.I)
    if condition_match:
        qualifiers["condition_text"] = condition_match.group(1).strip()

    return qualifiers


def _extract_operator(text: str) -> str | None:
    patterns = [
        (r"(不大于|不超过|小于等于|≤|<=|maximum|max\.?|not exceed)", "<="),
        (r"(不小于|大于等于|至少|≥|>=|minimum|min\.?)", ">="),
        (r"(等于|为|=)", "="),
        (r"(大于|>)", ">"),
        (r"(小于|<)", "<"),
    ]
    for pattern, operator in patterns:
        if re.search(pattern, text, re.I):
            return operator
    return None
