from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from agent_kb import __version__
from agent_kb.domains.loader import load_domain_pack
from agent_kb.runtime import (
    MultiTenantWorkerDaemon,
    SQLiteJobQueue,
    SQLiteLeaderLeaseStore,
    WorkerDaemonConfig,
)
from agent_kb.storage import PLATFORM_MIGRATIONS, SchemaMigrator, SQLiteKnowledgeStore


ROOT = Path(__file__).resolve().parents[1]


def test_platform_leader_lease_uses_optional_schema_v9(tmp_path: Path) -> None:
    db = tmp_path / "leadership.sqlite3"
    now = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)
    with SQLiteKnowledgeStore(db) as store:
        assert SchemaMigrator(store.connection).current_version() == 0
        leases = SQLiteLeaderLeaseStore(store.connection)
        assert SchemaMigrator(store.connection, migrations=PLATFORM_MIGRATIONS).current_version() == 9

        first = leases.acquire("scheduler", "holder-a", lease_seconds=30, now=now)
        assert first is not None
        assert first.holder_id == "holder-a"
        assert leases.acquire("scheduler", "holder-b", lease_seconds=30, now=now) is None

        renewed = leases.renew("scheduler", "holder-a", lease_seconds=60, now=now + timedelta(seconds=5))
        assert renewed is not None
        assert renewed.holder_id == "holder-a"
        assert leases.acquire(
            "scheduler",
            "holder-b",
            lease_seconds=30,
            now=now + timedelta(seconds=70),
        ) is not None
        assert not leases.release("scheduler", "holder-a")
        assert leases.release("scheduler", "holder-b")


def test_continuous_worker_processes_job_and_removes_ready_file(tmp_path: Path) -> None:
    tenant_root = tmp_path / "tenants"
    tenant_root.mkdir()
    tenant_db = tenant_root / "default.sqlite3"
    ready_file = tmp_path / "worker.ready"
    pack = load_domain_pack(ROOT / "domains" / "obc_dcdc")

    with SQLiteKnowledgeStore(tenant_db) as store:
        queued = SQLiteJobQueue(store.connection).submit(
            "index_text",
            {
                "text": "DCDC 输出纹波在额定负载下应不大于 30mVpp。",
                "title": "Worker fixture",
                "logical_document_id": "worker-fixture",
            },
            tenant_id="default",
        )

    daemon = MultiTenantWorkerDaemon(
        WorkerDaemonConfig(
            tenant_db_root=tenant_root,
            worker_id="phase9-test-worker",
            tenant_id="default",
            poll_interval_seconds=0.0,
            heartbeat_interval_seconds=0.1,
            lease_seconds=30,
            ready_file=ready_file,
            max_jobs=1,
        ),
        domain_pack=pack,
    )
    report = daemon.run(max_iterations=3, install_signals=False)

    assert report.jobs_processed == 1
    assert report.jobs_succeeded == 1
    assert report.jobs_failed == 0
    assert report.stopped
    assert not ready_file.exists()
    with SQLiteKnowledgeStore(tenant_db) as store:
        completed = SQLiteJobQueue(store.connection).get(queued.job_id)
        assert completed is not None
        assert completed.status == "succeeded"
        document_count = store.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        assert document_count == 1


def test_container_and_kubernetes_manifests_are_hardened() -> None:
    assert __version__ == "0.5.0"
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.count("FROM ") >= 2
    assert "USER ${APP_UID}:${APP_GID}" in dockerfile
    assert "PYTHONDONTWRITEBYTECODE=1" in dockerfile
    assert "VOLUME [\"/data\"]" in dockerfile

    compose = yaml.safe_load((ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8"))
    assert {"api", "worker"}.issubset(compose["services"])
    assert compose["services"]["api"]["healthcheck"]
    assert compose["services"]["worker"]["command"][0] == "agent-kb-worker"

    base = ROOT / "deploy" / "kubernetes" / "base"
    documents: dict[str, dict] = {}
    for path in base.glob("*.yaml"):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), path
        documents[path.name] = payload

    statefulset = documents["statefulset.yaml"]
    assert statefulset["kind"] == "StatefulSet"
    assert statefulset["spec"]["replicas"] == 1
    pod_spec = statefulset["spec"]["template"]["spec"]
    assert pod_spec["automountServiceAccountToken"] is False
    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    containers = {item["name"]: item for item in pod_spec["containers"]}
    assert set(containers) == {"api", "worker"}
    for container in containers.values():
        assert container["securityContext"]["readOnlyRootFilesystem"] is True
        assert container["securityContext"]["allowPrivilegeEscalation"] is False
        assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
        assert not container["image"].endswith(":latest")
    assert containers["api"]["readinessProbe"]
    assert containers["api"]["livenessProbe"]
    assert containers["worker"]["readinessProbe"]

    kustomization = documents["kustomization.yaml"]
    assert kustomization["kind"] == "Kustomization"
    assert "statefulset.yaml" in kustomization["resources"]
    assert "network-policy.yaml" in kustomization["resources"]
    assert documents["pvc.yaml"]["spec"]["accessModes"] == ["ReadWriteOnce"]
