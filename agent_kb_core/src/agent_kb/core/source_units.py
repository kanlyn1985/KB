from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .evidence import EvidenceBlock


@dataclass(frozen=True)
class SourceUnit:
    """Semantic knowledge unit derived from one evidence block.

    A SourceUnit is still evidence-bound. It is not yet a promoted domain object;
    it only declares what kind of knowledge a piece of evidence appears to carry.
    """

    unit_id: str
    document_id: str
    evidence_id: str
    unit_type: str
    text: str
    normalized_text: str
    title: str | None = None
    content_role: str = "candidate"
    expected_knowledge_type: str = "generic_text"
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_source_units(evidence_blocks: list[EvidenceBlock]) -> list[SourceUnit]:
    """Classify evidence blocks into generic semantic units."""

    units: list[SourceUnit] = []
    for block in evidence_blocks:
        unit_type = classify_source_unit(block.normalized_text, block_type=block.block_type)
        unit_id = _source_unit_id(block.evidence_id, unit_type, block.normalized_text)
        title = _extract_title(block.normalized_text) or block.section_path
        units.append(
            SourceUnit(
                unit_id=unit_id,
                document_id=block.document_id,
                evidence_id=block.evidence_id,
                unit_type=unit_type,
                text=block.text,
                normalized_text=block.normalized_text,
                title=title,
                content_role=_content_role(unit_type),
                expected_knowledge_type=_expected_knowledge_type(unit_type),
                confidence=_classification_confidence(unit_type),
                metadata={"source_block_type": block.block_type},
            )
        )
    return units


def classify_source_unit(text: str, *, block_type: str = "text") -> str:
    """Return a generic unit type used by retrieval and fact extraction."""

    compact = text.strip()
    if not compact:
        return "empty"
    if block_type == "table_like":
        return "table_like"
    if _looks_like_test_result(compact):
        return "test_result"
    if _looks_like_test_method(compact):
        return "test_method"
    if _looks_like_requirement(compact):
        return "requirement"
    if _looks_like_definition(compact):
        return "definition"
    if _looks_like_warning_or_exception(compact):
        return "warning_or_exception"
    return "narrative"


def _looks_like_definition(text: str) -> bool:
    return bool(re.search(r"(是指|定义为|指的是|表示|含义|refers to|means|is defined as)", text, re.I))


def _looks_like_requirement(text: str) -> bool:
    return bool(
        re.search(
            r"(应|必须|不得|不应|shall|must|should|requirement|不大于|不小于|不超过|至少|最大|最小|≤|>=|<=|≥)",
            text,
            re.I,
        )
    )


def _looks_like_test_method(text: str) -> bool:
    return bool(re.search(r"(测试方法|试验方法|检测方法|测量方法|验证方法|procedure|test method|measure)", text, re.I))


def _looks_like_test_result(text: str) -> bool:
    return bool(re.search(r"(测试结果|试验结果|检测结果|实测|measured|pass|fail|通过|不通过)", text, re.I))


def _looks_like_warning_or_exception(text: str) -> bool:
    return bool(re.search(r"(注意|例外|除非|风险|警告|warning|exception|risk)", text, re.I))


def _extract_title(text: str) -> str | None:
    first_line = text.splitlines()[0].strip() if text.splitlines() else ""
    if not first_line:
        return None
    if len(first_line) <= 120 and (re.match(r"^(?:第\s*)?\d+(?:\.\d+)*", first_line) or len(text.splitlines()) > 1):
        return first_line
    return None


def _content_role(unit_type: str) -> str:
    if unit_type in {"definition", "requirement", "test_method", "test_result", "table_like"}:
        return "candidate_knowledge"
    if unit_type == "warning_or_exception":
        return "risk_context"
    return "supporting_context"


def _expected_knowledge_type(unit_type: str) -> str:
    mapping = {
        "definition": "term_or_concept_definition",
        "requirement": "constraint_or_requirement",
        "test_method": "verification_method",
        "test_result": "verification_result",
        "table_like": "structured_table_or_row",
        "warning_or_exception": "risk_or_exception",
    }
    return mapping.get(unit_type, "generic_text")


def _classification_confidence(unit_type: str) -> float:
    if unit_type in {"definition", "requirement", "test_method", "test_result", "table_like"}:
        return 0.75
    if unit_type == "warning_or_exception":
        return 0.65
    return 0.45


def _source_unit_id(evidence_id: str, unit_type: str, text: str) -> str:
    digest = hashlib.sha256(f"{evidence_id}:{unit_type}:{text}".encode("utf-8")).hexdigest()
    return f"su_{digest[:16]}"
