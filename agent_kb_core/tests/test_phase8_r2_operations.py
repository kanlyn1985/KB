from datetime import UTC, datetime
from pathlib import Path

from agent_kb.domains.loader import load_domain_pack
from agent_kb.operations import evaluate_readiness
from agent_kb.operations.cli import main as operations_main
from agent_kb.pipeline import compile_text_to_production_store
from agent_kb.runtime import SQLiteJobQueue
from agent_kb.storage import SQLiteBackupManager, SQLiteKnowledgeStore, run_recovery_drill


ROOT = Path(__file__).resolve().parents[1]


def test_release_readiness_and_isolated_recovery_drill(tmp_path: Path) -> None:
    db = tmp_path / "release.sqlite3"
    pack = load_domain_pack(ROOT / "domains" / "obc_dcdc")
    compile_text_to_production_store(
        "DCDC 输出纹波在额定负载下应不大于 30mVpp。",
        title="Release readiness",
        db_path=db,
        domain_pack=pack,
        logical_document_id="ldoc_release",
        version_label="v1",
    )
    backup = SQLiteBackupManager(db, tenant_id="tenant-a").create_backup(tmp_path / "backups")

    readiness = evaluate_readiness(
        db,
        min_schema_version=8,
        require_documents=True,
        require_backup=True,
        now=datetime(2026, 7, 18, 8, 0, tzinfo=UTC),
    )
    assert readiness.ready
    assert readiness.schema_version == 8
    assert readiness.counts["documents"] == 1
    assert all(check.passed for check in readiness.checks if check.severity == "error")

    drill = run_recovery_drill(backup.path)
    assert drill.status == "passed"
    assert drill.integrity_ok
    assert drill.schema_version == 8
    assert drill.cleanup_performed
    assert not Path(drill.restored_path).exists()

    readiness_output = tmp_path / "readiness.json"
    assert operations_main(
        [
            "readiness",
            "--db",
            str(db),
            "--require-documents",
            "--require-backup",
            "--output",
            str(readiness_output),
        ]
    ) == 0
    assert readiness_output.exists()

    recovery_output = tmp_path / "recovery.json"
    assert operations_main(
        [
            "recovery-drill",
            "--backup-path",
            backup.path,
            "--output",
            str(recovery_output),
        ]
    ) == 0
    assert recovery_output.exists()


def test_readiness_blocks_stale_jobs_missing_backup_and_missing_database(tmp_path: Path) -> None:
    missing = evaluate_readiness(tmp_path / "missing.sqlite3")
    assert not missing.ready
    assert missing.schema_version == 0
    assert missing.checks[0].check_id == "database_exists"

    db = tmp_path / "unready.sqlite3"
    with SQLiteKnowledgeStore(db) as store:
        queue = SQLiteJobQueue(store.connection)
        job = queue.submit("echo", {"value": 1}, tenant_id="tenant-a")
        claimed = queue.claim("worker-a")
        assert claimed is not None
        assert claimed.job_id == job.job_id
        store.connection.execute(
            "UPDATE background_jobs SET locked_at = '2000-01-01T00:00:00Z' WHERE job_id = ?",
            (job.job_id,),
        )
        store.connection.commit()

    report = evaluate_readiness(
        db,
        min_schema_version=8,
        require_backup=True,
        max_stale_running_jobs=0,
        stale_job_age_seconds=60,
        now=datetime(2026, 7, 18, 8, 0, tzinfo=UTC),
    )
    assert not report.ready
    by_id = {check.check_id: check for check in report.checks}
    assert not by_id["stale_running_jobs"].passed
    assert not by_id["verified_backup"].passed
    assert by_id["schema_version"].passed
