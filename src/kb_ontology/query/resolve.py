"""Entity resolution against OntologyStore + Domain Pack terminology."""

from __future__ import annotations

from dataclasses import dataclass

from kb_ontology.domains.schema import DomainPack
from kb_ontology.query.frame import TargetEntityRef
from kb_ontology.storage.store import OntologyStore


@dataclass(frozen=True)
class ResolveHit:
    entity_id: str
    class_name: str
    canonical_name: str
    matched_text: str
    confidence: float
    match_kind: str  # exact | alias | substring


def _term_aliases(domain_pack: DomainPack | None) -> dict[str, list[str]]:
    """Normalize terminology to term_id → alias list."""
    if domain_pack is None:
        return {}
    out: dict[str, list[str]] = {}
    for term_id, entry in (domain_pack.terminology or {}).items():
        if isinstance(entry, list):
            aliases = [str(a).strip() for a in entry if str(a).strip()]
        elif isinstance(entry, dict):
            raw = entry.get("aliases") or []
            aliases = [str(a).strip() for a in raw if str(a).strip()]
        else:
            aliases = []
        out[str(term_id)] = aliases
    return out


def _preferred_display(term_id: str, aliases: list[str]) -> str:
    for alias in aliases:
        if any("\u4e00" <= ch <= "\u9fff" for ch in alias):
            return alias
    if aliases:
        return aliases[0]
    return term_id.replace("_", " ")


def _alias_index(domain_pack: DomainPack | None) -> list[tuple[str, str, str]]:
    """Return (alias_lower, term_id, preferred_display) rows from terminology."""
    rows: list[tuple[str, str, str]] = []
    for term_id, aliases in _term_aliases(domain_pack).items():
        display = _preferred_display(term_id, aliases)
        keys = {
            term_id.lower(),
            term_id.replace("_", " ").lower(),
            term_id.replace("_", "-").lower(),
        }
        for alias in aliases:
            keys.add(alias.lower())
        for key in keys:
            if key:
                rows.append((key, term_id, display))
    seen: set[str] = set()
    unique: list[tuple[str, str, str]] = []
    for row in rows:
        if row[0] in seen:
            continue
        seen.add(row[0])
        unique.append(row)
    return unique


def _compact(text: str) -> str:
    """Lowercase and strip spaces/hyphens for fuzzy equality."""
    return (
        (text or "")
        .lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
        .replace("—", "")
        .replace("–", "")
    )


def _significant_token(text: str) -> str | None:
    """Pick a useful search token (prefer longer CJK run or alnum run)."""
    import re

    raw = (text or "").strip()
    if not raw:
        return None
    cjk = re.findall(r"[\u4e00-\u9fff]{2,}", raw)
    if cjk:
        return max(cjk, key=len)
    alnum = re.findall(r"[A-Za-z0-9]{2,}", raw)
    if alnum:
        return max(alnum, key=len)
    return raw[:24] if len(raw) >= 2 else None


def expand_aliases(text: str, domain_pack: DomainPack | None) -> list[str]:
    """Return the input plus terminology displays/aliases that match it."""
    base = (text or "").strip()
    if not base:
        return []
    out: list[str] = [base]
    lower = base.lower()
    matched_terms: set[str] = set()
    index = _alias_index(domain_pack)
    # Tiered match so short tokens like "OBC" do not pull every alias that
    # merely contains them as a substring (e.g. OBC_TOPOLOGY).
    exact_terms: set[str] = set()
    for alias_l, term_id, display in index:
        if alias_l == lower:
            exact_terms.add(term_id)
            matched_terms.add(term_id)
            if display not in out:
                out.append(display)
    if not exact_terms:
        for alias_l, term_id, display in index:
            # Query contains alias, or alias contains query only when alias is
            # not much longer (avoid OBC → OBC电路拓扑 pollution).
            if alias_l and (
                (alias_l in lower)
                or (lower in alias_l and len(alias_l) <= max(len(lower) + 4, int(len(lower) * 1.5) + 1))
            ):
                matched_terms.add(term_id)
                if display not in out:
                    out.append(display)
    # Add a few sibling aliases for matched terms (helps store search).
    term_map = _term_aliases(domain_pack)
    for term_id in matched_terms:
        for alias in term_map.get(term_id, [])[:8]:
            if alias not in out:
                out.append(alias)
    return out[:16]


def resolve_entity_name(
    store: OntologyStore,
    name: str,
    *,
    domain_pack: DomainPack | None = None,
    class_name: str | None = None,
    domain: str | None = None,
    role: str = "primary",
    limit: int = 5,
) -> list[TargetEntityRef]:
    """Resolve a free-text name to zero-or-more entity refs, best first."""
    text = (name or "").strip()
    if not text:
        return []

    candidates: list[ResolveHit] = []
    by_id: dict[str, ResolveHit] = {}
    rank_kind = {"exact": 0, "alias": 1, "substring": 2}

    def _add(entity, matched: str, conf: float, kind: str) -> None:
        hit = ResolveHit(
            entity_id=entity.id,
            class_name=entity.class_name,
            canonical_name=entity.canonical_name,
            matched_text=matched,
            confidence=conf,
            match_kind=kind,
        )
        prev = by_id.get(entity.id)
        if prev is None:
            by_id[entity.id] = hit
            candidates.append(hit)
            return
        # Keep the stronger match (kind rank, then confidence).
        prev_key = (rank_kind.get(prev.match_kind, 9), -prev.confidence)
        new_key = (rank_kind.get(kind, 9), -conf)
        if new_key < prev_key:
            by_id[entity.id] = hit
            for i, old in enumerate(candidates):
                if old.entity_id == entity.id:
                    candidates[i] = hit
                    break

    # 1) Direct store search on the raw text.
    for ent in store.search_entities(
        text, class_name=class_name, domain=domain, limit=limit
    ):
        kind = "exact" if ent.canonical_name.lower() == text.lower() else "substring"
        conf = 0.95 if kind == "exact" else 0.7
        _add(ent, text, conf, kind)

    # 2) Terminology alias expansion → search each alias.
    for alias in expand_aliases(text, domain_pack):
        if alias.lower() == text.lower():
            continue
        for ent in store.search_entities(
            alias, class_name=class_name, domain=domain, limit=limit
        ):
            if ent.canonical_name.lower() == alias.lower():
                conf = 0.9
            elif _compact(ent.canonical_name) == _compact(alias):
                conf = 0.88
            else:
                conf = 0.65
            _add(ent, alias, conf, "alias")

    # 3) Compact / token fuzzy (DC-DC ↔ DCDC, 慢充 ↔ 慢充系统).
    compact = _compact(text)
    token = _significant_token(text)
    search_keys: list[str] = []
    for key in (text, token):
        if key and key not in search_keys:
            search_keys.append(key)
    # Peel common product prefixes so "车载DC-DC转换器" also finds bare names.
    for prefix in ("车载", "on-board ", "onboard "):
        raw = text
        if raw.lower().startswith(prefix):
            peeled = raw[len(prefix) :].strip()
            if peeled and peeled not in search_keys:
                search_keys.append(peeled)
    for key in search_keys:
        for ent in store.search_entities(
            key, class_name=class_name, domain=domain, limit=limit * 5
        ):
            ec = _compact(ent.canonical_name)
            if not ec:
                continue
            if compact and ec == compact:
                _add(ent, key, 0.9, "exact")
            elif compact and (compact in ec or ec in compact):
                # Prefer product-ish longer containment slightly higher.
                conf = 0.78 if ent.class_name in {
                    "Product",
                    "Subsystem",
                    "Standard",
                    "Requirement",
                } else 0.7
                _add(ent, key, conf, "substring")

    # Sort: exact > alias > substring, then confidence, then prefer Product.
    # Prefer names that share more compact overlap with the query text.
    q_compact = _compact(text)
    class_boost = {
        "Product": 0,
        "Subsystem": 1,
        "Parameter": 2,
        "Requirement": 2,
        "Standard": 1,
    }

    def _overlap_penalty(h: ResolveHit) -> int:
        ec = _compact(h.canonical_name)
        if not q_compact or not ec:
            return 50
        if ec == q_compact:
            return 0
        if q_compact in ec or ec in q_compact:
            return abs(len(ec) - len(q_compact))
        return 40

    candidates.sort(
        key=lambda h: (
            rank_kind.get(h.match_kind, 9),
            -h.confidence,
            _overlap_penalty(h),
            class_boost.get(h.class_name, 5),
            len(h.canonical_name),
        )
    )

    return [
        TargetEntityRef(
            entity_id=h.entity_id,
            class_name=h.class_name,
            canonical_name=h.canonical_name,
            matched_text=h.matched_text,
            confidence=h.confidence,
            role=role,
        )
        for h in candidates[:limit]
    ]


def resolve_frame_entities(
    store: OntologyStore,
    *,
    names: list[tuple[str, str]],
    domain_pack: DomainPack | None = None,
    domain: str | None = None,
) -> tuple[list[TargetEntityRef], list[str]]:
    """Resolve multiple (name, role) pairs.

    Returns (best refs per role — may include unresolved stubs, warnings).
    When multiple candidates tie, keeps the top one and emits an ambiguity warning.
    """
    refs: list[TargetEntityRef] = []
    warnings: list[str] = []
    for name, role in names:
        hits = resolve_entity_name(
            store, name, domain_pack=domain_pack, domain=domain, role=role
        )
        if not hits:
            refs.append(
                TargetEntityRef(
                    canonical_name=name,
                    matched_text=name,
                    confidence=0.0,
                    role=role,
                )
            )
            warnings.append(f"entity_not_found:{name}")
            continue
        if len(hits) > 1 and abs(hits[0].confidence - hits[1].confidence) < 0.05:
            warnings.append(
                "entity_ambiguous:"
                + name
                + "→"
                + ",".join(h.canonical_name for h in hits[:3])
            )
        refs.append(hits[0])
    return refs, warnings
