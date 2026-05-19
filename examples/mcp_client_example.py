from __future__ import annotations

import json
import subprocess


def send(proc: subprocess.Popen, message: dict) -> dict:
    assert proc.stdin is not None
    assert proc.stdout is not None
    proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


if __name__ == "__main__":
    proc = subprocess.Popen(
        ["python", "-m", "enterprise_agent_kb.cli", "--root", "knowledge_base", "serve-mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        print(
            json.dumps(
                send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                ensure_ascii=False,
                indent=2,
            )
        )
        print(
            json.dumps(
                send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
                ensure_ascii=False,
                indent=2,
            )
        )
        print(
            json.dumps(
                send(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "agent_query",
                            "arguments": {"query": "什么是V2G？", "limit": 4},
                        },
                    },
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        proc.terminate()
        proc.wait(timeout=5)

