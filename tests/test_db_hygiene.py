from __future__ import annotations

import json
import sys
from pathlib import Path

from enterprise_agent_kb.bootstrap import initialize_workspace
from enterprise_agent_kb.cli import build_parser, main
from enterprise_agent_kb.db_hygiene import quarantine_suspicious_db_files
from enterprise_agent_kb.workspace_doctor import run_workspace_doctor


SCHEMA_PATH = Path("src/enterprise_agent_kb/schema.sql")


def test_quarantine_suspicious_db_files_dry_run_is_readonly(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    extra_db = paths.root / "knowledge.db"
    extra_db.write_bytes(b"")

    report = quarantine_suspicious_db_files(paths.root, dry_run=True)

    assert report.dry_run is True
    assert report.summary["planned"] == 1
    assert report.items[0].path == "knowledge.db"
    assert report.items[0].reason == "empty_db_file"
    assert extra_db.exists()


def test_quarantine_suspicious_db_files_execute_moves_extra_db(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    extra_db = paths.root / "knowledge.db"
    extra_db.write_bytes(b"")

    report = quarantine_suspicious_db_files(paths.root, dry_run=False)

    assert report.summary["quarantined"] == 1
    assert not extra_db.exists()
    assert report.items[0].size_bytes == 0
    quarantined = paths.root / str(report.items[0].quarantine_path)
    assert quarantined.exists()
    assert paths.db_file.exists()


def test_workspace_doctor_recommends_public_db_quarantine_command(tmp_path: Path) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    (paths.root / "knowledge.db").write_bytes(b"")

    report = run_workspace_doctor(paths.root, scope="all")
    issue = next(item for item in report.issues if item.issue_id == "empty_db_file")

    assert issue.recommended_actions == ("quarantine-suspicious-db-files --dry-run",)


def test_quarantine_suspicious_db_files_cli_parser_and_json_output(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    paths = initialize_workspace(tmp_path / "kb", SCHEMA_PATH)
    (paths.root / "knowledge.db").write_bytes(b"")
    parser = build_parser()

    parsed = parser.parse_args(["--root", str(paths.root), "quarantine-suspicious-db-files"])
    assert parsed.command == "quarantine-suspicious-db-files"
    assert parsed.dry_run is True

    execute_parsed = parser.parse_args(
        ["--root", str(paths.root), "quarantine-suspicious-db-files", "--execute"]
    )
    assert execute_parsed.dry_run is False

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eakb",
            "--root",
            str(paths.root),
            "quarantine-suspicious-db-files",
            "--dry-run",
        ],
    )
    main()

    output = json.loads(capsys.readouterr().out)
    assert output["dry_run"] is True
    assert output["summary"]["planned"] == 1
