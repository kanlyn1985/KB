from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from agent_kb.query.query_frame import QueryFrame
from agent_kb.retrieval.models import RetrievalCandidate

# 自归一模式下各通道 Top1 映射到的统一分值上限。选择依据：保持融合 Top1
# 落在充分性判定的相关性阈值(1.5)之上，同时抹平词法(可达 3~4)对
# 余弦(<=0.95)/图衰减(<=1)的尺度压制。
_SELF_MAX_CEIL = 2.0

# 图通道门控阈值：词法 Top1 与向量 Top1 同时低于阈值才视为"双弱"并启用图 BFS。
# 依据 expAB 消融（43 分层样本）：域内查询 0 次触发，指标与双通道持平；
# 图通道价值域恰是双弱（冷门/表述外）查询。
_GATE_LEXICAL_TOP = 1.5
_GATE_VECTOR_TOP = 0.5


class CandidateProvider(Protocol):
    def search(self, query_frame: QueryFrame, *, limit: int = 32) -> list[RetrievalCandidate]: ...


class ProductionCandidateProvider:
    """Combine lexical, vector, and graph adapters behind one provider contract."""

    def __init__(
        self,
        *,
        lexical: CandidateProvider | None = None,
        vector: CandidateProvider | None = None,
        graph: CandidateProvider | None = None,
        normalize: str | None = None,
        graph_gate: bool = True,
    ) -> None:
        """normalize=None 保持历史行为（原始分数直接合并）；

        normalize="self_max" 时每个通道先除以本查询内自身 Top1 分数再乘以
        _SELF_MAX_CEIL——跨适配器可比性来自排名结构而非原始量纲，
        消融实验（43 样本分层）表明原始分数合并使三通道全开劣于单通道词法。
        """
        self.normalize_mode = normalize
        self.graph_gate = graph_gate and graph is not None
        self.providers: list[tuple[str, CandidateProvider, float]] = []
        if lexical is not None:
            self.providers.append(("lexical", lexical, 1.0))
        if vector is not None:
            self.providers.append(("vector", vector, 0.95))
        if graph is not None:
            self.providers.append(("graph", graph, 0.85))

    def search(self, query_frame: QueryFrame, *, limit: int = 32) -> list[RetrievalCandidate]:
        pool_limit = max(1, limit)
        merged: dict[str, RetrievalCandidate] = {}

        # 图通道置信门控（graph_gate 默认开）：词法+向量先行，双弱才放行图 BFS。
        # 探测与正式取候选合并为一次 provider.search（结果复用，不重复查询）。
        active = self.providers
        reused: dict[str, list[RetrievalCandidate]] = {}
        if self.graph_gate:
            strong = [(n, p, w) for n, p, w in self.providers if n != "graph"]
            gate_scores: dict[str, float] = {}
            for name, provider, _ in strong:
                try:
                    got = list(provider.search(query_frame, limit=pool_limit))
                except Exception:
                    got = []
                reused[name] = got
                gate_scores[name] = max((float(item.score) for item in got), default=0.0)
            gate_open = not strong or (
                gate_scores.get("lexical", 0.0) < _GATE_LEXICAL_TOP
                and gate_scores.get("vector", 0.0) < _GATE_VECTOR_TOP
            )
            active = (
                [*strong, *[(n, p, w) for n, p, w in self.providers if n == "graph"]]
                if gate_open
                else strong
            )

        for provider_name, provider, weight in active:
            if provider_name in reused:
                candidates = reused.pop(provider_name)
            else:
                candidates = list(provider.search(query_frame, limit=pool_limit))
            if self.normalize_mode == "self_max" and candidates:
                top = max(float(item.score) for item in candidates)
                if top > 0:
                    candidates = [
                        replace(item, score=float(item.score) / top * _SELF_MAX_CEIL)
                        for item in candidates
                    ]
            for candidate in candidates:
                key = f"{candidate.source_type}:{candidate.source_id}"
                weighted = replace(candidate, score=float(candidate.score) * weight)
                existing = merged.get(key)
                if existing is None:
                    payload = dict(weighted.payload)
                    payload["production_channels"] = [provider_name]
                    merged[key] = replace(weighted, payload=payload)
                    continue
                payload = dict(existing.payload)
                channels = list(payload.get("production_channels") or [])
                if provider_name not in channels:
                    channels.append(provider_name)
                payload["production_channels"] = channels
                for name, value in weighted.payload.items():
                    payload.setdefault(name, value)
                reasons = list(existing.reasons)
                for reason in weighted.reasons:
                    if reason not in reasons:
                        reasons.append(reason)
                if "multi_adapter_corroboration" not in reasons:
                    reasons.append("multi_adapter_corroboration")
                matched_terms = list(existing.matched_terms)
                for term in weighted.matched_terms:
                    if term not in matched_terms:
                        matched_terms.append(term)
                score = max(existing.score, weighted.score) + min(existing.score, weighted.score) * 0.25
                merged[key] = replace(
                    existing if existing.score >= weighted.score else weighted,
                    score=score,
                    channel="production",
                    payload=payload,
                    reasons=reasons,
                    matched_terms=matched_terms,
                )
        candidates = sorted(merged.values(), key=lambda item: (item.score, item.source_id), reverse=True)
        return candidates[:pool_limit]
