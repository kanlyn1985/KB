from __future__ import annotations

import json
import os
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def main() -> None:
    env = load_env()
    anthropic_base = env["OPENAI_BASE_URL"].rstrip("/")
    api_key = env["OPENAI_API_KEY"]
    model = env["LLM_MODEL"]

    results: dict[str, object] = {
        "anthropic_base": anthropic_base,
        "model": model,
        "checks": [],
        "conclusion": {},
    }

    text_payload = {
        "model": model,
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
    }
    text_headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    text_resp = httpx.post(f"{anthropic_base}/v1/messages", json=text_payload, headers=text_headers, timeout=60)
    results["checks"].append(
        {
            "name": "anthropic_text",
            "status_code": text_resp.status_code,
            "ok": text_resp.status_code == 200,
            "body_preview": text_resp.text[:500],
        }
    )

    results["conclusion"] = {
        "anthropic_text_available": text_resp.status_code == 200,
        "anthropic_multimodal_supported_by_current_interface": False,
        "openai_multimodal_supported_by_current_interface": False,
        "summary": (
            "根据 MiniMax 官方文档，Anthropic API 兼容接口不支持图像和文档输入；"
            "OpenAI API 兼容接口不支持图像输入。当前项目中的 MiniMax 配置仅适用于文本模型调用，"
            "不适合直接做 PDF/图片 OCR。"
        ),
    }

    report_json = ROOT / "docs" / "minimax_multimodal_support_check_2026-04-19.json"
    report_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report_json)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
