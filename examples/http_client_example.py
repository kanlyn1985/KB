from __future__ import annotations

import json
from urllib import request


BASE_URL = "http://127.0.0.1:8000"


def post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    result = post_json(
        "/answer-query",
        {"query": "什么是控制导引电路？", "limit": 4},
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

