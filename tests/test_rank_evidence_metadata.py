"""Tests for _rank_evidence academic-metadata penalty (Sprint 3 [6])."""
from __future__ import annotations

from enterprise_agent_kb.answer_evidence_selection import (
    _is_academic_metadata_evidence,
    _rank_evidence,
)


def test_is_academic_metadata_doi() -> None:
    assert _is_academic_metadata_evidence(
        "山博轩，杨郁\nDOI: 10.12677/sg.2024.142002\n12\n智能电网\ncomprehensive energy systems"
    ) is True


def test_is_academic_metadata_keywords() -> None:
    assert _is_academic_metadata_evidence(
        "Smart Grid\ncomprehensive energy systems...\nKeywords\nV2G, vehicle-to-grid"
    ) is True


def test_is_academic_metadata_journal_citation() -> None:
    assert _is_academic_metadata_evidence(
        "智能电网, 2024, 14(2), 11-20\nPublished Online April 2024 in Hans Publishers"
    ) is True


def test_is_academic_metadata_keeps_real_content() -> None:
    # Real V2G content paragraph must NOT be flagged as metadata.
    assert _is_academic_metadata_evidence(
        "标准最初由日本汽车制造商和电力公司共同开发,可支持双向充电,适合于V2G 场景应用。"
    ) is False
    assert _is_academic_metadata_evidence(
        "控制导引电路 control pilot circuit: 设计用于电动汽车和供电设备之间信号传输或通信的电路。"
    ) is False


def test_rank_evidence_demotes_metadata_below_content() -> None:
    """Metadata evidence (same confidence) must rank below real content."""
    metadata = {
        "evidence_id": "EV-META",
        "normalized_text": "山博轩，杨郁\nDOI: 10.12677/sg.2024.142002\ncomprehensive energy systems Keywords V2G",
        "confidence": 0.95,
    }
    content = {
        "evidence_id": "EV-REAL",
        "normalized_text": "标准最初由日本汽车制造商和电力公司共同开发,可支持双向充电,适合于V2G 场景应用。",
        "confidence": 0.95,
    }
    ranked = _rank_evidence([metadata, content], "V2G架构", "general_search")
    # Real content should rank first (metadata penalized -2.5)
    assert ranked[0]["evidence_id"] == "EV-REAL"
    assert ranked[1]["evidence_id"] == "EV-META"


def test_rank_evidence_real_content_used_when_only_metadata_and_content() -> None:
    """Even with lower confidence, content should beat heavily-penalized metadata."""
    metadata = {
        "evidence_id": "EV-META",
        "normalized_text": "智能电网, 2024, 14(2), 11-20 Published Online DOI: 10.12677/sg.2024.142002",
        "confidence": 0.99,
    }
    content = {
        "evidence_id": "EV-REAL",
        "normalized_text": "V2G 车网融合架构在逻辑上可划分为三个层次,即物理层、平台层及融合层。",
        "confidence": 0.50,
    }
    ranked = _rank_evidence([metadata, content], "V2G架构", "general_search")
    assert ranked[0]["evidence_id"] == "EV-REAL"
