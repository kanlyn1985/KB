#!/usr/bin/env python3
"""Enqueue (and optionally process) curated Athena markdown into kb-ontology.

Does not import KB1 code. Reads clean markdown under Athena ``raw/``.

Usage (from kb-ontology root)::

    PYTHONPATH=src python3 scripts/ingest_athena_sample.py \\
        --db /tmp/kb_ontology_athena.db \\
        --domain-dir domains/obc_dcdc \\
        --max-files 12 \\
        --enqueue-only

    # process queue (requires AGENT_KB_LLM_* / .env):
    PYTHONPATH=src python3 scripts/ingest_athena_sample.py \\
        --db /tmp/kb_ontology_athena.db \\
        --domain-dir domains/obc_dcdc \\
        --worker-only --max-jobs 12
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_ATHENA_RAW = Path(
    "/home/evt/projects/KB1/knowledge_base/raw/Athena-main/raw"
)

# Curated, domain-relevant paths (relative to athena raw). Prefer short
# product/intro docs; skip datasheets and empty stubs via max_bytes / min_bytes.
CURATED_RELATIVE_PATHS: tuple[str, ...] = (
    "30_产品平台知识/06_其他知识点/1_车载充电机的简介.md",
    "30_产品平台知识/06_其他知识点/2_车载DCDC的简介.md",
    "30_产品平台知识/06_其他知识点/3_慢充系统的工作原理.md",
    "30_产品平台知识/06_其他知识点/4_快充系统工作原理.md",
    "30_产品平台知识/06_其他知识点/5_AD采样原理与模型设计.md",
    "30_产品平台知识/OBC产品线/OBC电路拓扑工作原理.md",
    "30_产品平台知识/OBC产品线/充放电流程介绍_20251210.md",
    "30_产品平台知识/OBC产品线/G5_6.6kW_关键硬件参数.md",
    "30_产品平台知识/OBC产品线/G5_DC启动预充策略.md",
    "30_产品平台知识/软件组件库/DCDCState详细设计规范.md",
    # wave-2 / wave-3 strategy + software components
    "30_产品平台知识/OBC产品线/G5_11kW_DCDC抖频策略.md",
    "30_产品平台知识/OBC产品线/G5_DCDC抖频策略.md",
    "30_产品平台知识/OBC产品线/G5_CBC策略.md",
    "30_产品平台知识/OBC产品线/G5_DCDC峰值功率策略.md",
    "30_产品平台知识/OBC产品线/G5_NTC查表策略.md",
    "30_产品平台知识/OBC产品线/G5_V2L_Inside策略.md",
    "30_产品平台知识/OBC产品线/G5_低温启机策略.md",
    "30_产品平台知识/OBC产品线/G5_光耦黏连检测策略.md",
    "30_产品平台知识/OBC产品线/GPIO_PWM回读策略.md",
    "30_产品平台知识/软件组件库/OBC状态机需求解析.md",
    "30_产品平台知识/软件组件库/ASW4.0_OBCState架构设计知识.md",
    "30_产品平台知识/软件组件库/DCDCPowerCtrl详细设计规范.md",
    "30_产品平台知识/软件组件库/DCDCFaultDetect详细设计规范.md",
    "30_产品平台知识/软件组件库/OBCPowerCtrl详细设计规范.md",
)

# Known empty / corrupt / index-only pages — never enqueue even if size gate passes.
SKIP_RELATIVE_PATHS: frozenset[str] = frozenset(
    {
        "30_产品平台知识/06_其他知识点/6_枪连接CC、CP、S2原理介绍.md",  # corrupt export
        "30_产品平台知识/06_其他知识点/OBC相关知识.md",  # stub title only
        "30_产品平台知识/06_其他知识点/DCDC相关知识.md",  # stub title only
        "30_产品平台知识/OBC产品线/OBC产品线.md",  # empty index
        "30_产品平台知识/DCDC产品线/DCDC产品线.md",  # empty index
        "30_产品平台知识/06_其他知识点/8_模型单元测试相关事项.md",  # dingding TOC noise
        "30_产品平台知识/06_其他知识点/9_AM263P代码集成.md",  # dingding TOC noise
    }
)

PREFERRED_GLOBS = (
    "**/30_产品平台知识/06_其他知识点/*.md",
    "**/30_产品平台知识/OBC产品线/*.md",
    "**/30_产品平台知识/DCDC产品线/*.md",
    "**/*DCDC*.md",
    "**/*OBC*.md",
)


def _ref_for(path: Path, root: Path):
    from kb_ontology.ingestion.batch import DocumentRef

    try:
        rel = str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        rel = path.name
    return DocumentRef(
        path=path.resolve(),
        document_id=rel.replace("/", "__").replace(" ", "_"),
        relative_path=rel,
    )


def select_documents(
    root: Path,
    *,
    max_files: int,
    min_bytes: int,
    max_bytes: int,
    use_curated: bool,
) -> list:
    from kb_ontology.ingestion.batch import DocumentRef, discover_documents

    selected: list[DocumentRef] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        if len(selected) >= max_files:
            return
        if not path.is_file():
            return
        if "node_modules" in path.parts:
            return
        try:
            rel = str(path.resolve().relative_to(root.resolve()))
        except ValueError:
            rel = path.name
        if rel in SKIP_RELATIVE_PATHS:
            return
        try:
            size = path.stat().st_size
        except OSError:
            return
        if size < min_bytes or size > max_bytes:
            return
        # Heuristic: skip wiki exports that are mostly HTML/noise with no CJK body.
        try:
            sample = path.read_text(encoding="utf-8", errors="ignore")[:2000]
        except OSError:
            return
        cjk = sum(1 for ch in sample if "\u4e00" <= ch <= "\u9fff")
        if cjk < 20 and size < 2000:
            return
        key = str(path.resolve())
        if key in seen:
            return
        seen.add(key)
        selected.append(_ref_for(path, root))

    if use_curated:
        for rel in CURATED_RELATIVE_PATHS:
            _add(root / rel)
            if len(selected) >= max_files:
                return selected

    for pattern in PREFERRED_GLOBS:
        if len(selected) >= max_files:
            break
        for path in sorted(root.glob(pattern)):
            _add(path)
            if len(selected) >= max_files:
                break

    if not selected:
        for ref in discover_documents(root, max_files=max_files * 3):
            try:
                size = ref.path.stat().st_size
            except OSError:
                continue
            if size < min_bytes or size > max_bytes:
                continue
            if str(ref.path.resolve()) in seen:
                continue
            seen.add(str(ref.path.resolve()))
            selected.append(ref)
            if len(selected) >= max_files:
                break
    return selected[:max_files]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--domain-dir", required=True)
    parser.add_argument(
        "--athena-raw",
        default=str(DEFAULT_ATHENA_RAW),
        help="Athena raw markdown root",
    )
    parser.add_argument("--max-files", type=int, default=8)
    parser.add_argument("--max-jobs", type=int, default=None, help="Worker drain cap")
    parser.add_argument(
        "--min-bytes",
        type=int,
        default=400,
        help="Skip stub/index pages with almost no body text",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=50_000,
        help="Skip huge markdown (e.g. datasheets)",
    )
    parser.add_argument(
        "--enqueue-only",
        action="store_true",
        help="Only enqueue jobs; do not call the LLM worker",
    )
    parser.add_argument(
        "--worker-only",
        action="store_true",
        help="Only drain existing queue (no new enqueue)",
    )
    parser.add_argument("--no-curated", action="store_true", help="Skip curated list")
    parser.add_argument("--worker-id", default="athena-sample-worker")
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument(
        "--jobs-db",
        default=None,
        help="Override job queue path (default: <db>.jobs)",
    )
    parser.add_argument(
        "--text-limit",
        type=int,
        default=8000,
        help="Cap characters sent to LLM per doc (0 = full file)",
    )
    parser.add_argument(
        "--requeue-empty",
        action="store_true",
        help="Requeue succeeded jobs whose result entity_count is 0 "
        "(skips SKIP_RELATIVE_PATHS / tiny stubs)",
    )
    args = parser.parse_args(argv)

    root = Path(args.athena_raw)
    if not args.worker_only and not root.is_dir():
        print(f"Athena raw path not found: {root}", file=sys.stderr)
        return 1

    from kb_ontology.domains.loader import load_domain_pack
    from kb_ontology.ingestion.batch import (
        enqueue_extract_jobs,
        run_extract_worker_loop,
    )
    from kb_ontology.runtime.jobs import SQLiteJobQueue

    jobs_path = args.jobs_db or (str(args.db) + ".jobs")
    queue = SQLiteJobQueue.open(jobs_path)
    report: dict = {
        "athena_raw": str(root),
        "jobs_db": jobs_path,
        "ontology_db": args.db,
    }

    text_limit = None if int(args.text_limit) <= 0 else int(args.text_limit)

    if args.requeue_empty:
        requeued = []
        for job in queue.list(status="succeeded", limit=500):
            result = job.result or {}
            if int(result.get("entity_count") or 0) > 0:
                continue
            payload = dict(job.payload or {})
            rel = str(payload.get("relative_path") or "")
            path = Path(str(payload.get("path") or ""))
            if rel in SKIP_RELATIVE_PATHS:
                continue
            try:
                size = path.stat().st_size if path.is_file() else 0
            except OSError:
                size = 0
            if size < int(args.min_bytes):
                continue
            # Skip if store already has evidence for this document (prior
            # out-of-band re-extract may have filled the hollow job record).
            # Checked cheaply via evidence table when ontology db exists.
            doc_id = str(payload.get("document_id") or "")
            if doc_id and Path(args.db).is_file():
                import sqlite3 as _sqlite3

                try:
                    with _sqlite3.connect(args.db) as _conn:
                        n = _conn.execute(
                            "SELECT COUNT(*) FROM evidence WHERE document_id = ?",
                            (doc_id,),
                        ).fetchone()[0]
                    if int(n) > 0:
                        continue
                except _sqlite3.Error:
                    pass
            updates = {
                "max_tokens": int(args.max_tokens),
            }
            if text_limit is not None:
                updates["text_limit"] = text_limit
            updated = queue.requeue(
                job.job_id,
                payload_updates=updates,
                reset_attempts=True,
            )
            requeued.append(
                {
                    "job_id": updated.job_id,
                    "document_id": doc_id,
                    "size": size,
                }
            )
        report["requeue_empty"] = {
            "requeued": len(requeued),
            "jobs": requeued,
        }

    if not args.worker_only:
        selected = select_documents(
            root,
            max_files=args.max_files,
            min_bytes=args.min_bytes,
            max_bytes=args.max_bytes,
            use_curated=not args.no_curated,
        )
        batch = enqueue_extract_jobs(
            queue,
            selected,
            max_tokens=args.max_tokens,
            text_limit=text_limit,
        )
        report["selected"] = [d.to_dict() for d in selected]
        report["enqueue"] = batch.to_dict()
    else:
        report.setdefault("selected", [])
        report.setdefault("enqueue", None)

    if args.enqueue_only:
        queued = queue.list(status="queued", limit=200)
        report["queue_queued"] = len(queued)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    pack = load_domain_pack(Path(args.domain_dir))
    from kb_ontology.llm.llm_client import LLMChatClient

    client = LLMChatClient.from_environment()
    max_jobs = args.max_jobs
    if max_jobs is None:
        max_jobs = args.max_files if not args.worker_only else 50
    done = run_extract_worker_loop(
        queue,
        db_path=args.db,
        domain_pack=pack,
        client=client,
        worker_id=args.worker_id,
        max_jobs=max_jobs,
    )
    report["worker"] = {
        "processed": len(done),
        "succeeded": sum(1 for j in done if j.status == "succeeded"),
        "failed": sum(1 for j in done if j.status == "failed"),
        "jobs": [
            {
                "job_id": j.job_id,
                "status": j.status,
                "document_id": (j.payload or {}).get("document_id"),
                "error": j.error,
                "result": j.result,
            }
            for j in done
        ],
    }
    # store summary
    try:
        from kb_ontology.service.app import OntologyService

        svc = OntologyService(db_path=args.db, domain_pack=pack)
        report["store"] = svc.health().to_dict()
    except Exception as exc:  # pragma: no cover
        report["store_error"] = f"{type(exc).__name__}: {exc}"

    print(json.dumps(report, ensure_ascii=False, indent=2))
    failed = report.get("worker", {}).get("failed", 0)
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
