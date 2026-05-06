from __future__ import annotations

from enterprise_agent_kb.quality import _page_metrics


def test_page_metrics_flags_unreadable_garbled_text() -> None:
    page = {
        "page_no": 1,
        "blocks": [
            {
                "block_type": "paragraph",
                "text": ("!\"#$%&'() * %&!$%&!&'!\"$#$( qrstuvwk0 " * 40),
            }
        ],
    }

    metrics = _page_metrics(page)

    assert metrics["risk_level"] == "high"
    assert metrics["page_status"] == "review_required"
    assert "low_readability" in metrics["risk_flags"] or "symbol_noise" in metrics["risk_flags"]


def test_page_metrics_keeps_readable_standard_text_ready() -> None:
    page = {
        "page_no": 1,
        "blocks": [
            {
                "block_type": "paragraph",
                "text": (
                    "GB/T 99999.1—2025 电动汽车传导充电系统通用要求。"
                    "本文件规定了充电接口、控制导引、电气安全和试验方法。"
                    "This document specifies charging system requirements and test methods. "
                    * 8
                ),
            }
        ],
    }

    metrics = _page_metrics(page)

    assert metrics["risk_level"] == "low"
    assert metrics["page_status"] == "ready"
    assert metrics["readability_score"] >= 0.35
