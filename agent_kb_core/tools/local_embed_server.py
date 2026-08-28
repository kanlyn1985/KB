# -*- coding: utf-8 -*-
"""本机嵌入服务器：OpenAI 兼容 /v1/embeddings，fastembed ONNX CPU 推理。

用法：
  python local_embed_server.py [--port 11500]

客户端（agent_kb RemoteJSONEmbeddingProvider）：
  AGENT_KB_EMBEDDING_URL=http://127.0.0.1:11500/v1/embeddings
  AGENT_KB_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
  AGENT_KB_EMBEDDING_DIMENSIONS=512
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FASTEMBED_CACHE_PATH = r"C:\Users\000043ce\.fastembed_cache"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def build_model():
    os.environ["FASTEMBED_CACHE_PATH"] = FASTEMBED_CACHE_PATH
    os.environ["HF_HUB_OFFLINE"] = "1"
    from fastembed import TextEmbedding
    return TextEmbedding(MODEL_NAME)


class Handler(BaseHTTPRequestHandler):
    model = None          # 类属性，主线程初始化
    dim = 512
    lock = threading.Lock()

    def log_message(self, fmt, *args):  # 静默默认日志
        pass

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/health", "/v1/health"):
            self._json(200, {"status": "ok", "model": MODEL_NAME, "dimensions": self.dim})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ("/v1/embeddings", "/embeddings"):
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(length).decode("utf-8"))
            inputs = req.get("input", [])
            if isinstance(inputs, str):
                inputs = [inputs]
            if not isinstance(inputs, list):
                self._json(400, {"error": "input must be string or list"})
                return
            t0 = time.time()
            with Handler.lock:
                vectors = [v.tolist() for v in self.model.embed(inputs)]
            dt = time.time() - t0
            self._json(200, {
                "object": "list",
                "data": [
                    {"object": "embedding", "index": i, "embedding": vec}
                    for i, vec in enumerate(vectors)
                ],
                "model": req.get("model", MODEL_NAME),
                "usage": {"prompt_tokens": 0, "total_tokens": 0},
                "x_inference_seconds": round(dt, 4),
            })
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=11500)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    print("loading model ...", flush=True)
    t0 = time.time()
    Handler.model = build_model()
    print(f"model ready in {time.time()-t0:.1f}s, listening on http://{args.host}:{args.port}", flush=True)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("serving ...", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()