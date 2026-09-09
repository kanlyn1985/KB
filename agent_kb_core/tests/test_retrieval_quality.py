"""检索质量门禁：golden 召回 + negative 拒绝（离线，不依赖网关/SQLite）。

- test_golden_cases_hit10：30 个 golden cases 的节点级召回 ≥ 95%
- test_negative_off_topic_no_strong_hit：完全无关查询不得强命中
- test_negative_no_regression：负面误召回数不超过已知基线（规则层）
- test_negative_with_llm_rejection：LLM 拒绝机制在理解层生效（mock，不调网关）

评测面与 validation/eval_node_recall.py 一致：内存检索卡 + 规则理解层，
保证 CI 离线可跑、结果确定。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]  # agent_kb_core/
sys.path.insert(0, str(ROOT / "validation"))
sys.path.insert(0, str(ROOT / "src"))

from agent_kb.domains.loader import load_domain_pack  # noqa: E402
from agent_kb.query.understanding import understand_query  # noqa: E402
from agent_kb.retrieval.engine import retrieve  # noqa: E402

TREE = ROOT.parent / "docs" / "ontology" / "tree_skeleton"
NODE_CARDS = TREE / "llm_landing" / "node_cards.jsonl"
GOLDEN_CASES = TREE / "llm_landing" / "golden_cases.json"
NEGATIVE_CASES = TREE / "llm_landing" / "negative_cases.json"
DOMAIN_DIR = ROOT / "domains" / "obc_dcdc"

# 已知基线：规则理解层对短泛词类（CAN/ISO/OBC 别名命中）存在误召回，
# 由 LLM 语义分解（use_llm=True）解决；此处只防新增回归。
KNOWN_NEGATIVE_EXCLUDES = {
    "stock_unrelated", "can_help_english", "iso_camera", "obc_battery",
}


def _load_cards() -> list:
    from eval_node_recall import load_cards
    cards, _node2card = load_cards()
    return cards


def _retrieve_top(query: str, domain_pack, cards, top_k: int = 10):
    frame = understand_query(query, domain_pack=domain_pack)

    class Index:
        object_projections = []
        retrieval_cards = cards
        context_facts = []
        context_evidence = []

    return retrieve(frame, Index(), top_k=top_k)


@pytest.fixture(scope="module")
def domain_pack():
    return load_domain_pack(DOMAIN_DIR)


@pytest.fixture(scope="module")
def cards():
    return _load_cards()


def test_golden_cases_hit10(domain_pack, cards) -> None:
    """golden cases 节点级召回门禁：Hit@10 ≥ 95%（当前 100%）。"""
    cases = json.loads(GOLDEN_CASES.read_text(encoding="utf-8"))
    hits = 0
    for case in cases:
        result = _retrieve_top(case["query"], domain_pack, cards)
        expected_ids = {f"card:obc_dcdc:{e.split('#')[0]}" for e in case["expected"]}
        cand_ids = {c.source_id.split("#")[0] for c in result.candidates}
        hits += 1 if (expected_ids & cand_ids) else 0
    rate = hits / len(cases) * 100
    assert rate >= 95.0, f"golden Hit@10 过低: {hits}/{len(cases)} = {rate:.1f}%"


def test_negative_off_topic_no_strong_hit(domain_pack, cards) -> None:
    """完全无关查询（off_topic 且无 exclude）top1 不得强命中（score ≥ 2.0）。"""
    cases = json.loads(NEGATIVE_CASES.read_text(encoding="utf-8"))
    checked = 0
    for case in cases:
        if case.get("kind") != "off_topic" or case.get("exclude"):
            continue
        result = _retrieve_top(case["query"], domain_pack, cards)
        top1 = result.candidates[0] if result.candidates else None
        checked += 1
        assert top1 is None or top1.score < 2.0, (
            f"无关查询 {case['query']} 强命中 top1={top1.source_id} score={top1.score:.2f}"
        )
    assert checked >= 2, "negative cases 中 off_topic 用例不足，评测无效"


def test_negative_no_regression(domain_pack, cards) -> None:
    """负面误召回数不超过已知基线（规则层）。"""
    cases = json.loads(NEGATIVE_CASES.read_text(encoding="utf-8"))
    failures = set()
    for case in cases:
        exclude = set(case.get("exclude", []))
        if not exclude:
            continue
        result = _retrieve_top(case["query"], domain_pack, cards, top_k=5)
        cand_ids = {c.source_id.replace("card:obc_dcdc:", "").split("#")[0]
                    for c in result.candidates}
        if exclude & cand_ids:
            failures.add(case["case_id"])
    new_failures = failures - KNOWN_NEGATIVE_EXCLUDES
    assert not new_failures, f"负面误召回回归: {sorted(new_failures)}"


def test_negative_llm_rejection_clears_generic_targets() -> None:
    """LLM 明确拒绝（空 targets）时清空规则泛词目标（离线 mock，不调网关）。"""
    from agent_kb.query import llm_understanding as lu
    from agent_kb.query.understanding import UnderstandingOptions

    # mock LLM：明确返回空 targets（拒绝）
    def _chat(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return '{"targets": []}'

    def _extract_json(text, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return json.loads(text)

    lu.chat = _chat  # type: ignore[assignment]
    lu.extract_json = _extract_json  # type: ignore[assignment]
    lu._LLM_CACHE.clear()
    try:
        frame = understand_query(
            "股票投资策略",
            domain_pack=load_domain_pack(DOMAIN_DIR),
            options=UnderstandingOptions(use_llm=True),
        )
        assert frame.used_llm is True
        assert frame.target_objects == []
    finally:
        lu._LLM_CACHE.clear()
