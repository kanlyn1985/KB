from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_kb.domains.loader import load_domain_pack
from agent_kb.runtime import MultiTenantWorkerDaemon, WorkerDaemonConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-kb-worker",
        description="Run the continuous multi-tenant Agent KB background worker.",
    )
    parser.add_argument("--tenant-db-root", type=Path, required=True)
    parser.add_argument("--domain-dir", type=Path)
    parser.add_argument("--worker-id", default="")
    parser.add_argument("--tenant-id")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--heartbeat-interval", type=float, default=15.0)
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--max-jobs", type=int)
    parser.add_argument("--max-iterations", type=int)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    daemon = MultiTenantWorkerDaemon(
        WorkerDaemonConfig(
            tenant_db_root=args.tenant_db_root,
            worker_id=args.worker_id,
            tenant_id=args.tenant_id,
            poll_interval_seconds=max(0.0, args.poll_interval),
            heartbeat_interval_seconds=max(0.1, args.heartbeat_interval),
            lease_seconds=max(1, args.lease_seconds),
            ready_file=args.ready_file,
            max_jobs=max(1, args.max_jobs) if args.max_jobs is not None else None,
        ),
        domain_pack=load_domain_pack(args.domain_dir) if args.domain_dir else None,
    )
    report = daemon.run(
        max_iterations=max(1, args.max_iterations) if args.max_iterations is not None else None,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
