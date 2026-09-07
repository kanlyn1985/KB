"""Domain pack loading and schema."""

from .loader import DomainPackError, load_domain_pack
from .schema import (
    AnswerContractSpec,
    DomainPack,
    HiddenContextRule,
    ObjectTypeSpec,
    RelationTypeSpec,
)

__all__ = [
    "AnswerContractSpec",
    "DomainPack",
    "DomainPackError",
    "HiddenContextRule",
    "ObjectTypeSpec",
    "RelationTypeSpec",
    "load_domain_pack",
]

# V0.7 CrossDomainGuard（AKB-V07-IMPL-004）
from agent_kb.domains.guard import CrossDomainError, CrossDomainGuard  # noqa: E402,F401
from agent_kb.domains.guard import GuardDecision  # noqa: E402,F401

__all__ = list(globals().get("__all__", [])) + [
    "CrossDomainGuard", "CrossDomainError", "GuardDecision"]