"""Tests for answer_safety.py — citation correctness and unsupported-claim detection.

Sprint 3 WP4. These verify the safety observations (read-only) without
modifying the answer payload.
"""
from __future__ import annotations

import pytest

from enterprise_agent_kb.answer_safety import diagnose_answer_safety


def _ev(evidence_id: str, doc_id: str, text: str) -> dict:
    return {"evidence_id": evidence_id, "doc_id": doc_id, "normalized_text": text}


@pytest.mark.unit
class TestDiagnoseAnswerSafety:
    def test_citation_correct_when_evidence_matches_preferred_doc(self) -> None:
        answer = {
            "direct_answer": "室外使用的供电设备的温度范围是-25℃到+40℃。",
            "preferred_doc_id": "DOC-000003",
            "supporting_evidence": [
                _ev("EV-049796", "DOC-000003", "室外使用 outdoor use 能用于无气候防护场所"),
            ],
        }
        r = diagnose_answer_safety(answer)
        assert r["citation_correct"] is True
        assert r["unsupported_claim"] is False
        assert r["title_block_citation"] is False

    def test_unsupported_claim_when_substantive_answer_has_no_evidence(self) -> None:
        answer = {
            "direct_answer": "室外使用的供电设备的温度范围是-25℃到+40℃。",
            "preferred_doc_id": "DOC-000003",
            "supporting_evidence": [],
        }
        r = diagnose_answer_safety(answer)
        assert r["unsupported_claim"] is True
        assert r["reason"] == "substantive_claim_no_supporting_evidence"

    def test_title_block_citation_flagged_when_only_title_evidence(self) -> None:
        answer = {
            "direct_answer": "该标准是中华人民共和国国家标准。",
            "preferred_doc_id": "DOC-000016",
            "supporting_evidence": [
                _ev("EV-000001", "DOC-000016", "GB/T 18487.4—2025\n中华人民共和国国家标准"),
            ],
        }
        r = diagnose_answer_safety(answer)
        assert r["title_block_citation"] is True

    def test_degraded_answer_is_safe_not_unsupported(self) -> None:
        answer = {
            "direct_answer": "知识库中未找到与该查询相关的信息。",
            "preferred_doc_id": None,
            "supporting_evidence": [],
        }
        r = diagnose_answer_safety(answer)
        assert r["degraded_answer"] is True
        assert r["unsupported_claim"] is False

    def test_citation_doc_mismatch_flagged(self) -> None:
        answer = {
            "direct_answer": "室外使用的供电设备的温度范围是-25℃到+40℃。",
            "preferred_doc_id": "DOC-000003",
            "supporting_evidence": [
                _ev("EV-999999", "DOC-000012", "车辆控制器保持 S2 闭合"),
            ],
        }
        r = diagnose_answer_safety(answer)
        assert r["citation_correct"] is False
        assert r["reason"] == "citation_doc_mismatch_with_preferred_doc"

    def test_invalid_payload_returns_invalid_reason(self) -> None:
        r = diagnose_answer_safety("not a dict")  # type: ignore[arg-type]
        assert r["citation_correct"] is False
        assert "invalid_payload" in r["reason"]

    def test_academic_header_citation_flagged_as_title_block(self) -> None:
        answer = {
            "direct_answer": "该研究由山博轩和杨郁完成。",
            "preferred_doc_id": "DOC-000013",
            "supporting_evidence": [
                _ev("EV-049931", "DOC-000013", "山博轩，杨郁 DOI: 10.12677/sg.2014 Keywords: smart grid"),
            ],
        }
        r = diagnose_answer_safety(answer)
        assert r["title_block_citation"] is True

    def test_non_substantive_short_answer_not_flagged(self) -> None:
        # A short parameter value answer with no evidence is not unsupported.
        answer = {
            "direct_answer": "4V",
            "preferred_doc_id": "DOC-000003",
            "supporting_evidence": [],
        }
        r = diagnose_answer_safety(answer)
        assert r["unsupported_claim"] is False
        assert r["degraded_answer"] is False

    def test_never_raises_on_malformed_evidence_items(self) -> None:
        answer = {
            "direct_answer": "室外使用的供电设备的温度范围。",
            "preferred_doc_id": "DOC-000003",
            "supporting_evidence": ["not a dict", None, {"no": "fields"}],
        }
        r = diagnose_answer_safety(answer)
        assert "reason" in r  # must not raise
