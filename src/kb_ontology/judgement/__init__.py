"""Rule-first + LLM-fallback judgement (ADR-0003)."""

from kb_ontology.judgement.judge import judge
from kb_ontology.judgement.models import AnswerStrategy, Judgement, SufficiencyStatus
from kb_ontology.judgement.rules import judge_rules

__all__ = [
    "AnswerStrategy",
    "Judgement",
    "SufficiencyStatus",
    "judge",
    "judge_rules",
]
