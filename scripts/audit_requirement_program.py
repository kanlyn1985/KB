#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class AuditCheck:
    name: str
    status: str
    severity: str
    message: str
    data: dict[str, Any]


REQUIRED_MODULES = [
    "schema.py",
    "models.py",
    "repository.py",
    "comparator.py",
    "resolver.py",
    "diff.py",
    "query.py",
    "answer.py",
    "router.py",
    "api.py",
    "compliance.py",
    "impact.py",
    "approval.py",
    "extraction.py",
    "package_import.py",
    "baseline.py",
    "release_gate.py",
    "eco.py",
]

REQUIRED_SCRIPTS = [
    "apply_requirement_cli_integration.py",
    "apply_requirement_answer_api_integration.py",
    "apply_requirement_api_integration.py",
    "run_requirement_program.py",
]

REQUIRED_DOCS = [
    "REQUIREMENT_PROGRAM_PLAN.md",
    "REQUIREMENT_VALIDATION_GATES.md",
    "ORCHESTRATOR_VALIDATION_REPORT.md",
    "BASELINE_VERSIONING_PROGRAM.md",
    "RELEASE_READINESS_GATE_PROGRAM.md",
    "ECO_PROGRAM.md",
    "SYSTEM_INTEGRATION_AUDIT.md",
]

EXPECTED_TABLES = [
    "customers",
    "customer_projects",
    "requirement_atoms",
    "requirement_profiles",
    "requirement_profile_inheritance",
    "requirement_variants",
    "requirement_overrides",
    "effective_requirements",
    "requirement_evidence_bindings",
    "requirement_test_methods",
    "requirement_test_cases",
    "requirement_test_results",
    "requirement_approvals",
    "requirement_approval_events",
    "requirement_candidate_batches",
    "requirement_candidates",
    "requirement_candidate_events",
    "requirement_import_packages",
    "requirement_baselines",
    "requirement_baseline_items",
    "requirement_baseline_events",
    "requirement_release_gate_runs",
    "requirement_release_gate_findings",
    "requirement_eco_orders",
    "requirement_eco_actions",
    "requirement_eco_events",
]

EXPECTED_GATES = [
    "preflight",
    "unit.tests",
    "smoke.workspace.reset",
    "smoke.schema",
    "smoke.seed",
    "smoke.resolver",
    "smoke.diff",
    "smoke.query_answer",
    "smoke.api_adapter",
    "smoke.compliance",
    "smoke.impact",
    "smoke.approval",
    "smoke.extraction",
    "smoke.package_import",
    "smoke.baseline",
    "smoke.release_gate",
    "smoke.eco",
]


class AuditRunner:
    def __init__(self, repo_root: Path, run_tests: bool) -> None:
        self.repo_root = repo_root.resolve()
        self.run_tests = run_tests
        self.checks: list[AuditCheck] = []
        self.reports_dir = self.repo_root / ".requirement_program_runtime" / "reports"

    @property
    def requirements_dir(self) -> Path:
        return self.repo_root / "src" / "enterprise_agent_kb" / "requirements"

    def add(self, name: str, status: str, severity: str, message: str, **data: Any) -> None:
        self.checks.append(AuditCheck(name=name, status=status, severity=severity, message=message, data=data))
        print(f"[{status.upper()}] {name}: {message}")

    def run(self) -> int:
        start = time.time()
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.check_base_repository_files()
        self.check_required_files()
        self.check_no_build_artifacts()
        self.check_python_syntax()
        self.check_schema_tables()
        self.check_migration_file()
        self.check_orchestrator_gates()
        self.check_integration_scripts_are_guarded()
        self.check_module_size_hotspots()
        self.check_tests_present()
        self.check_documentation_consistency()
        if self.run_tests:
            self.run_unit_tests()
        result = self.write_reports(duration_s=time.time() - start)
        return 0 if result["summary"]["failed"] == 0 else 1


    def check_base_repository_files(self) -> None:
        # KB1 CLI is a modular package (cli/ with submodules), not a single cli.py.
        required = [
            "pyproject.toml",
            "src/enterprise_agent_kb/config.py",
            "src/enterprise_agent_kb/db.py",
            "src/enterprise_agent_kb/cli/__init__.py",
            "src/enterprise_agent_kb/cli/_orchestrator.py",
        ]
        missing = [item for item in required if not (self.repo_root / item).exists()]
        if missing:
            self.add(
                "base.repository.files",
                "failed",
                "blocker",
                "base EVT repository files are missing; run this audit after applying the package in the real repository root",
                missing=missing,
            )
        else:
            self.add("base.repository.files", "passed", "blocker", "base EVT repository files exist")

    def check_required_files(self) -> None:
        missing_modules = [m for m in REQUIRED_MODULES if not (self.requirements_dir / m).exists()]
        missing_scripts = [s for s in REQUIRED_SCRIPTS if not (self.repo_root / "scripts" / s).exists()]
        # Requirement docs live under docs/requirement-program/ (not docs/ root).
        docs_subdir = self.repo_root / "docs" / "requirement-program"
        missing_docs = [d for d in REQUIRED_DOCS if not (docs_subdir / d).exists()]
        missing = missing_modules + [f"scripts/{s}" for s in missing_scripts] + [f"docs/requirement-program/{d}" for d in missing_docs]
        if missing:
            self.add("required.files", "failed", "blocker", "required files missing", missing=missing)
        else:
            self.add("required.files", "passed", "blocker", "all required modules/scripts/docs exist", count=len(REQUIRED_MODULES)+len(REQUIRED_SCRIPTS)+len(REQUIRED_DOCS))

    def check_no_build_artifacts(self) -> None:
        # Scope the scan to the requirement package + scripts + tests/requirement
        # so KB1's own __pycache__ elsewhere is not flagged as a package defect.
        forbidden = []
        scan_roots = [
            self.requirements_dir,
            self.repo_root / "scripts",
            self.repo_root / "tests" / "requirement",
        ]
        for root in scan_roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                parts = set(path.parts)
                if "__pycache__" in parts or path.suffix in {".pyc", ".pyo"}:
                    forbidden.append(str(path.relative_to(self.repo_root)))
        if forbidden:
            self.add("no.build.artifacts", "failed", "major", "build artifacts found in package", artifacts=forbidden[:50], count=len(forbidden))
        else:
            self.add("no.build.artifacts", "passed", "major", "no pycache/pyc artifacts found")

    def check_python_syntax(self) -> None:
        py_files = list((self.repo_root / "src").rglob("*.py")) + list((self.repo_root / "scripts").glob("*.py")) + list((self.repo_root / "tests").rglob("*.py"))
        failures: list[dict[str, str]] = []
        for path in py_files:
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                failures.append({"path": str(path.relative_to(self.repo_root)), "error": str(exc)})
        if failures:
            self.add("python.syntax", "failed", "blocker", "syntax errors detected", failures=failures)
        else:
            self.add("python.syntax", "passed", "blocker", "all Python files parse", python_file_count=len(py_files))

    def check_schema_tables(self) -> None:
        # Primary source of truth is now the migration file; schema.py
        # SCHEMA_SQL is kept as a legacy fallback mirror.
        migration_path = self.repo_root / "src" / "enterprise_agent_kb" / "migrations" / "002_requirement_program.sql"
        schema_path = self.requirements_dir / "schema.py"
        sources: list[tuple[str, str]] = []
        if migration_path.exists():
            sources.append((str(migration_path.name), migration_path.read_text(encoding="utf-8")))
        if schema_path.exists():
            sources.append(("schema.py", schema_path.read_text(encoding="utf-8")))
        if not sources:
            self.add("schema.tables", "failed", "blocker", "neither 002_requirement_program.sql nor schema.py found")
            return
        # Union of tables declared across all sources (handles migration + fallback mirror).
        found = sorted(set(t for _, text in sources for t in re.findall(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z0-9_]+)", text)))
        missing = [t for t in EXPECTED_TABLES if t not in found]
        if missing:
            self.add("schema.tables", "failed", "blocker", "expected requirement tables missing", missing=missing, found=found)
        else:
            self.add("schema.tables", "passed", "blocker", "all expected requirement tables declared", table_count=len(found), sources=[name for name, _ in sources])

        any_indexes = any("CREATE INDEX IF NOT EXISTS" in text for _, text in sources)
        if not any_indexes:
            self.add("schema.indexes", "warning", "major", "no indexes found in schema sources; query performance may degrade")
        else:
            index_count = sum(text.count("CREATE INDEX IF NOT EXISTS") for _, text in sources)
            # Count unique indexes (migration + fallback mirror may duplicate).
            index_names = set(re.findall(r"CREATE INDEX IF NOT EXISTS\s+([a-zA-Z0-9_]+)", "\n".join(text for _, text in sources)))
            self.add("schema.indexes", "passed", "major", "requirement indexes declared", index_count=len(index_names), raw_count=index_count)

    def check_migration_file(self) -> None:
        """Verify the Phase 2 migration file exists and is well-formed."""
        migration_path = self.repo_root / "src" / "enterprise_agent_kb" / "migrations" / "002_requirement_program.sql"
        if not migration_path.exists():
            self.add("migration.file", "failed", "major", "002_requirement_program.sql missing (Phase 2 schema migration)")
            return
        text = migration_path.read_text(encoding="utf-8")
        if "CREATE TABLE IF NOT EXISTS" not in text:
            self.add("migration.file", "failed", "major", "migration file has no CREATE TABLE statements")
            return
        tables = re.findall(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z0-9_]+)", text)
        self.add("migration.file", "passed", "major", "Phase 2 migration file present", table_count=len(tables))

    def check_orchestrator_gates(self) -> None:
        runner_path = self.repo_root / "scripts" / "run_requirement_program.py"
        if not runner_path.exists():
            self.add("orchestrator.gates", "failed", "blocker", "run_requirement_program.py missing")
            return
        text = runner_path.read_text(encoding="utf-8")
        missing = [g for g in EXPECTED_GATES if g not in text]
        if missing:
            self.add("orchestrator.gates", "failed", "blocker", "orchestrator missing expected gates", missing=missing)
        else:
            self.add("orchestrator.gates", "passed", "blocker", "all expected smoke gates present", gate_count=len(EXPECTED_GATES))

    def check_integration_scripts_are_guarded(self) -> None:
        scripts = {
            "cli": self.repo_root / "scripts" / "apply_requirement_cli_integration.py",
            "answer_api": self.repo_root / "scripts" / "apply_requirement_answer_api_integration.py",
            "api": self.repo_root / "scripts" / "apply_requirement_api_integration.py",
        }
        problems = []
        for name, path in scripts.items():
            if not path.exists():
                problems.append({"script": name, "problem": "missing"})
                continue
            text = path.read_text(encoding="utf-8")
            if "already" not in text.lower() and "marker" not in text.lower() and "idempotent" not in text.lower():
                problems.append({"script": name, "problem": "no obvious idempotency guard text"})
            if "raise SystemExit" not in text and "return" not in text:
                problems.append({"script": name, "problem": "no obvious refusal/exit path"})
        if problems:
            self.add("integration.safety", "warning", "major", "integration scripts need manual review", problems=problems)
        else:
            self.add("integration.safety", "passed", "major", "integration scripts contain guard/refusal patterns")

    def check_module_size_hotspots(self) -> None:
        hotspots = []
        for path in self.requirements_dir.glob("*.py"):
            lines = path.read_text(encoding="utf-8").splitlines()
            if len(lines) > 700:
                hotspots.append({"path": str(path.relative_to(self.repo_root)), "lines": len(lines)})
        if hotspots:
            self.add("module.size", "warning", "minor", "large modules should be split before long-term maintenance", hotspots=hotspots)
        else:
            self.add("module.size", "passed", "minor", "no requirement module exceeds 700 lines")

    def check_tests_present(self) -> None:
        # Tests live under tests/requirement/ (module-layout convention).
        tests_dir = self.repo_root / "tests" / "requirement"
        tests = sorted(str(p.relative_to(self.repo_root)) for p in tests_dir.glob("test_requirement_*.py")) if tests_dir.exists() else []
        required_keywords = ["resolver", "query", "api", "compliance", "impact", "approval", "extraction", "package", "baseline", "release_gate", "eco"]
        missing_keywords = [kw for kw in required_keywords if not any(kw in t for t in tests)]
        if missing_keywords:
            self.add("tests.coverage.files", "failed", "blocker", "test files missing for expected areas", missing_keywords=missing_keywords, test_count=len(tests))
        else:
            self.add("tests.coverage.files", "passed", "blocker", "test files exist for all expected areas", test_count=len(tests))

    def check_documentation_consistency(self) -> None:
        # Requirement docs live under docs/requirement-program/; also scan docs/ root
        # so KB1's own docs are still considered for term coverage.
        docs_root = self.repo_root / "docs"
        md_paths = []
        if docs_root.exists():
            md_paths.extend(docs_root.glob("*.md"))
            md_paths.extend((docs_root / "requirement-program").glob("*.md"))
        docs_text = "\n".join(p.read_text(encoding="utf-8") for p in md_paths)
        required_terms = ["Requirement Resolver", "Compliance", "Baseline", "Release", "ECO", "Gate"]
        missing = [term for term in required_terms if term.lower() not in docs_text.lower()]
        if missing:
            self.add("docs.consistency", "warning", "minor", "documentation may not cover all major capabilities", missing_terms=missing)
        else:
            self.add("docs.consistency", "passed", "minor", "documentation mentions all major capabilities")

    def run_unit_tests(self) -> None:
        proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests/requirement", "-v"], cwd=self.repo_root, text=True, capture_output=True)
        status = "passed" if proc.returncode == 0 else "failed"
        severity = "blocker" if proc.returncode != 0 else "blocker"
        self.add("unit.tests.execution", status, severity, "unit test execution completed", returncode=proc.returncode, stdout=proc.stdout[-4000:], stderr=proc.stderr[-4000:])

    def write_reports(self, duration_s: float) -> dict[str, Any]:
        failed = sum(1 for c in self.checks if c.status == "failed")
        warnings = sum(1 for c in self.checks if c.status == "warning")
        passed = sum(1 for c in self.checks if c.status == "passed")
        result = {
            "summary": {"passed": passed, "failed": failed, "warnings": warnings, "duration_s": round(duration_s, 3)},
            "checks": [asdict(c) for c in self.checks],
        }
        json_path = self.reports_dir / "requirement_program_audit.json"
        md_path = self.reports_dir / "requirement_program_audit.md"
        json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        lines = [
            "# Requirement Program Audit Report",
            "",
            f"- Passed: {passed}",
            f"- Failed: {failed}",
            f"- Warnings: {warnings}",
            f"- Duration: {duration_s:.2f}s",
            "",
            "| Check | Status | Severity | Message |",
            "|---|---|---|---|",
        ]
        for c in self.checks:
            lines.append(f"| `{c.name}` | {c.status} | {c.severity} | {c.message.replace('|', '/')} |")
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"audit report: {json_path}")
        print(f"audit report: {md_path}")
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the integrated requirement program package before repository merge.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--run-tests", action="store_true", help="Also run unittest discovery.")
    args = parser.parse_args()
    raise SystemExit(AuditRunner(args.repo_root, args.run_tests).run())


if __name__ == "__main__":
    main()
