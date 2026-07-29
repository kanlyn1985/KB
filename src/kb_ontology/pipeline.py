"""End-to-end ontology query pipeline → ContextPack."""

from __future__ import annotations

from kb_ontology.context.pack import ContextPack, assemble_context_pack
from kb_ontology.domains.schema import DomainPack
from kb_ontology.judgement.judge import judge
from kb_ontology.llm.llm_client import LLMChatClient
from kb_ontology.query.engine import execute_frame, query as run_query
from kb_ontology.query.frame import QueryFrame, QueryResult
from kb_ontology.storage.store import OntologyStore


def answer_query(
    store: OntologyStore,
    text: str,
    *,
    domain_pack: DomainPack | None = None,
    domain: str | None = None,
    client: LLMChatClient | None = None,
    use_llm_understanding: bool = False,
    use_llm_judgement: bool = False,
    frame: QueryFrame | None = None,
) -> ContextPack:
    """Understand → template execute → judge → ContextPack.

    LLM usage is opt-in and split:
    - ``use_llm_understanding``: refine QueryFrame when rules are weak
    - ``use_llm_judgement``: semantic judgement only when rules need it
    """
    result: QueryResult = run_query(
        store,
        text,
        domain_pack=domain_pack,
        domain=domain,
        client=client,
        use_llm=use_llm_understanding,
        frame=frame,
    )
    judgement = judge(result, client=client, use_llm=use_llm_judgement)
    return assemble_context_pack(result, judgement)


def answer_frame(
    store: OntologyStore,
    frame: QueryFrame,
    *,
    client: LLMChatClient | None = None,
    use_llm_judgement: bool = False,
) -> ContextPack:
    """Execute a pre-built QueryFrame through templates + judgement."""
    result = execute_frame(store, frame)
    judgement = judge(result, client=client, use_llm=use_llm_judgement)
    return assemble_context_pack(result, judgement)
