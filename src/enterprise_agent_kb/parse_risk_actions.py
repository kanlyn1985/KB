from __future__ import annotations

import json
import hashlib
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import AppPaths
from .db import connect
from .doc_diagnostics import build_document_diagnostics


@dataclass(frozen=True)
class ParseRiskRepairTask:
    reason: str
    module: str
    action: str
    priority: int
    page_count: int
    page_numbers: list[int]
    attribution: str


@dataclass(frozen=True)
class ParseRiskGoldenCandidateRequest:
    doc_id: str
    page_no: int
    origin: str
    reason: str
    activation_gate: str
    suggested_command: str


@dataclass(frozen=True)
class ParseRiskActionPlan:
    doc_id: str
    generated_at: str
    status: str
    attribution_counts: dict[str, int]
    repair_tasks: list[ParseRiskRepairTask]
    golden_candidate_requests: list[ParseRiskGoldenCandidateRequest]
    guardrails: list[str]
    diagnostics_summary: dict[str, Any]
    persisted_repair_tasks: list[dict[str, Any]]
    persist_repair_tasks: bool = False
    json_path: str | None = None
    report_path: str | None = None
    history_json_path: str | None = None
    history_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass(frozen=True)
class ParseRiskRepairReview:
    doc_id: str
    generated_at: str
    review_count: int
    status_counts: dict[str, int]
    reviews: list[dict[str, Any]]
    json_path: str | None = None
    report_path: str | None = None
    history_json_path: str | None = None
    history_report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_ACTION_BY_ATTRIBUTION = {
    "provider_quality_issue": {
        "reason": "parse_provider_quality_issue",
        "module": "parse.py / parser provider",
        "action": "增强 PDF/HTML/OCR provider 或 provider fallback；优先处理所有候选视图都低质量的页面。",
        "priority": 90,
    },
    "selection_rule_issue": {
        "reason": "parse_selection_rule_issue",
        "module": "parse_views.py",
        "action": "调整 parse view selection 评分规则；存在更高质量候选但未被选中时应先修选择器。",
        "priority": 95,
    },
    "extraction_chain_issue": {
        "reason": "parse_extraction_chain_issue",
        "module": "evidence / source_units / facts",
        "action": "检查 evidence、source_units、facts 及映射构建；不要先改问答策略。",
        "priority": 85,
    },
    "structural_navigation_noise": {
        "reason": "parse_structural_navigation_noise",
        "module": "doc_diagnostics.py / knowledge_units.py",
        "action": "目录/图表目录类导航页不生成知识单元；保留为结构性噪声复核，不进入修复 backlog。",
        "priority": 20,
    },
    "test_coverage_gap": {
        "reason": "parse_test_coverage_gap",
        "module": "golden_generation.py / corpus_eval.py",
        "action": "从证据链完整的风险页生成 golden/corpus 候选，并经过 readiness/activation gate 后再入回归集。",
        "priority": 70,
    },
    "review_only": {
        "reason": "parse_review_only",
        "module": "doc_diagnostics.py",
        "action": "保留人工复核 backlog；证据链完整且无明确测试缺口时不阻塞入库。",
        "priority": 30,
    },
}


def generate_parse_risk_action_plan(
    workspace_root: Path,
    doc_id: str,
    *,
    output_dir: Path | None = None,
    persist_repair_tasks: bool = False,
) -> ParseRiskActionPlan:
    diagnostics = build_document_diagnostics(workspace_root, doc_id)
    plan = build_parse_risk_action_plan(doc_id, diagnostics)
    persisted_tasks: list[dict[str, Any]] = []
    if persist_repair_tasks:
        connection = connect(AppPaths.from_root(workspace_root).db_file)
        try:
            persisted_tasks = persist_parse_risk_repair_tasks(connection, plan)
            connection.commit()
        finally:
            connection.close()
        plan = _with_persisted_tasks(plan, persisted_tasks)
    if output_dir is None:
        output_dir = workspace_root / "reports" / "parse_risk_actions"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{doc_id.lower()}-parse-risk-actions.json"
    report_path = output_dir / f"{doc_id.lower()}-parse-risk-actions.md"
    history_json_path = output_dir / f"{doc_id.lower()}-parse-risk-actions-{_timestamp_slug(plan.generated_at)}.json"
    history_report_path = output_dir / f"{doc_id.lower()}-parse-risk-actions-{_timestamp_slug(plan.generated_at)}.md"

    payload = plan.to_dict()
    payload["json_path"] = str(json_path)
    payload["report_path"] = str(report_path)
    payload["history_json_path"] = str(history_json_path)
    payload["history_report_path"] = str(history_report_path)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    history_json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    report_text = _format_markdown_report(payload)
    report_path.write_text(report_text, encoding="utf-8")
    history_report_path.write_text(report_text, encoding="utf-8")
    return ParseRiskActionPlan(
        doc_id=plan.doc_id,
        generated_at=plan.generated_at,
        status=plan.status,
        attribution_counts=plan.attribution_counts,
        repair_tasks=plan.repair_tasks,
        golden_candidate_requests=plan.golden_candidate_requests,
        guardrails=plan.guardrails,
        diagnostics_summary=plan.diagnostics_summary,
        persisted_repair_tasks=plan.persisted_repair_tasks,
        persist_repair_tasks=plan.persist_repair_tasks,
        json_path=str(json_path),
        report_path=str(report_path),
        history_json_path=str(history_json_path),
        history_report_path=str(history_report_path),
    )


def build_parse_risk_action_plan(doc_id: str, diagnostics: dict[str, Any]) -> ParseRiskActionPlan:
    parse_quality = diagnostics.get("parse_quality") if isinstance(diagnostics, dict) else {}
    if not isinstance(parse_quality, dict):
        parse_quality = {}
    pages = [page for page in parse_quality.get("pages", []) if isinstance(page, dict)]
    attribution_counts = _normalize_counts(parse_quality.get("attribution_counts"), pages)
    repair_tasks = _build_repair_tasks(pages, attribution_counts)
    golden_requests = _build_golden_candidate_requests(doc_id, pages)
    status = "action_required" if any(task.priority >= 70 for task in repair_tasks) else "review_only"
    if not pages:
        status = "no_parse_risk"
    return ParseRiskActionPlan(
        doc_id=doc_id,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        status=status,
        attribution_counts=attribution_counts,
        repair_tasks=repair_tasks,
        golden_candidate_requests=golden_requests,
        guardrails=[
            "Only pages attributed as test_coverage_gap may request golden/corpus candidates.",
            "Provider, selection, and extraction chain issues must be fixed upstream before generating answer regression cases.",
            "This plan is dry-run by default and does not activate golden cases or mutate repair_tasks.",
        ],
        diagnostics_summary={
            "high_risk_page_count": parse_quality.get("high_risk_page_count", 0),
            "actionable_parse_risk_pages": parse_quality.get("actionable_parse_risk_pages", 0),
            "chain_gap_pages": parse_quality.get("chain_gap_pages", 0),
            "fully_backed_high_risk_pages": parse_quality.get("fully_backed_high_risk_pages", 0),
        },
        persisted_repair_tasks=[],
    )


def review_parse_risk_repair_tasks(
    workspace_root: Path,
    doc_id: str,
    *,
    output_dir: Path | None = None,
) -> ParseRiskRepairReview:
    diagnostics = build_document_diagnostics(workspace_root, doc_id)
    current_plan = build_parse_risk_action_plan(doc_id, diagnostics)
    connection = connect(AppPaths.from_root(workspace_root).db_file)
    try:
        review = build_parse_risk_repair_review(connection, doc_id, current_plan)
    finally:
        connection.close()

    if output_dir is None:
        output_dir = workspace_root / "reports" / "parse_risk_actions"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{doc_id.lower()}-parse-risk-repair-review.json"
    report_path = output_dir / f"{doc_id.lower()}-parse-risk-repair-review.md"
    history_json_path = output_dir / f"{doc_id.lower()}-parse-risk-repair-review-{_timestamp_slug(review.generated_at)}.json"
    history_report_path = output_dir / f"{doc_id.lower()}-parse-risk-repair-review-{_timestamp_slug(review.generated_at)}.md"
    payload = review.to_dict()
    payload["json_path"] = str(json_path)
    payload["report_path"] = str(report_path)
    payload["history_json_path"] = str(history_json_path)
    payload["history_report_path"] = str(history_report_path)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    history_json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    report_text = _format_repair_review_markdown(payload)
    report_path.write_text(report_text, encoding="utf-8")
    history_report_path.write_text(report_text, encoding="utf-8")
    return ParseRiskRepairReview(
        doc_id=review.doc_id,
        generated_at=review.generated_at,
        review_count=review.review_count,
        status_counts=review.status_counts,
        reviews=review.reviews,
        json_path=str(json_path),
        report_path=str(report_path),
        history_json_path=str(history_json_path),
        history_report_path=str(history_report_path),
    )


def build_parse_risk_repair_review(
    connection,
    doc_id: str,
    current_plan: ParseRiskActionPlan,
) -> ParseRiskRepairReview:
    _ensure_repair_tasks_table(connection)
    current_by_reason = {task.reason: task for task in current_plan.repair_tasks}
    rows = connection.execute(
        """
        SELECT task_id, reason, module, action, priority, status,
               case_ids_json, query_types_json, impact_count,
               source_eval_run_id, metadata_json, first_seen_at, last_seen_at
        FROM repair_tasks
        WHERE json_extract(metadata_json, '$.source') = 'parse_risk_action_plan'
        ORDER BY priority DESC, last_seen_at DESC, task_id ASC
        """
    ).fetchall()
    reviews: list[dict[str, Any]] = []
    for row in rows:
        task = _repair_task_row_to_dict(row)
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        docs = metadata.get("parse_risk_docs") if isinstance(metadata, dict) else {}
        if not isinstance(docs, dict) or doc_id not in docs:
            continue
        previous_doc = docs.get(doc_id) if isinstance(docs.get(doc_id), dict) else {}
        previous_pages = _as_int_set(previous_doc.get("page_numbers") if isinstance(previous_doc, dict) else [])
        current_task = current_by_reason.get(str(task.get("reason") or ""))
        current_pages = set(current_task.page_numbers) if current_task else set()
        suggested_status = _suggest_repair_status(previous_pages, current_pages)
        reviews.append(
            {
                "task_id": task["task_id"],
                "reason": task["reason"],
                "module": task["module"],
                "status": task["status"],
                "suggested_status": suggested_status,
                "previous_page_count": len(previous_pages),
                "current_page_count": len(current_pages),
                "resolved_pages": sorted(previous_pages - current_pages),
                "remaining_pages": sorted(previous_pages & current_pages),
                "new_pages": sorted(current_pages - previous_pages),
                "previous_pages": sorted(previous_pages),
                "current_pages": sorted(current_pages),
                "action": _review_action_for_status(suggested_status),
            }
        )
    status_counts = Counter(str(review["suggested_status"]) for review in reviews)
    return ParseRiskRepairReview(
        doc_id=doc_id,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        review_count=len(reviews),
        status_counts=dict(sorted(status_counts.items())),
        reviews=reviews,
    )


def persist_parse_risk_repair_tasks(connection, plan: ParseRiskActionPlan) -> list[dict[str, Any]]:
    _ensure_repair_tasks_table(connection)
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    persisted: list[dict[str, Any]] = []
    for task in plan.repair_tasks:
        if task.attribution in {"review_only", "structural_navigation_noise"}:
            continue
        task_id = _stable_task_id(task.reason, task.module, task.action)
        existing = connection.execute(
            """
            SELECT task_id, reason, module, action, priority, status,
                   case_ids_json, query_types_json, impact_count,
                   source_eval_run_id, metadata_json, first_seen_at, last_seen_at
            FROM repair_tasks
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        metadata = _merge_parse_risk_metadata(
            _safe_json(existing["metadata_json"], {}) if existing else {},
            plan=plan,
            task=task,
        )
        status = "open"
        if existing:
            existing_status = str(existing["status"] or "open")
            status = "reopened" if existing_status in {"done", "resolved"} else existing_status
        connection.execute(
            """
            INSERT INTO repair_tasks (
                task_id, reason, module, action, priority, status,
                case_ids_json, query_types_json, impact_count,
                source_eval_run_id, metadata_json, first_seen_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', ?, NULL, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                priority = MAX(repair_tasks.priority, excluded.priority),
                status = CASE
                    WHEN repair_tasks.status IN ('done', 'resolved') THEN excluded.status
                    ELSE repair_tasks.status
                END,
                impact_count = MAX(repair_tasks.impact_count, excluded.impact_count),
                metadata_json = excluded.metadata_json,
                last_seen_at = excluded.last_seen_at
            """,
            (
                task_id,
                task.reason,
                task.module,
                task.action,
                task.priority,
                status,
                int(metadata.get("parse_risk_total_page_count") or task.page_count),
                json.dumps(metadata, ensure_ascii=False),
                existing["first_seen_at"] if existing else timestamp,
                timestamp,
            ),
        )
        persisted_row = connection.execute(
            """
            SELECT task_id, reason, module, action, priority, status,
                   case_ids_json, query_types_json, impact_count,
                   source_eval_run_id, metadata_json, first_seen_at, last_seen_at
            FROM repair_tasks
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        if persisted_row:
            persisted.append(_repair_task_row_to_dict(persisted_row))
    return persisted


def _normalize_counts(raw_counts: object, pages: list[dict[str, Any]]) -> dict[str, int]:
    counts = {key: 0 for key in _ACTION_BY_ATTRIBUTION}
    if isinstance(raw_counts, dict):
        for key in counts:
            counts[key] = int(raw_counts.get(key) or 0)
    else:
        page_counts = Counter(str(page.get("attribution") or "review_only") for page in pages)
        for key in counts:
            counts[key] = int(page_counts.get(key, 0))
    return counts


def _build_repair_tasks(
    pages: list[dict[str, Any]],
    attribution_counts: dict[str, int],
) -> list[ParseRiskRepairTask]:
    pages_by_attribution: dict[str, list[int]] = {key: [] for key in _ACTION_BY_ATTRIBUTION}
    for page in pages:
        attribution = str(page.get("attribution") or "review_only")
        if attribution not in pages_by_attribution:
            attribution = "review_only"
        page_no = int(page.get("page_no") or 0)
        if page_no > 0:
            pages_by_attribution[attribution].append(page_no)

    tasks: list[ParseRiskRepairTask] = []
    for attribution, template in _ACTION_BY_ATTRIBUTION.items():
        count = int(attribution_counts.get(attribution) or 0)
        if count <= 0:
            continue
        page_numbers = sorted(set(pages_by_attribution.get(attribution, [])))
        tasks.append(
            ParseRiskRepairTask(
                reason=str(template["reason"]),
                module=str(template["module"]),
                action=str(template["action"]),
                priority=int(template["priority"]),
                page_count=count,
                page_numbers=page_numbers[:50],
                attribution=attribution,
            )
        )
    return sorted(tasks, key=lambda task: (-task.priority, task.reason))


def _build_golden_candidate_requests(
    doc_id: str,
    pages: list[dict[str, Any]],
) -> list[ParseRiskGoldenCandidateRequest]:
    requests: list[ParseRiskGoldenCandidateRequest] = []
    for page in pages:
        if page.get("attribution") != "test_coverage_gap":
            continue
        page_no = int(page.get("page_no") or 0)
        if page_no <= 0:
            continue
        requests.append(
            ParseRiskGoldenCandidateRequest(
                doc_id=doc_id,
                page_no=page_no,
                origin="source_unit",
                reason="证据链已闭合但测试覆盖不足，可从对应 source_unit 生成候选。",
                activation_gate="generate-golden-candidates -> readiness review -> activate/promote",
                suggested_command=(
                    "C:\\Python314\\python.exe -m enterprise_agent_kb.cli --root knowledge_base "
                    f"generate-golden-candidates --origin source_unit --doc-id {doc_id}"
                ),
            )
        )
    return requests


def _with_persisted_tasks(
    plan: ParseRiskActionPlan,
    persisted_tasks: list[dict[str, Any]],
) -> ParseRiskActionPlan:
    return ParseRiskActionPlan(
        doc_id=plan.doc_id,
        generated_at=plan.generated_at,
        status=plan.status,
        attribution_counts=plan.attribution_counts,
        repair_tasks=plan.repair_tasks,
        golden_candidate_requests=plan.golden_candidate_requests,
        guardrails=plan.guardrails,
        diagnostics_summary=plan.diagnostics_summary,
        persisted_repair_tasks=persisted_tasks,
        persist_repair_tasks=True,
        json_path=plan.json_path,
        report_path=plan.report_path,
    )


def _merge_parse_risk_metadata(
    existing: dict[str, Any],
    *,
    plan: ParseRiskActionPlan,
    task: ParseRiskRepairTask,
) -> dict[str, Any]:
    metadata = dict(existing) if isinstance(existing, dict) else {}
    metadata["source"] = "parse_risk_action_plan"
    metadata["last_doc_id"] = plan.doc_id
    metadata["last_attribution"] = task.attribution
    metadata["last_page_numbers"] = task.page_numbers
    docs = metadata.get("parse_risk_docs")
    if not isinstance(docs, dict):
        docs = {}
    docs[plan.doc_id] = {
        "page_count": task.page_count,
        "page_numbers": task.page_numbers,
        "attribution": task.attribution,
        "generated_at": plan.generated_at,
    }
    metadata["parse_risk_docs"] = dict(sorted(docs.items()))
    metadata["parse_risk_doc_count"] = len(metadata["parse_risk_docs"])
    metadata["parse_risk_total_page_count"] = sum(
        int(item.get("page_count") or 0)
        for item in metadata["parse_risk_docs"].values()
        if isinstance(item, dict)
    )
    return metadata


def _stable_task_id(*parts: str) -> str:
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:16].upper()
    return f"REPAIR-PARSE-{digest}"


def _timestamp_slug(value: str) -> str:
    return (
        str(value or "")
        .replace(":", "")
        .replace("-", "")
        .replace("+", "Z")
        .replace(".", "")
    )


def _safe_json(value: object, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _as_int_set(values: object) -> set[int]:
    if not isinstance(values, list):
        return set()
    result: set[int] = set()
    for value in values:
        try:
            page_no = int(value)
        except (TypeError, ValueError):
            continue
        if page_no > 0:
            result.add(page_no)
    return result


def _suggest_repair_status(previous_pages: set[int], current_pages: set[int]) -> str:
    if not previous_pages and current_pages:
        return "new_scope"
    if previous_pages and not current_pages:
        return "done"
    if len(current_pages) < len(previous_pages):
        return "improved"
    if current_pages == previous_pages:
        return "still_open"
    if current_pages - previous_pages:
        return "expanded"
    return "still_open"


def _review_action_for_status(status: str) -> str:
    if status == "done":
        return "建议将 repair task 标记为 done；当前文档已不再复现该归因。"
    if status == "improved":
        return "风险页减少，保持任务 open 并继续处理 remaining_pages。"
    if status == "expanded":
        return "风险范围扩大，优先复核 new_pages，并检查修复是否引入回退。"
    if status == "new_scope":
        return "当前文档出现新影响范围，建议先持久化 action plan 后再纳入任务影响面。"
    return "风险范围未改善，保持任务 open 并回到对应上游模块修根因。"


def _ensure_repair_tasks_table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS repair_tasks (
            task_id TEXT PRIMARY KEY,
            reason TEXT NOT NULL,
            module TEXT NOT NULL,
            action TEXT NOT NULL,
            priority INTEGER NOT NULL,
            status TEXT NOT NULL,
            case_ids_json TEXT NOT NULL DEFAULT '[]',
            query_types_json TEXT NOT NULL DEFAULT '[]',
            impact_count INTEGER NOT NULL DEFAULT 0,
            source_eval_run_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_repair_tasks_status ON repair_tasks(status)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_repair_tasks_reason ON repair_tasks(reason)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_repair_tasks_last_seen_at ON repair_tasks(last_seen_at)")


def _repair_task_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "task_id": row["task_id"],
        "reason": row["reason"],
        "module": row["module"],
        "action": row["action"],
        "priority": row["priority"],
        "status": row["status"],
        "case_ids": _safe_json(row["case_ids_json"], []),
        "query_types": _safe_json(row["query_types_json"], []),
        "impact_count": row["impact_count"],
        "source_eval_run_id": row["source_eval_run_id"],
        "metadata": _safe_json(row["metadata_json"], {}),
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
    }


def _format_markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# Parse Risk Action Plan: {payload.get('doc_id')}",
        "",
        f"- Status: {payload.get('status')}",
        f"- Generated at: {payload.get('generated_at')}",
        f"- Persist repair tasks: {payload.get('persist_repair_tasks')}",
        "",
        "## Attribution Counts",
        "",
    ]
    for key, value in (payload.get("attribution_counts") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Repair Tasks", ""])
    for task in payload.get("repair_tasks") or []:
        lines.append(
            f"- P{task.get('priority')} {task.get('reason')} "
            f"({task.get('page_count')} pages): {task.get('action')}"
        )
    if not payload.get("repair_tasks"):
        lines.append("- None")
    lines.extend(["", "## Golden Candidate Requests", ""])
    for request in payload.get("golden_candidate_requests") or []:
        lines.append(
            f"- Page {request.get('page_no')}: {request.get('reason')} "
            f"Gate: {request.get('activation_gate')}"
        )
    if not payload.get("golden_candidate_requests"):
        lines.append("- None")
    lines.extend(["", "## Persisted Repair Tasks", ""])
    for task in payload.get("persisted_repair_tasks") or []:
        lines.append(f"- {task.get('task_id')}: {task.get('reason')} [{task.get('status')}]")
    if not payload.get("persisted_repair_tasks"):
        lines.append("- None")
    lines.extend(["", "## Guardrails", ""])
    for guardrail in payload.get("guardrails") or []:
        lines.append(f"- {guardrail}")
    lines.append("")
    return "\n".join(lines)


def _format_repair_review_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Parse Risk Repair Review: {payload.get('doc_id')}",
        "",
        f"- Generated at: {payload.get('generated_at')}",
        f"- Review count: {payload.get('review_count')}",
        "",
        "## Status Counts",
        "",
    ]
    for key, value in (payload.get("status_counts") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Reviews", ""])
    for review in payload.get("reviews") or []:
        lines.append(
            f"- {review.get('task_id')} {review.get('reason')}: "
            f"{review.get('suggested_status')} "
            f"({review.get('previous_page_count')} -> {review.get('current_page_count')})"
        )
        lines.append(f"  - action: {review.get('action')}")
        if review.get("remaining_pages"):
            lines.append(f"  - remaining_pages: {review.get('remaining_pages')}")
        if review.get("new_pages"):
            lines.append(f"  - new_pages: {review.get('new_pages')}")
    if not payload.get("reviews"):
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)
