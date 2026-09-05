from __future__ import annotations

import argparse
import json
import os
from urllib import error, request


def probe_http(
    url: str,
    *,
    api_key: str,
    tenant_id: str | None = None,
    timeout_seconds: float = 5.0,
) -> dict[str, object]:
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    outbound = request.Request(url, headers=headers, method="GET")
    try:
        with request.urlopen(outbound, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
            status_code = int(response.status)
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)}
    ok = status_code == 200 and isinstance(payload, dict) and payload.get("status") == "ok"
    return {"ok": ok, "status_code": status_code, "payload": payload}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-kb-platform", description="Platform deployment utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    probe = subparsers.add_parser("http-probe", help="Probe an authenticated Agent KB health endpoint.")
    probe.add_argument("--url", default="http://127.0.0.1:8080/v1/health")
    probe.add_argument("--api-key")
    probe.add_argument("--api-key-env", default="AGENT_KB_HEALTH_API_KEY")
    probe.add_argument("--tenant-id")
    probe.add_argument("--tenant-id-env", default="AGENT_KB_TENANT_ID")
    probe.add_argument("--timeout", type=float, default=5.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "http-probe":
        api_key = args.api_key or os.environ.get(args.api_key_env, "")
        if not api_key:
            raise SystemExit(f"API key is required via --api-key or {args.api_key_env}")
        tenant_id = args.tenant_id or os.environ.get(args.tenant_id_env) or None
        result = probe_http(
            args.url,
            api_key=api_key,
            tenant_id=tenant_id,
            timeout_seconds=max(0.1, args.timeout),
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        if not result["ok"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
