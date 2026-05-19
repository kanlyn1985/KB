from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def summarize_parse_risk_history(workspace_root: Path, *, limit_per_doc: int = 8) -> dict[str, Any]:
    report_dir = workspace_root / "reports" / "parse_risk_actions"
    action_reports = _load_reports(report_dir, "-parse-risk-actions-")
    review_reports = _load_reports(report_dir, "-parse-risk-repair-review-")
    docs: dict[str, dict[str, Any]] = {}
    for doc_id, reports in _group_by_doc(action_reports).items():
        sorted_reports = sorted(reports, key=lambda item: str(item.get("generated_at") or ""))
        latest = sorted_reports[-1] if sorted_reports else {}
        previous = sorted_reports[-2] if len(sorted_reports) >= 2 else None
        docs[doc_id] = {
            "doc_id": doc_id,
            "action_run_count": len(sorted_reports),
            "latest_action": _action_summary(latest),
            "previous_action": _action_summary(previous) if previous else None,
            "attribution_delta": _attribution_delta(previous, latest) if previous else {},
            "action_history": [_action_summary(item) for item in sorted_reports[-limit_per_doc:]],
            "latest_review": None,
            "review_history": [],
        }
    for doc_id, reports in _group_by_doc(review_reports).items():
        sorted_reports = sorted(reports, key=lambda item: str(item.get("generated_at") or ""))
        entry = docs.setdefault(
            doc_id,
            {
                "doc_id": doc_id,
                "action_run_count": 0,
                "latest_action": None,
                "previous_action": None,
                "attribution_delta": {},
                "action_history": [],
                "latest_review": None,
                "review_history": [],
            },
        )
        entry["review_run_count"] = len(sorted_reports)
        entry["latest_review"] = _review_summary(sorted_reports[-1]) if sorted_reports else None
        entry["review_history"] = [_review_summary(item) for item in sorted_reports[-limit_per_doc:]]

    latest_counts = Counter()
    review_counts = Counter()
    for entry in docs.values():
        latest_action = entry.get("latest_action") if isinstance(entry.get("latest_action"), dict) else {}
        latest_counts.update(latest_action.get("attribution_counts") or {})
        latest_review = entry.get("latest_review") if isinstance(entry.get("latest_review"), dict) else {}
        review_counts.update(latest_review.get("status_counts") or {})
    return {
        "report_dir": str(report_dir),
        "doc_count": len(docs),
        "action_report_count": len(action_reports),
        "review_report_count": len(review_reports),
        "latest_attribution_counts": dict(sorted(latest_counts.items())),
        "latest_review_status_counts": dict(sorted(review_counts.items())),
        "docs": sorted(docs.values(), key=lambda item: str(item.get("doc_id") or "")),
    }


def _load_reports(report_dir: Path, marker: str) -> list[dict[str, Any]]:
    if not report_dir.exists():
        return []
    reports: list[dict[str, Any]] = []
    for path in sorted(report_dir.glob(f"*{marker}*.json")):
        suffix = path.name.rsplit(marker, 1)[-1]
        if not suffix[:8].isdigit():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("generated_at"):
            payload["_path"] = str(path)
            reports.append(payload)
    return reports


def _group_by_doc(reports: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for report in reports:
        doc_id = str(report.get("doc_id") or "").strip()
        if doc_id:
            grouped[doc_id].append(report)
    return grouped


def _action_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    return {
        "generated_at": report.get("generated_at"),
        "status": report.get("status"),
        "attribution_counts": report.get("attribution_counts") or {},
        "repair_task_count": len(report.get("repair_tasks") or []),
        "golden_candidate_request_count": len(report.get("golden_candidate_requests") or []),
        "persist_repair_tasks": bool(report.get("persist_repair_tasks")),
        "path": report.get("_path") or report.get("history_json_path") or report.get("json_path"),
    }


def _review_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    return {
        "generated_at": report.get("generated_at"),
        "review_count": report.get("review_count", 0),
        "status_counts": report.get("status_counts") or {},
        "path": report.get("_path") or report.get("history_json_path") or report.get("json_path"),
    }


def _attribution_delta(previous: dict[str, Any], latest: dict[str, Any]) -> dict[str, int]:
    previous_counts = previous.get("attribution_counts") if isinstance(previous, dict) else {}
    latest_counts = latest.get("attribution_counts") if isinstance(latest, dict) else {}
    if not isinstance(previous_counts, dict) or not isinstance(latest_counts, dict):
        return {}
    keys = set(previous_counts) | set(latest_counts)
    return {
        key: int(latest_counts.get(key) or 0) - int(previous_counts.get(key) or 0)
        for key in sorted(keys)
        if int(latest_counts.get(key) or 0) - int(previous_counts.get(key) or 0)
    }
