from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ConstraintKind(str, Enum):
    MAX_LIMIT = "max_limit"
    MIN_LIMIT = "min_limit"
    RANGE_CAPABILITY = "range_capability"
    RANGE_TOLERANCE = "range_tolerance"
    ENUM_ALLOWED = "enum_allowed"
    BOOLEAN_REQUIRED = "boolean_required"
    TEXTUAL = "textual"


class ConflictStatus(str, Enum):
    NONE = "none"
    DUPLICATE = "duplicate"
    VALUE_CONFLICT = "value_conflict"
    CONDITION_CONFLICT = "condition_conflict"
    APPROVAL_REQUIRED = "approval_required"
    EVIDENCE_MISSING = "evidence_missing"
    HARD_BLOCKER = "hard_blocker"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class CustomerProject:
    project_id: str
    customer_id: str
    project_code: str
    product_family: str
    product_variant_id: str | None = None
    platform_id: str | None = None
    lifecycle_status: str | None = None


@dataclass(frozen=True)
class RequirementAtom:
    atom_id: str
    domain: str
    category: str
    canonical_name: str
    constraint_kind: str
    parameter_name: str | None = None
    default_unit: str | None = None


@dataclass(frozen=True)
class RequirementProfile:
    profile_id: str
    profile_type: str
    owner_type: str
    owner_id: str
    name: str
    priority: int
    version: str | None = None
    status: str = "active"


@dataclass(frozen=True)
class RequirementVariant:
    variant_id: str
    atom_id: str
    profile_id: str
    requirement_text: str
    operator: str | None = None
    value_numeric: float | None = None
    value_text: str | None = None
    unit: str | None = None
    condition_json: dict[str, Any] = field(default_factory=dict)
    mandatory_level: str | None = None
    priority: int = 100
    evidence_id: str | None = None
    fact_id: str | None = None
    document_id: str | None = None
    status: str = "active"


@dataclass(frozen=True)
class RequirementOverride:
    override_id: str
    profile_id: str
    atom_id: str
    override_type: str
    base_variant_id: str | None = None
    new_variant_id: str | None = None
    evidence_id: str | None = None
    approval_status: str = "draft"
    risk_level: str = "medium"


@dataclass(frozen=True)
class CompareResult:
    effect: str
    reason: str
    confidence: float = 1.0


@dataclass
class ResolutionStep:
    profile_id: str
    profile_type: str
    variant_id: str | None
    requirement_text: str | None
    effect: str
    conflict_status: str = "none"
    evidence_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EffectiveRequirement:
    project_id: str
    atom_id: str
    selected_variant_id: str | None
    effective_requirement_text: str
    operator: str | None
    value_numeric: float | None
    value_text: str | None
    unit: str | None
    condition_json: dict[str, Any]
    resolution_path: list[ResolutionStep]
    conflict_status: str
    verification_status: str
    approval_status: str
    evidence_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["resolution_path"] = [step.to_dict() for step in self.resolution_path]
        return data
