from __future__ import annotations

import os
import signal
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid4

from agent_kb.domains.schema import DomainPack
from agent_kb.security import TenantDatabaseRouter
from agent_kb.service.api import AgentKBService
from agent_kb.storage import SQLiteKnowledgeStore

from .distributed import SQLiteWorkerRegistry
from .jobs import SQLiteJobQueue


@dataclass(frozen=True)
class WorkerDaemonConfig:
    tenant_db_root: Path
    worker_id: str = ""
    tenant_id: str | None = None
    poll_interval_seconds: float = 1.0
    heartbeat_interval_seconds: float = 15.0
    lease_seconds: int = 60
    ready_file: Path | None = None
    max_jobs: int | None = None

    def normalized_worker_id(self) -> str:
        return self.worker_id.strip() or f"worker-{os.getpid()}-{uuid4().hex[:8]}"


@dataclass(frozen=True)
class WorkerDaemonReport:
    worker_id: str
    iterations: int
    jobs_processed: int
    jobs_succeeded: int
    jobs_failed: int
    tenant_count: int
    stopped: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MultiTenantWorkerDaemon:
    """Continuously processes tenant-local jobs with graceful shutdown.

    The current storage model uses one SQLite database per tenant. The daemon
    scans the configured tenant directory, registers a heartbeat in each
    active tenant database, and finishes the current job before stopping after
    SIGTERM or SIGINT.
    """

    def __init__(
        self,
        config: WorkerDaemonConfig,
        *,
        domain_pack: DomainPack | None = None,
        stop_event: Event | None = None,
    ) -> None:
        if config.poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds cannot be negative")
        if config.heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds must be positive")
        if config.lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        self.config = config
        self.domain_pack = domain_pack
        self.stop_event = stop_event or Event()
        self.worker_id = config.normalized_worker_id()
        self.router = TenantDatabaseRouter(config.tenant_db_root)
        self._last_heartbeat: dict[str, float] = {}
        self._known_tenants: set[str] = set()

    def request_stop(self) -> None:
        self.stop_event.set()

    def install_signal_handlers(self) -> None:
        def _request_stop(signum, frame) -> None:  # noqa: ARG001
            self.request_stop()

        signal.signal(signal.SIGTERM, _request_stop)
        signal.signal(signal.SIGINT, _request_stop)

    def run(self, *, max_iterations: int | None = None, install_signals: bool = True) -> WorkerDaemonReport:
        if max_iterations is not None and max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        if install_signals:
            self.install_signal_handlers()
        self._set_ready(True)
        iterations = 0
        jobs_processed = 0
        jobs_succeeded = 0
        jobs_failed = 0
        try:
            while not self.stop_event.is_set():
                iterations += 1
                processed_this_iteration = False
                tenants = self._tenant_ids()
                self._known_tenants.update(tenants)
                for tenant_id in tenants:
                    if self.stop_event.is_set():
                        break
                    job = self._run_tenant_once(tenant_id)
                    if job is None:
                        continue
                    processed_this_iteration = True
                    jobs_processed += 1
                    if job.status == "succeeded":
                        jobs_succeeded += 1
                    elif job.status == "failed":
                        jobs_failed += 1
                    if self.config.max_jobs is not None and jobs_processed >= self.config.max_jobs:
                        self.request_stop()
                        break
                if max_iterations is not None and iterations >= max_iterations:
                    break
                if not processed_this_iteration and not self.stop_event.is_set():
                    self.stop_event.wait(self.config.poll_interval_seconds)
        finally:
            self._mark_stopped()
            self._set_ready(False)
        return WorkerDaemonReport(
            worker_id=self.worker_id,
            iterations=iterations,
            jobs_processed=jobs_processed,
            jobs_succeeded=jobs_succeeded,
            jobs_failed=jobs_failed,
            tenant_count=len(self._known_tenants),
            stopped=self.stop_event.is_set(),
        )

    def _tenant_ids(self) -> list[str]:
        if self.config.tenant_id:
            return [self.config.tenant_id]
        return self.router.list_tenants()

    def _run_tenant_once(self, tenant_id: str):
        db_path = self.router.path_for(tenant_id)
        if not db_path.exists() and not self.config.tenant_id:
            return None
        service = AgentKBService(
            db_path=db_path,
            domain_pack=self.domain_pack,
            tenant_id=tenant_id,
        )
        with SQLiteKnowledgeStore(db_path) as store:
            registry = SQLiteWorkerRegistry(store.connection)
            self._heartbeat_if_due(registry, tenant_id, status="ready")
            queue = SQLiteJobQueue(store.connection)
            job = queue.run_once(
                self.worker_id,
                {"index_text": service.index},
                tenant_id=tenant_id,
            )
            if job is not None:
                registry.heartbeat(
                    self.worker_id,
                    tenant_id=tenant_id,
                    capabilities=["index_text"],
                    status="ready",
                    lease_seconds=self.config.lease_seconds,
                    metadata={"last_job_id": job.job_id, "last_job_status": job.status},
                )
                self._last_heartbeat[tenant_id] = time.monotonic()
            return job

    def _heartbeat_if_due(self, registry: SQLiteWorkerRegistry, tenant_id: str, *, status: str) -> None:
        now = time.monotonic()
        previous = self._last_heartbeat.get(tenant_id)
        if previous is not None and now - previous < self.config.heartbeat_interval_seconds:
            return
        registry.heartbeat(
            self.worker_id,
            tenant_id=tenant_id,
            capabilities=["index_text"],
            status=status,
            lease_seconds=self.config.lease_seconds,
            metadata={"pid": os.getpid()},
        )
        self._last_heartbeat[tenant_id] = now

    def _mark_stopped(self) -> None:
        for tenant_id in sorted(self._known_tenants):
            db_path = self.router.path_for(tenant_id)
            if not db_path.exists():
                continue
            with SQLiteKnowledgeStore(db_path) as store:
                SQLiteWorkerRegistry(store.connection).heartbeat(
                    self.worker_id,
                    tenant_id=tenant_id,
                    capabilities=["index_text"],
                    status="stopped",
                    lease_seconds=1,
                    metadata={"pid": os.getpid()},
                )

    def _set_ready(self, ready: bool) -> None:
        path = self.config.ready_file
        if path is None:
            return
        if ready:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.worker_id + "\n", encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
