#!/usr/bin/env python3
"""KB1 知识库 Web UI 服务。

在同一端口同时提供：
- 前端页面（webui/ 目录静态托管）
- /v1/* JSON API（query / answer / documents / feedback / health）

用法：
  python webui/server.py --db node-index.sqlite3 --domain-dir domains/obc_dcdc \
      --host 127.0.0.1 --port 8080
浏览器打开 http://127.0.0.1:8080
"""

from __future__ import annotations

import argparse
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_kb.commands.answer_query import answer_query  # noqa: E402
from agent_kb.domains.loader import load_domain_pack  # noqa: E402
from agent_kb.service.api import AgentKBService  # noqa: E402

WEBUI_DIR = Path(__file__).resolve().parent


def create_webui_server(
    *,
    db_path: Path,
    domain_dir: Path | None,
    host: str,
    port: int,
) -> ThreadingHTTPServer:
    domain_pack = load_domain_pack(domain_dir) if domain_dir else None
    service = AgentKBService(db_path=db_path, domain_pack=domain_pack)

    class Handler(BaseHTTPRequestHandler):
        server_version = "AgentKBWebUI/0.1"

        # ---- 静态资源 ----
        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/v1/"):
                self._handle_api_get()
                return
            self._serve_static(self.path)

        # ---- JSON API ----
        def do_POST(self) -> None:  # noqa: N802
            try:
                payload = self._read_json()
                if self.path == "/v1/query":
                    result = service.query(payload)
                    self._write_json(HTTPStatus.OK, result)
                    return
                if self.path == "/v1/answer":
                    query_text = str(payload.get("query") or "")
                    if not query_text.strip():
                        raise ValueError("query is required")
                    result = answer_query(
                        query_text,
                        db_path=db_path,
                        domain_dir=domain_dir,
                        use_llm_understanding=bool(payload.get("llm_understanding", False)),
                        max_answer_chars=int(payload.get("max_answer_chars") or 2000),
                    )
                    self._write_json(HTTPStatus.OK, result)
                    return
                if self.path == "/v1/feedback":
                    self._write_json(HTTPStatus.CREATED, service.feedback(payload))
                    return
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            except (ValueError, KeyError, TypeError) as exc:
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": type(exc).__name__, "detail": str(exc)})
            except Exception as exc:  # noqa: BLE001 - final service boundary
                self._write_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": type(exc).__name__, "detail": str(exc)},
                )

        # ---- helpers ----
        def _handle_api_get(self) -> None:
            if self.path in ("/v1/health", "/v1/health/"):
                self._write_json(HTTPStatus.OK, service.health().to_dict())
                return
            if self.path.startswith("/v1/documents"):
                include_deleted = "include_deleted=true" in self.path.lower()
                self._write_json(HTTPStatus.OK, {"documents": service.documents(include_deleted=include_deleted)})
                return
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def _serve_static(self, path: str) -> None:
            # 防目录穿越：只允许 webui 目录内的文件
            rel = path.lstrip("/")
            if not rel or rel.endswith("/"):
                rel = "index.html"
            target = (WEBUI_DIR / rel).resolve()
            try:
                target.relative_to(WEBUI_DIR.resolve())
            except ValueError:
                self._write_json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                return
            if not target.is_file():
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            body = target.read_bytes()
            ctype = {
                ".html": "text/html; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".json": "application/json; charset=utf-8",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".ico": "image/x-icon",
            }.get(target.suffix.lower(), "application/octet-stream")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _write_json(self, status: HTTPStatus, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            print(f"[webui] {self.address_string()} {format % args}")

    return ThreadingHTTPServer((host, port), Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--domain-dir", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    server = create_webui_server(
        db_path=args.db,
        domain_dir=args.domain_dir,
        host=args.host,
        port=args.port,
    )
    print(f"KB1 Web UI: http://{args.host}:{args.port}  (db={args.db})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
