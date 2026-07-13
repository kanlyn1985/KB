#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GateResult:
    name: str
    status: str
    duration_s: float
    command: list[str] | None = None
    message: str = ""
    stdout: str = ""
    stderr: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class RequirementProgramRunner:
    def __init__(self, repo_root: Path, workspace_root: Path, mode: str, continue_on_error: bool, apply_integrations: bool, api_integration: bool):
        self.repo_root = repo_root.resolve()
        self.workspace_root = workspace_root.resolve()
        self.mode = mode
        self.continue_on_error = continue_on_error
        self.apply_integrations = apply_integrations
        self.api_integration = api_integration
        self.runtime_root = self.repo_root / ".requirement_program_runtime"
        self.reports_dir = self.runtime_root / "reports"
        self.results: list[GateResult] = []
        self.env = os.environ.copy()
        src_path = str(self.repo_root / "src")
        existing = self.env.get("PYTHONPATH")
        self.env["PYTHONPATH"] = src_path if not existing else f"{src_path}{os.pathsep}{existing}"

    def run(self) -> int:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self._gate("preflight", self.preflight)
        if self.apply_integrations:
            self._gate("integration.cli", lambda: self.run_command([sys.executable, "scripts/apply_requirement_cli_integration.py"]))
            self._gate("integration.answer_api", lambda: self.run_command([sys.executable, "scripts/apply_requirement_answer_api_integration.py"]))
            if self.api_integration:
                self._gate("integration.api", lambda: self.run_command([sys.executable, "scripts/apply_requirement_api_integration.py"], allow_nonzero=True))
        self._gate("unit.tests", self.run_unit_tests)
        self._gate("smoke.workspace.reset", self.reset_workspace)
        self._gate("smoke.schema", self.smoke_schema)
        self._gate("smoke.seed", self.smoke_seed)
        self._gate("smoke.resolver", self.smoke_resolver)
        self._gate("smoke.diff", self.smoke_diff)
        self._gate("smoke.query_answer", self.smoke_query_answer)
        self._gate("smoke.api_adapter", self.smoke_api_adapter)
        self._gate("smoke.compliance", self.smoke_compliance)
        self._gate("smoke.impact", self.smoke_impact)
        self._gate("smoke.approval", self.smoke_approval)
        self._gate("smoke.extraction", self.smoke_extraction)
        self._gate("smoke.package_import", self.smoke_package_import)
        self._gate("smoke.baseline", self.smoke_baseline)
        self._gate("smoke.release_gate", self.smoke_release_gate)
        self._gate("smoke.eco", self.smoke_eco)
        self.write_reports()
        return 0 if all(r.status == "passed" for r in self.results) else 1

    def _gate(self, name: str, fn):
        start = time.time()
        try:
            result = fn()
            if isinstance(result, GateResult):
                result.name = name
                result.duration_s = time.time() - start
                self.results.append(result)
                ok = result.status == "passed"
            else:
                self.results.append(GateResult(name=name, status="passed", duration_s=time.time() - start, data=result or {}))
                ok = True
        except Exception as exc:
            self.results.append(GateResult(name=name, status="failed", duration_s=time.time() - start, message=str(exc)))
            ok = False
        print(f"[{self.results[-1].status.upper()}] {name} ({self.results[-1].duration_s:.2f}s)")
        if not ok and not self.continue_on_error:
            self.write_reports()
            raise SystemExit(1)

    def run_command(self, cmd: list[str], *, allow_nonzero: bool = False, parse_json: bool = False, env_extra: dict[str, str] | None = None) -> GateResult:
        env = self.env.copy()
        if env_extra:
            env.update(env_extra)
        start = time.time()
        proc = subprocess.run(cmd, cwd=self.repo_root, env=env, text=True, capture_output=True)
        status = "passed" if proc.returncode == 0 or allow_nonzero else "failed"
        data: dict[str, Any] = {"returncode": proc.returncode}
        if parse_json and proc.stdout.strip():
            try:
                data["json"] = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                status = "failed"
                data["json_error"] = str(exc)
        return GateResult(
            name="command",
            status=status,
            duration_s=time.time() - start,
            command=cmd,
            stdout=proc.stdout[-4000:],
            stderr=proc.stderr[-4000:],
            data=data,
        )

    def preflight(self) -> dict[str, Any]:
        required = [
            self.repo_root / "pyproject.toml",
            self.repo_root / "src" / "enterprise_agent_kb" / "config.py",
            self.repo_root / "src" / "enterprise_agent_kb" / "db.py",
            self.repo_root / "src" / "enterprise_agent_kb" / "requirements",
        ]
        missing = [str(path.relative_to(self.repo_root)) for path in required if not path.exists()]
        if missing:
            raise RuntimeError(f"missing required repository paths: {missing}")
        import_result = self.run_command([sys.executable, "-c", "import enterprise_agent_kb.requirements; print('ok')"])
        if import_result.status != "passed":
            raise RuntimeError(import_result.stderr or import_result.stdout or "cannot import enterprise_agent_kb.requirements")
        return {"repo_root": str(self.repo_root), "workspace_root": str(self.workspace_root)}

    def run_unit_tests(self) -> GateResult:
        if self.mode == "smoke":
            tests = [
                "tests/test_requirement_resolver_mvp.py",
                "tests/test_requirement_query_adapter.py",
                "tests/test_requirement_compliance.py",
                "tests/test_requirement_impact.py",
                "tests/test_requirement_package_import.py",
                "tests/test_requirement_release_gate.py",
                "tests/test_requirement_eco.py",
            ]
            cmd = [sys.executable, "-m", "unittest", "-v", *tests]
        else:
            cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
        return self.run_command(cmd)

    def reset_workspace(self) -> dict[str, Any]:
        if self.workspace_root.exists():
            shutil.rmtree(self.workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        return {"workspace_root": str(self.workspace_root)}

    def req_cli(self, *args: str, parse_json: bool = True) -> GateResult:
        return self.run_command([sys.executable, "-m", "enterprise_agent_kb.requirements.cli", "--root", str(self.workspace_root), *args], parse_json=parse_json)

    def smoke_schema(self) -> GateResult:
        result = self.req_cli("init-schema")
        self.assert_json(result, lambda data: "requirement_atoms" in data.get("tables", []), "requirement_atoms table missing")
        return result

    def smoke_seed(self) -> GateResult:
        result = self.req_cli("seed-sample")
        self.assert_json(result, lambda data: data.get("status") == "ok", "seed-sample status not ok")
        return result

    def smoke_resolver(self) -> GateResult:
        p1 = self.req_cli("resolve", "--project-id", "CUST-A-P1", "--atom-id", "REQATOM-DCDC-OUTPUT-RIPPLE")
        self.assert_json(p1, lambda d: d.get("value_numeric") == 30 and d.get("unit") == "mV" and d.get("conflict_status") == "none", "P1 ripple expected 30mV/no conflict")
        p2 = self.req_cli("resolve", "--project-id", "CUST-A-P2", "--atom-id", "REQATOM-DCDC-OUTPUT-RIPPLE")
        self.assert_json(p2, lambda d: d.get("conflict_status") == "approval_required", "P2 ripple should require approval")
        p1.data["p2"] = p2.data.get("json")
        return p1

    def smoke_diff(self) -> GateResult:
        result = self.req_cli("diff", "--project-id", "CUST-A-P1", "--base-profile-id", "PROFILE-CUST-A-DCDC-COMMON")
        self.assert_json(result, lambda d: d.get("project_id") == "CUST-A-P1", "diff project mismatch")
        return result

    def smoke_query_answer(self) -> GateResult:
        result = self.req_cli("ask", "--query", "客户A P1项目 DCDC 输出纹波要求是多少？", "--raw")
        self.assert_json(result, lambda d: d.get("intent") == "requirement_effective" and "30" in d.get("direct_answer", ""), "query answer did not resolve expected requirement")
        return result

    def smoke_api_adapter(self) -> GateResult:
        code = f"""
from pathlib import Path
from enterprise_agent_kb.requirements.api import handle_requirement_api_request
r = handle_requirement_api_request(Path({str(self.workspace_root)!r}), 'GET', '/requirements/projects/CUST-A-P1/effective/REQATOM-DCDC-OUTPUT-RIPPLE')
import json
print(json.dumps(r, ensure_ascii=False))
"""
        result = self.run_command([sys.executable, "-c", code], parse_json=True)
        self.assert_json(result, lambda d: d.get("status_code") == 200, "API adapter status_code should be 200")
        payload = result.data.get("json", {})
        body = payload.get("body", payload) if isinstance(payload, dict) else {}
        if body.get("value_numeric") != 30:
            raise RuntimeError("API adapter body expected value_numeric=30")
        return result

    def smoke_compliance(self) -> GateResult:
        result = self.req_cli("compliance", "--project-id", "CUST-A-P1")
        self.assert_json(result, lambda d: d.get("project_id") == "CUST-A-P1" and d.get("summary", {}).get("fail", 0) == 0, "P1 compliance should not have failures in seeded sample")
        return result

    def smoke_impact(self) -> GateResult:
        result = self.req_cli("impact", "--variant-id", "REQVAR-CUST-A-RIPPLE", "--new-value", "20", "--unit", "mV")
        self.assert_json(result, lambda d: d.get("summary", {}).get("affected_project_count", 0) >= 1, "impact should affect at least one project")
        return result

    def smoke_approval(self) -> GateResult:
        result = self.req_cli("review", "--project-id", "CUST-A-P2")
        self.assert_json(result, lambda d: d.get("summary", {}).get("approval_required_count", 0) >= 1, "P2 should have approval review items")
        return result

    def smoke_extraction(self) -> GateResult:
        result = self.req_cli("extract-candidates", "--text", "客户A要求DCDC输出纹波应不大于30mV。", "--profile-id", "PROFILE-CUST-A-DCDC-COMMON")
        self.assert_json(result, lambda d: d.get("candidate_count", 0) >= 1, "candidate extraction expected at least one candidate")
        return result

    def smoke_package_import(self) -> GateResult:
        result = self.req_cli(
            "import-package",
            "--customer-id", "CUST-A",
            "--customer-name", "客户A",
            "--project-id", "CUST-A-P3",
            "--project-code", "A-DCDC-P3",
            "--product-family", "DCDC",
            "--text", "项目要求DCDC输出纹波应不大于25mV。休眠电流应不超过1mA。",
            "--auto-promote",
            "--promoted-by", "validator",
            "--refresh-effective",
        )
        self.assert_json(result, lambda d: d.get("candidate_count", 0) >= 1 and d.get("promoted_count", 0) >= 1, "package import expected candidates/promotions")
        return result


    def smoke_baseline(self) -> GateResult:
        # Run baseline validation in-process to keep the orchestrator report compact.
        from enterprise_agent_kb.requirements.baseline import RequirementBaselineService
        from enterprise_agent_kb.requirements.repository import RequirementRepository

        service = RequirementBaselineService(RequirementRepository(self.workspace_root))
        freeze = service.freeze_project_baseline("CUST-A-P1", frozen_by="validator")
        if freeze.get("status") != "frozen" or freeze.get("requirement_count", 0) < 3:
            raise RuntimeError("baseline freeze expected frozen status and requirements")
        baseline_id = freeze.get("baseline_id")
        listed = service.list_baselines(project_id="CUST-A-P1")
        if listed.get("baseline_count", 0) < 1:
            raise RuntimeError("baseline list expected at least one baseline")
        drift = service.detect_drift(str(baseline_id))
        if drift.get("summary", {}).get("drifted", 999) != 0:
            raise RuntimeError("fresh baseline should not drift")
        return GateResult(name="smoke.baseline", status="passed", duration_s=0.0, data={"json": {"baseline_id": baseline_id, "status": freeze.get("status"), "requirement_count": freeze.get("requirement_count")}, "list": listed, "drift": drift})



    def smoke_release_gate(self) -> GateResult:
        # Evaluate directly to avoid subprocess-level SQLite lock or pipe edge cases in CI.
        from enterprise_agent_kb.requirements.release_gate import RequirementReleaseGateService
        from enterprise_agent_kb.requirements.repository import RequirementRepository

        service = RequirementReleaseGateService(RequirementRepository(self.workspace_root))
        payload = service.evaluate_project("CUST-A-P1", stage="DV", evaluated_by="validator", persist=True)
        if payload.get("readiness_status") not in {"pass", "conditional_pass"} or not payload.get("baseline_id"):
            raise RuntimeError("P1 DV release gate should not be blocked in seeded sample")
        listed = service.list_runs(project_id="CUST-A-P1", stage="DV")
        if listed.get("run_count", 0) < 1:
            raise RuntimeError("release gate run should be persisted")
        return GateResult(name="smoke.release_gate", status="passed", duration_s=0.0, data={"json": payload, "list": listed})


    def smoke_eco(self) -> GateResult:
        from enterprise_agent_kb.requirements.eco import RequirementEcoService
        from enterprise_agent_kb.requirements.repository import RequirementRepository

        service = RequirementEcoService(RequirementRepository(self.workspace_root))
        payload = service.run_full_cycle(
            project_id="CUST-A-P1",
            title="Tighten customer ripple to 20mV",
            variant_id="REQVAR-CUST-A-RIPPLE",
            proposed_change={"value_numeric": 20, "unit": "mV", "operator": "<="},
            actor="validator",
            stage="DV",
        )
        closed = payload.get("closed", {})
        if closed.get("status") not in {"closed", "gate_blocked"}:
            raise RuntimeError("ECO full cycle should finish with closed or gate_blocked status")
        if not closed.get("baseline_after_id") or not closed.get("release_gate_after_id"):
            raise RuntimeError("ECO closure should create a post-change baseline and release gate run")
        return GateResult(name="smoke.eco", status="passed", duration_s=0.0, data={"json": {"eco_id": payload.get("eco_id"), "status": closed.get("status"), "baseline_after_id": closed.get("baseline_after_id"), "release_gate_after_id": closed.get("release_gate_after_id")}})

    def assert_json(self, result: GateResult, predicate, message: str) -> None:
        if result.status != "passed":
            raise RuntimeError(message + "\n" + result.stderr)
        data = result.data.get("json")
        if not isinstance(data, dict) or not predicate(data):
            raise RuntimeError(message + f"\nPayload: {json.dumps(data, ensure_ascii=False)[:2000]}")

    def write_reports(self) -> None:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": "passed" if all(r.status == "passed" for r in self.results) else "failed",
            "repo_root": str(self.repo_root),
            "workspace_root": str(self.workspace_root),
            "mode": self.mode,
            "results": [asdict(r) for r in self.results],
        }
        json_path = self.reports_dir / "requirement_program_report.json"
        md_path = self.reports_dir / "requirement_program_report.md"
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        lines = ["# Requirement Program Report", "", f"Status: **{payload['status']}**", "", "| Gate | Status | Duration |", "|---|---:|---:|"]
        for r in self.results:
            lines.append(f"| {r.name} | {r.status} | {r.duration_s:.2f}s |")
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Report JSON: {json_path}")
        print(f"Report MD: {md_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full KB1 requirement program with automatic validation gates.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--root", type=Path, default=Path(".requirement_program_runtime/knowledge_base"), help="Temporary KB workspace root used for smoke validation.")
    parser.add_argument("--mode", choices=["smoke", "full"], default="full")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--apply-integrations", action="store_true", help="Apply CLI and answer_api integration scripts before validation.")
    parser.add_argument("--api-integration", action="store_true", help="Also attempt optional API server integration script.")
    args = parser.parse_args()

    runner = RequirementProgramRunner(
        repo_root=args.repo_root,
        workspace_root=args.root,
        mode=args.mode,
        continue_on_error=args.continue_on_error,
        apply_integrations=args.apply_integrations,
        api_integration=args.api_integration,
    )
    raise SystemExit(runner.run())


if __name__ == "__main__":
    main()
