from __future__ import annotations

import json
from pathlib import Path

from enterprise_agent_kb.parse_risk_history import summarize_parse_risk_history


def test_parse_risk_history_summarizes_latest_counts_and_delta(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports" / "parse_risk_actions"
    report_dir.mkdir(parents=True)
    _write_json(
        report_dir / "doc-a-parse-risk-actions-20260517T100000Z0000.json",
        {
            "doc_id": "DOC-A",
            "generated_at": "2026-05-17T10:00:00+00:00",
            "status": "action_required",
            "attribution_counts": {"provider_quality_issue": 2, "structural_navigation_noise": 0},
            "repair_tasks": [{}, {}],
            "golden_candidate_requests": [{}],
        },
    )
    _write_json(
        report_dir / "doc-a-parse-risk-actions-20260517T110000Z0000.json",
        {
            "doc_id": "DOC-A",
            "generated_at": "2026-05-17T11:00:00+00:00",
            "status": "review_only",
            "attribution_counts": {"provider_quality_issue": 0, "structural_navigation_noise": 2},
            "repair_tasks": [{}],
            "golden_candidate_requests": [],
        },
    )
    _write_json(
        report_dir / "doc-a-parse-risk-repair-review-20260517T111000Z0000.json",
        {
            "doc_id": "DOC-A",
            "generated_at": "2026-05-17T11:10:00+00:00",
            "review_count": 1,
            "status_counts": {"done": 1},
        },
    )

    summary = summarize_parse_risk_history(tmp_path)

    assert summary["doc_count"] == 1
    assert summary["action_report_count"] == 2
    assert summary["review_report_count"] == 1
    assert summary["latest_attribution_counts"] == {
        "provider_quality_issue": 0,
        "structural_navigation_noise": 2,
    }
    doc = summary["docs"][0]
    assert doc["attribution_delta"] == {
        "provider_quality_issue": -2,
        "structural_navigation_noise": 2,
    }
    assert doc["latest_review"]["status_counts"] == {"done": 1}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
