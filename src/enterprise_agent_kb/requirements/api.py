from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .answer import answer_requirement_query
from .approval import RequirementApprovalService
from .compliance import RequirementComplianceService
from .diff import RequirementDiffService
from .impact import RequirementImpactAnalyzer
from .extraction import RequirementExtractionService
from .package_import import RequirementPackageImportService
from .repository import RequirementRepository
from .resolver import RequirementResolver
from .baseline import RequirementBaselineService
from .release_gate import RequirementReleaseGateService
from .eco import RequirementEcoService


class RequirementApiError(Exception):
    """Structured error raised by the framework-neutral requirement API adapter."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message

    def to_response(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "ok": False,
            "error": {"code": self.code, "message": self.message},
        }


def handle_requirement_api_request(
    root: Path,
    method: str,
    path: str,
    *,
    query_params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Framework-neutral HTTP-style adapter for requirement endpoints.

    This function lets the existing API server integrate the Requirement Resolver without
    depending on a specific web framework. Existing handlers can call it after matching a
    `/requirements/...` path and serialize the returned dict as JSON.
    """
    try:
        return _handle_requirement_api_request(root, method, path, query_params=query_params, body=body)
    except RequirementApiError as exc:
        return exc.to_response()
    except ValueError as exc:
        return RequirementApiError(404, "not_found", str(exc)).to_response()
    except Exception as exc:  # pragma: no cover - defensive boundary for HTTP servers
        return RequirementApiError(500, "requirement_api_error", str(exc)).to_response()


def _handle_requirement_api_request(
    root: Path,
    method: str,
    path: str,
    *,
    query_params: dict[str, Any] | None,
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    method = method.upper().strip()
    parsed = urlparse(path)
    route_path = parsed.path.rstrip("/") or "/"
    params = _merge_query_params(parsed.query, query_params or {})
    parts = [part for part in route_path.split("/") if part]

    if not parts or parts[0] != "requirements":
        raise RequirementApiError(404, "not_requirement_route", f"unsupported path: {path}")

    if method == "GET" and parts == ["requirements", "health"]:
        return _response({"status": "ok", "component": "requirements_api"})

    if method == "GET" and parts == ["requirements", "ecos"]:
        return _response(RequirementEcoService(RequirementRepository(root)).list_change_orders(
            project_id=_first(params, "project_id") or _first(params, "projectId"),
            status=_first(params, "status"),
            limit=int(_first(params, "limit") or 100),
        ))

    if method == "POST" and parts == ["requirements", "ecos"]:
        body = body or {}
        project_id = str(body.get("project_id") or body.get("projectId") or "").strip()
        variant_id = str(body.get("variant_id") or body.get("variantId") or "").strip()
        title = str(body.get("title") or "").strip()
        new_value = body.get("new_value", body.get("newValue"))
        if not project_id or not variant_id or not title or new_value is None:
            raise RequirementApiError(400, "missing_eco_fields", "project_id, title, variant_id, and new_value are required.")
        return _response(RequirementEcoService(RequirementRepository(root)).create_change_order(
            project_id=project_id,
            title=title,
            variant_id=variant_id,
            proposed_change={"value_numeric": float(new_value), "unit": body.get("unit"), "operator": body.get("operator")},
            created_by=body.get("created_by") or body.get("createdBy"),
            description=body.get("description"),
            auto_analyze=bool(body.get("auto_analyze", body.get("autoAnalyze", True))),
        ), status_code=201)

    if method == "GET" and len(parts) == 3 and parts[1] == "ecos":
        return _response(RequirementEcoService(RequirementRepository(root)).get_change_order(parts[2]))

    if method == "POST" and len(parts) == 4 and parts[1] == "ecos" and parts[3] == "submit":
        body = body or {}
        return _response(RequirementEcoService(RequirementRepository(root)).submit_for_approval(
            parts[2],
            submitted_by=body.get("submitted_by") or body.get("submittedBy"),
            reason=body.get("reason"),
        ))

    if method == "POST" and len(parts) == 4 and parts[1] == "ecos" and parts[3] == "approve":
        body = body or {}
        approver = body.get("approver") or body.get("actor")
        if not approver:
            raise RequirementApiError(400, "missing_approver", "approver is required.")
        return _response(RequirementEcoService(RequirementRepository(root)).approve(parts[2], approver=approver, comment=body.get("comment")))

    if method == "POST" and len(parts) == 4 and parts[1] == "ecos" and parts[3] == "apply":
        body = body or {}
        return _response(RequirementEcoService(RequirementRepository(root)).apply_change(
            parts[2],
            applied_by=body.get("applied_by") or body.get("appliedBy") or body.get("actor"),
            refresh_effective=bool(body.get("refresh_effective", body.get("refreshEffective", True))),
        ))

    if method == "POST" and len(parts) == 4 and parts[1] == "ecos" and parts[3] == "close":
        body = body or {}
        return _response(RequirementEcoService(RequirementRepository(root)).close_with_release_gate(
            parts[2],
            stage=body.get("stage") or "DV",
            closed_by=body.get("closed_by") or body.get("closedBy") or body.get("actor"),
            freeze_baseline=bool(body.get("freeze_baseline", body.get("freezeBaseline", True))),
        ))

    if method == "POST" and parts == ["requirements", "ecos", "run-cycle"]:
        body = body or {}
        project_id = str(body.get("project_id") or body.get("projectId") or "").strip()
        variant_id = str(body.get("variant_id") or body.get("variantId") or "").strip()
        title = str(body.get("title") or "").strip()
        new_value = body.get("new_value", body.get("newValue"))
        if not project_id or not variant_id or not title or new_value is None:
            raise RequirementApiError(400, "missing_eco_fields", "project_id, title, variant_id, and new_value are required.")
        return _response(RequirementEcoService(RequirementRepository(root)).run_full_cycle(
            project_id=project_id,
            title=title,
            variant_id=variant_id,
            proposed_change={"value_numeric": float(new_value), "unit": body.get("unit"), "operator": body.get("operator")},
            actor=body.get("actor"),
            stage=body.get("stage") or "DV",
        ), status_code=201)






    if method == "GET" and parts == ["requirements", "release-gates"]:
        return _response(RequirementReleaseGateService(RequirementRepository(root)).list_runs(
            project_id=_first(params, "project_id") or _first(params, "projectId"),
            stage=_first(params, "stage"),
            status=_first(params, "status"),
            limit=int(_first(params, "limit") or 100),
        ))

    if method == "GET" and len(parts) == 3 and parts[1] == "release-gates":
        return _response(RequirementReleaseGateService(RequirementRepository(root)).get_run(parts[2]))

    if method == "GET" and len(parts) == 4 and parts[1] == "projects" and parts[3] == "release-gate":
        return _response(RequirementReleaseGateService(RequirementRepository(root)).evaluate_project(
            parts[2],
            stage=_first(params, "stage") or "DV",
            baseline_id=_first(params, "baseline_id") or _first(params, "baselineId"),
            evaluated_by=_first(params, "evaluated_by") or _first(params, "evaluatedBy"),
            persist=(_first(params, "persist") or "true").lower() != "false",
        ))

    if method == "GET" and parts == ["requirements", "baselines"]:
        return _response(RequirementBaselineService(RequirementRepository(root)).list_baselines(
            project_id=_first(params, "project_id") or _first(params, "projectId"),
            status=_first(params, "status"),
            limit=int(_first(params, "limit") or 100),
        ))

    if method == "POST" and len(parts) == 4 and parts[1] == "projects" and parts[3] == "baselines":
        body = body or {}
        return _response(RequirementBaselineService(RequirementRepository(root)).freeze_project_baseline(
            parts[2],
            baseline_name=body.get("baseline_name") or body.get("baselineName") or body.get("name"),
            baseline_version=body.get("baseline_version") or body.get("baselineVersion") or body.get("version"),
            parent_baseline_id=body.get("parent_baseline_id") or body.get("parentBaselineId"),
            source_type=body.get("source_type") or body.get("sourceType") or "api_freeze",
            source_id=body.get("source_id") or body.get("sourceId"),
            frozen_by=body.get("frozen_by") or body.get("frozenBy"),
            comment=body.get("comment"),
        ), status_code=201)

    if method == "GET" and parts == ["requirements", "baselines", "compare"]:
        base_id = _first(params, "base_baseline_id") or _first(params, "baseBaselineId") or _first(params, "base")
        head_id = _first(params, "head_baseline_id") or _first(params, "headBaselineId") or _first(params, "head")
        if not base_id or not head_id:
            raise RequirementApiError(400, "missing_baseline_ids", "base_baseline_id and head_baseline_id are required.")
        return _response(RequirementBaselineService(RequirementRepository(root)).compare_baselines(base_id, head_id))

    if method == "GET" and len(parts) == 3 and parts[1] == "baselines":
        return _response(RequirementBaselineService(RequirementRepository(root)).get_baseline(parts[2]))

    if method == "GET" and len(parts) == 4 and parts[1] == "baselines" and parts[3] == "drift":
        return _response(RequirementBaselineService(RequirementRepository(root)).detect_drift(parts[2]))

    if method == "POST" and len(parts) == 4 and parts[1] == "baselines" and parts[3] == "rollback-plan":
        return _response(RequirementBaselineService(RequirementRepository(root)).build_rollback_plan(parts[2]))

    if method == "GET" and parts == ["requirements", "import-packages"]:
        service = RequirementPackageImportService(RequirementRepository(root))
        return _response(service.list_import_packages(
            customer_id=_first(params, "customer_id") or _first(params, "customerId"),
            project_id=_first(params, "project_id") or _first(params, "projectId"),
            status=_first(params, "status"),
            limit=int(_first(params, "limit") or 100),
        ))

    if method == "POST" and parts == ["requirements", "import-packages"]:
        body = body or {}
        sources = body.get("sources") or []
        if body.get("text"):
            sources = [*sources, {"name": "body.text", "text": body.get("text"), "source_type": body.get("source_type") or body.get("sourceType") or "api_text"}]
        if not sources:
            raise RequirementApiError(400, "missing_package_sources", "body.sources or body.text is required.")
        customer_id = str(body.get("customer_id") or body.get("customerId") or "").strip()
        project_id = str(body.get("project_id") or body.get("projectId") or "").strip()
        if not customer_id or not project_id:
            raise RequirementApiError(400, "missing_customer_project", "body.customer_id and body.project_id are required.")
        service = RequirementPackageImportService(RequirementRepository(root))
        return _response(service.import_project_package(
            customer_id=customer_id,
            customer_name=body.get("customer_name") or body.get("customerName"),
            project_id=project_id,
            project_code=body.get("project_code") or body.get("projectCode") or project_id,
            product_family=body.get("product_family") or body.get("productFamily") or "DCDC",
            package_name=body.get("package_name") or body.get("packageName"),
            profile_scope=body.get("profile_scope") or body.get("profileScope") or "project_overlay",
            sources=sources,
            auto_promote=bool(body.get("auto_promote") or body.get("autoPromote") or False),
            promoted_by=body.get("promoted_by") or body.get("promotedBy"),
            refresh_effective=bool(body.get("refresh_effective") or body.get("refreshEffective") or False),
            actor=body.get("actor") or body.get("promoted_by") or body.get("promotedBy"),
        ), status_code=201)

    if method == "POST" and len(parts) == 4 and parts[1] == "import-packages" and parts[3] == "refresh":
        return _response(RequirementPackageImportService(RequirementRepository(root)).refresh_package_effective_requirements(parts[2]))

    if method == "GET" and parts == ["requirements", "candidates"]:
        service = RequirementExtractionService(RequirementRepository(root))
        return _response(service.list_candidates(
            batch_id=_first(params, "batch_id") or _first(params, "batchId"),
            status=_first(params, "status"),
            profile_id=_first(params, "profile_id") or _first(params, "profileId"),
            limit=int(_first(params, "limit") or 100),
        ))

    if method == "POST" and parts == ["requirements", "candidates", "extract"]:
        body = body or {}
        text = str(body.get("text") or "").strip()
        doc_id = body.get("doc_id") or body.get("docId")
        profile_id = body.get("profile_id") or body.get("profileId")
        service = RequirementExtractionService(RequirementRepository(root))
        if text:
            return _response(service.extract_from_text(
                text,
                source_type=str(body.get("source_type") or body.get("sourceType") or "api_text"),
                source_id=body.get("source_id") or body.get("sourceId"),
                profile_id=profile_id,
                document_id=body.get("document_id") or body.get("documentId"),
                fact_id=body.get("fact_id") or body.get("factId"),
                evidence_id=body.get("evidence_id") or body.get("evidenceId"),
            ), status_code=201)
        if doc_id:
            return _response(service.extract_from_facts(doc_id=str(doc_id), profile_id=profile_id, limit=int(body.get("limit") or 50)), status_code=201)
        raise RequirementApiError(400, "missing_extraction_source", "body.text or body.doc_id is required.")

    if method == "POST" and len(parts) == 4 and parts[1] == "candidates" and parts[3] == "promote":
        body = body or {}
        return _response(RequirementExtractionService(RequirementRepository(root)).promote_candidate(
            parts[2],
            profile_id=body.get("profile_id") or body.get("profileId"),
            promoted_by=body.get("promoted_by") or body.get("promotedBy"),
        ))

    if method == "POST" and len(parts) == 4 and parts[1] == "candidates" and parts[3] == "reject":
        body = body or {}
        return _response(RequirementExtractionService(RequirementRepository(root)).reject_candidate(
            parts[2],
            reviewer=body.get("reviewer"),
            reason=body.get("reason"),
        ))

    if method == "GET" and len(parts) >= 4 and parts[1] == "projects" and parts[3] == "effective":
        project_id = parts[2]
        resolver = RequirementResolver(RequirementRepository(root))
        if len(parts) == 4:
            requirements = resolver.resolve_project(project_id)
            return _response(
                {
                    "project_id": project_id,
                    "count": len(requirements),
                    "requirements": [requirement.to_dict() for requirement in requirements],
                }
            )
        if len(parts) == 5:
            atom_id = parts[4]
            effective = resolver.resolve_requirement(project_id, atom_id)
            return _response(effective.to_dict())

    if method == "GET" and len(parts) == 4 and parts[1] == "projects" and parts[3] == "diff":
        project_id = parts[2]
        base_profile_id = _first(params, "base_profile_id") or _first(params, "baseProfileId")
        if not base_profile_id:
            raise RequirementApiError(400, "missing_base_profile_id", "base_profile_id is required for diff.")
        diff = RequirementDiffService(RequirementRepository(root)).diff_project_against_profile(project_id, base_profile_id)
        return _response(diff)


    if method == "GET" and len(parts) >= 4 and parts[1] == "projects" and parts[3] == "compliance":
        project_id = parts[2]
        service = RequirementComplianceService(RequirementRepository(root))
        if len(parts) == 4:
            return _response(service.build_project_matrix(project_id))
        if len(parts) == 5:
            return _response(service.build_requirement_compliance(project_id, parts[4]))

    if method == "GET" and parts == ["requirements", "impact"]:
        variant_id = _first(params, "variant_id") or _first(params, "variantId")
        new_value = _first(params, "new_value") or _first(params, "newValue") or _first(params, "value_numeric")
        unit = _first(params, "unit")
        operator = _first(params, "operator")
        if not variant_id:
            raise RequirementApiError(400, "missing_variant_id", "variant_id is required for impact analysis.")
        if new_value is None:
            raise RequirementApiError(400, "missing_new_value", "new_value is required for impact analysis.")
        impact = RequirementImpactAnalyzer(RequirementRepository(root)).analyze_variant_change(
            variant_id,
            {"value_numeric": float(new_value), "unit": unit, "operator": operator},
        )
        return _response(impact)

    if method == "POST" and parts == ["requirements", "impact-analysis"]:
        body = body or {}
        variant_id = str(body.get("variant_id") or body.get("variantId") or "").strip()
        proposed_change = dict(body.get("proposed_change") or body.get("proposedChange") or {})
        if "value_numeric" not in proposed_change and "new_value" in body:
            proposed_change["value_numeric"] = body.get("new_value")
        if "unit" not in proposed_change and body.get("unit"):
            proposed_change["unit"] = body.get("unit")
        if not variant_id:
            raise RequirementApiError(400, "missing_variant_id", "body.variant_id is required.")
        if not proposed_change:
            raise RequirementApiError(400, "missing_proposed_change", "body.proposed_change or body.new_value is required.")
        return _response(RequirementImpactAnalyzer(RequirementRepository(root)).analyze_variant_change(variant_id, proposed_change))

    if method == "GET" and len(parts) == 4 and parts[1] == "projects" and parts[3] == "conflicts":
        project_id = parts[2]
        resolver = RequirementResolver(RequirementRepository(root))
        requirements = resolver.resolve_project(project_id)
        issues = [
            requirement.to_dict()
            for requirement in requirements
            if requirement.conflict_status != "none" or requirement.verification_status != "verified"
        ]
        return _response({"project_id": project_id, "issue_count": len(issues), "issues": issues})

    if method == "GET" and parts == ["requirements", "reviews"]:
        project_id = _first(params, "project_id") or _first(params, "projectId")
        return _response(RequirementApprovalService(RequirementRepository(root)).build_review_report(project_id=project_id))

    if method == "GET" and parts == ["requirements", "approvals"]:
        project_id = _first(params, "project_id") or _first(params, "projectId")
        status = _first(params, "status")
        approvals = RequirementApprovalService(RequirementRepository(root)).list_approvals(project_id=project_id, status=status)
        return _response({"project_id": project_id, "status": status, "approvals": approvals})

    if method == "POST" and parts == ["requirements", "approvals"]:
        body = body or {}
        target_type = str(body.get("target_type") or body.get("targetType") or "").strip()
        target_id = str(body.get("target_id") or body.get("targetId") or "").strip()
        if not target_type or not target_id:
            raise RequirementApiError(400, "missing_approval_target", "body.target_type and body.target_id are required.")
        approval = RequirementApprovalService(RequirementRepository(root)).create_approval_request(
            target_type=target_type,
            target_id=target_id,
            project_id=body.get("project_id") or body.get("projectId"),
            atom_id=body.get("atom_id") or body.get("atomId"),
            variant_id=body.get("variant_id") or body.get("variantId"),
            override_id=body.get("override_id") or body.get("overrideId"),
            risk_level=body.get("risk_level") or body.get("riskLevel") or "medium",
            reason=body.get("reason"),
            requested_by=body.get("requested_by") or body.get("requestedBy"),
            evidence_id=body.get("evidence_id") or body.get("evidenceId"),
        )
        return _response(approval, status_code=201)

    if method == "POST" and len(parts) == 4 and parts[1] == "approvals" and parts[3] == "approve":
        body = body or {}
        approver = str(body.get("approver") or "").strip()
        if not approver:
            raise RequirementApiError(400, "missing_approver", "body.approver is required.")
        approval = RequirementApprovalService(RequirementRepository(root)).approve(
            parts[2],
            approver=approver,
            evidence_id=body.get("evidence_id") or body.get("evidenceId"),
            comment=body.get("comment"),
        )
        return _response(approval)

    if method == "POST" and len(parts) == 4 and parts[1] == "approvals" and parts[3] == "reject":
        body = body or {}
        approver = str(body.get("approver") or "").strip()
        if not approver:
            raise RequirementApiError(400, "missing_approver", "body.approver is required.")
        approval = RequirementApprovalService(RequirementRepository(root)).reject(
            parts[2],
            approver=approver,
            reason=body.get("reason"),
        )
        return _response(approval)

    if method == "POST" and parts == ["requirements", "query"]:
        body = body or {}
        query = str(body.get("query") or "").strip()
        if not query:
            raise RequirementApiError(400, "missing_query", "body.query is required.")
        return _response(answer_requirement_query(root, query))

    raise RequirementApiError(404, "unsupported_requirement_route", f"unsupported {method} {path}")


def create_fastapi_router(root: Path):
    """Create an optional FastAPI router for requirement endpoints.

    The import is intentionally lazy so projects without FastAPI can still import the
    requirement package and use the framework-neutral adapter.
    """
    from fastapi import APIRouter, Body, Query  # type: ignore

    router = APIRouter(prefix="/requirements", tags=["requirements"])

    @router.get("/health")
    def requirement_health() -> dict[str, Any]:
        return handle_requirement_api_request(root, "GET", "/requirements/health")

    @router.get("/projects/{project_id}/effective")
    def get_project_effective_requirements(project_id: str) -> dict[str, Any]:
        return handle_requirement_api_request(root, "GET", f"/requirements/projects/{project_id}/effective")

    @router.get("/projects/{project_id}/effective/{atom_id}")
    def get_effective_requirement(project_id: str, atom_id: str) -> dict[str, Any]:
        return handle_requirement_api_request(root, "GET", f"/requirements/projects/{project_id}/effective/{atom_id}")

    @router.get("/projects/{project_id}/diff")
    def get_requirement_diff(project_id: str, base_profile_id: str = Query(...)) -> dict[str, Any]:
        return handle_requirement_api_request(
            root,
            "GET",
            f"/requirements/projects/{project_id}/diff",
            query_params={"base_profile_id": base_profile_id},
        )

    @router.get("/projects/{project_id}/compliance")
    def get_requirement_compliance_matrix(project_id: str) -> dict[str, Any]:
        return handle_requirement_api_request(root, "GET", f"/requirements/projects/{project_id}/compliance")

    @router.get("/projects/{project_id}/compliance/{atom_id}")
    def get_requirement_atom_compliance(project_id: str, atom_id: str) -> dict[str, Any]:
        return handle_requirement_api_request(root, "GET", f"/requirements/projects/{project_id}/compliance/{atom_id}")

    @router.get("/impact")
    def get_requirement_impact(variant_id: str = Query(...), new_value: float = Query(...), unit: str | None = Query(None)) -> dict[str, Any]:
        return handle_requirement_api_request(
            root,
            "GET",
            "/requirements/impact",
            query_params={"variant_id": variant_id, "new_value": new_value, "unit": unit},
        )

    @router.post("/impact-analysis")
    def post_requirement_impact(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", "/requirements/impact-analysis", body=payload)

    @router.get("/projects/{project_id}/conflicts")
    def get_requirement_conflicts(project_id: str) -> dict[str, Any]:
        return handle_requirement_api_request(root, "GET", f"/requirements/projects/{project_id}/conflicts")

    @router.get("/reviews")
    def get_requirement_reviews(project_id: str | None = Query(None)) -> dict[str, Any]:
        return handle_requirement_api_request(root, "GET", "/requirements/reviews", query_params={"project_id": project_id})

    @router.get("/approvals")
    def get_requirement_approvals(project_id: str | None = Query(None), status: str | None = Query(None)) -> dict[str, Any]:
        return handle_requirement_api_request(root, "GET", "/requirements/approvals", query_params={"project_id": project_id, "status": status})

    @router.post("/approvals")
    def post_requirement_approval(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", "/requirements/approvals", body=payload)

    @router.post("/approvals/{approval_id}/approve")
    def approve_requirement_approval(approval_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", f"/requirements/approvals/{approval_id}/approve", body=payload)

    @router.post("/approvals/{approval_id}/reject")
    def reject_requirement_approval(approval_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", f"/requirements/approvals/{approval_id}/reject", body=payload)



    @router.get("/import-packages")
    def get_requirement_import_packages(
        customer_id: str | None = Query(None),
        project_id: str | None = Query(None),
        status: str | None = Query(None),
        limit: int = Query(100),
    ) -> dict[str, Any]:
        return handle_requirement_api_request(
            root,
            "GET",
            "/requirements/import-packages",
            query_params={"customer_id": customer_id, "project_id": project_id, "status": status, "limit": limit},
        )

    @router.post("/import-packages")
    def post_requirement_import_package(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", "/requirements/import-packages", body=payload)

    @router.post("/import-packages/{package_id}/refresh")
    def refresh_requirement_import_package(package_id: str) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", f"/requirements/import-packages/{package_id}/refresh")

    @router.get("/candidates")
    def get_requirement_candidates(
        batch_id: str | None = Query(None),
        status: str | None = Query(None),
        profile_id: str | None = Query(None),
        limit: int = Query(100),
    ) -> dict[str, Any]:
        return handle_requirement_api_request(
            root,
            "GET",
            "/requirements/candidates",
            query_params={"batch_id": batch_id, "status": status, "profile_id": profile_id, "limit": limit},
        )

    @router.post("/candidates/extract")
    def post_requirement_candidate_extraction(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", "/requirements/candidates/extract", body=payload)

    @router.post("/candidates/{candidate_id}/promote")
    def promote_requirement_candidate(candidate_id: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", f"/requirements/candidates/{candidate_id}/promote", body=payload)

    @router.post("/candidates/{candidate_id}/reject")
    def reject_requirement_candidate(candidate_id: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", f"/requirements/candidates/{candidate_id}/reject", body=payload)



    @router.get("/baselines")
    def get_requirement_baselines(
        project_id: str | None = Query(None),
        status: str | None = Query(None),
        limit: int = Query(100),
    ) -> dict[str, Any]:
        return handle_requirement_api_request(root, "GET", "/requirements/baselines", query_params={"project_id": project_id, "status": status, "limit": limit})

    @router.post("/projects/{project_id}/baselines")
    def post_requirement_baseline(project_id: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", f"/requirements/projects/{project_id}/baselines", body=payload)

    @router.get("/baselines/compare")
    def compare_requirement_baselines(base_baseline_id: str, head_baseline_id: str) -> dict[str, Any]:
        return handle_requirement_api_request(root, "GET", "/requirements/baselines/compare", query_params={"base_baseline_id": base_baseline_id, "head_baseline_id": head_baseline_id})

    @router.get("/baselines/{baseline_id}")
    def get_requirement_baseline(baseline_id: str) -> dict[str, Any]:
        return handle_requirement_api_request(root, "GET", f"/requirements/baselines/{baseline_id}")

    @router.get("/baselines/{baseline_id}/drift")
    def get_requirement_baseline_drift(baseline_id: str) -> dict[str, Any]:
        return handle_requirement_api_request(root, "GET", f"/requirements/baselines/{baseline_id}/drift")

    @router.post("/baselines/{baseline_id}/rollback-plan")
    def post_requirement_baseline_rollback_plan(baseline_id: str) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", f"/requirements/baselines/{baseline_id}/rollback-plan")

    @router.get("/ecos")
    def get_requirement_ecos(project_id: str | None = Query(None), status: str | None = Query(None), limit: int = Query(100)) -> dict[str, Any]:
        return handle_requirement_api_request(root, "GET", "/requirements/ecos", query_params={"project_id": project_id, "status": status, "limit": limit})

    @router.post("/ecos")
    def post_requirement_eco(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", "/requirements/ecos", body=payload)

    @router.get("/ecos/{eco_id}")
    def get_requirement_eco(eco_id: str) -> dict[str, Any]:
        return handle_requirement_api_request(root, "GET", f"/requirements/ecos/{eco_id}")

    @router.post("/ecos/{eco_id}/submit")
    def submit_requirement_eco(eco_id: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", f"/requirements/ecos/{eco_id}/submit", body=payload)

    @router.post("/ecos/{eco_id}/approve")
    def approve_requirement_eco(eco_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", f"/requirements/ecos/{eco_id}/approve", body=payload)

    @router.post("/ecos/{eco_id}/apply")
    def apply_requirement_eco(eco_id: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", f"/requirements/ecos/{eco_id}/apply", body=payload)

    @router.post("/ecos/{eco_id}/close")
    def close_requirement_eco(eco_id: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", f"/requirements/ecos/{eco_id}/close", body=payload)

    @router.post("/ecos/run-cycle")
    def run_requirement_eco_cycle(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", "/requirements/ecos/run-cycle", body=payload)

    @router.post("/query")
    def post_requirement_query(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return handle_requirement_api_request(root, "POST", "/requirements/query", body=payload)

    return router


def response_to_json_bytes(response: dict[str, Any]) -> bytes:
    """Serialize a requirement response for stdlib HTTP handlers."""
    return json.dumps(response, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _response(payload: dict[str, Any], status_code: int = 200) -> dict[str, Any]:
    return {"status_code": status_code, "ok": 200 <= status_code < 300, **payload}


def _merge_query_params(raw_query: str, explicit: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if raw_query:
        merged.update({key: values for key, values in parse_qs(raw_query, keep_blank_values=True).items()})
    merged.update(explicit)
    return merged


def _first(params: dict[str, Any], key: str) -> str | None:
    value = params.get(key)
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else None
    return str(value)
