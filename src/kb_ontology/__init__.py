"""KB-Ontology: Ontology-driven agent knowledge backend."""

__version__ = "0.1.0"

from kb_ontology.context import ContextPack, assemble_context_pack
from kb_ontology.judgement import Judgement, judge, judge_rules
from kb_ontology.pipeline import answer_frame, answer_query
from kb_ontology.query import QueryFrame, QueryResult, execute_frame, query

__all__ = [
    "ContextPack",
    "Judgement",
    "QueryFrame",
    "QueryResult",
    "answer_frame",
    "answer_query",
    "assemble_context_pack",
    "execute_frame",
    "judge",
    "judge_rules",
    "query",
    "__version__",
]
