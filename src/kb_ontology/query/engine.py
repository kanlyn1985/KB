"""Query template engine — QueryFrame → deterministic OntologyStore results."""

from __future__ import annotations

from kb_ontology.domains.schema import DomainPack
from kb_ontology.llm.llm_client import LLMChatClient
from kb_ontology.query.frame import QueryFrame, QueryResult
from kb_ontology.query.templates import TEMPLATE_REGISTRY, get_template
from kb_ontology.query.understanding import understand_query
from kb_ontology.storage.store import OntologyStore


def execute_frame(store: OntologyStore, frame: QueryFrame) -> QueryResult:
    """Run the template registered for ``frame.intent``.

    Unknown intents return an empty result with ``empty_reason=unknown_intent``.
    """
    template = get_template(frame.intent)
    if template is None:
        return QueryResult(
            intent=frame.intent,
            template_id="none",
            frame=frame,
            empty_reason="unknown_intent",
            warnings=[f"no_template_for_intent:{frame.intent}"],
            meta={"registered_intents": sorted(TEMPLATE_REGISTRY.keys())},
        )
    result = template(store, frame)
    # Propagate frame-level ambiguity as warnings without dropping hits.
    extra_warnings = list(result.warnings)
    for amb in frame.ambiguity:
        extra_warnings.append(f"ambiguity:{amb.term}")
    if extra_warnings != list(result.warnings):
        return QueryResult(
            intent=result.intent,
            template_id=result.template_id,
            frame=result.frame,
            hits=list(result.hits),
            related=list(result.related),
            evidence=list(result.evidence),
            warnings=extra_warnings,
            empty_reason=result.empty_reason,
            meta=dict(result.meta),
        )
    return result


def query(
    store: OntologyStore,
    text: str,
    *,
    domain_pack: DomainPack | None = None,
    domain: str | None = None,
    client: LLMChatClient | None = None,
    use_llm: bool = False,
    frame: QueryFrame | None = None,
) -> QueryResult:
    """End-to-end: understand (unless frame given) → execute template."""
    if frame is None:
        frame = understand_query(
            text,
            store=store,
            domain_pack=domain_pack,
            domain=domain,
            client=client,
            use_llm=use_llm,
        )
    return execute_frame(store, frame)
