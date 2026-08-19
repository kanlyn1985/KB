"""LLM 语义分解单元测试（mock LLM，不依赖网关）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]  # agent_kb_core/
sys.path.insert(0, str(ROOT / "src"))

from agent_kb.domains.loader import load_domain_pack  # noqa: E402
from agent_kb.query import llm_understanding as lu  # noqa: E402
from agent_kb.query.understanding import UnderstandingOptions, understand_query  # noqa: E402

PACK = load_domain_pack(ROOT / "domains" / "obc_dcdc")


@pytest.fixture(autouse=True)
def _clear_llm_cache():
    """每个测试前清空 LLM 缓存（内存 + 磁盘），避免跨测试污染。"""
    lu._LLM_CACHE.clear()
    if lu._CACHE_FILE.exists():
        lu._CACHE_FILE.unlink()
    yield
    lu._LLM_CACHE.clear()
    if lu._CACHE_FILE.exists():
        lu._CACHE_FILE.unlink()


def _fake_llm(targets: list[tuple[str, float, str]]):
    """构造 mock chat/extract_json，返回固定 LLM 结果。"""
    payload = {"targets": [
        {"object_id": nid, "conf": conf, "reason": reason}
        for nid, conf, reason in targets
    ]}
    import json

    def _chat(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return json.dumps(payload)

    def _extract_json(text, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return json.loads(text)

    return _chat, _extract_json


def test_rule_match_is_uncertain_on_short_alias_conflict() -> None:
    """含短别名（≤3 字符）的多目标匹配 → 不确定（需 LLM）。"""
    frame = understand_query("OBC水道设计", domain_pack=PACK)
    assert lu.rule_match_is_uncertain("OBC水道设计", frame.target_objects) is True


def test_llm_link_targets_returns_mapped_nodes() -> None:
    """LLM 返回合法节点时，产出 TargetObject 列表（白名单校验）。"""
    chat, extract_json = _fake_llm([("P-HW-MECH", 0.9, "水道属于结构件"), ("P-MECH", 0.7, "机械域")])
    lu.chat = chat  # type: ignore[assignment]
    lu.extract_json = extract_json  # type: ignore[assignment]
    targets = lu.llm_link_targets("OBC水道设计", PACK)
    assert [t.object_id for t in targets] == ["P-HW-MECH", "P-MECH"]
    assert all(t.confidence >= 0.6 for t in targets)


def test_llm_link_targets_rejects_unknown_node() -> None:
    """LLM 编造不存在的节点 → 白名单拦截。"""
    chat, extract_json = _fake_llm([("FAKE-NODE", 0.95, "不存在")])
    lu.chat = chat  # type: ignore[assignment]
    lu.extract_json = extract_json  # type: ignore[assignment]
    targets = lu.llm_link_targets("测试", PACK)
    assert targets == []


def test_llm_link_targets_rejects_low_confidence() -> None:
    """conf < 0.6 的 LLM 结果被丢弃。"""
    chat, extract_json = _fake_llm([("P-HW-MECH", 0.5, "把握不足")])
    lu.chat = chat  # type: ignore[assignment]
    lu.extract_json = extract_json  # type: ignore[assignment]
    targets = lu.llm_link_targets("测试", PACK)
    assert targets == []


def test_llm_link_targets_fallback_on_error() -> None:
    """LLM 调用异常 → 返回空（调用方回退规则）。"""

    def _boom(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise RuntimeError("gateway down")

    lu.chat = _boom  # type: ignore[assignment]
    targets = lu.llm_link_targets("测试", PACK)
    assert targets == []


def test_understand_query_with_llm_merges_targets() -> None:
    """use_llm=True 且 LLM 可用时，LLM 目标优先合并。"""
    chat, extract_json = _fake_llm([("P-HW-MECH", 0.9, "水道设计属结构件")])
    lu.chat = chat  # type: ignore[assignment]
    lu.extract_json = extract_json  # type: ignore[assignment]
    frame = understand_query(
        "OBC水道设计",
        domain_pack=PACK,
        options=UnderstandingOptions(use_llm=True),
    )
    ids = [o.object_id for o in frame.target_objects]
    assert "P-HW-MECH" in ids
    assert frame.used_llm is True
    # LLM 目标应排在前
    assert ids[0] == "P-HW-MECH"


def test_understand_query_llm_fallback_keeps_rule_result() -> None:
    """use_llm=True 但 LLM 失败 → 回退规则结果，不崩溃。"""

    def _boom(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise RuntimeError("gateway down")

    lu.chat = _boom  # type: ignore[assignment]
    frame = understand_query(
        "OBC水道设计",
        domain_pack=PACK,
        options=UnderstandingOptions(use_llm=True),
    )
    assert frame.used_llm is False
    # 规则结果保留（含 L-STATE 等，行为与默认一致）
    assert any(o.object_id == "P-HW-MECH" for o in frame.target_objects)


def test_cache_persists_across_process_boundary() -> None:
    """缓存写盘后，清空内存可从磁盘恢复（模拟进程重启）。"""
    lu._cache_put("持久化测试", "obc_dcdc", [{"object_id": "P-HW-MECH", "conf": 0.9}])
    assert lu._CACHE_FILE.exists()
    # 模拟重启：清内存，重新加载
    lu._LLM_CACHE.clear()
    lu._cache_load()
    assert lu._cache_get("持久化测试", "obc_dcdc") == [{"object_id": "P-HW-MECH", "conf": 0.9}]


def test_cache_lru_evicts_oldest() -> None:
    """超过上限时淘汰最久未用的条目（真 LRU）。"""
    old_max = lu._LLM_CACHE_MAX
    lu._LLM_CACHE_MAX = 3
    try:
        lu._cache_put("q1", "d", [{"object_id": "A", "conf": 0.9}])
        lu._cache_put("q2", "d", [{"object_id": "B", "conf": 0.9}])
        lu._cache_put("q3", "d", [{"object_id": "C", "conf": 0.9}])
        # 访问 q1（标记最近使用）
        assert lu._cache_get("q1", "d") is not None
        # 写入 q4 → 应淘汰 q2（最久未用）
        lu._cache_put("q4", "d", [{"object_id": "D", "conf": 0.9}])
        assert lu._cache_get("q2", "d") is None  # 已淘汰
        assert lu._cache_get("q1", "d") is not None  # 保留
        assert lu._cache_get("q3", "d") is not None
        assert lu._cache_get("q4", "d") is not None
    finally:
        lu._LLM_CACHE_MAX = old_max
